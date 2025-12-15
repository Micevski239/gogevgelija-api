"""
Management command to find and fix duplicate user emails
Usage: python manage.py fix_duplicate_users
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db.models import Count


class Command(BaseCommand):
    help = 'Find and fix duplicate user email addresses'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show duplicates without making changes',
        )
        parser.add_argument(
            '--auto-fix',
            action='store_true',
            help='Automatically merge duplicate users (keeps oldest account)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        auto_fix = options['auto_fix']

        # Find duplicate emails
        duplicates = (
            User.objects.values('email')
            .annotate(email_count=Count('email'))
            .filter(email_count__gt=1)
        )

        if not duplicates:
            self.stdout.write(self.style.SUCCESS('✅ No duplicate email addresses found!'))
            return

        self.stdout.write(self.style.WARNING(f'⚠️  Found {duplicates.count()} duplicate email addresses:'))

        for dup in duplicates:
            email = dup['email']
            count = dup['email_count']
            users = User.objects.filter(email=email).order_by('date_joined')

            self.stdout.write(f'\n📧 Email: {email} ({count} users)')
            for i, user in enumerate(users):
                marker = '✓ KEEP' if i == 0 else '✗ DELETE'
                self.stdout.write(
                    f'  [{marker}] User ID: {user.id}, Username: {user.username}, '
                    f'Joined: {user.date_joined}, Last Login: {user.last_login}'
                )

            if auto_fix and not dry_run:
                # Keep the oldest user, delete the rest
                primary_user = users.first()
                duplicate_users = users[1:]

                for dup_user in duplicate_users:
                    self.stdout.write(
                        self.style.WARNING(f'  🗑️  Deleting duplicate user: {dup_user.username} (ID: {dup_user.id})')
                    )
                    # You might want to transfer data (wishlists, permissions, etc.) before deleting
                    # For now, we'll just delete
                    dup_user.delete()

                self.stdout.write(
                    self.style.SUCCESS(f'  ✅ Kept primary user: {primary_user.username} (ID: {primary_user.id})')
                )

        if dry_run:
            self.stdout.write(
                self.style.NOTICE('\n💡 This was a dry run. Use --auto-fix to actually fix duplicates.')
            )
        elif not auto_fix:
            self.stdout.write(
                self.style.NOTICE('\n💡 Use --auto-fix to automatically fix duplicates (keeps oldest account).')
            )
        else:
            self.stdout.write(self.style.SUCCESS('\n✅ Duplicate users have been cleaned up!'))
