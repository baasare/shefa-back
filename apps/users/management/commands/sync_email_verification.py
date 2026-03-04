"""
Management command to sync email verification status from EmailAddress to User model.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from allauth.account.models import EmailAddress
from apps.users.models import User


class Command(BaseCommand):
    help = 'Sync email verification status from EmailAddress to User.is_verified'

    def handle(self, *args, **options):
        """Sync verification status for all users."""

        synced_count = 0
        already_synced = 0
        no_email_address = 0

        users = User.all_objects.all()
        total = users.count()

        self.stdout.write(f"Checking {total} users...\n")

        for user in users:
            try:
                email_addr = EmailAddress.objects.get(user=user, primary=True)

                if email_addr.verified and not user.is_verified:
                    user.is_verified = True
                    user.save(update_fields=['is_verified'])
                    synced_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Synced {user.email}")
                    )
                elif user.is_verified:
                    already_synced += 1

            except EmailAddress.DoesNotExist:
                no_email_address += 1
                self.stdout.write(
                    self.style.WARNING(f"⚠ No EmailAddress for {user.email}")
                )

        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS(f"\nSynced: {synced_count}"))
        self.stdout.write(f"Already synced: {already_synced}")
        self.stdout.write(f"No EmailAddress: {no_email_address}")
        self.stdout.write(f"Total: {total}\n")
