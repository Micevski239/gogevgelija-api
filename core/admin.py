from django.contrib import admin
from django.db import models
from django.forms import Textarea
# from modeltranslation.admin import TranslationAdmin
from .models import Category, Listing, Event, Promotion, Blog, EventJoin, Wishlist, UserProfile, UserPermission, HelpSupport, CollaborationContact, GuestUser

class MultilingualAdminMixin:
    """Mixin for multilingual admin interfaces with tabbed layout"""
    
    class Media:
        css = {
            'all': ('admin/css/multilang.css',)
        }
        js = ('admin/js/multilang.js',)
    
    formfield_overrides = {
        models.TextField: {'widget': Textarea(attrs={'rows': 4, 'cols': 80})},
        models.JSONField: {'widget': Textarea(attrs={'rows': 6, 'cols': 80})},
    }
    
    def copy_en_to_mk(self, request, queryset):
        """Copy English content to Macedonian fields"""
        updated = 0
        for obj in queryset:
            # Copy title fields
            if hasattr(obj, 'title') and hasattr(obj, 'title_mk'):
                if obj.title and not obj.title_mk:
                    obj.title_mk = obj.title
                    updated += 1
            
            # Copy description fields  
            if hasattr(obj, 'description') and hasattr(obj, 'description_mk'):
                if obj.description and not obj.description_mk:
                    obj.description_mk = obj.description
                    updated += 1
            
            # Copy location fields (for Events)
            if hasattr(obj, 'location') and hasattr(obj, 'location_mk'):
                if obj.location and not obj.location_mk:
                    obj.location_mk = obj.location
                    updated += 1
            
            # Copy other fields as needed
            if hasattr(obj, 'subtitle') and hasattr(obj, 'subtitle_mk'):
                if obj.subtitle and not obj.subtitle_mk:
                    obj.subtitle_mk = obj.subtitle
                    updated += 1
            
            obj.save()
        
        self.message_user(request, f'{updated} fields copied from English to Macedonian.')
    
    copy_en_to_mk.short_description = "📝 Copy English → Macedonian (empty fields only)"
    
    def clear_mk_content(self, request, queryset):
        """Clear all Macedonian content"""
        updated = 0
        for obj in queryset:
            fields_to_clear = [f for f in obj._meta.fields if f.name.endswith('_mk')]
            for field in fields_to_clear:
                if getattr(obj, field.name):
                    setattr(obj, field.name, '' if field.get_internal_type() == 'TextField' else None)
                    updated += 1
            obj.save()
        
        self.message_user(request, f'{updated} Macedonian fields cleared.')
    
    clear_mk_content.short_description = "🗑️ Clear all Macedonian content"
    
    actions = ['copy_en_to_mk', 'clear_mk_content']




@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'trending', 'show_in_events', 'created_at')
    list_filter = ('trending', 'show_in_events', 'created_at')
    search_fields = ('name', 'icon')
    list_editable = ('trending', 'show_in_events')
    ordering = ('name',)

