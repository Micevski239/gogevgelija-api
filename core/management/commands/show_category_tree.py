from django.core.management.base import BaseCommand
from core.models import Category


class Command(BaseCommand):
    help = 'Display the category hierarchy tree'

    def add_arguments(self, parser):
        parser.add_argument(
            '--show-inactive',
            action='store_true',
            help='Include inactive categories',
        )
        parser.add_argument(
            '--show-counts',
            action='store_true',
            help='Show item counts for each category',
        )

    def handle(self, *args, **options):
        show_inactive = options['show_inactive']
        show_counts = options['show_counts']

        # Get root categories
        queryset = Category.objects.filter(parent__isnull=True)
        if not show_inactive:
            queryset = queryset.filter(is_active=True)

        root_categories = queryset.order_by('order', 'name_en')

        if not root_categories:
            self.stdout.write(self.style.WARNING('No categories found.'))
            return

        self.stdout.write(self.style.SUCCESS('\n📂 Category Hierarchy Tree\n'))
        self.stdout.write('=' * 80)

        for root in root_categories:
            self._print_category_tree(root, 0, show_inactive, show_counts)

        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS(f'\n✅ Total root categories: {root_categories.count()}\n'))

    def _print_category_tree(self, category, level, show_inactive, show_counts):
        """Recursively print category and its children"""
        indent = '  ' * level
        prefix = '├─ ' if level > 0 else ''

        # Status indicators
        status = ''
        if not category.is_active:
            status = self.style.ERROR(' [INACTIVE]')
        elif category.featured:
            status = self.style.SUCCESS(' ⭐')
        elif category.trending:
            status = self.style.WARNING(' 🔥')

        # Display name
        name = category.name_en or category.name_mk or category.name

        # Item count
        count_str = ''
        if show_counts:
            count = category.item_count
            count_str = self.style.NOTICE(f' ({count} items)')

        # Additional info
        info = []
        if category.slug:
            info.append(f'slug: {category.slug}')
        if category.color:
            info.append(f'color: {category.color}')
        if category.applies_to != 'both':
            info.append(f'applies_to: {category.applies_to}')

        info_str = ''
        if info:
            info_str = self.style.NOTICE(f' [{", ".join(info)}]')

        # Print the category
        self.stdout.write(f'{indent}{prefix}{name}{status}{count_str}{info_str}')

        # Print children
        children_queryset = Category.objects.filter(parent=category)
        if not show_inactive:
            children_queryset = children_queryset.filter(is_active=True)

        children = children_queryset.order_by('order', 'name_en')
        for child in children:
            self._print_category_tree(child, level + 1, show_inactive, show_counts)
