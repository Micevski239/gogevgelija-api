"""
Management command to shuffle listing order
Usage: python manage.py shuffle_listings
"""
import random
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Listing


class Command(BaseCommand):
    help = 'Shuffle the random_order field for all active listings to randomize their display order'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be shuffled without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Get all active listings
        listings = Listing.objects.filter(is_active=True)
        total_count = listings.count()

        if total_count == 0:
            self.stdout.write(self.style.WARNING('No active listings found.'))
            return

        self.stdout.write(f'Found {total_count} active listings to shuffle')

        if dry_run:
            self.stdout.write(self.style.NOTICE('DRY RUN - No changes will be made'))
            self.stdout.write(f'Would shuffle {total_count} listings')
            return

        # Generate random values for each listing
        # Use transaction for better performance
        with transaction.atomic():
            for listing in listings:
                # Generate a random decimal between 0 and 1
                listing.random_order = random.random()

            # Bulk update for better performance
            Listing.objects.bulk_update(listings, ['random_order'], batch_size=100)

        self.stdout.write(
            self.style.SUCCESS(f'✅ Successfully shuffled {total_count} listings!')
        )
        self.stdout.write('Listings will now appear in a new random order.')
