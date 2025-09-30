from django.utils import timezone as django_timezone
import pytz

class AutoTimezoneMiddleware:
    """
    Automatically activates user's timezone for all requests
    
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Set timezone based on authenticated user
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_timezone = getattr(request.user, 'timezone', 'UTC')
            try:
                django_timezone.activate(pytz.timezone(user_timezone))
            except pytz.exceptions.UnknownTimeZoneError:
                django_timezone.activate(pytz.UTC)
        else:
            django_timezone.activate(pytz.UTC)

        response = self.get_response(request)
        django_timezone.deactivate()
        return response
