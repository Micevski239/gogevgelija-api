"""
Management command to extract latitude/longitude from Google Maps URLs.
Usage: python manage.py extract_coordinates
"""
import re
import requests
from django.core.management.base import BaseCommand
from core.models import Listing


class Command(BaseCommand):
    help = 'Extract latitude and longitude from google_maps_url field for all listings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without actually updating',
        )

    def expand_short_url(self, url):
        """
        Expand shortened URLs (goo.gl, maps.app.goo.gl) to full URLs.
        """
        if 'goo.gl' in url or 'maps.app.goo.gl' in url:
            try:
                response = requests.head(url, allow_redirects=True, timeout=10)
                return response.url
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'Failed to expand URL {url}: {e}')
                )
                return url
        return url

    def extract_coordinates(self, url):
        """
        Extract lat/long from Google Maps URL.
        Supports formats:
        - https://maps.google.com/?q=41.1234,22.5678
        - https://www.google.com/maps/@41.1234,22.5678,15z
        - https://www.google.com/maps/place/.../@41.1234,22.5678,...
        - https://goo.gl/maps/... (will be expanded first)
        - https://maps.app.goo.gl/... (will be expanded first)
        """
        if not url:
            return None, None

        # Expand shortened URLs first
        expanded_url = self.expand_short_url(url)

        # Pattern 1: ?q=lat,lng
        match = re.search(r'[?&]q=(-?\d+\.?\d*),(-?\d+\.?\d*)', expanded_url)
        if match:
            return float(match.group(1)), float(match.group(2))

        # Pattern 2: @lat,lng (most common for expanded goo.gl links)
        match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', expanded_url)
        if match:
            return float(match.group(1)), float(match.group(2))

        # Pattern 3: /place/.../@lat,lng or /@lat,lng with comma separator
        match = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+),', expanded_url)
        if match:
            return float(match.group(1)), float(match.group(2))

        # Pattern 4: ll=lat,lng
        match = re.search(r'll=(-?\d+\.?\d*),(-?\d+\.?\d*)', expanded_url)
        if match:
            return float(match.group(1)), float(match.group(2))

        return None, None

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))

        listings = Listing.objects.all()
        updated_count = 0
        failed_count = 0
        skipped_count = 0

        for listing in listings:
            # Skip if already has coordinates
            if listing.latitude and listing.longitude:
                skipped_count += 1
                continue

            # Skip if no Google Maps URL
            if not listing.google_maps_url:
                continue

            lat, lng = self.extract_coordinates(listing.google_maps_url)

            if lat and lng:
                if dry_run:
                    self.stdout.write(
                        f'Would update "{listing.title}": lat={lat}, lng={lng}'
                    )
                else:
                    listing.latitude = lat
                    listing.longitude = lng
                    listing.save(update_fields=['latitude', 'longitude'])
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Updated "{listing.title}": lat={lat}, lng={lng}'
                        )
                    )
                updated_count += 1
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ Failed to extract coordinates from: {listing.google_maps_url} (Listing: {listing.title})'
                    )
                )
                failed_count += 1

        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS(f'Updated: {updated_count}'))
        self.stdout.write(self.style.WARNING(f'Skipped (already have coordinates): {skipped_count}'))
        self.stdout.write(self.style.ERROR(f'Failed: {failed_count}'))
        self.stdout.write('='*50)

        if dry_run:
            self.stdout.write(
                self.style.WARNING('\nThis was a dry run. Run without --dry-run to apply changes.')
            )
