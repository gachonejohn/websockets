from django.db import models
from django.contrib.auth import get_user_model
import uuid
from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import Badge
import pytz

Account = get_user_model()

class UserProfile(models.Model):
    user = models.OneToOneField(Account, on_delete=models.CASCADE, related_name='profile')
    profile_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    # company_logo_url = models.URLField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    background_picture = models.ImageField(upload_to='background_pictures/', blank=True, null=True)
    about_bio = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    interest = models.JSONField(default=list, blank=True)
    language_preference = models.CharField(max_length=10, default='en')
    is_omc = models.BooleanField(default=False)
    # verification_badge = models.CharField(max_length=50, blank=True, null=True)
    badge = models.ForeignKey(Badge, on_delete=models.SET_NULL, null=True, blank=True)
    verification_documents = models.JSONField(default=list, blank=True)
    timezone = models.CharField(max_length=50, choices=[(tz, tz) for tz in pytz.common_timezones], default='UTC', help_text="User's preferred timezone" )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_profiles'

    @property
    def user_timezone(self):
        """Get user's timezone object"""
        return pytz.timezone(self.timezone)     



# auto create UserProfile when Account is created
@receiver(post_save, sender=Account)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                'language_preference': 'en',
                'is_omc': False,
            }
        )

@receiver(post_save, sender=Account)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()

class Follow(models.Model):
    follow_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    follower = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='following')
    following = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'connections_follows'
        unique_together = ('follower', 'following')

class Rating(models.Model):
    rating_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rater = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='given_ratings')
    rated = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='received_ratings')
    rating_count = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    review_content = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=[('active', 'Active'), ('hidden', 'Hidden')], default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # track updates

    class Meta:
        db_table = 'ratings'
        unique_together = ('rater', 'rated')  # only 1 rating per user







