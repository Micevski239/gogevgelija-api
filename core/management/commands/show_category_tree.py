from django.core.management.base import BaseCommand
from core.models import Category


class Command(BaseCommand):
    help = 'Display all categories'

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

        queryset = Category.objects.all()
        if not show_inactive:
            queryset = queryset.filter(is_active=True)

        categories = queryset.order_by('order', 'name_en')

        if not categories.exists():
            self.stdout.write(self.style.WARNING('No categories found.'))
            return

        self.stdout.write(self.style.SUCCESS('\n📂 Categories\n'))
        self.stdout.write('=' * 80)

        for cat in categories:
            status = ''
            if not cat.is_active:
                status = self.style.ERROR(' [INACTIVE]')
            elif cat.featured:
                status = self.style.SUCCESS(' ⭐')
            elif cat.trending:
                status = self.style.WARNING(' 🔥')

            name = cat.name_en or cat.name_mk or cat.name

            count_str = ''
            if show_counts:
                count_str = self.style.NOTICE(f' ({cat.get_item_count()} items)')

            info = []
            if cat.slug:
                info.append(f'slug: {cat.slug}')
            if cat.applies_to != 'both':
                info.append(f'applies_to: {cat.applies_to}')
            info_str = self.style.NOTICE(f' [{", ".join(info)}]') if info else ''

            self.stdout.write(f'{name}{status}{count_str}{info_str}')

        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS(f'\n✅ Total: {categories.count()} categories\n'))
