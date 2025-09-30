from rest_framework import serializers
from django.contrib.auth import authenticate
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Account, OTPCode
from .utils import send_otp_email, send_otp_sms

from shared.tz_mixins import BaseModelSerializer


class AccountRegistrationSerializer(BaseModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    device_token = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Account
        fields = ('email', 'phone', 'password', 'full_name', 'device_token')

    #check password strength
    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in value):
            raise serializers.ValidationError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError("Password must contain at least one digit")
        return value

    def create(self, validated_data):
        user = Account.objects.create_user(**validated_data)
        
        # Send verification OTP
        otp = OTPCode.generate_code(user, 'registration')
        
        #send only via email
        send_otp_email(user.email, otp.code, 'registration')
        
        return user


# class LoginSerializer(serializers.Serializer):
#     username = serializers.CharField()  # Can be email or phone
#     password = serializers.CharField()
#     device_token = serializers.CharField(required=False, allow_blank=True)

#     def validate(self, attrs):
#         username = attrs.get('username')
#         password = attrs.get('password')
#         device_token = attrs.get('device_token')

#         if username and password:
#             try:
#                 if '@' in username:
#                     user = Account.objects.get(email=username)
#                 else:
#                     user = Account.objects.get(phone=username)
                
#                 # Check if account is locked
#                 if user.is_account_locked():
#                     raise serializers.ValidationError('Account is temporarily locked due to too many failed login attempts')
                
#                 # Check if user is verified
#                 if not user.is_verified:
#                     raise serializers.ValidationError('Account is not verified. Please verify your account first.')
                
#                 # Check if user is active (state = 1)
#                 if user.state != 1:
#                     state_names = {0: 'inactive', 1: 'active', 2: 'suspended', 3: 'pending'}
#                     raise serializers.ValidationError(f'User account is {state_names.get(user.state, "unknown")}')
                
#                 # Authenticate password
#                 if not user.check_password(password):
#                     user.increment_failed_login()
#                     raise serializers.ValidationError('Invalid credentials')
                
#                 # Reset failed login attempts on successful credential validation
#                 if user.failed_login_attempts > 0:
#                     user.unlock_account()
                
#                 # Update device token if provided
#                 if device_token:
#                     user.device_token = device_token
#                     user.save(update_fields=['device_token', 'updated_at'])
                
#                 # Generate and send OTP for login
#                 otp = OTPCode.generate_code(user, 'login')

#                 #send only via email
#                 send_otp_email(user.email, otp.code, 'login')
                
#                 attrs['user'] = user
#                 attrs['credentials_valid'] = True
#                 return attrs
            
#             except Account.DoesNotExist:
#                 raise serializers.ValidationError('Invalid credentials')
#         else:
#             raise serializers.ValidationError('Must include username and password')


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()  # Can be email or phone
    password = serializers.CharField()
    device_token = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')
        device_token = attrs.get('device_token')

        if username and password:
            try:
                if '@' in username:
                    user = Account.objects.get(email=username)
                else:
                    user = Account.objects.get(phone=username)
                
                # Check if account is locked
                if user.is_account_locked():
                    raise serializers.ValidationError('Account is temporarily locked due to too many failed login attempts')
                
                # Check if user is verified
                if not user.is_verified:
                    raise serializers.ValidationError('Account is not verified. Please verify your account first.')
                
                # Check if user is active (state = 1)
                if user.state != 1:
                    state_names = {0: 'inactive', 1: 'active', 2: 'suspended', 3: 'pending'}
                    raise serializers.ValidationError(f'User account is {state_names.get(user.state, "unknown")}')
                
                # Authenticate password
                if not user.check_password(password):
                    user.increment_failed_login()
                    raise serializers.ValidationError('Invalid credentials')
                
                # Reset failed login attempts on successful credential validation
                if user.failed_login_attempts > 0:
                    user.unlock_account()
                
                # Update device token if provided
                if device_token:
                    user.device_token = device_token
                    user.save(update_fields=['device_token', 'updated_at'])
                
                # No OTP generation for login - direct authentication
                attrs['user'] = user
                attrs['authenticated'] = True
                return attrs
            
            except Account.DoesNotExist:
                raise serializers.ValidationError('Invalid credentials')
        else:
            raise serializers.ValidationError('Must include username and password')


