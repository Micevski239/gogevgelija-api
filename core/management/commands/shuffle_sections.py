import random
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import HomeSection, HomeSectionItem


class Command(BaseCommand):
    help = 'Shuffle section order on home screen and item order within each section'

    def handle(self, *args, **options):
        with transaction.atomic():
            sections = list(HomeSection.objects.filter(is_active=True, display_on__contains='home'))

            # Shuffle section order
            orders = list(range(len(sections)))
            random.shuffle(orders)
            for section, new_order in zip(sections, orders):
                section.order = new_order
            HomeSection.objects.bulk_update(sections, ['order'])

            # Shuffle items within each section
            all_items = []
            for section in sections:
                items = list(HomeSectionItem.objects.filter(section=section, is_active=True))
                item_orders = list(range(len(items)))
                random.shuffle(item_orders)
                for item, new_order in zip(items, item_orders):
                    item.order = new_order
                all_items.extend(items)
            HomeSectionItem.objects.bulk_update(all_items, ['order'])

        self.stdout.write(self.style.SUCCESS(
            f'Shuffled {len(sections)} sections and {len(all_items)} items.'
        ))
