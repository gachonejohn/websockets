from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.contrib.auth import login
from django.utils import timezone
from django.conf import settings
from .serializers import (
    AccountRegistrationSerializer, LoginSerializer, AccountSerializer, 
    VerifyOTPSerializer, ResendOTPSerializer, PasswordChangeSerializer
)
from .models import Account, OTPCode, RefreshToken as CustomRefreshToken
from .utils import get_client_ip, get_device_info, send_otp_email, send_otp_sms




class RegisterView(generics.CreateAPIView):
    queryset = Account.objects.all()
    serializer_class = AccountRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        return Response({
            'acc_id': user.acc_id,
            'email': user.email,
            'phone': user.phone,
            'message': f'Account created successfully. Please verify your account with the OTP sent to {user.email}.',
            'requires_verification': True
        }, status=status.HTTP_201_CREATED)


# class LoginView(APIView):
#     permission_classes = [permissions.AllowAny]

#     def post(self, request):
#         serializer = LoginSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
        
#         user = serializer.validated_data['user']
#         credentials_valid = serializer.validated_data.get('credentials_valid', False)
        
#         if credentials_valid:
#             return Response({
#                 'acc_id': user.acc_id,
#                 'message': 'Credentials verified. OTP sent to your registered email.',
#                 'requires_otp': True
#             }, status=status.HTTP_200_OK)

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        authenticated = serializer.validated_data.get('authenticated', False)
        
        if authenticated:
            # Update last login
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            device_info = get_device_info(request)
            CustomRefreshToken.create_token(user, device_info)

            return Response({
                'user': AccountSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                },
                'message': 'Login successful'
            }, status=status.HTTP_200_OK)

class VerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        otp = serializer.validated_data['otp']
        purpose = otp.purpose

        if purpose == 'registration':
            user.verify_account()
            refresh = RefreshToken.for_user(user)
            device_info = get_device_info(request)
            CustomRefreshToken.create_token(user, device_info)

            return Response({
                'user': AccountSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                },
                'message': 'Account verified and activated successfully'
            }, status=status.HTTP_200_OK)

        elif purpose == 'login':
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            refresh = RefreshToken.for_user(user)
            device_info = get_device_info(request)
            CustomRefreshToken.create_token(user, device_info)

            return Response({
                'user': AccountSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                },
                'message': 'Login successful'
            }, status=status.HTTP_200_OK)

        else:
            return Response({
                'message': 'OTP verified successfully'
            }, status=status.HTTP_200_OK)


class ResendOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        purpose = serializer.validated_data['purpose']

        # Generate new OTP
        otp = OTPCode.generate_code(user, purpose)

        # Send OTP
        send_otp_email(user.email, otp.code, purpose)

        return Response({
            'message': f'{purpose.capitalize()} OTP resent successfully'
        }, status=status.HTTP_200_OK)



# class VerifyOTPView(APIView):
#     permission_classes = [permissions.AllowAny]

#     def post(self, request):
#         serializer = VerifyOTPSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)

#         user = serializer.validated_data['user']
#         otp = serializer.validated_data['otp']
#         purpose = otp.purpose

#         if purpose == 'registration':
#             user.verify_account()
#             refresh = RefreshToken.for_user(user)
#             device_info = get_device_info(request)
#             CustomRefreshToken.create_token(user, device_info)

#             return Response({
#                 'user': AccountSerializer(user).data,
#                 'tokens': {
#                     'access': str(refresh.access_token),
#                     'refresh': str(refresh)
#                 },
#                 'message': 'Account verified and activated successfully'
#             }, status=status.HTTP_200_OK)

#         elif purpose == 'login':
#             user.last_login = timezone.now()
#             user.save(update_fields=['last_login'])
#             refresh = RefreshToken.for_user(user)
#             device_info = get_device_info(request)
#             CustomRefreshToken.create_token(user, device_info)

#             return Response({
#                 'user': AccountSerializer(user).data,
#                 'tokens': {
#                     'access': str(refresh.access_token),
#                     'refresh': str(refresh)
#                 },
#                 'message': 'Login successful'
#             }, status=status.HTTP_200_OK)

