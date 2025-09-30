from django.urls import path, re_path
from chat import consumers

websocket_urlpatterns = [
    path("ws/chat/<uuid:conversation_id>/", consumers.ChatConsumer.as_asgi()),
    # re_path(r'ws/chat/(?P<room_name>\w+)/$', consumers.ChatConsumer.as_asgi()),
]
