from django.urls import path
from profiles import views

urlpatterns = [
    # Profile management
    path('profile/stats/', views.profile_stats, name='profile-stats'),

    path('profile/', views.ProfileDetailView.as_view(), name='profile-detail'),
    path('profile/<str:acc_id>/', views.ProfileDetailView.as_view(), name='profile-detail-by-id'),
    path('update/profile/', views.ProfileUpdateView.as_view(), name='profile-update'),


    
    path('profile/stats/<str:acc_id>/', views.profile_stats, name='profile-stats-by-id'),
    # path('upload-profile-picture/', views.upload_profile_picture, name='upload-profile-picture'),

    path('upload-profiles/', views.upload_profile_assets, name='upload-profile-assets'),
    
    # Follow system
    path('follow/<str:acc_id>/', views.FollowUserView.as_view(), name='follow-user'),
    path('unfollow/<str:acc_id>/', views.UnfollowUserView.as_view(), name='unfollow-user'),
    path('followers/', views.FollowersListView.as_view(), name='followers-list'),
    path('followers/<str:acc_id>/', views.FollowersListView.as_view(), name='followers-list-by-id'),
    path('following/', views.FollowingListView.as_view(), name='following-list'),
    path('following/<str:acc_id>/', views.FollowingListView.as_view(), name='following-list-by-id'),
    
    # Ratings system
    path('ratings/', views.RatingsListView.as_view(), name='ratings-list'),
    path('ratings/<str:acc_id>/', views.RatingsListView.as_view(), name='ratings-list-by-id'),
    path('create/rating/', views.CreateRatingView.as_view(), name='create-rating'),
    
    # Featured users
    path('featured-users/', views.featured_users, name='featured-users'),
    # Search
    path('search/', views.search_users, name='search-users'),
]