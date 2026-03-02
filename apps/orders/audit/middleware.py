from apps.orders.audit.trail import log_security_event


# Middleware to automatically log requests
class AuditMiddleware:
    """
    Middleware to automatically log certain requests.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if response.status_code == 403:
            if request.user.is_authenticated:
                log_security_event(
                    user=request.user,
                    action='unauthorized_access',
                    description=f"Unauthorized access attempt to {request.path}",
                    request=request,
                    status_code=403
                )

        return response
