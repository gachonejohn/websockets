from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.db.models import Q, Avg
from django.db import transaction
from accounts.models import Account 
from profiles.models import UserProfile, Follow, Rating
from profiles.serializers import (
    AccountProfileSerializer, ProfileUpdateSerializer, FollowSerializer,
    RatingSerializer, RatingCreateSerializer
)
from rest_framework import serializers

from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import PermissionDenied


from django.contrib.auth import get_user_model    
Account = get_user_model()

# # get profile details
# class ProfileDetailView(generics.RetrieveAPIView):
#     serializer_class = AccountProfileSerializer
#     permission_classes = [IsAuthenticated]
    
#     def get_object(self):
#         # Get profile by acc_id or current user
#         acc_id = self.kwargs.get('acc_id')
#         if acc_id:
#             return get_object_or_404(Account, acc_id=acc_id)
#         return self.request.user

# get profile details
class ProfileDetailView(generics.RetrieveAPIView):
    serializer_class = AccountProfileSerializer
    permission_classes = [AllowAny]  # allow anonymous access

    def get_object(self):
        acc_id = self.kwargs.get('acc_id')

        if acc_id:
            # Anyone can fetch a profile by acc_id (for posts)
            return get_object_or_404(Account, acc_id=acc_id)

        # If no acc_id, return current user's profile (auth only)
        if self.request.user.is_authenticated:
            return self.request.user

        # Anonymous users must specify acc_id/login to view own profile
        raise PermissionDenied("Please login to manage your profile.")


