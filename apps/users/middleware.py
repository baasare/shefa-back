"""
Middleware to capture session metadata.
"""


class SessionMetadataMiddleware:
    """Middleware to store user agent and IP address in session."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Store user agent
            user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown')
            request.session['user_agent'] = user_agent

            # Store IP address
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR', 'Unknown')
            request.session['ip_address'] = ip_address

            # Mark session as modified to ensure it's saved
            request.session.modified = True

        response = self.get_response(request)
        return response
