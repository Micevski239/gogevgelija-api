import json
from django.core.management.base import BaseCommand
from core.models import Category


class Command(BaseCommand):
    help = 'Import categories from a JSON file'

    def add_arguments(self, parser):
        parser.add_argument(
            'json_file',
            type=str,
            help='Path to JSON file containing category data'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing categories before importing',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without actually importing',
        )

    def handle(self, *args, **options):
        json_file = options['json_file']
        clear = options['clear']
        dry_run = options['dry_run']

        # Load JSON data
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'❌ File not found: {json_file}'))
            return
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f'❌ Invalid JSON: {e}'))
            return

        if not isinstance(data, list):
            self.stdout.write(self.style.ERROR('❌ JSON must be a list of category objects'))
            return

        # Clear existing categories if requested
        if clear and not dry_run:
            count = Category.objects.all().count()
            Category.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'🗑️  Deleted {count} existing categories'))

        # Import categories
        self.stdout.write(self.style.SUCCESS(f'\n📥 Importing categories from {json_file}...\n'))

        created_count = 0
        updated_count = 0
        parent_map = {}  # Map of temporary IDs to actual Category objects

        for item in data:
            if dry_run:
                self.stdout.write(f'Would import: {item.get("name_en", item.get("name", "Unknown"))}')
                continue

            # Get or create category
            category_data = {
                'name': item.get('name', ''),
                'name_en': item.get('name_en', ''),
                'name_mk': item.get('name_mk', ''),
                'icon': item.get('icon', 'ellipse-outline'),
                'color': item.get('color', ''),
                'slug': item.get('slug', ''),
                'order': item.get('order', 0),
                'is_active': item.get('is_active', True),
                'show_in_search': item.get('show_in_search', True),
                'show_in_navigation': item.get('show_in_navigation', True),
                'trending': item.get('trending', False),
                'featured': item.get('featured', False),
                'applies_to': item.get('applies_to', 'both'),
                'description': item.get('description', ''),
                'description_en': item.get('description_en', ''),
                'description_mk': item.get('description_mk', ''),
            }

            # Handle parent relationship
            parent_ref = item.get('parent')
            if parent_ref:
                # Parent can be referenced by slug, name, or temp_id
                if isinstance(parent_ref, str):
                    parent = Category.objects.filter(slug=parent_ref).first()
                    if not parent:
                        parent = Category.objects.filter(name_en=parent_ref).first()
                    category_data['parent'] = parent
                elif isinstance(parent_ref, int):
                    # Temporary ID from JSON
                    parent = parent_map.get(parent_ref)
                    category_data['parent'] = parent

            # Check if category exists (by slug or name)
            existing = None
            if category_data.get('slug'):
                existing = Category.objects.filter(slug=category_data['slug']).first()
            if not existing and category_data.get('name_en'):
                existing = Category.objects.filter(name_en=category_data['name_en']).first()

            if existing:
                # Update existing category
                for key, value in category_data.items():
                    setattr(existing, key, value)
                existing.save()
                category = existing
                updated_count += 1
                self.stdout.write(self.style.WARNING(f'  ↻ Updated: {category.name_en or category.name}'))
            else:
                # Create new category
                category = Category.objects.create(**category_data)
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created: {category.name_en or category.name}'))

            # Store in parent map if temp_id provided
            temp_id = item.get('temp_id')
            if temp_id:
                parent_map[temp_id] = category

        if dry_run:
            self.stdout.write(self.style.NOTICE(f'\n🔍 Dry run completed. {len(data)} categories would be imported.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Import completed!'))
            self.stdout.write(self.style.SUCCESS(f'   Created: {created_count}'))
            self.stdout.write(self.style.SUCCESS(f'   Updated: {updated_count}'))
            self.stdout.write(self.style.SUCCESS(f'   Total: {created_count + updated_count}\n'))


# Example JSON format:
"""
[
  {
    "temp_id": 1,
    "name": "Food & Drink",
    "name_en": "Food & Drink",
    "name_mk": "Храна и Пијалаци",
    "slug": "food-drink",
    "icon": "restaurant",
    "color": "#FF5722",
    "order": 1,
    "is_active": true,
    "trending": false,
    "featured": true,
    "applies_to": "both",
    "description_en": "Restaurants, cafés, bars, and dining options",
    "description_mk": "Ресторани, кафеани, барови и опции за јадење"
  },
  {
    "temp_id": 2,
    "parent": 1,
    "name": "Restaurants",
    "name_en": "Restaurants",
    "name_mk": "Ресторани",
    "slug": "restaurants",
    "icon": "restaurant-outline",
    "order": 1,
    "applies_to": "listing"
  },
  {
    "temp_id": 3,
    "parent": 2,
    "name": "Traditional Macedonian",
    "name_en": "Traditional Macedonian",
    "name_mk": "Традиционална Македонска",
    "slug": "traditional-macedonian",
    "icon": "restaurant-outline",
    "order": 1
  }
]
"""
