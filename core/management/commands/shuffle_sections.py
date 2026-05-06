import random
from django.core.management.base import BaseCommand
from django.db import transaction
from django.core.cache import cache
from core.models import HomeSection, HomeSectionItem


class Command(BaseCommand):
    help = 'Shuffle section order on home screen and item order within each section'

    def _interleave(self, small, big):
        """Place small-card sections into big-card slots so no two smalls are adjacent."""
        if len(small) > len(big) + 1:
            # More smalls than available gaps — just concatenate and shuffle
            combined = small + big
            random.shuffle(combined)
            return combined

        # Pick len(small) distinct slot indices out of len(big)+1 available slots
        slots = sorted(random.sample(range(len(big) + 1), len(small)))
        result = list(big)
        for i, slot in enumerate(slots):
            result.insert(slot + i, small[i])
        return result

    def handle(self, *args, **options):
        with transaction.atomic():
            sections = list(HomeSection.objects.filter(is_active=True, display_on__contains='home'))

            # Split by card type, shuffle each group, then interleave
            small = [s for s in sections if s.card_type == 'small']
            big = [s for s in sections if s.card_type != 'small']
            random.shuffle(small)
            random.shuffle(big)
            ordered = self._interleave(small, big)

            for new_order, section in enumerate(ordered):
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

        cache.clear()

        self.stdout.write(self.style.SUCCESS(
            f'Shuffled {len(sections)} sections and {len(all_items)} items.'
        ))
