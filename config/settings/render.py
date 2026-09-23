"""Production deployment on Render with a Supabase PostgreSQL database."""
from .production import *

# Render supplies a service hostname rather than our api.* custom domain.
DEFAULT_HOST = 'api'
ROOT_URLCONF = 'config.urls.api'

render_hostname = config('RENDER_EXTERNAL_HOSTNAME', default='')
if render_hostname and render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_hostname)

DATABASES['default']['OPTIONS'] = {'sslmode': 'require'}
DATABASES['default']['CONN_MAX_AGE'] = 60
DATABASES['default']['CONN_HEALTH_CHECKS'] = True
