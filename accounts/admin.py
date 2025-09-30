from django.contrib import admin
from .models import OTPCode, Account

@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'purpose', 'created_at', 'expires_at', 'is_used', 'attempts')
    list_filter = ('purpose', 'is_used', 'created_at')
    search_fields = ('user__email', 'code')


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('email', 'is_verified', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_verified', 'is_active', 'created_at')
    search_fields = ('email', 'phone')
    readonly_fields = ('acc_id',)

   


