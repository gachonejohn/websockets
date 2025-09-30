from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from .utils import send_otp_email, send_otp_sms, send_security_alert


@shared_task
def send_otp_email_task(email, otp_code, purpose):
    return send_otp_email(email, otp_code, purpose)


@shared_task
def send_otp_sms_task(phone, otp_code):
    return send_otp_sms(phone, otp_code)


@shared_task
def send_security_alert_task(user_id, event_type, details):
    from .models import Account
    try:
        user = Account.objects.get(acc_id=user_id)
        return send_security_alert(user, event_type, details)
    except Account.DoesNotExist:
        return False


@shared_task
def cleanup_expired_tokens():
    from django.utils import timezone
    from .models import OTPCode, RefreshToken
    
    # Clean up expired OTP codes
    expired_otps = OTPCode.objects.filter(expires_at__lt=timezone.now())
    otp_count = expired_otps.count()
    expired_otps.delete()
    
    # Clean up expired refresh tokens
    expired_tokens = RefreshToken.objects.filter(expires_at__lt=timezone.now())
    token_count = expired_tokens.count()
    expired_tokens.delete()
    
    return f'Cleaned up {otp_count} OTP codes and {token_count} refresh tokens'