class VerifyOTPSerializer(serializers.Serializer):
    acc_id = serializers.CharField()
    otp_code = serializers.CharField(max_length=6)

    def validate(self, attrs):
        acc_id = attrs.get('acc_id')
        otp_code = attrs.get('otp_code')

        try:
            user = Account.objects.get(acc_id=acc_id)
            
            otp = OTPCode.objects.filter(user=user, is_used=False).order_by('-created_at').first()
            if not otp:
                raise serializers.ValidationError('No valid OTP found for this account')

            if not otp.is_valid():
                raise serializers.ValidationError('OTP code is expired or invalid')

            if otp.code != otp_code:
                otp.attempts += 1
                otp.save()
                remaining_attempts = 3 - otp.attempts
                if remaining_attempts > 0:
                    raise serializers.ValidationError(f'Invalid OTP code. {remaining_attempts} attempts remaining.')
                else:
                    raise serializers.ValidationError('Invalid OTP code. No attempts remaining.')

            otp.is_used = True
            otp.save()

            attrs['user'] = user
            attrs['otp'] = otp
            attrs['otp_verified'] = True
            return attrs

        except Account.DoesNotExist:
            raise serializers.ValidationError('Invalid account ID')



# class ResendOTPSerializer(serializers.Serializer):
#     acc_id = serializers.CharField()

#     def validate(self, attrs):
#         acc_id = attrs.get('acc_id')

#         try:
#             user = Account.objects.get(acc_id=acc_id)

#             # Infer purpose
#             if not user.is_verified:
#                 purpose = 'registration'
#             else:
#                 purpose = 'login'

#             attrs['user'] = user
#             attrs['purpose'] = purpose
#             return attrs

#         except Account.DoesNotExist:
#             raise serializers.ValidationError('Invalid account ID')

class ResendOTPSerializer(serializers.Serializer):
    acc_id = serializers.CharField()

    def validate(self, attrs):
        acc_id = attrs.get('acc_id')

        try:
            user = Account.objects.get(acc_id=acc_id)

            # Only allow OTP resend for unverified accounts (registration purpose)
            if not user.is_verified:
                purpose = 'registration'
            else:
                raise serializers.ValidationError('Account is already verified. OTP resend not needed.')

            attrs['user'] = user
            attrs['purpose'] = purpose
            return attrs

        except Account.DoesNotExist:
            raise serializers.ValidationError('Invalid account ID')


class AccountSerializer(BaseModelSerializer):
    class Meta:
        model = Account
        fields = ('acc_id', 'email', 'phone', 'full_name', 'is_verified', 'state', 
                 'created_at', 'updated_at', 'last_login', 'device_token')
        read_only_fields = ('acc_id', 'created_at', 'updated_at', 'last_login', 'is_verified', 'state')


class PasswordChangeSerializer(serializers.Serializer):
    acc_id = serializers.CharField()
    old_password = serializers.CharField()
    new_password = serializers.CharField(min_length=8)

    #check new password strength
    def validate_new_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in value):
            raise serializers.ValidationError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError("Password must contain at least one digit")
        return value

    def validate(self, attrs):
        acc_id = attrs.get('acc_id')
        old_password = attrs.get('old_password')
        
        try:
            user = Account.objects.get(acc_id=acc_id)
            if not user.check_password(old_password):
                raise serializers.ValidationError("Old password is incorrect")
            
            attrs['user'] = user
            return attrs
            
        except Account.DoesNotExist:
            raise serializers.ValidationError('Invalid account ID')








