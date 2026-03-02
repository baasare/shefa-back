"""
Django management command to rotate encryption keys.

Usage:
    # Generate new key
    python manage.py rotate_keys --generate

    # Rotate existing credentials to new key
    python manage.py rotate_keys --rotate
"""
from django.core.management.base import BaseCommand
from apps.brokers.key_rotation import generate_new_key, rotate_broker_credentials


class Command(BaseCommand):
    """Manage encryption key rotation."""

    help = 'Manage encryption key rotation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--generate',
            action='store_true',
            help='Generate a new encryption key'
        )
        parser.add_argument(
            '--rotate',
            action='store_true',
            help='Rotate all credentials to new primary key'
        )

    def handle(self, *args, **options):
        if options['generate']:
            new_key = generate_new_key()
            self.stdout.write(self.style.SUCCESS(
                f"\nNew encryption key generated:\n{new_key}\n"
            ))
            self.stdout.write(self.style.WARNING(
                "\nTo rotate keys:\n"
                "1. Set ENCRYPTION_KEY_OLD_1 to current ENCRYPTION_KEY in .env\n"
                "2. Set ENCRYPTION_KEY to new key above in .env\n"
                "3. Restart application\n"
                "4. Run: python manage.py rotate_keys --rotate\n"
                "5. After 24 hours, remove ENCRYPTION_KEY_OLD_1 from .env\n"
            ))

        elif options['rotate']:
            self.stdout.write("Starting key rotation...")
            rotated, errors = rotate_broker_credentials()

            if errors == 0:
                self.stdout.write(self.style.SUCCESS(
                    f"Successfully rotated {rotated} broker connections"
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    f"Rotation completed with {errors} errors. "
                    f"{rotated} connections rotated successfully."
                ))

        else:
            self.stdout.write(self.style.ERROR(
                "Please specify --generate or --rotate"
            ))
