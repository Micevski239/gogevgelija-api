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

        if clear and not dry_run:
            count = Category.objects.all().count()
            Category.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'🗑️  Deleted {count} existing categories'))

        self.stdout.write(self.style.SUCCESS(f'\n📥 Importing categories from {json_file}...\n'))

        created_count = 0
        updated_count = 0

        for item in data:
            if dry_run:
                self.stdout.write(f'Would import: {item.get("name_en", item.get("name", "Unknown"))}')
                continue

            category_data = {
                'name': item.get('name', ''),
                'name_en': item.get('name_en', ''),
                'name_mk': item.get('name_mk', ''),
                'icon': item.get('icon', 'ellipse-outline'),
                'slug': item.get('slug', ''),
                'order': item.get('order', 0),
                'is_active': item.get('is_active', True),
                'trending': item.get('trending', False),
                'featured': item.get('featured', False),
                'applies_to': item.get('applies_to', 'both'),
            }

            existing = None
            if category_data.get('slug'):
                existing = Category.objects.filter(slug=category_data['slug']).first()
            if not existing and category_data.get('name_en'):
                existing = Category.objects.filter(name_en=category_data['name_en']).first()

            if existing:
                for key, value in category_data.items():
                    setattr(existing, key, value)
                existing.save()
                updated_count += 1
                self.stdout.write(self.style.WARNING(f'  ↻ Updated: {existing.name_en or existing.name}'))
            else:
                category = Category.objects.create(**category_data)
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created: {category.name_en or category.name}'))

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
    "name": "Food & Drink",
    "name_en": "Food & Drink",
    "name_mk": "Храна и Пијалаци",
    "slug": "food-drink",
    "icon": "restaurant",
    "order": 1,
    "is_active": true,
    "trending": false,
    "featured": true,
    "applies_to": "both"
  }
]
"""
