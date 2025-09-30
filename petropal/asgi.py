import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# 1. Set the settings module first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'petropal.settings')

# 2. Initialize Django apps before importing anything that touches models
django_asgi_app = get_asgi_application()

# 3. Now safe to import your app-level code
import chat.routing
from chat.middleware import JWTAuthMiddleware  # custom JWT middleware

# 4. Define the application
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(   
        AuthMiddlewareStack(
            URLRouter(
                chat.routing.websocket_urlpatterns
            )
        )
    ),
})
