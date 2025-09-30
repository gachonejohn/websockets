import jwt
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model

User = get_user_model()


@database_sync_to_async
def get_user(user_id: int):
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
   
    async def __call__(self, scope, receive, send):
        token = None

        # --- 1. Get token from query string ---
        query_string = parse_qs(scope.get("query_string", b"").decode())
        if "token" in query_string:
            token = query_string["token"][0]

        # --- 2. Or from headers ---
        if not token and scope.get("headers"):
            headers = dict(scope["headers"])
            if b"authorization" in headers:
                auth_header = headers[b"authorization"].decode()
                if auth_header.startswith("Bearer "):
                    token = auth_header.split(" ")[1]

        # --- 3. Validate token & set user ---
        if token:
            try:
                UntypedToken(token)  # validates signature & expiry
                decoded = jwt.decode(
                    token,
                    settings.SIMPLE_JWT["SIGNING_KEY"],
                    algorithms=["HS256"]
                )
                scope["user"] = await get_user(decoded["user_id"])
            except (InvalidToken, TokenError, jwt.ExpiredSignatureError, jwt.DecodeError):
                scope["user"] = AnonymousUser()
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
