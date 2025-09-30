import requests
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)


#collect client IP address from request
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


#collect device information from request
def get_device_info(request):
    return {
        'ip_address': get_client_ip(request),
        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
        'device_token': request.data.get('device_token', ''),
    }


# Function to send OTP via email
def send_otp_email(email, otp_code, purpose):
    try:
        subject_map = {
            'login': 'Your Login OTP Code',
            'registration': 'Welcome to Petropal, Please Verify Your Account',
            'password_reset': 'Password Reset OTP Code',
        }
        
        subject = subject_map.get(purpose, 'Your OTP Code')
        
        html_message = render_to_string('email/otp_email.html', {
            'otp_code': otp_code,
            'purpose': purpose,
            'app_name': getattr(settings, 'APP_NAME', 'Petropal')
        })
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"OTP email sent to {email} for purpose: {purpose}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send OTP email to {email}: {str(e)}")
        return False


# Function to send OTP via SMS
def send_otp_sms(phone, otp_code):
    try:
        # Example using Twilio
        # from twilio.rest import Client
        
        # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # message = client.messages.create(
        #     body=f"Your OTP code is: {otp_code}. Valid for 10 minutes.",
        #     from_=settings.TWILIO_PHONE_NUMBER,
        #     to=phone
        # )
        
        # For now, we'll just log the OTP (replace with actual SMS service)
        logger.info(f"SMS OTP sent to {phone}: {otp_code}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send SMS to {phone}: {str(e)}")
        return False


# Function to send security alert email
def send_security_alert(user, event_type, details):
    try:
        subject = f"Security Alert - {event_type}"
        
        html_message = render_to_string('email/security_alert.html', {
            'user': user,
            'event_type': event_type,
            'details': details,
            'app_name': getattr(settings, 'APP_NAME', 'Petropal')
        })
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Security alert sent to {user.email} for event: {event_type}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send security alert to {user.email}: {str(e)}")
        return False