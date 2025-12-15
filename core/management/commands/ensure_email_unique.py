"""
Management command to add unique constraint to User email field
This is needed if you migrated from an older Django version
Usage: python manage.py ensure_email_unique
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Add unique constraint to User email field at database level'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # Check if unique constraint exists
            cursor.execute("""
                SELECT COUNT(*)
                FROM pg_constraint
                WHERE conname = 'auth_user_email_key'
                AND conrelid = 'auth_user'::regclass;
            """)

            constraint_exists = cursor.fetchone()[0] > 0

            if constraint_exists:
                self.stdout.write(self.style.SUCCESS('✅ Email unique constraint already exists!'))
                return

            # Check for duplicates before adding constraint
            cursor.execute("""
                SELECT email, COUNT(*) as count
                FROM auth_user
                WHERE email IS NOT NULL AND email != ''
                GROUP BY email
                HAVING COUNT(*) > 1;
            """)

            duplicates = cursor.fetchall()

            if duplicates:
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ Cannot add unique constraint! Found {len(duplicates)} duplicate emails:'
                    )
                )
                for email, count in duplicates:
                    self.stdout.write(f'  - {email}: {count} users')

                self.stdout.write(
                    self.style.NOTICE('\n💡 Run "python manage.py fix_duplicate_users --auto-fix" first!')
                )
                return

            # Add unique constraint
            self.stdout.write('Adding unique constraint to auth_user.email...')
            cursor.execute("""
                ALTER TABLE auth_user
                ADD CONSTRAINT auth_user_email_key UNIQUE (email);
            """)

            self.stdout.write(self.style.SUCCESS('✅ Unique constraint added successfully!'))
            self.stdout.write(
                self.style.SUCCESS('Email addresses are now enforced to be unique at the database level.')
            )
