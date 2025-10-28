from collections import defaultdict

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import User, Group
from django.db import models
from django.forms import Textarea
# Modeltranslation will automatically add language fields to admin
from .models import Category, Listing, Event, Promotion, Blog, EventJoin, Wishlist, UserProfile, UserPermission, HelpSupport, CollaborationContact, GuestUser, VerificationCode


class GroupedAdminSite(admin.AdminSite):
    site_header = "GoGevgelija Admin"
    site_title = "GoGevgelija Admin"
    index_title = "Management"

    model_groups = {
        "MAIN": [Listing, Blog, Event, Promotion, Category],
        "USERS": [User, Group, GuestUser, UserPermission, UserProfile, VerificationCode],
        "INTERACTIONS": [Wishlist, HelpSupport, CollaborationContact, EventJoin],
    }

    def get_app_list(self, request):
        original = super().get_app_list(request)

        model_lookup = {}
        for app in original:
            for model in app["models"]:
                key = (app["app_label"], model["object_name"])
                entry = model.copy()
                entry["_app_name"] = app["name"]
                entry["_app_label"] = app["app_label"]
                entry["_app_url"] = app["app_url"]
                entry["_has_module_perms"] = app["has_module_perms"]
                model_lookup[key] = entry

        grouped_apps = []
        used_keys = set()

        for group_name, model_classes in self.model_groups.items():
            grouped_models = []
            for model_class in model_classes:
                key = (model_class._meta.app_label, model_class.__name__)
                entry = model_lookup.get(key)
                if not entry:
                    continue
                grouped_models.append({
                    "name": entry["name"],
                    "object_name": entry["object_name"],
                    "admin_url": entry["admin_url"],
                    "add_url": entry.get("add_url"),
                    "perms": entry["perms"],
                    "view_only": entry.get("view_only", False),
                })
                used_keys.add(key)

            if grouped_models:
                grouped_apps.append({
                    "name": group_name,
                    "app_label": group_name.lower(),
                    "app_url": "",
                    "has_module_perms": True,
                    "models": grouped_models,
                })

        remaining_apps = defaultdict(lambda: {
            "name": "Other",
            "app_label": "other",
            "app_url": "",
            "has_module_perms": True,
            "models": [],
        })

        for app in original:
            for model in app["models"]:
                key = (app["app_label"], model["object_name"])
                if key in used_keys:
                    continue
                app_entry = remaining_apps[app["name"]]
                app_entry.update({
                    "name": app["name"],
                    "app_label": app["app_label"],
                    "app_url": app["app_url"],
                    "has_module_perms": app["has_module_perms"],
                })
                app_entry["models"].append(model)

        grouped_apps.extend(entry for entry in remaining_apps.values() if entry["models"])
        return grouped_apps


admin_site = GroupedAdminSite()
admin.site = admin_site
admin_site.register(User, UserAdmin)
admin_site.register(Group, GroupAdmin)

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