@admin.register(Listing)
class ListingAdmin(MultilingualAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'category', 'featured', 'created_at', 'phone_number')
    list_filter = ('category', 'featured', 'created_at')
    search_fields = ('title', 'address', 'category__name')
    list_editable = ('featured',)
    ordering = ('-created_at',)
    filter_horizontal = ('promotions',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('category', 'featured', 'image', 'phone_number', 'website_url', 'facebook_url', 'instagram_url'),
            'classes': ('wide',),
        }),
        ('Promotions', {
            'fields': ('promotions',),
            'classes': ('wide',),
            'description': 'Select promotions associated with this listing (optional)',
        }),
        ('English Content', {
            'fields': ('title', 'description', 'address', 'open_time', 'tags', 'working_hours'),
            'classes': ('lang-tab', 'lang-en'),
        }),
        ('Macedonian Content', {
            'fields': ('title_mk', 'description_mk', 'address_mk', 'open_time_mk', 'tags_mk', 'working_hours_mk'),
            'classes': ('lang-tab', 'lang-mk'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

@admin.register(Event)
class EventAdmin(MultilingualAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'date_time', 'location', 'category', 'featured', 'join_count', 'created_at')
    list_filter = ('category', 'featured', 'created_at')
    search_fields = ('title', 'location', 'description', 'category')
    list_editable = ('featured',)
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('category', 'featured', 'date_time', 'cover_image', 'join_count'),
            'classes': ('wide',),
        }),
        ('English Content', {
            'fields': ('title', 'description', 'location', 'entry_price', 'age_limit', 'expectations'),
            'classes': ('lang-tab', 'lang-en'),
        }),
        ('Macedonian Content', {
            'fields': ('title_mk', 'description_mk', 'location_mk', 'entry_price_mk', 'age_limit_mk', 'expectations_mk'),
            'classes': ('lang-tab', 'lang-mk'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Promotion)
class PromotionAdmin(MultilingualAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'discount_code', 'valid_until', 'featured', 'created_at')
    list_filter = ('featured', 'has_discount_code', 'valid_until', 'created_at')
    search_fields = ('title', 'discount_code', 'description')
    list_editable = ('featured',)
    ordering = ('-created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('featured', 'image', 'valid_until', 'has_discount_code', 'discount_code', 'website', 'phone_number', 'facebook_url', 'instagram_url', 'address'),
            'classes': ('wide',),
        }),
        ('English Content', {
            'fields': ('title', 'description', 'tags'),
            'classes': ('lang-tab', 'lang-en'),
        }),
        ('Macedonian Content', {
            'fields': ('title_mk', 'description_mk', 'tags_mk'),
            'classes': ('lang-tab', 'lang-mk'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

@admin.register(Blog)
class BlogAdmin(MultilingualAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'read_time_minutes', 'featured', 'published', 'created_at')
    list_filter = ('category', 'featured', 'published', 'created_at')
    search_fields = ('title', 'subtitle', 'content', 'author', 'category')
    list_editable = ('featured', 'published')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('category', 'featured', 'published', 'cover_image', 'read_time_minutes', 'tags'),
            'classes': ('wide',),
        }),
        ('English Content', {
            'fields': ('title', 'subtitle', 'content', 'author'),
            'classes': ('lang-tab', 'lang-en'),
        }),
        ('Macedonian Content', {
            'fields': ('title_mk', 'subtitle_mk', 'content_mk', 'author_mk'),
            'classes': ('lang-tab', 'lang-mk'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')

@admin.register(EventJoin)
class EventJoinAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'created_at')
    list_filter = ('created_at', 'event')
    search_fields = ('user__username', 'user__email', 'event__title')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ('user', 'content_type', 'content_object', 'item_type', 'created_at')
    list_filter = ('content_type', 'created_at')
    search_fields = ('user__username', 'user__email')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

@admin.register(GuestUser)
class GuestUserAdmin(admin.ModelAdmin):
    list_display = ('guest_id', 'language_preference', 'created_at', 'last_active')
    list_filter = ('language_preference', 'created_at', 'last_active')
    search_fields = ('guest_id',)
    ordering = ('-last_active',)
    readonly_fields = ('guest_id', 'created_at', 'last_active')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'language_preference', 'created_at', 'updated_at')
    list_filter = ('language_preference', 'created_at')
    search_fields = ('user__username', 'user__email')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(UserPermission)
class UserPermissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'listing', 'can_edit', 'granted_by', 'created_at')
    list_filter = ('can_edit', 'created_at', 'granted_by')
    search_fields = ('user__username', 'user__email', 'listing__title')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Permission Details', {
            'fields': ('user', 'listing', 'can_edit'),
            'classes': ('wide',),
        }),
        ('Grant Information', {
            'fields': ('granted_by',),
            'classes': ('wide',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # Only set granted_by when creating new permission
            obj.granted_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(HelpSupport)
class HelpSupportAdmin(admin.ModelAdmin):
    list_display = ('subject', 'user', 'category', 'priority', 'status', 'created_at', 'resolved_at')
    list_filter = ('category', 'priority', 'status', 'created_at')
    search_fields = ('subject', 'user__username', 'user__email', 'name', 'email', 'message')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at', 'resolved_at')
    
    fieldsets = (
        ('Request Information', {
            'fields': ('user', 'name', 'email', 'category', 'subject', 'message'),
            'classes': ('wide',),
        }),
        ('Status & Priority', {
            'fields': ('status', 'priority'),
            'classes': ('wide',),
        }),
        ('Admin Response', {
            'fields': ('admin_response', 'responded_by'),
            'classes': ('wide',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'resolved_at'),
            'classes': ('collapse',),
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if obj.admin_response and not obj.responded_by:
            obj.responded_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'responded_by')
    
    actions = ['mark_as_resolved', 'mark_as_in_progress']
    
    def mark_as_resolved(self, request, queryset):
        updated = queryset.update(status='resolved')
        self.message_user(request, f"{updated} help requests marked as resolved.")
    mark_as_resolved.short_description = "Mark selected requests as resolved"
    
    def mark_as_in_progress(self, request, queryset):
        updated = queryset.update(status='in_progress')
        self.message_user(request, f"{updated} help requests marked as in progress.")
    mark_as_in_progress.short_description = "Mark selected requests as in progress"


@admin.register(CollaborationContact)
class CollaborationContactAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'name', 'collaboration_type', 'status', 'created_at', 'review_date')
    list_filter = ('collaboration_type', 'status', 'created_at')
    search_fields = ('company_name', 'name', 'email', 'proposal', 'user__username')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at', 'review_date')
    
    fieldsets = (
        ('Contact Information', {
            'fields': ('user', 'name', 'email', 'phone', 'company_name'),
            'classes': ('wide',),
        }),
        ('Collaboration Details', {
            'fields': ('collaboration_type', 'proposal', 'timeline'),
            'classes': ('wide',),
        }),
        ('Admin Management', {
            'fields': ('status', 'admin_notes', 'reviewed_by'),
            'classes': ('wide',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'review_date'),
            'classes': ('collapse',),
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if obj.admin_notes and not obj.reviewed_by:
            obj.reviewed_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'reviewed_by')
    
    actions = ['mark_as_interested', 'mark_as_reviewing', 'mark_as_scheduled']
    
    def mark_as_interested(self, request, queryset):
        updated = queryset.update(status='interested')
        self.message_user(request, f"{updated} collaboration requests marked as interested.")
    mark_as_interested.short_description = "Mark selected requests as interested"
    
    def mark_as_reviewing(self, request, queryset):
        updated = queryset.update(status='reviewing')
        self.message_user(request, f"{updated} collaboration requests marked as under review.")
    mark_as_reviewing.short_description = "Mark selected requests as under review"
    
    def mark_as_scheduled(self, request, queryset):
        updated = queryset.update(status='scheduled')
        self.message_user(request, f"{updated} collaboration requests marked as meeting scheduled.")
    mark_as_scheduled.short_description = "Mark selected requests as meeting scheduled"
