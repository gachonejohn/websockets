from django.contrib import admin

from django.utils.html import format_html
from .models import UserProfile, Follow, Rating, Badge
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'company_name', 'location', 'country', 'city', 'is_omc', 'created_at', 'updated_at')
    search_fields = ('user__email', 'company_name', 'location', 'country', 'city')
    list_filter = ('is_omc', 'created_at')
    readonly_fields = ('profile_id', 'created_at', 'updated_at')

@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ('follower', 'following', 'created_at')
    search_fields = ('follower__email', 'following__email')
    list_filter = ('created_at',)
    readonly_fields = ('follow_id', 'created_at')


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ('rater', 'rated', 'rating_count', 'status', 'created_at')
    search_fields = ('rater__email', 'rated__email', 'review_content')
    list_filter = ('status', 'created_at')
    readonly_fields = ('rating_id', 'created_at')

    def has_add_permission(self, request):
        return False
    




@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ['name', 'badge_preview']

    def badge_preview(self, obj):
        if obj.icon:
            return format_html('<img src="{}" width="50" />', obj.icon.url)
        return "-"
    badge_preview.short_description = "Badge Image"
