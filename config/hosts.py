from django_hosts import patterns, host

host_patterns = patterns('',
    host(r'api', 'config.urls.api', name='api'),
    host(r'www', 'config.urls', name='www'),
    host(r'', 'config.urls', name='root'),
)