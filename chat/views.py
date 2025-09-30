from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Q, Max, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from chat.models import (
    Conversation, Message, MessageReaction, UserStatus, 
    MessageReadStatus, MessageDeletion, ConversationDeletion
)
from chat.serializers import (
    ConversationSerializer, 
    ConversationCreateSerializer, 
    MessageSerializer,
    MessageReactionSerializer,
    UserDisplaySerializer,
    MessageEditSerializer
)
from accounts.models import Account
from datetime import datetime

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# Helper function to serialize datetime objects for WebSocket compatibility
def serialize_datetime_objects(obj):
    if isinstance(obj, dict):
        return {key: serialize_datetime_objects(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [serialize_datetime_objects(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, 'isoformat'):  # Handle other datetime-like objects
        return obj.isoformat()
    else:
        return obj

class ConversationListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Exclude conversations that the user has deleted
        return Conversation.objects.filter(
            participants=self.request.user
        ).exclude(
            user_deletions__user=self.request.user
        ).prefetch_related(
            'participants__profile',
            'participants__status',
            Prefetch('messages', queryset=Message.objects.filter(is_deleted=False))
        )
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ConversationCreateSerializer
        return ConversationSerializer

class ConversationDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'conversation_id'
    
    def get_queryset(self):
        return Conversation.objects.filter(
            participants=self.request.user
        ).exclude(
            user_deletions__user=self.request.user
        )

class MessageListCreateView(generics.ListCreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        conversation_id = self.kwargs['conversation_id']
        conversation = get_object_or_404(
            Conversation,
            conversation_id=conversation_id,
            participants=self.request.user
        )
        
        # Exclude messages that the user has deleted
        return Message.objects.filter(
            conversation=conversation,
            is_deleted=False
        ).exclude(
            user_deletions__user=self.request.user
        ).prefetch_related('reactions__user', 'sender__profile')

    def perform_create(self, serializer):
        conversation_id = self.kwargs['conversation_id']
        conversation = get_object_or_404(
            Conversation,
            conversation_id=conversation_id,
            participants=self.request.user
        )

        reply_to = None
        if 'reply_to' in self.request.data:
            reply_to = get_object_or_404(Message, message_id=self.request.data['reply_to'])

        # Save message
        message = serializer.save(
            sender=self.request.user,
            conversation=conversation,
            reply_to=reply_to
        )

        # Update conversation
        conversation.save()

        # Clear typing status
        user_status, _ = UserStatus.objects.get_or_create(user=self.request.user)
        user_status.is_typing_in = None
        user_status.typing_started_at = None
        user_status.save()

        # 🔥 Broadcast to WebSocket group
        channel_layer = get_channel_layer()
        message_data = MessageSerializer(message, context={'request': self.request}).data
        
        async_to_sync(channel_layer.group_send)(
            f"chat_{conversation.conversation_id}",
            {
                "type": "chat_message_broadcast",
                "message": serialize_datetime_objects(message_data)
            }
        )

# Message detail view for editing and deleting
class MessageDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'message_id'

    def get_queryset(self):
        return Message.objects.filter(
            sender=self.request.user,  # Only allow editing own messages
            is_deleted=False
        ).exclude(
            user_deletions__user=self.request.user
        )

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return MessageEditSerializer
        return MessageSerializer

    def perform_update(self, serializer):
        message = serializer.save()
        
        # Broadcast message edit to WebSocket group
        channel_layer = get_channel_layer()
        message_data = MessageSerializer(message, context={'request': self.request}).data
        
        async_to_sync(channel_layer.group_send)(
            f"chat_{message.conversation.conversation_id}",
            {
                "type": "message_edited_broadcast",
                "message": serialize_datetime_objects(message_data)
            }
        )

@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
# Soft delete a message for the current user
def delete_message(request, message_id):
   
    message = get_object_or_404(Message, message_id=message_id)
    
    # Check if user is a participant in the conversation
    if not message.conversation.participants.filter(acc_id=request.user.acc_id).exists():
        return Response({'error': 'You do not have permission to delete this message'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    # Create or get deletion record
    deletion, created = MessageDeletion.objects.get_or_create(
        message=message,
        user=request.user
    )
    
    if created:
        # Broadcast message deletion to WebSocket group
        channel_layer = get_channel_layer()
        user_data = UserDisplaySerializer(request.user).data
        
        async_to_sync(channel_layer.group_send)(
            f"chat_{message.conversation.conversation_id}",
            {
                "type": "message_deleted_broadcast",
                "message_id": str(message_id),
                "user_data": serialize_datetime_objects(user_data),
                "timestamp": timezone.now().isoformat()
            }
        )
        
        return Response({'status': 'Message deleted successfully'})
    else:
        return Response({'status': 'Message was already deleted'})

@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
# Soft delete a conversation for the current user only
def delete_conversation(request, conversation_id):

    conversation = get_object_or_404(
        Conversation,
        conversation_id=conversation_id,
        participants=request.user
    )
    
    # Create or get deletion record
    deletion, created = ConversationDeletion.objects.get_or_create(
        conversation=conversation,
        user=request.user
    )
    
    if created:
        return Response({'status': 'Conversation deleted successfully'})
    else:
        return Response({'status': 'Conversation was already deleted'})

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
# Restore a deleted message for the current user
def restore_message(request, message_id):
    message = get_object_or_404(Message, message_id=message_id)
    
    try:
        deletion = MessageDeletion.objects.get(message=message, user=request.user)
        deletion.delete()
        
        # Broadcast message restoration to WebSocket group
        channel_layer = get_channel_layer()
        message_data = MessageSerializer(message, context={'request': request}).data
        
        async_to_sync(channel_layer.group_send)(
            f"chat_{message.conversation.conversation_id}",
            {
                "type": "message_restored_broadcast",
                "message": serialize_datetime_objects(message_data)
            }
        )
        
        return Response({'status': 'Message restored successfully'})
    except MessageDeletion.DoesNotExist:
        return Response({'error': 'Message was not deleted'}, 
                       status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
# Restore a deleted conversation for the current user
def restore_conversation(request, conversation_id):
    conversation = get_object_or_404(
        Conversation,
        conversation_id=conversation_id,
        participants=request.user
    )
    
    try:
        deletion = ConversationDeletion.objects.get(conversation=conversation, user=request.user)
        deletion.delete()
        return Response({'status': 'Conversation restored successfully'})
    except ConversationDeletion.DoesNotExist:
        return Response({'error': 'Conversation was not deleted'}, 
                       status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_messages_read(request, conversation_id):
    conversation = get_object_or_404(
        Conversation,
        conversation_id=conversation_id,
        participants=request.user
    )
    
    # Get latest message that user hasn't deleted
    latest_message = conversation.messages.filter(
        is_deleted=False
    ).exclude(
        user_deletions__user=request.user
    ).first()
    
    if latest_message:
        # Create or update read status
        MessageReadStatus.objects.update_or_create(
            user=request.user,
            message=latest_message,
            defaults={'read_at': timezone.now()}
        )
        
        # 🔥 Broadcast read receipt to WebSocket group
        channel_layer = get_channel_layer()
        user_data = UserDisplaySerializer(request.user).data
        
        async_to_sync(channel_layer.group_send)(
            f"chat_{conversation.conversation_id}",
            {
                "type": "read_receipt_broadcast",
                "message_id": str(latest_message.message_id),
                "user_data": serialize_datetime_objects(user_data),
                "read_at": timezone.now().isoformat()
            }
        )
    
    return Response({'status': 'Messages marked as read'})

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_or_create_conversation(request, user_id):
    other_user = get_object_or_404(Account, acc_id=user_id)
    
    conversation = Conversation.objects.filter(
        participants=request.user,
        is_group=False
    ).filter(
        participants=other_user
    ).exclude(
        user_deletions__user=request.user
    ).first()
    
    if not conversation:
        conversation = Conversation.objects.create(is_group=False, created_by=request.user)
        conversation.participants.add(request.user, other_user)
    
    serializer = ConversationSerializer(conversation, context={'request': request})
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def add_reaction(request, message_id):
    message = get_object_or_404(Message, message_id=message_id)
    reaction_type = request.data.get('reaction')
    
    if reaction_type not in dict(MessageReaction.REACTION_CHOICES):
        return Response({'error': 'Invalid reaction'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Toggle reaction
    reaction, created = MessageReaction.objects.get_or_create(
        message=message,
        user=request.user,
        reaction=reaction_type
    )
    
    action = "added"
    reaction_data = None
    
    if not created:
        reaction.delete()
        action = "removed"
    else:
        reaction_data = MessageReactionSerializer(reaction).data
        reaction_data = serialize_datetime_objects(reaction_data)
    
    # 🔥 Broadcast reaction to WebSocket group
    channel_layer = get_channel_layer()
    user_data = UserDisplaySerializer(request.user).data
    
    async_to_sync(channel_layer.group_send)(
        f"chat_{message.conversation.conversation_id}",
        {
            "type": "reaction_broadcast",
            "message_id": str(message_id),
            "reaction": reaction_type,
            "user_data": serialize_datetime_objects(user_data),
            "action": action,
            "reaction_data": reaction_data,
            "timestamp": timezone.now().isoformat()
        }
    )
    
    return Response({
        'status': f'Reaction {action}',
        'action': action,
        'reaction_data': reaction_data
    })

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def set_typing_status(request, conversation_id):
    conversation = get_object_or_404(
        Conversation,
        conversation_id=conversation_id,
        participants=request.user
    )
    
    is_typing = request.data.get('is_typing', False)
    user_status, _ = UserStatus.objects.get_or_create(user=request.user)
    
    if is_typing:
        user_status.is_typing_in = conversation
        user_status.typing_started_at = timezone.now()
    else:
        user_status.is_typing_in = None
        user_status.typing_started_at = None
    
    user_status.save()
    
    # 🔥 Broadcast typing status to WebSocket group
    channel_layer = get_channel_layer()
    user_data = UserDisplaySerializer(request.user).data
    
    async_to_sync(channel_layer.group_send)(
        f"chat_{conversation.conversation_id}",
        {
            "type": "user_typing_broadcast",
            "user_data": serialize_datetime_objects(user_data),
            "is_typing": is_typing,
            "timestamp": timezone.now().isoformat()
        }
    )
    
    return Response({'status': 'Typing status updated'})

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_user_status(request):
    status_value = request.data.get('status', 'online')
    
    user_status, _ = UserStatus.objects.get_or_create(user=request.user)
    user_status.status = status_value
    user_status.last_seen = timezone.now()
    user_status.save()
    
    # 🔥 Broadcast status change to all conversations the user is part of
    channel_layer = get_channel_layer()
    user_data = UserDisplaySerializer(request.user).data
    
    # Get all conversations the user is part of (excluding deleted ones)
    conversations = Conversation.objects.filter(
        participants=request.user
    ).exclude(
        user_deletions__user=request.user
    )
    
    for conversation in conversations:
        async_to_sync(channel_layer.group_send)(
            f"chat_{conversation.conversation_id}",
            {
                "type": "status_broadcast",
                "user_data": serialize_datetime_objects(user_data),
                "status": status_value,
                "timestamp": timezone.now().isoformat()
            }
        )
    
    return Response({'status': f'Status updated to {status_value}'})