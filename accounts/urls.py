from django.urls import path
from .views import (
    RegisterView, LoginView, LogoutView, AccountProfileView, 
    VerifyOTPView, ResendOTPView, ChangePasswordView, CustomTokenRefreshView,
    PasswordResetRequestView, PasswordResetVerifyOTPView,
    PasswordResetConfirmView, PasswordResetResendOTPView
)

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView


urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend_otp'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', AccountProfileView.as_view(), name='account_profile'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),


    path('password-reset/request/', PasswordResetRequestView.as_view()),
    path('password-reset/verify-otp/', PasswordResetVerifyOTPView.as_view()),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view()),
    path('password-reset/resend-otp/', PasswordResetResendOTPView.as_view()),


        # JWT Auth endpoints
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
     
]