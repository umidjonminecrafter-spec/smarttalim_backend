from django.contrib import admin
from organizations.models import Organization, Tariff, Subscription

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'subdomain', 'created_at')
    search_fields = ('name', 'subdomain')
    list_display_links = ('id', 'name')
    list_per_page = 50

@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price', 'old_price', 'months', 'discount_badge')
    search_fields = ('name',)
    list_display_links = ('id', 'name')
    list_per_page = 50

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'tariff', 'start_date', 'end_date', 'is_active', 'balance')
    list_filter = ('is_active', 'start_date', 'end_date')
    list_display_links = ('id', 'organization')
    list_per_page = 50