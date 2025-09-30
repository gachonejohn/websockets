import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from chat.models import (
    Conversation, Message, MessageReaction, UserStatus, 
    MessageReadStatus, MessageDeletion, ConversationDeletion
)
from chat.serializers import MessageSerializer, UserDisplaySerializer, MessageReactionSerializer
import uuid
from urllib.parse import parse_qs
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from jwt import decode as jwt_decode
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from datetime import datetime

Account = get_user_model()

# Custom JSON encoder to handle datetime serialization
class DateTimeAwareJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Get conversation ID from URL
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f"chat_{self.conversation_id}"

        # Try to authenticate user from token in query params
        await self.authenticate_user()

        # Verify user has access to this conversation
        if not hasattr(self, 'user') or not self.user or not self.user.is_authenticated:
            await self.close(code=4001)  # Custom close code for authentication failure
            return

        # Update scope with authenticated user
        self.scope["user"] = self.user

        has_access = await self.verify_conversation_access()
        if not has_access:
            await self.close(code=4003)  # Custom close code for access denied
            return

        # Join the group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Mark user as online and broadcast status
        await self.set_user_status('online')
        await self.broadcast_status_change('online')

    async def disconnect(self, close_code):
        # Leave the group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        # Clear typing status and mark user as offline
        if hasattr(self, 'user') and self.user and self.user.is_authenticated:
            await self.clear_typing_status()
            await self.set_user_status('offline')
            await self.broadcast_status_change('offline')

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            event_type = data.get("type")

            if event_type == "chat_message":
                await self.handle_chat_message(data)
            elif event_type == "message_edit":
                await self.handle_message_edit(data)
            elif event_type == "message_delete":
                await self.handle_message_delete(data)
            elif event_type == "reaction":
                await self.handle_reaction(data)
            elif event_type == "read_receipt":
                await self.handle_read_receipt(data)
            elif event_type == "user_typing":
                await self.handle_user_typing(data)
            elif event_type == "ping":
                await self.handle_ping()
            else:
                await self.send_error("Unknown event type")
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format")
        except Exception as e:
            await self.send_error(f"Server error: {str(e)}")

    # --------------------
    # AUTHENTICATION
    # --------------------
    @database_sync_to_async
    # Authenticate user using JWT token from query parameters
    def authenticate_user(self):
        try:
            # Get token from query parameters
            query_string = self.scope.get('query_string', b'').decode('utf-8')
            query_params = parse_qs(query_string)
            token = query_params.get('token', [None])[0]
            
            if token:
                # Decode JWT token
                try:
                    # Validate the token
                    UntypedToken(token)
                    
                    # Decode the token to get user information
                    decoded_token = jwt_decode(
                        token, 
                        settings.SIMPLE_JWT["SIGNING_KEY"], 
                        algorithms=["HS256"]
                    )
                    
                    user_id = decoded_token.get('user_id')
                    if user_id:
                        self.user = Account.objects.get(acc_id=user_id)  # Using acc_id based on account model
                    else:
                        self.user = None
                        
                except (InvalidToken, TokenError, Account.DoesNotExist):
                    self.user = None
            else:
                # Check if user is already authenticated via session
                self.user = self.scope.get("user")
                
        except Exception as e:
            print(f"Authentication error: {e}")  # For debugging
            self.user = None

    # --------------------
    # HANDLERS
    # --------------------
    async def handle_chat_message(self, data):
        if not hasattr(self, 'user') or not self.user or not self.user.is_authenticated:
            await self.send_error("Authentication required")
            return
            
        message_content = data.get("message", "").strip()
        if not message_content:
            await self.send_error("Message content cannot be empty")
            return

        reply_to_id = data.get("reply_to")
        attachment = data.get("attachment")
        message_type = data.get("message_type", "text")

        try:
            # Save message to database
            message = await self.save_message(
                message_content, 
                reply_to_id, 
                attachment, 
                message_type
            )
            
            # Serialize the message for broadcasting
            serialized_message = await self.serialize_message(message)

            # Broadcast to all users in the conversation
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message_broadcast",
                    "message": serialized_message
                }
            )

            # Clear typing status after sending message
            await self.clear_typing_status()

        except Exception as e:
            await self.send_error(f"Failed to save message: {str(e)}")

    async def handle_message_edit(self, data):
        if not hasattr(self, 'user') or not self.user or not self.user.is_authenticated:
            await self.send_error("Authentication required")
            return
            
        message_id = data.get("message_id")
        new_content = data.get("message", "").strip()
        
        if not message_id or not new_content:
            await self.send_error("Message ID and content are required")
            return

        try:
            # Update message in database
            message = await self.edit_message(message_id, new_content)
            
            # Serialize the message for broadcasting
            serialized_message = await self.serialize_message(message)

            # Broadcast to all users in the conversation
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "message_edited_broadcast",
                    "message": serialized_message
                }
            )

        except Exception as e:
            await self.send_error(f"Failed to edit message: {str(e)}")

    async def handle_message_delete(self, data):
        if not hasattr(self, 'user') or not self.user or not self.user.is_authenticated:
            await self.send_error("Authentication required")
            return
            
        message_id = data.get("message_id")
        
        if not message_id:
            await self.send_error("Message ID is required")
            return

        try:
            # Delete message for this user
            await self.delete_message_for_user(message_id)

            # Broadcast deletion to all users in the conversation
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "message_deleted_broadcast",
                    "message_id": message_id,
                    "user_data": await self.get_user_data(),
                    "timestamp": timezone.now().isoformat()
                }
            )

        except Exception as e:
            await self.send_error(f"Failed to delete message: {str(e)}")

    async def handle_reaction(self, data):
        if not hasattr(self, 'user') or not self.user or not self.user.is_authenticated:
            await self.send_error("Authentication required")
            return
            
        message_id = data.get("message_id")
        reaction = data.get("reaction")
        
        if not message_id or not reaction:
            await self.send_error("Message ID and reaction are required")
            return

        try:
            # Toggle reaction in database
            action, reaction_data = await self.toggle_reaction(message_id, reaction)

            # Broadcast reaction update to all users in the conversation
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "reaction_broadcast",
                    "message_id": message_id,
                    "reaction": reaction,
                    "user_data": await self.get_user_data(),
                    "action": action,  # "added" or "removed"
                    "reaction_data": reaction_data,  # Full reaction object if added
                    "timestamp": timezone.now().isoformat()
                }
            )
        except Exception as e:
            await self.send_error(f"Failed to process reaction: {str(e)}")

    async def handle_read_receipt(self, data):
        if not hasattr(self, 'user') or not self.user or not self.user.is_authenticated:
            return
            
        message_id = data.get("message_id")
        if not message_id:
            return

        try:
            await self.mark_message_read(message_id)

            # Broadcast read receipt to all users in the conversation
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "read_receipt_broadcast",
                    "message_id": message_id,
                    "user_data": await self.get_user_data(),
                    "read_at": timezone.now().isoformat()
                }
            )
        except Exception as e:
            await self.send_error(f"Failed to mark message as read: {str(e)}")

    async def handle_user_typing(self, data):
        if not hasattr(self, 'user') or not self.user or not self.user.is_authenticated:
            return
            
        is_typing = data.get("is_typing", False)

        try:
            await self.set_typing_status(is_typing)

            # Broadcast typing status to all users in the conversation
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_typing_broadcast",
                    "user_data": await self.get_user_data(),
                    "is_typing": is_typing,
                    "timestamp": timezone.now().isoformat()
                }
            )
        except Exception as e:
            await self.send_error(f"Failed to update typing status: {str(e)}")

    # Handle ping for keeping connection alive
    async def handle_ping(self):
        await self.send(text_data=json.dumps({
            "type": "pong",
            "timestamp": timezone.now().isoformat()
        }, cls=DateTimeAwareJSONEncoder))

    # --------------------
    # BROADCASTERS
    # --------------------
    async def chat_message_broadcast(self, event):
        await self.send(text_data=json.dumps({
            "type": "chat_message",
            "message": event["message"]
        }, cls=DateTimeAwareJSONEncoder))

    async def message_edited_broadcast(self, event):
        await self.send(text_data=json.dumps({
            "type": "message_edited",
            "message": event["message"]
        }, cls=DateTimeAwareJSONEncoder))

    async def message_deleted_broadcast(self, event):
        # Only send to users who haven't deleted this message themselves
        message_id = event["message_id"]
        user_has_deleted = await self.user_has_deleted_message(message_id)
        
        if not user_has_deleted:
            await self.send(text_data=json.dumps({
                "type": "message_deleted",
                "message_id": message_id,
                "user_data": event["user_data"],
                "timestamp": event["timestamp"]
            }, cls=DateTimeAwareJSONEncoder))

    async def message_restored_broadcast(self, event):
        await self.send(text_data=json.dumps({
            "type": "message_restored",
            "message": event["message"]
        }, cls=DateTimeAwareJSONEncoder))

    async def reaction_broadcast(self, event):
        await self.send(text_data=json.dumps({
            "type": "reaction",
            "message_id": event["message_id"],
            "reaction": event["reaction"],
            "user_data": event["user_data"],
            "action": event["action"],
            "reaction_data": event.get("reaction_data"),
            "timestamp": event["timestamp"]
        }, cls=DateTimeAwareJSONEncoder))

    async def read_receipt_broadcast(self, event):
        # Don't send read receipts to the sender
        if hasattr(self, 'user') and self.user and event["user_data"]["acc_id"] != self.user.acc_id:
            await self.send(text_data=json.dumps({
                "type": "read_receipt",
                "message_id": event["message_id"],
                "user_data": event["user_data"],
                "read_at": event["read_at"]
            }, cls=DateTimeAwareJSONEncoder))

    async def user_typing_broadcast(self, event):
        # Don't send typing events to the sender
        if hasattr(self, 'user') and self.user and event["user_data"]["acc_id"] != self.user.acc_id:
            await self.send(text_data=json.dumps({
                "type": "user_typing",
                "user_data": event["user_data"],
                "is_typing": event["is_typing"],
                "timestamp": event["timestamp"]
            }, cls=DateTimeAwareJSONEncoder))

    async def status_broadcast(self, event):
        # Don't send status updates to the sender
        if hasattr(self, 'user') and self.user and event["user_data"]["acc_id"] != self.user.acc_id:
            await self.send(text_data=json.dumps({
                "type": "user_status",
                "user_data": event["user_data"],
                "status": event["status"],
                "timestamp": event["timestamp"]
            }, cls=DateTimeAwareJSONEncoder))

    async def broadcast_status_change(self, status):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "status_broadcast",
                "user_data": await self.get_user_data(),
                "status": status,
                "timestamp": timezone.now().isoformat()
            }
        )

    # --------------------
    # UTILITY METHODS
    # --------------------

    # Send error message to the client
    async def send_error(self, message):
        await self.send(text_data=json.dumps({
            "type": "error",
            "message": message,
            "timestamp": timezone.now().isoformat()
        }, cls=DateTimeAwareJSONEncoder))

    @database_sync_to_async
    def get_user_data(self):
        """Get serialized user data for broadcasting"""
        serializer = UserDisplaySerializer(self.user)
        data = serializer.data
        # Convert any datetime objects to ISO strings
        return self.serialize_datetime_objects(data)

    # --------------------
    # DATABASE HELPERS
    # --------------------
    @database_sync_to_async
    # Verify if the user has access to the conversation
    def verify_conversation_access(self):
        try:
            conversation = Conversation.objects.get(
                conversation_id=self.conversation_id,
                participants=self.user
            )
            # Also check if user hasn't deleted this conversation
            return not ConversationDeletion.objects.filter(
                conversation=conversation,
                user=self.user
            ).exists()
        except Conversation.DoesNotExist:
            return False

    @database_sync_to_async
    # Save message to the database
    def save_message(self, content, reply_to_id=None, attachment=None, message_type="text"):
        conversation = get_object_or_404(
            Conversation, 
            conversation_id=self.conversation_id
        )
        
        reply_to = None
        if reply_to_id:
            try:
                reply_to = Message.objects.get(message_id=reply_to_id)
            except Message.DoesNotExist:
                pass

        message = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            content=content,  # Will be encrypted in the model's save method
            message_type=message_type,
            attachment=attachment,
            reply_to=reply_to
        )
        
        # Update conversation timestamp
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])
        
        return message

    @database_sync_to_async
    # Edit a message
    def edit_message(self, message_id, new_content):
        message = get_object_or_404(
            Message, 
            message_id=message_id,
            sender=self.user  # Only allow editing own messages
        )
        
        message.content = new_content  # Will be encrypted in the model's save method
        message.is_edited = True
        message.edited_at = timezone.now()
        message.save()
        
        return message

    @database_sync_to_async
    # Soft delete a message for the current user
    def delete_message_for_user(self, message_id):
        message = get_object_or_404(Message, message_id=message_id)
        
        # Check if user is a participant in the conversation
        if not message.conversation.participants.filter(acc_id=self.user.acc_id).exists():
            raise Exception("You do not have permission to delete this message")
        
        # Create or get deletion record
        MessageDeletion.objects.get_or_create(
            message=message,
            user=self.user
        )

    @database_sync_to_async
    # Check if user has deleted a message
    def user_has_deleted_message(self, message_id):
        return MessageDeletion.objects.filter(
            message_id=message_id,
            user=self.user
        ).exists()

    @database_sync_to_async
    # Serialize message for broadcasting
    def serialize_message(self, message):
        from chat.serializers import MessageSerializer
        # Create a mock request object for context
        class MockRequest:
            def __init__(self, user):
                self.user = user
        
        mock_request = MockRequest(self.user)
        serializer = MessageSerializer(message, context={'request': mock_request})
        data = serializer.data
        # Convert any datetime objects to ISO strings
        return self.serialize_datetime_objects(data)
        
    # Recursively convert datetime objects to ISO strings for MessagePack compatibility
    def serialize_datetime_objects(self, obj):
        if isinstance(obj, dict):
            return {key: self.serialize_datetime_objects(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self.serialize_datetime_objects(item) for item in obj]
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, 'isoformat'):  # Handle other datetime-like objects
            return obj.isoformat()
        else:
            return obj

    @database_sync_to_async
    # Toggle reaction for a message and return reaction data
    def toggle_reaction(self, message_id, reaction):
        try:
            message = Message.objects.get(message_id=message_id)
            reaction_obj, created = MessageReaction.objects.get_or_create(
                message=message,
                user=self.user,
                reaction=reaction
            )
            
            if not created:
                reaction_obj.delete()
                return "removed", None
            else:
                # Serialize the reaction for broadcasting
                serializer = MessageReactionSerializer(reaction_obj)
                data = serializer.data
                # Convert any datetime objects to ISO strings
                return "added", self.serialize_datetime_objects(data)
        except Message.DoesNotExist:
            raise Exception("Message not found")

    @database_sync_to_async
    # Mark a message as read
    def mark_message_read(self, message_id):
        try:
            message = Message.objects.get(message_id=message_id)
            read_status, created = MessageReadStatus.objects.update_or_create(
                user=self.user,
                message=message,
                defaults={'read_at': timezone.now()}
            )
            return read_status
        except Message.DoesNotExist:
            raise Exception("Message not found")

    @database_sync_to_async
    # Set user status (online/offline)
    def set_user_status(self, status):
        user_status, created = UserStatus.objects.get_or_create(
            user=self.user
        )
        user_status.status = status
        user_status.last_seen = timezone.now()
        user_status.save(update_fields=["status", "last_seen"])

    @database_sync_to_async
    # Set typing status for the user
    def set_typing_status(self, is_typing):
        conversation = Conversation.objects.get(conversation_id=self.conversation_id)
        user_status, created = UserStatus.objects.get_or_create(
            user=self.user
        )
        
        if is_typing:
            user_status.is_typing_in = conversation
            user_status.typing_started_at = timezone.now()
        else:
            user_status.is_typing_in = None
            user_status.typing_started_at = None
        
        user_status.save(update_fields=["is_typing_in", "typing_started_at"])

    @database_sync_to_async
    # Clear typing status for the user
    def clear_typing_status(self):
        try:
            user_status = UserStatus.objects.get(user=self.user)
            user_status.is_typing_in = None
            user_status.typing_started_at = None
            user_status.save(update_fields=["is_typing_in", "typing_started_at"])
        except UserStatus.DoesNotExist:
            pass

    @database_sync_to_async
    # Get the display name of the user
    def get_user_display_name(self):
        user = self.user
        if hasattr(user, 'profile') and user.profile.company_name:
            return user.profile.company_name
        if user.full_name:
            return user.full_name
        return user.email