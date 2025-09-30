from django.contrib import admin

# Register your models here.
from chat.models import Conversation, Message, MessageReaction, UserStatus, MessageReadStatus
@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('conversation_id', 'created_at', 'updated_at')
    search_fields = ('conversation_id',)
    readonly_fields = ('created_at', 'updated_at')
@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('message_id', 'sender', 'timestamp', 'is_deleted')
    search_fields = ('content', 'sender__email')
    readonly_fields = ('timestamp', 'edited_at')
@admin.register(MessageReaction)
class MessageReactionAdmin(admin.ModelAdmin):
    list_display = ('reaction', 'user', 'message', 'created_at')
    search_fields = ('user__email', 'message__content')
    readonly_fields = ('created_at',)
@admin.register(UserStatus)
class UserStatusAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'last_seen', 'is_typing_in', 'typing_started_at')
    search_fields = ('user__email',)
    readonly_fields = ('last_seen', 'is_typing_in', 'typing_started_at')
@admin.register(MessageReadStatus)
class MessageReadStatusAdmin(admin.ModelAdmin):
    list_display = ('message', 'user', 'read_at')
    search_fields = ('user__email', 'message__content')
    readonly_fields = ('read_at',)
    