# password reset serializers
from datetime import timedelta

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        """Validate that the email exists in the system"""
        try:
            user = Account.objects.get(email=value)
            if not user.is_verified:
                raise serializers.ValidationError("Account is not verified. Please verify your account first.")
            if user.state != 1:  # Not active
                raise serializers.ValidationError("Account is not active.")
        except Account.DoesNotExist:
            raise serializers.ValidationError("No account found with this email address.")
        return value

    def save(self):
        """Generate and send OTP for password reset"""
        email = self.validated_data['email']
        user = Account.objects.get(email=email)
        
        # Generate OTP
        otp = OTPCode.generate_code(user, 'password_reset')
        
        # Send OTP via email
        send_otp_email(user.email, otp.code, 'password_reset')
        
        return {
            'acc_id': user.acc_id,
            'email': user.email,
            'message': 'Password reset OTP sent to your email address.'
        }


class PasswordResetVerifyOTPSerializer(serializers.Serializer):
    acc_id = serializers.CharField()
    otp_code = serializers.CharField(max_length=6)

    def validate(self, attrs):
        acc_id = attrs.get('acc_id')
        otp_code = attrs.get('otp_code')

        try:
            user = Account.objects.get(acc_id=acc_id)
            
            # Check if user has a valid password reset OTP
            try:
                otp = OTPCode.objects.get(user=user, purpose='password_reset', is_used=False)
                
                if not otp.is_valid():
                    raise serializers.ValidationError('OTP code is expired or invalid.')
                
                if otp.code != otp_code:
                    otp.attempts += 1
                    otp.save(update_fields=['attempts'])
                    remaining_attempts = 3 - otp.attempts
                    if remaining_attempts > 0:
                        raise serializers.ValidationError(f'Invalid OTP code. {remaining_attempts} attempts remaining.')
                    else:
                        otp.is_used = True  # Mark as used after max attempts
                        otp.save(update_fields=['is_used'])
                        raise serializers.ValidationError('Invalid OTP code. No attempts remaining.')
                
                # Mark OTP as used
                otp.is_used = True
                otp.save(update_fields=['is_used'])
                
                attrs['user'] = user
                attrs['otp_verified'] = True
                return attrs
                
            except OTPCode.DoesNotExist:
                raise serializers.ValidationError('No valid password reset OTP found for this account.')
                
        except Account.DoesNotExist:
            raise serializers.ValidationError('Invalid account ID.')


class PasswordResetConfirmSerializer(serializers.Serializer):
    acc_id = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)
    confirm_password = serializers.CharField(min_length=8, write_only=True)

    def validate_new_password(self, value):
      
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        if not any(c.islower() for c in value):
            raise serializers.ValidationError("Password must contain at least one lowercase letter.")
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError("Password must contain at least one digit.")
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in value):
            raise serializers.ValidationError("Password must contain at least one special character.")
        return value

    def validate(self, attrs):
        acc_id = attrs.get('acc_id')
        new_password = attrs.get('new_password')
        confirm_password = attrs.get('confirm_password')

        if new_password != confirm_password:
            raise serializers.ValidationError("Passwords do not match.")

        try:
            user = Account.objects.get(acc_id=acc_id)
            
            # Check if user has recently verified a password reset OTP
            # We'll check if there's a used password reset OTP within the last 10 minutes
            recent_otp = OTPCode.objects.filter(
                user=user, 
                purpose='password_reset', 
                is_used=True,
                created_at__gte=timezone.now() - timedelta(minutes=10)
            ).order_by('-created_at').first()
            
            if not recent_otp:
                raise serializers.ValidationError('No verified password reset session found. Please request a new password reset.')
            
            # Check if user is trying to use the same password
            if user.check_password(new_password):
                raise serializers.ValidationError('New password cannot be the same as your current password.')
            
            attrs['user'] = user
            return attrs
            
        except Account.DoesNotExist:
            raise serializers.ValidationError('Invalid account ID.')
        



