
from django.core.management.base import BaseCommand
from core.monitoring.uptimerobot_config import setup_monitors
from django.conf import settings

class Command(BaseCommand):
    help = 'Setup UptimeRobot monitoring'

    def handle(self, *args, **options):
        base_url = settings.SITE_URL
        monitors = setup_monitors(base_url)

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created {len(monitors)} monitors'
            )
        )

        for monitor in monitors:
            self.stdout.write(f"  - {monitor['name']} (ID: {monitor['id']})")