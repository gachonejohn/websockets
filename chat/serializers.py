from rest_framework import serializers
from chat.models import (
    Conversation, Message, MessageReadStatus, MessageReaction, 
    UserStatus, MessageDeletion, ConversationDeletion
)
from accounts.models import Account
from django.utils import timezone

from shared.tz_mixins import BaseModelSerializer

class UserDisplaySerializer(BaseModelSerializer):
    display_name = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ['acc_id', 'email', 'display_name', 'profile_picture', 'status']

    def get_display_name(self, obj):
        if hasattr(obj, 'profile') and obj.profile.company_name:
            return obj.profile.company_name
        if obj.full_name:
            return obj.full_name
        return obj.email

    def get_profile_picture(self, obj):
        if hasattr(obj, 'profile') and obj.profile.profile_picture:
            return obj.profile.profile_picture.url
        return None

    def get_status(self, obj):
        if hasattr(obj, 'status'):
            return {
                'status': obj.status.status,
                'last_seen': obj.status.last_seen
            }
        return {'status': 'offline', 'last_seen': None}

class MessageReactionSerializer(BaseModelSerializer):
    user = UserDisplaySerializer(read_only=True)

    class Meta:
        model = MessageReaction
        fields = ['reaction', 'user', 'created_at']

class MessageSerializer(BaseModelSerializer):
    sender = UserDisplaySerializer(read_only=True)
    content = serializers.SerializerMethodField()
    reactions = MessageReactionSerializer(many=True, read_only=True)
    reaction_counts = serializers.SerializerMethodField()
    reply_to = serializers.SerializerMethodField()
    is_deleted_by_me = serializers.SerializerMethodField()
    
    # Add a write-only field for creating/editing messages
    message_content = serializers.CharField(write_only=True)

    class Meta:
        model = Message
        fields = ['message_id', 'content', 'message_content', 'timestamp', 'message_type', 
                 'attachment', 'sender', 'is_edited', 'edited_at', 
                 'reactions', 'reaction_counts', 'reply_to', 'is_deleted_by_me']
        read_only_fields = ['message_id', 'timestamp', 'sender', 'is_edited', 'edited_at']

    def get_content(self, obj):
        # Check if current user has deleted this message
        request = self.context.get('request')
        if request and request.user:
            if MessageDeletion.objects.filter(message=obj, user=request.user).exists():
                return None  # Return None for deleted messages
        return obj.get_decrypted_content()

    def get_is_deleted_by_me(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return MessageDeletion.objects.filter(message=obj, user=request.user).exists()
        return False

    def create(self, validated_data):
        # Extract the actual content from message_content field
        content = validated_data.pop('message_content', validated_data.get('content', ''))
        validated_data['content'] = content
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Handle content update for editing
        if 'message_content' in validated_data:
            content = validated_data.pop('message_content')
            validated_data['content'] = content
            validated_data['is_edited'] = True
            validated_data['edited_at'] = timezone.now()
        return super().update(instance, validated_data)

    # Get reaction counts for the message
    def get_reaction_counts(self, obj):
        reactions = obj.reactions.all()
        counts = {}
        for reaction in reactions:
            reaction_type = reaction.reaction
            if reaction_type not in counts:
                counts[reaction_type] = 0
            counts[reaction_type] += 1
        return counts

    def get_reply_to(self, obj):
        if obj.reply_to:
            # Check if the replied message is deleted by current user
            request = self.context.get('request')
            if request and request.user:
                if MessageDeletion.objects.filter(message=obj.reply_to, user=request.user).exists():
                    return {
                        'message_id': obj.reply_to.message_id,
                        'content': '[Message deleted]',
                        'sender': UserDisplaySerializer(obj.reply_to.sender).data
                    }
            
            return {
                'message_id': obj.reply_to.message_id,
                'content': obj.reply_to.get_decrypted_content()[:100],
                'sender': UserDisplaySerializer(obj.reply_to.sender).data
            }
        return None

class ConversationSerializer(BaseModelSerializer):
    participants = UserDisplaySerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    typing_users = serializers.SerializerMethodField()
    is_deleted_by_me = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['conversation_id', 'name', 'is_group', 'created_at', 'updated_at', 
                 'participants', 'last_message', 'unread_count', 'typing_users', 'is_deleted_by_me']

    def get_last_message(self, obj):
        request = self.context.get('request')
        if not request or not request.user:
            return None
        
        # Get the last message that hasn't been deleted by this user
        last_message = obj.messages.exclude(
            user_deletions__user=request.user
        ).first()
        
        if last_message:
            return MessageSerializer(last_message, context=self.context).data
        return None

    def get_is_deleted_by_me(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return ConversationDeletion.objects.filter(conversation=obj, user=request.user).exists()
        return False

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if request and request.user:
            last_read = MessageReadStatus.objects.filter(
                user=request.user,
                message__conversation=obj
            ).order_by('-message__timestamp').first()
            
            messages_query = obj.messages.exclude(
                user_deletions__user=request.user  # Exclude messages deleted by user
            ).exclude(sender=request.user)
            
            if last_read:
                return messages_query.filter(
                    timestamp__gt=last_read.read_at
                ).count()
            else:
                return messages_query.count()
        return 0

    def get_typing_users(self, obj):
        typing_users = UserStatus.objects.filter(
            is_typing_in=obj,
            typing_started_at__gte=timezone.now() - timezone.timedelta(seconds=10)
        ).exclude(user=self.context.get('request').user if self.context.get('request') else None)
        return UserDisplaySerializer([status.user for status in typing_users], many=True).data

class ConversationCreateSerializer(BaseModelSerializer):
    participant_ids = serializers.ListField(
        child=serializers.CharField(),
        write_only=True
    )

    class Meta:
        model = Conversation
        fields = ['name', 'is_group', 'participant_ids']

    def create(self, validated_data):
        participant_ids = validated_data.pop('participant_ids')
        conversation = Conversation.objects.create(
            created_by=self.context['request'].user,
            **validated_data
        )
        
        # Add participants
        participants = Account.objects.filter(acc_id__in=participant_ids)
        conversation.participants.set(participants)
        
        # Add the creator as a participant
        conversation.participants.add(self.context['request'].user)
        
        return conversation

# Serializer for editing messages
class MessageEditSerializer(BaseModelSerializer):
    message_content = serializers.CharField(source="content")

    class Meta:
        model = Message
        fields = ['message_content']

    def update(self, instance, validated_data):
        instance.content = validated_data['content']  
        instance.is_edited = True
        instance.edited_at = timezone.now()
        instance.save()
        return instance

    def to_representation(self, instance):
        return MessageSerializer(instance, context=self.context).data