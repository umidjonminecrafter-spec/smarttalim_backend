from django.contrib import admin
from crm.models import Pipeline, Source, LostReason, Section, LeadForm, Lead

@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'order', 'organization')
    search_fields = ('name',)
    list_per_page = 50

@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'organization')
    search_fields = ('name',)
    list_per_page = 50

@admin.register(LostReason)
class LostReasonAdmin(admin.ModelAdmin):
    list_display = ('id', 'reason', 'organization')
    search_fields = ('reason',)
    list_per_page = 50

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'organization')
    search_fields = ('name',)
    list_per_page = 50

@admin.register(LeadForm)
class LeadFormAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'organization')
    search_fields = ('name',)
    list_per_page = 50

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'status', 'pipeline', 'source', 'organization')
    list_filter = ('status', 'pipeline', 'source', 'is_archived')
    search_fields = ('name', 'phone', 'email')
    list_per_page = 50