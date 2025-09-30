from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

Account = get_user_model()


# allow authentication using either email or phone number
class EmailPhoneAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get('email')
        
        try:
            # Try email first
            if '@' in username:
                user = Account.objects.get(email=username, state=1)  # Only active users
            else:
                # Try phone
                user = Account.objects.get(phone=username, state=1)  # Only active users
            
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        except Account.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return Account.objects.get(pk=user_id, state=1)  # Only active users
        except Account.DoesNotExist:
            return None