# profile imports
from rest_framework import serializers
from accounts.models import Account
from profiles.models import UserProfile, Follow, Rating, Badge
from django.db import models

from shared.tz_mixins import BaseModelSerializer


# verification badge serializer
class BadgeSerializer(BaseModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Badge
        fields = ['name', 'image_url']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.icon and request:
            return request.build_absolute_uri(obj.icon.url)
        return None

# profile serializers
class UserProfileSerializer(BaseModelSerializer):
    badge = BadgeSerializer(read_only=True)  # Use nested serializer
    class Meta:
        model = UserProfile
        fields = '__all__'
        read_only_fields = ('profile_id', 'user', 'created_at', 'updated_at')


class AccountProfileSerializer(BaseModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    ratings_count = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    
    class Meta:
        model = Account
        fields = [
            'acc_id', 'email', 'full_name', 'phone', 'is_verified', 
            'created_at', 'updated_at', 'profile', 'followers_count',
            'following_count', 'ratings_count', 'average_rating'
        ]
        read_only_fields = ('acc_id', 'email', 'created_at', 'updated_at', 'is_verified')
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        
        # Ensure profile exists
        if not hasattr(instance, 'profile') or instance.profile is None:
            # Create default profile representation
            data['profile'] = {
                'profile_id': None,
                'user': str(instance.acc_id),
                'company_name': None,
                'profile_picture': None,
                'background_picture': None,
                'about_bio': None,
                'location': None,
                'country': None,
                'city': None,
                'interest': [],
                'language_preference': 'en',
                'is_omc': False,
                'verification_badge': None,
                'verification_documents': [],
                'created_at': instance.created_at.isoformat(),
                'updated_at': instance.updated_at.isoformat(),
            }
        
        return data
    
    def get_followers_count(self, obj):
        return obj.followers.count()
    
    def get_following_count(self, obj):
        return obj.following.count()
    
    def get_ratings_count(self, obj):
        return obj.received_ratings.filter(status='active').count()
    
    def get_average_rating(self, obj):
        ratings = obj.received_ratings.filter(status='active')
        if ratings.exists():
            return round(ratings.aggregate(avg=models.Avg('rating_count'))['avg'], 1)
        return 0.0

class ProfileUpdateSerializer(BaseModelSerializer):
    company_name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    company_logo_url = serializers.URLField(required=False, allow_blank=True)
    about_bio = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    location = serializers.CharField(required=False, allow_blank=True, max_length=255)
    country = serializers.CharField(required=False, allow_blank=True, max_length=100)
    city = serializers.CharField(required=False, allow_blank=True, max_length=100)
    interest = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False, 
        allow_empty=True
    )
    language_preference = serializers.CharField(required=False, max_length=10)
    
    class Meta:
        model = UserProfile
        fields = [
            'company_name', 'company_logo_url', 'about_bio', 'location',
            'country', 'city', 'interest', 'language_preference'
        ]
    
    def validate_interest(self, value):
        if len(value) > 10:
            raise serializers.ValidationError("Maximum 10 interests allowed")
        return value

class FollowSerializer(BaseModelSerializer):
    follower_info = AccountProfileSerializer(source='follower', read_only=True)
    following_info = AccountProfileSerializer(source='following', read_only=True)
    
    class Meta:
        model = Follow
        fields = ['follow_id', 'follower_info', 'following_info', 'created_at']

class RatingSerializer(BaseModelSerializer):
    rater_info = AccountProfileSerializer(source='rater', read_only=True)
    
    class Meta:
        model = Rating
        fields = [
            'rating_id', 'rater_info', 'rating_count', 'review_content',
            'status', 'created_at'
        ]



class RatingCreateSerializer(BaseModelSerializer):
    class Meta:
        model = Rating
        fields = ['rated', 'rating_count', 'review_content']

    def validate_rated(self, value):
        request_user = self.context['request'].user
        if value == request_user:
            raise serializers.ValidationError("You cannot rate yourself.")
        if not Account.objects.filter(acc_id=value.acc_id).exists():
            raise serializers.ValidationError("The specified user does not exist.")
        return value

    def validate_rating_count(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value