class ProfileUpdateView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProfileUpdateSerializer
    http_method_names = ['patch', 'put']

    def get_object(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        return profile


# post to follow a user
class FollowUserView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['post']
    
    def post(self, request, acc_id):
        user_to_follow = get_object_or_404(Account, acc_id=acc_id)
        
        if user_to_follow == request.user:
            return Response(
                {'error': 'You cannot follow yourself'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        follow, created = Follow.objects.get_or_create(
            follower=request.user,
            following=user_to_follow
        )
        
        if created:
            return Response(
                {'message': 'Successfully followed user'},
                status=status.HTTP_201_CREATED
            )
        else:
            return Response(
                {'message': 'Already following this user'},
                status=status.HTTP_200_OK
            )

# delete to unfollow a user
class UnfollowUserView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['delete']
    
    def delete(self, request, acc_id):
        user_to_unfollow = get_object_or_404(Account, acc_id=acc_id)
        
        try:
            follow = Follow.objects.get(
                follower=request.user,
                following=user_to_unfollow
            )
            follow.delete()
            return Response(
                {'message': 'Successfully unfollowed user'},
                status=status.HTTP_200_OK
            )
        except Follow.DoesNotExist:
            return Response(
                {'error': 'You are not following this user'},
                status=status.HTTP_400_BAD_REQUEST
            )

# get a list of followers
class FollowersListView(generics.ListAPIView):
    serializer_class = FollowSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        acc_id = self.kwargs.get('acc_id', self.request.user.acc_id)
        user = get_object_or_404(Account, acc_id=acc_id)
        return Follow.objects.filter(following=user).order_by('-created_at')

# get a list of users being followed
class FollowingListView(generics.ListAPIView):
    serializer_class = FollowSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        acc_id = self.kwargs.get('acc_id', self.request.user.acc_id)
        user = get_object_or_404(Account, acc_id=acc_id)
        return Follow.objects.filter(follower=user).order_by('-created_at')

# get ratings for a user
class RatingsListView(generics.ListAPIView):
    serializer_class = RatingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        acc_id = self.kwargs.get('acc_id', self.request.user.acc_id)
        user = get_object_or_404(Account, acc_id=acc_id)
        return Rating.objects.filter(
            rated=user, 
            status='active'
        ).order_by('-created_at')
    





class CreateRatingView(generics.CreateAPIView):
    serializer_class = RatingCreateSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['post']

    def perform_create(self, serializer):
        data = serializer.validated_data
        rater = self.request.user
        rated = data['rated']

        if rater == rated:
            raise serializers.ValidationError("You cannot rate yourself.")

        # Check for existing rating
        existing_rating = Rating.objects.filter(rater=rater, rated=rated).first()

        if existing_rating:
            # Update existing rating
            existing_rating.rating_count = data['rating_count']
            existing_rating.review_content = data.get('review_content', '')
            existing_rating.save()
            self.instance = existing_rating  
        else:
            serializer.save(rater=rater)

# get profile statistics
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile_stats(request, acc_id=None):
    if acc_id:
        user = get_object_or_404(Account, acc_id=acc_id)
    else:
        user = request.user
    
    stats = {
        'followers_count': user.followers.count(),
        'following_count': user.following.count(),
        'ratings_count': user.received_ratings.filter(status='active').count(),
        'average_rating': user.received_ratings.filter(status='active').aggregate(
            avg=Avg('rating_count')
        )['avg'] or 0.0,
        'total_reviews': user.received_ratings.filter(
            status='active',
            review_content__isnull=False
        ).exclude(review_content='').count(),
        'verification_status': user.is_verified,
        'is_omc': getattr(user.profile, 'is_omc', False) if hasattr(user, 'profile') else False
    }
    
    return Response(stats)



@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_profile_assets(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    if 'profile_picture' in request.FILES:
        profile.profile_picture = request.FILES['profile_picture']

    if 'background_picture' in request.FILES:
        profile.background_picture = request.FILES['background_picture']

    profile.save()

    return Response({
        'message': 'Upload successful',
        'profile_picture_url': request.build_absolute_uri(profile.profile_picture.url) if profile.profile_picture else None,
        'background_picture_url': request.build_absolute_uri(profile.background_picture.url) if profile.background_picture else None
    }, status=status.HTTP_200_OK)

# Search users by name, email, or company
# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def search_users(request):
#     query = request.GET.get('q', '')
    
#     if not query:
#         return Response(
#             {'error': 'Search query is required'},
#             status=status.HTTP_400_BAD_REQUEST
#         )
    
#     users = Account.objects.filter(
#         Q(full_name__icontains=query) |
#         Q(email__icontains=query) |
#         Q(profile__company_name__icontains=query),
#         is_verified=True,
#         state=1  # Active users only
#     ).select_related('profile')[:20]
    
#     serializer = AccountProfileSerializer(users, many=True)
#     return Response(serializer.data)

# return all users
@api_view(['GET'])
@permission_classes([AllowAny])
def featured_users(request):
    try:
        # Get all active, verified users excluding current user and admin/staff/superuser
        users = Account.objects.filter(
            is_verified=True,
            state=1,  # Active users only
            is_staff=False,  # Exclude staff users
            is_superuser=False  # Exclude superuser
        )
        # If authenticated, exclude current user
        if request.user.is_authenticated:
            users = users.exclude(acc_id=request.user.acc_id)
        
        serializer = AccountProfileSerializer(users, many=True)
        return Response(serializer.data)
    except Exception as e:
        return Response(
            {'error': 'Failed to load users. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# search users by name, email, or company
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_users(request):
    query = request.GET.get('q', '').strip()
    
    # Enhanced validation
    if not query:
        return Response(
            {'error': 'Search query is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if len(query) < 2:
        return Response(
            {'error': 'Search query must be at least 2 characters long'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        users = Account.objects.filter(
            Q(full_name__icontains=query) |
            Q(email__icontains=query) |
            Q(profile__company_name__icontains=query),
            is_verified=True,
            state=1
        ).exclude(
            acc_id=request.user.acc_id  # Exclude current user from search
        ).select_related('profile')[:20]
        
        serializer = AccountProfileSerializer(users, many=True)
        return Response(serializer.data)
        
    except Exception as e:
        return Response(
            {'error': 'Search failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )




