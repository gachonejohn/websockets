from rest_framework import serializers
from django.utils import timezone
import pytz


class BaseModelSerializer(serializers.ModelSerializer):
    """
    Base serializer that automatically converts all DateTimeFields 
    to the authenticated user's timezone.
    """

    def to_representation(self, instance):
        """Convert all datetime fields to user's timezone"""
        data = super().to_representation(instance)

        # Get user from request context
        request = self.context.get('request')
        if not (request and hasattr(request, 'user') and request.user.is_authenticated):
            return data

        user_tz = getattr(request.user, 'timezone', 'UTC')
        try:
            user_timezone = pytz.timezone(user_tz)
        except pytz.UnknownTimeZoneError:
            user_timezone = pytz.UTC

        # Convert all DateTimeFields
        for field_name, field in self.fields.items():
            if isinstance(field, serializers.DateTimeField) and field_name in data:
                if data[field_name]:
                    try:
                        dt = timezone.datetime.fromisoformat(data[field_name].replace('Z', '+00:00'))
                        if timezone.is_naive(dt):
                            dt = timezone.make_aware(dt, timezone.utc)

                        user_dt = dt.astimezone(user_timezone)
                        data[field_name] = user_dt.strftime('%Y-%m-%d %H:%M:%S')
                    except (ValueError, TypeError):
                        pass  # Keep original value if conversion fails

        return data