#         else:
#             return Response({
#                 'message': 'OTP verified successfully'
#             }, status=status.HTTP_200_OK)



class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh_token')
            
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            # Clear device token
            request.user.device_token = None
            request.user.save(update_fields=['device_token', 'updated_at'])
            
            # Revoke custom refresh tokens
            CustomRefreshToken.objects.filter(user=request.user).update(is_revoked=True)
            
            return Response({
                'message': 'Logout successful'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'error': 'Something went wrong'
            }, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        new_password = serializer.validated_data['new_password']
        
        user.set_password(new_password)
        user.password_changed_at = timezone.now()
        user.save(update_fields=['password', 'password_changed_at'])
        
        # Revoke all refresh tokens to force re-login
        CustomRefreshToken.objects.filter(user=user).update(is_revoked=True)
        
        return Response({
            'message': 'Password changed successfully. Please login again.'
        }, status=status.HTTP_200_OK)


class AccountProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = AccountSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        
        if response.status_code == 200:
            # Track refresh token usage
            refresh_token = request.data.get('refresh')
            if refresh_token:
                try:
                    token = RefreshToken(refresh_token)
                    user_id = token.payload.get('user_id')
                    if user_id:
                        device_info = get_device_info(request)
                        # additional tracking here
                except (TokenError, InvalidToken):
                    pass
        
        return response
    




# password reset views
from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from django.utils import timezone
from datetime import timedelta
from .utils import get_client_ip, send_otp_email, send_security_alert
from .serializers import (
    PasswordResetRequestSerializer, 
    PasswordResetVerifyOTPSerializer, 
    PasswordResetConfirmSerializer,
    ResendOTPSerializer
)

class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]  # Add rate limiting
    
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = serializer.save()
        
        return Response({
            'acc_id': result['acc_id'],
            'message': result['message'],
            'requires_otp_verification': True,
            'otp_expires_in_minutes': 10
        }, status=status.HTTP_200_OK)


class PasswordResetVerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]
    
    def post(self, request):
        serializer = PasswordResetVerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        
        return Response({
            'acc_id': user.acc_id,
            'message': 'OTP verified successfully. You can now set a new password.',
            'otp_verified': True,
            'reset_token_expires_in_minutes': 10
        }, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]
    
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        new_password = serializer.validated_data['new_password']
        
        # Update password
        user.set_password(new_password)
        user.password_changed_at = timezone.now()
        user.force_password_change = False  # Clear any force password change flag
        user.save(update_fields=['password', 'password_changed_at', 'force_password_change', 'updated_at'])
        
        # Revoke all existing refresh tokens to force re-login
        CustomRefreshToken.objects.filter(user=user).update(is_revoked=True)
        
        # Clear any remaining password reset OTPs
        OTPCode.objects.filter(user=user, purpose='password_reset', is_used=False).update(is_used=True)
        
        # Send security alert email
        send_security_alert(user, 'Password Reset', {
            'ip_address': get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'timestamp': timezone.now().isoformat()
        })
        
        return Response({
            'message': 'Password reset successful. Please login with your new password.',
            'password_changed': True,
            'tokens_revoked': True
        }, status=status.HTTP_200_OK)


class PasswordResetResendOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]
    
    def post(self, request):
        acc_id = request.data.get('acc_id')
        
        if not acc_id:
            return Response({
                'error': 'acc_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = Account.objects.get(acc_id=acc_id)
            
            # Validate user is eligible for password reset
            if not user.is_verified:
                return Response({
                    'error': 'Account is not verified'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if user.state != 1:  # Not active
                return Response({
                    'error': 'Account is not active'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Generate new OTP with password_reset purpose
            otp = OTPCode.generate_code(user, 'password_reset')
            
            # Send OTP via email
            send_otp_email(user.email, otp.code, 'password_reset')
            
            return Response({
                'message': 'Password reset OTP resent successfully.',
                'otp_expires_in_minutes': 10
            }, status=status.HTTP_200_OK)
            
        except Account.DoesNotExist:
            return Response({
                'error': 'Invalid account ID'
            }, status=status.HTTP_400_BAD_REQUEST)






