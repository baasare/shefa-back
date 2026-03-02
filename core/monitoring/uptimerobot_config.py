"""
UptimeRobot monitoring configuration and setup.

Automatically creates monitors for your application.
"""
import requests
import logging
import os

logger = logging.getLogger(__name__)


class UptimeRobotManager:
    """
    Manage UptimeRobot monitors programmatically.
    """

    API_URL = "https://api.uptimerobot.com/v2"

    def __init__(self, api_key=None):
        """
        Initialize with API key.

        Get API key from: https://uptimerobot.com/dashboard#mySettings
        """
        self.api_key = api_key or os.environ.get('UPTIMEROBOT_API_KEY')
        if not self.api_key:
            raise ValueError("UptimeRobot API key required")

    def create_monitor(self, name, url, monitor_type='http', interval=300):
        """
        Create a new monitor.

        Args:
            name: Monitor name
            url: URL to monitor
            monitor_type: 'http', 'https', 'keyword', 'ping', 'port'
            interval: Check interval in seconds (300 = 5 min)

        Returns:
            Monitor ID if successful
        """
        payload = {
            'api_key': self.api_key,
            'format': 'json',
            'type': self._get_type_id(monitor_type),
            'friendly_name': name,
            'url': url,
            'interval': interval,
        }

        try:
            response = requests.post(
                f"{self.API_URL}/newMonitor",
                data=payload
            )
            result = response.json()

            if result.get('stat') == 'ok':
                monitor_id = result['monitor']['id']
                logger.info(f"Created UptimeRobot monitor: {name} (ID: {monitor_id})")
                return monitor_id
            else:
                logger.error(f"Failed to create monitor: {result.get('error')}")
                return None

        except Exception as e:
            logger.error(f"Error creating UptimeRobot monitor: {e}")
            return None

    def get_monitors(self):
        """Get all monitors."""
        payload = {
            'api_key': self.api_key,
            'format': 'json',
        }

        try:
            response = requests.post(
                f"{self.API_URL}/getMonitors",
                data=payload
            )
            return response.json()

        except Exception as e:
            logger.error(f"Error fetching monitors: {e}")
            return None

    def delete_monitor(self, monitor_id):
        """Delete a monitor."""
        payload = {
            'api_key': self.api_key,
            'format': 'json',
            'id': monitor_id,
        }

        try:
            response = requests.post(
                f"{self.API_URL}/deleteMonitor",
                data=payload
            )
            return response.json()

        except Exception as e:
            logger.error(f"Error deleting monitor: {e}")
            return None

    def _get_type_id(self, monitor_type):
        """Convert monitor type string to ID."""
        types = {
            'http': 1,
            'keyword': 2,
            'ping': 3,
            'port': 4,
            'heartbeat': 5,
        }
        return types.get(monitor_type.lower(), 1)


def setup_monitors(base_url, api_key=None):
    """
    Setup recommended monitors for the application.

    Args:
        base_url: Base URL of your application (e.g., https://api.shefaai.com)
        api_key: UptimeRobot API key (optional if in env)
    """
    manager = UptimeRobotManager(api_key)

    monitors = [
        {
            'name': 'ShefaAI - Homepage',
            'url': base_url,
            'type': 'http',
            'interval': 300,  # 5 minutes
        },
        {
            'name': 'ShefaAI - API Health',
            'url': f'{base_url}/api/health/',
            'type': 'http',
            'interval': 300,
        },
        {
            'name': 'ShefaAI - Admin Panel',
            'url': f'{base_url}/admin/',
            'type': 'http',
            'interval': 600,  # 10 minutes
        },
        {
            'name': 'ShefaAI - Market Data API',
            'url': f'{base_url}/api/market-data/quotes/',
            'type': 'http',
            'interval': 300,
        },
    ]

    created = []
    for monitor_config in monitors:
        monitor_id = manager.create_monitor(**monitor_config)
        if monitor_id:
            created.append({
                'id': monitor_id,
                'name': monitor_config['name']
            })

    logger.info(f"Created {len(created)} UptimeRobot monitors")
    return created