@admin.register(Category, site=admin_site)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'parent', 'level', 'order', 'icon', 'applies_to', 'is_active', 'trending', 'featured', 'item_count_display')
    list_filter = ('is_active', 'trending', 'featured', 'applies_to', 'level', 'parent', 'show_in_search', 'show_in_navigation')
    search_fields = ('name', 'name_en', 'name_mk', 'slug', 'icon')
    list_editable = ('order', 'is_active', 'trending', 'featured')
    ordering = ('level', 'order', 'name')

    # Note: modeltranslation will auto-generate name_en field, so we can prepopulate from it
    # But we need to be careful since it might not exist yet during initial setup
    # prepopulated_fields = {'slug': ('name_en',)}

    fieldsets = (
        ('Basic Information', {
            'fields': ('name_en', 'name_mk', 'name', 'icon', 'image', 'color', 'slug'),
            'classes': ('wide',),
            'description': 'Name fields: English (en), Macedonian (mk), and fallback name.',
        }),
        ('Description', {
            'fields': ('description_en', 'description_mk', 'description'),
            'classes': ('wide',),
            'description': 'Description fields: English (en), Macedonian (mk), and fallback description.',
        }),
        ('Hierarchy', {
            'fields': ('parent', 'level', 'order'),
            'classes': ('wide',),
            'description': 'Parent category and display order. Level is auto-calculated.',
        }),
        ('Visibility Settings', {
            'fields': (
                'is_active',
                'show_in_search',
                'show_in_navigation',
                'trending',
                'featured',
            ),
            'classes': ('wide',),
        }),
        ('Scope', {
            'fields': ('applies_to', 'show_in_events'),
            'classes': ('wide',),
            'description': 'Determines where this category can be used. "show_in_events" is kept for backward compatibility.',
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('level', 'created_at', 'updated_at')

    def item_count_display(self, obj):
        """Display the item count"""
        count = obj.item_count
        return f"{count} items" if count != 1 else "1 item"
    item_count_display.short_description = 'Items'

    def get_queryset(self, request):
        """Optimize queries with select_related"""
        return super().get_queryset(request).select_related('parent')

    actions = ['make_active', 'make_inactive', 'make_featured', 'remove_featured']

    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} categories activated.')
    make_active.short_description = '✅ Activate selected categories'

    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} categories deactivated.')
    make_inactive.short_description = '❌ Deactivate selected categories'

    def make_featured(self, request, queryset):
        updated = queryset.update(featured=True)
        self.message_user(request, f'{updated} categories marked as featured.')
    make_featured.short_description = '⭐ Mark as featured'

    def remove_featured(self, request, queryset):
        updated = queryset.update(featured=False)
        self.message_user(request, f'{updated} categories unmarked as featured.')
    remove_featured.short_description = '⚪ Remove featured status'

@admin.register(Listing, site=admin_site)
class ListingAdmin(MultilingualAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'category', 'featured', 'is_active', 'created_at', 'phone_number')
    list_filter = ('category', 'featured', 'is_active', 'created_at')
    search_fields = ('title', 'address', 'category__name')
    list_editable = ('featured', 'is_active')
    ordering = ('-created_at',)
    filter_horizontal = ('promotions',)

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'category',
                'featured',
                'is_active',
                'image', 'image_1', 'image_2', 'image_3', 'image_4', 'image_5',
                'phone_number',
                'website_url',
                'facebook_url',
                'instagram_url'
            ),
            'classes': ('wide',),
        }),
        ('Promotions', {
            'fields': ('promotions',),
            'classes': ('wide',),
            'description': 'Select promotions associated with this listing (optional)',
        }),
        ('English Content', {
            'fields': ('title', 'description', 'address', 'open_time', 'tags', 'amenities_title', 'amenities', 'working_hours', 'show_open_status', 'manual_open_status'),
            'classes': ('lang-tab', 'lang-en'),
        }),
        ('Macedonian Content', {
            'fields': ('title_mk', 'description_mk', 'address_mk', 'open_time_mk', 'tags_mk', 'amenities_title_mk', 'amenities_mk', 'working_hours_mk'),
            'classes': ('lang-tab', 'lang-mk'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

@admin.register(Event, site=admin_site)
class EventAdmin(MultilingualAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'date_time', 'location', 'category', 'featured', 'is_active', 'show_join_button', 'join_count', 'created_at')
    list_filter = ('category', 'featured', 'is_active', 'show_join_button', 'created_at')
    search_fields = ('title', 'location', 'description', 'category')
    list_editable = ('featured', 'is_active', 'show_join_button')
    ordering = ('-created_at',)
    filter_horizontal = ('listings',)

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'category',
                'featured',
                'is_active',
                'show_join_button',
                'date_time',
                'image', 'image_1', 'image_2', 'image_3', 'image_4', 'image_5',
                'join_count'
            ),
            'classes': ('wide',),
        }),
        ('Listings', {
            'fields': ('listings',),
            'classes': ('wide',),
            'description': 'Select listings associated with this event (optional)',
        }),
        ('Contact Information', {
            'fields': (
                'phone_number',
                'website_url',
                'facebook_url',
                'instagram_url'
            ),
            'classes': ('wide',),
            'description': 'Contact details (shown when Join button is disabled)',
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

@admin.register(Promotion, site=admin_site)
class PromotionAdmin(MultilingualAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'discount_code', 'valid_until', 'featured', 'is_active', 'created_at')
    list_filter = ('featured', 'is_active', 'has_discount_code', 'valid_until', 'created_at')
    search_fields = ('title', 'discount_code', 'description')
    list_editable = ('featured', 'is_active')
    ordering = ('-created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'featured',
                'is_active',
                'image', 'image_1', 'image_2', 'image_3', 'image_4', 'image_5',
                'valid_until',
                'has_discount_code',
                'discount_code',
                'website',
                'phone_number',
                'facebook_url',
                'instagram_url',
                'address'
            ),
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

@admin.register(Blog, site=admin_site)
class BlogAdmin(MultilingualAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'read_time_minutes', 'featured', 'published', 'is_active', 'created_at')
    list_filter = ('category', 'featured', 'published', 'is_active', 'created_at')
    search_fields = ('title', 'subtitle', 'content', 'author', 'category')
    list_editable = ('featured', 'published', 'is_active')
    ordering = ('-created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'category',
                'featured',
                'published',
                'is_active',
                'image', 'image_1', 'image_2', 'image_3', 'image_4', 'image_5',
                'read_time_minutes',
                'tags'
            ),
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

@admin.register(EventJoin, site=admin_site)
class EventJoinAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'created_at')
    list_filter = ('created_at', 'event')
    search_fields = ('user__username', 'user__email', 'event__title')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

@admin.register(Wishlist, site=admin_site)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ('user', 'content_type', 'content_object', 'item_type', 'created_at')
    list_filter = ('content_type', 'created_at')
    search_fields = ('user__username', 'user__email')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

@admin.register(VerificationCode, site=admin_site)
class VerificationCodeAdmin(admin.ModelAdmin):
    list_display = ('email', 'code', 'is_used', 'created_at', 'expires_at')
    list_filter = ('is_used', 'created_at', 'expires_at')
    search_fields = ('email', 'code')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

@admin.register(GuestUser, site=admin_site)
class GuestUserAdmin(admin.ModelAdmin):
    list_display = ('guest_id', 'language_preference', 'created_at', 'last_active')
    list_filter = ('language_preference', 'created_at', 'last_active')
    search_fields = ('guest_id',)
    ordering = ('-last_active',)
    readonly_fields = ('guest_id', 'created_at', 'last_active')

@admin.register(UserProfile, site=admin_site)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'language_preference', 'created_at', 'updated_at')
    list_filter = ('language_preference', 'created_at')
    search_fields = ('user__username', 'user__email')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(UserPermission, site=admin_site)
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


@admin.register(HelpSupport, site=admin_site)
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


@admin.register(CollaborationContact, site=admin_site)
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
