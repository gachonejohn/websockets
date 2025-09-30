from django.db import models, transaction
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
import uuid
import hashlib
import random
import string
from datetime import timedelta


def hash_uuid():
    random_uuid = uuid.uuid4()
    return hashlib.sha256(str(random_uuid).encode()).hexdigest()


class AccountManager(BaseUserManager):
    def get_by_natural_key(self, email):
        email = self.normalize_email(email)
        return self.get(email=email)

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('state', 1)  # Active state
        extra_fields.setdefault('is_verified', True)  # Superuser is verified by default

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        return self.create_user(email, password, **extra_fields)


class Account(AbstractUser):
    STATE_CHOICES = [
        (0, 'Inactive'),
        (1, 'Active'),
        (2, 'Suspended'),
        (3, 'Pending'),
    ]

    acc_id = models.CharField(primary_key=True, max_length=64, unique=True, editable=False)
    action_state_code = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    email = models.EmailField(_('email address'), unique=True)
    password = models.CharField(max_length=128)
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    phone = models.CharField(validators=[phone_regex], max_length=17, unique=True, null=True, blank=True)
    state = models.IntegerField(choices=STATE_CHOICES, default=3)  # 3 = Pending (unverified)
    system_state_code = models.CharField(max_length=255, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_verified = models.BooleanField(default=False)
    full_name = models.CharField(max_length=255, blank=True, null=True)
    device_token = models.CharField(max_length=255, null=True, blank=True)
    google_auth_data = models.JSONField(null=True, blank=True)
    
    # Authentication fields
    failed_login_attempts = models.IntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)
    
    # Security fields
    password_changed_at = models.DateTimeField(auto_now_add=True)
    force_password_change = models.BooleanField(default=False)

    # Remove default Django fields we don't need
    username = None
    first_name = None
    last_name = None

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = AccountManager()

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        if not self.acc_id:
            self.acc_id = hash_uuid()
        super().save(*args, **kwargs)

    def is_account_locked(self):
        if self.account_locked_until:
            return timezone.now() < self.account_locked_until
        return False

    def lock_account(self, duration_minutes=30):
        self.account_locked_until = timezone.now() + timedelta(minutes=duration_minutes)
        self.save(update_fields=['account_locked_until'])

    def unlock_account(self):
        self.failed_login_attempts = 0
        self.account_locked_until = None
        self.save(update_fields=['failed_login_attempts', 'account_locked_until'])

    def increment_failed_login(self):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:  # Lock after 5 failed attempts
            self.lock_account()
        self.save(update_fields=['failed_login_attempts'])
    # verify account and set state to active
    def verify_account(self):
        self.is_verified = True
        self.state = 1  # Active
        self.save(update_fields=['is_verified', 'state'])

    class Meta:
        db_table = 'account'



class OTPCode(models.Model):
    OTP_PURPOSES = [
        ('login', 'Login'),
        ('registration', 'Registration Verification'),
        ('password_reset', 'Password Reset'),
    ]

    user = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='otp_codes')
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=OTP_PURPOSES)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)

    class Meta:
        db_table = 'otp_code'
        indexes = [
            models.Index(fields=['user', 'purpose', 'is_used']),
        ]

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def is_valid(self):
        return not self.is_used and not self.is_expired() and self.attempts < 3

    # marking existing unused OTPs as used before generating a new one
    @classmethod
    def generate_code(cls, user, purpose):
        with transaction.atomic():
            # Mark existing unused OTPs for this purpose as used
            cls.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)

            # Generate a new 6-digit numeric OTP
            code = ''.join(random.choices(string.digits, k=6))

            return cls.objects.create(
                user=user,
                code=code,
                purpose=purpose
            )

    # Verifying the OTP code
    @classmethod
    def verify_code(cls, user, code_input, purpose):
        try:
            otp = cls.objects.get(user=user, code=code_input, purpose=purpose, is_used=False)

            if not otp.is_valid():
                return False, "OTP is expired or exceeded attempt limit."

            # Mark as used
            otp.is_used = True
            otp.save(update_fields=['is_used'])

            return True, "OTP verified successfully."

        except cls.DoesNotExist:
            return False, "Invalid OTP."


# verification badges
class Badge(models.Model):
    badge_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)  # e.g. "Top Seller, standard, gold, platinum"
    icon = models.ImageField(upload_to='badges/')  

    def __str__(self):
        return self.name

    def image_url(self):
        if self.icon:
            return self.icon.url
        return ""


class RefreshToken(models.Model):
    user = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='refresh_tokens')
    token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_revoked = models.BooleanField(default=False)
    device_info = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'refresh_token'

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)  # 7 days expiry
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def is_valid(self):
        return not self.is_revoked and not self.is_expired()

    # Create a new refresh token for a user
    @classmethod
    def create_token(cls, user, device_info=None):
        token = hash_uuid()
        return cls.objects.create(
            user=user,
            token=token,
            device_info=device_info or {}
        )



