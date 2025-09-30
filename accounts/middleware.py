from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseForbidden
from django.core.cache import cache
from django.conf import settings
import time
import logging

logger = logging.getLogger(__name__)


class SecurityMiddleware(MiddlewareMixin):
    """Security middleware for rate limiting and security headers"""
    
    def process_request(self, request):
        # Rate limiting
        if self.is_rate_limited(request):
            return HttpResponseForbidden("Rate limit exceeded")
        
        return None
    
    def process_response(self, request, response):
        # Add security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        return response
    
    def is_rate_limited(self, request):
        """Check if request is rate limited"""
        if not hasattr(settings, 'RATE_LIMIT_ENABLED') or not settings.RATE_LIMIT_ENABLED:
            return False
        
        # Get client IP
        ip = self.get_client_ip(request)
        
        # Different limits for different endpoints
        if request.path.startswith('/api/auth/login'):
            return self.check_rate_limit(f"login_{ip}", 5, 300)  # 5 attempts per 5 minutes
        elif request.path.startswith('/api/auth/register'):
            return self.check_rate_limit(f"register_{ip}", 3, 3600)  # 3 attempts per hour
        elif request.path.startswith('/api/auth/'):
            return self.check_rate_limit(f"auth_{ip}", 20, 60)  # 20 requests per minute
        
        return False
    
    def check_rate_limit(self, key, limit, window):
        """Check rate limit for a given key"""
        current_time = int(time.time())
        window_start = current_time - window
        
        # Get existing requests in the window
        requests = cache.get(key, [])
        
        # Filter out old requests
        requests = [req_time for req_time in requests if req_time > window_start]
        
        # Check if limit exceeded
        if len(requests) >= limit:
            return True
        
        # Add current request
        requests.append(current_time)
        cache.set(key, requests, window)
        
        return False
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip