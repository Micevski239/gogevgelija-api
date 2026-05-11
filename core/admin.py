import json
import os
from collections import defaultdict
from datetime import timedelta
from itertools import chain
from operator import attrgetter

import requests as http_requests

from django.contrib import admin
from django.utils import timezone
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import User, Group
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.forms import Textarea
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
# Modeltranslation will automatically add language fields to admin
from .models import Category, Listing, Event, Promotion, Blog, BlogSection, EventJoin, Wishlist, UserProfile, UserPermission, HelpSupport, CollaborationContact, GuestUser, VerificationCode, HomeSection, HomeSectionItem, TourismCarousel, TourismCategoryButton, GalleryPhoto


class GroupedAdminSite(admin.AdminSite):
    site_header = "GoGevgelija Admin"
    site_title = "GoGevgelija Admin"
    index_title = "Management"

    model_groups = {
        "CONTENT": [Listing, Blog, Event, Promotion, Category],
        "SCREENS": [HomeSection, TourismCarousel, GalleryPhoto],
        "USERS": [User, UserProfile, UserPermission],
        "SUPPORT": [HelpSupport, CollaborationContact],
        "VIEW LOGS": [EventJoin, Wishlist, GuestUser, VerificationCode, Group],
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

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        today = now.date()

        # ── Stat cards ──
        extra_context['stats'] = [
            {
                'label': 'Listings',
                'count': Listing.objects.filter(is_active=True).count(),
                'delta': Listing.objects.filter(created_at__gte=week_ago).count(),
                'icon': 'bi-shop',
                'url': '/admin/core/listing/',
                'add_url': '/admin/core/listing/add/',
            },
            {
                'label': 'Events',
                'count': Event.objects.filter(is_active=True).count(),
                'delta': Event.objects.filter(created_at__gte=week_ago).count(),
                'icon': 'bi-calendar-event',
                'url': '/admin/core/event/',
                'add_url': '/admin/core/event/add/',
            },
            {
                'label': 'Promotions',
                'count': Promotion.objects.filter(is_active=True).count(),
                'delta': Promotion.objects.filter(created_at__gte=week_ago).count(),
                'icon': 'bi-tag',
                'url': '/admin/core/promotion/',
                'add_url': '/admin/core/promotion/add/',
            },
            {
                'label': 'Blogs',
                'count': Blog.objects.filter(is_active=True).count(),
                'delta': Blog.objects.filter(created_at__gte=week_ago).count(),
                'icon': 'bi-newspaper',
                'url': '/admin/core/blog/',
                'add_url': '/admin/core/blog/add/',
            },
            {
                'label': 'Users',
                'count': User.objects.count(),
                'delta': User.objects.filter(date_joined__gte=week_ago).count(),
                'icon': 'bi-people',
                'url': '/admin/auth/user/',
                'add_url': '/admin/auth/user/add/',
            },
        ]

        # ── Needs attention ──
        attention = []
        open_tickets = HelpSupport.objects.filter(status__in=['open', 'in_progress']).count()
        if open_tickets:
            attention.append({
                'text': f'{open_tickets} open support ticket{"s" if open_tickets != 1 else ""}',
                'icon': 'bi-exclamation-triangle',
                'color': '#dc2626',
                'url': '/admin/core/helpsupport/?status__exact=open',
            })
        new_collabs = CollaborationContact.objects.filter(status='new').count()
        if new_collabs:
            attention.append({
                'text': f'{new_collabs} new collaboration request{"s" if new_collabs != 1 else ""}',
                'icon': 'bi-handshake',
                'color': '#d97706',
                'url': '/admin/core/collaborationcontact/?status__exact=new',
            })
        expiring = Promotion.objects.filter(
            valid_until__range=[today, today + timedelta(days=7)],
            is_active=True,
        ).count()
        if expiring:
            attention.append({
                'text': f'{expiring} promotion{"s" if expiring != 1 else ""} expiring within 7 days',
                'icon': 'bi-clock',
                'color': '#ea580c',
                'url': '/admin/core/promotion/',
            })
        extra_context['attention'] = attention

        # ── Quick actions ──
        extra_context['quick_actions'] = [
            {'label': 'Add Event', 'url': '/admin/core/event/add/', 'icon': 'bi-calendar-plus'},
            {'label': 'Add Listing', 'url': '/admin/core/listing/add/', 'icon': 'bi-shop-window'},
            {'label': 'Add Promotion', 'url': '/admin/core/promotion/add/', 'icon': 'bi-megaphone'},
            {'label': 'Write Blog', 'url': '/admin/core/blog/add/', 'icon': 'bi-pencil-square'},
        ]

        # ── Recent content (last 8 across types) ──
        recent_events = Event.objects.order_by('-created_at')[:4]
        recent_listings = Listing.objects.order_by('-created_at')[:4]
        recent_promos = Promotion.objects.order_by('-created_at')[:4]

        combined = []
        for item in recent_events:
            combined.append({'title': item.title, 'type': 'Event', 'date': item.created_at,
                             'url': f'/admin/core/event/{item.pk}/change/', 'color': '#b91c1c'})
        for item in recent_listings:
            combined.append({'title': item.title, 'type': 'Listing', 'date': item.created_at,
                             'url': f'/admin/core/listing/{item.pk}/change/', 'color': '#2563eb'})
        for item in recent_promos:
            combined.append({'title': item.title, 'type': 'Promotion', 'date': item.created_at,
                             'url': f'/admin/core/promotion/{item.pk}/change/', 'color': '#059669'})
        combined.sort(key=lambda x: x['date'], reverse=True)
        extra_context['recent_content'] = combined[:8]

        # ── Engagement ──
        extra_context['engagement'] = {
            'event_joins': EventJoin.objects.count(),
            'wishlists': Wishlist.objects.count(),
            'active_today': GuestUser.objects.filter(last_active__date=today).count(),
            'guest_users': GuestUser.objects.count(),
        }

        return super().index(request, extra_context)


admin_site = GroupedAdminSite()
admin.site = admin_site
admin_site.register(User, UserAdmin)
admin_site.register(Group, GroupAdmin)

class MultilingualAdminMixin:
    """Mixin for multilingual admin interfaces with tabbed layout"""

    class Media:
        js = ('admin/js/vendor/jquery/jquery.js', 'admin/js/multilang.js')
    
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
    list_display = ('__str__', 'order', 'icon', 'applies_to', 'is_active', 'trending', 'featured', 'item_count_display')
    list_filter = ('is_active', 'trending', 'featured', 'applies_to')
    search_fields = ('name', 'name_en', 'name_mk', 'slug', 'icon')
    list_editable = ('order', 'is_active', 'trending', 'featured')
    ordering = ('order', 'name')

    # Note: modeltranslation will auto-generate name_en field, so we can prepopulate from it
    # But we need to be careful since it might not exist yet during initial setup
    # prepopulated_fields = {'slug': ('name_en',)}

    fieldsets = (
        ('Basic Information', {
            'fields': ('name_en', 'name_mk', 'name', 'icon', 'slug', 'image'),
            'classes': ('wide',),
            'description': 'Name fields: English (en), Macedonian (mk), and fallback name.',
        }),
        ('Order', {
            'fields': ('order',),
            'classes': ('wide',),
        }),
        ('Visibility Settings', {
            'fields': ('is_active', 'trending', 'featured'),
            'classes': ('wide',),
        }),
        ('Scope', {
            'fields': ('applies_to',),
            'classes': ('wide',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def item_count_display(self, obj):
        """Display the item count"""
        count = obj.get_item_count()
        return f"{count} items" if count != 1 else "1 item"
    item_count_display.short_description = 'Items'

    def get_queryset(self, request):
        """Optimize queries with select_related"""
        return super().get_queryset(request)

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
    list_display = ('id', 'title', 'category', 'featured', 'trending', 'is_active', 'created_at', 'phone_number')
    list_filter = ('category', 'featured', 'trending', 'is_active', 'created_at')
    search_fields = ('title', 'address', 'category__name')
    list_editable = ('featured', 'trending', 'is_active')
    ordering = ('-created_at',)
    filter_horizontal = ('promotions', 'blogs', 'sections')

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'category',
                'featured',
                'trending',
                'is_active',
                'image', 'image_1', 'image_2', 'image_3', 'image_4', 'image_5',
                'thumbnail_image',
                'phone_number',
                'website_url',
                'facebook_url',
                'instagram_url',
                'google_maps_url'
            ),
            'classes': ('wide',),
        }),
        ('Sections', {
            'fields': ('sections',),
            'classes': ('wide',),
            'description': 'Select which screen sections this listing should appear in',
        }),
        ('Promotions', {
            'fields': ('promotions',),
            'classes': ('wide',),
            'description': 'Select promotions associated with this listing (optional)',
        }),
        ('Related Articles', {
            'fields': ('blogs',),
            'classes': ('wide',),
            'description': 'Select blog articles related to this listing (optional)',
        }),
        ('Menu / Price List Configuration', {
            'fields': ('menu_icon', 'menu_label', 'menu_label_mk', 'menu_url'),
            'description': 'Configure the button that opens the price list. Set a label (e.g. "Memberships", "Services") and choose an icon. Leave label blank to use the default "Menu / Мени". Set Menu URL to link to an external menu (PDF, website) — when set, this overrides the in-app menu sections.',
        }),
        ('English Content', {
            'fields': ('title', 'description', 'address', 'tags', 'amenities_title', 'amenities', 'working_hours', 'show_open_status', 'manual_open_status', 'menu'),
            'classes': ('lang-tab', 'lang-en'),
        }),
        ('Macedonian Content', {
            'fields': ('title_mk', 'description_mk', 'address_mk', 'tags_mk', 'amenities_title_mk', 'amenities_mk', 'working_hours_mk', 'menu_mk'),
            'classes': ('lang-tab', 'lang-mk'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if request.method == 'GET':
            from django.contrib.contenttypes.models import ContentType
            from .models import HomeSectionItem, Listing
            try:
                listing = Listing.objects.get(pk=object_id)
                listing_ct = ContentType.objects.get_for_model(Listing)
                hsi_section_ids = HomeSectionItem.objects.filter(
                    content_type=listing_ct,
                    object_id=listing.id,
                    is_active=True,
                ).values_list('section_id', flat=True)
                listing.sections.add(*hsi_section_ids)
            except Listing.DoesNotExist:
                pass
        return super().change_view(request, object_id, form_url, extra_context)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        from django.contrib.contenttypes.models import ContentType
        from .models import HomeSectionItem
        listing = form.instance
        listing_ct = ContentType.objects.get_for_model(listing)

        selected_ids = set(listing.sections.values_list('id', flat=True))

        existing_ids = set(
            HomeSectionItem.objects.filter(
                content_type=listing_ct,
                object_id=listing.id,
            ).values_list('section_id', flat=True)
        )
        for section_id in selected_ids - existing_ids:
            HomeSectionItem.objects.create(
                section_id=section_id,
                content_type=listing_ct,
                object_id=listing.id,
                order=0,
                is_active=True,
            )

@admin.register(Event, site=admin_site)
class EventAdmin(MultilingualAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'title', 'date_time', 'location', 'category', 'featured', 'is_active', 'show_join_button', 'join_count', 'created_at')
    list_filter = ('category', 'featured', 'is_active', 'show_join_button', 'created_at')
    search_fields = ('title', 'location', 'description', 'category')
    list_editable = ('featured', 'is_active', 'show_join_button')
    ordering = ('-created_at',)
    filter_horizontal = ('listings', 'sections',)

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'category',
                'featured',
                'is_active',
                'show_join_button',
                'date_time',
                'image', 'image_1', 'image_2', 'image_3', 'image_4', 'image_5',
                'thumbnail_image',
                'join_count'
            ),
            'classes': ('wide',),
        }),
        ('Sections', {
            'fields': ('sections',),
            'classes': ('wide',),
            'description': 'Select which screen sections this event should appear in',
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
                'instagram_url',
                'google_maps_url'
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

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """On GET, sync HomeSectionItem entries into the M2M so the widget reflects reality."""
        if request.method == 'GET':
            from django.contrib.contenttypes.models import ContentType
            from .models import HomeSectionItem, Event
            try:
                event = Event.objects.get(pk=object_id)
                event_ct = ContentType.objects.get_for_model(Event)
                hsi_section_ids = HomeSectionItem.objects.filter(
                    content_type=event_ct,
                    object_id=event.id,
                    is_active=True,
                ).values_list('section_id', flat=True)
                event.sections.add(*hsi_section_ids)
            except Event.DoesNotExist:
                pass
        return super().change_view(request, object_id, form_url, extra_context)

    def save_related(self, request, form, formsets, change):
        """On save, sync the M2M selection back to HomeSectionItem entries."""
        super().save_related(request, form, formsets, change)
        from django.contrib.contenttypes.models import ContentType
        from .models import HomeSectionItem
        event = form.instance
        event_ct = ContentType.objects.get_for_model(event)

        selected_ids = set(event.sections.values_list('id', flat=True))

        # Create HomeSectionItem entries for newly selected sections
        existing_ids = set(
            HomeSectionItem.objects.filter(
                content_type=event_ct,
                object_id=event.id,
            ).values_list('section_id', flat=True)
        )
        for section_id in selected_ids - existing_ids:
            HomeSectionItem.objects.create(
                section_id=section_id,
                content_type=event_ct,
                object_id=event.id,
                order=0,
                is_active=True,
            )

    class Media:
        js = ('admin/js/vendor/jquery/jquery.js', 'admin/js/multilang.js', 'admin/js/ai_fill.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('ai-fill/', self.admin_site.admin_view(self.ai_fill_view), name='event_ai_fill'),
            path('ai-listings/', self.admin_site.admin_view(self.ai_listings_view), name='event_ai_listings'),
        ]
        return custom_urls + urls

    def ai_listings_view(self, request):
        from .models import Listing
        listings = list(
            Listing.objects.filter(is_active=True)
            .values('id', 'title', 'phone_number', 'website_url', 'facebook_url', 'instagram_url', 'google_maps_url')
            .order_by('title')
        )
        return JsonResponse({'listings': listings})

    VALID_ICONS = [
        "musical-notes","restaurant","beer","wine","camera","people","happy","star",
        "heart","flash","time","location","ticket","gift","trophy","mic","headset",
        "bonfire","cafe","cart","fitness","football","game-controller","globe","leaf",
        "paw","ribbon","rose","sparkles","sunny","water",
    ]

    AI_SYSTEM_PROMPT = """You are an assistant that extracts structured event information from social media post captions for a tourism app in Gevgelija, North Macedonia.

Your task:
1. Extract event details from the provided caption text
2. Structure them into specific fields matching the Django Event model
3. Translate ALL text fields into natural Macedonian (not Google Translate quality — use proper Macedonian phrasing)

Output a JSON object with these exact fields:
- title: Event title in English (concise, catchy)
- description: Event description in English (2-4 sentences, engaging)
- date_time: Date/time string (e.g., "Fri, 20:00" or "Dec 25, 18:00")
- location: Venue name and/or address in English
- entry_price: Price string (e.g., "Free", "500 MKD", "10 EUR"). Default to "Free" if not mentioned.
- age_limit: Age restriction (e.g., "All ages welcome", "18+"). Default to "All ages welcome" if not mentioned.
- expectations: Array of 3-5 objects with {"icon": string, "text": string}. Icons MUST be from this list: {icons}. Text should be short phrases.
- title_mk, description_mk, location_mk, entry_price_mk, age_limit_mk: Macedonian translations
- expectations_mk: Same array structure but text in Macedonian. Icons stay the same.

Rules:
- If information is missing, make reasonable inferences for a venue in Gevgelija
- Macedonian translations must sound natural — as if written by a native speaker
- ONLY output valid JSON, no markdown fences, no extra text"""

    def ai_fill_view(self, request):
        if request.method != 'POST':
            return JsonResponse({'error': 'POST required'}, status=405)

        try:
            body = json.loads(request.body)
            caption = body.get('caption', '')
            platform = body.get('platform', 'instagram')
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON body'}, status=400)

        if not caption:
            return JsonResponse({'error': 'Caption is required'}, status=400)

        api_key = os.getenv('OPENAI_API_KEY', '')
        if not api_key:
            return JsonResponse({'error': 'OPENAI_API_KEY not configured'}, status=500)

        api_url = 'https://api.openai.com/v1/chat/completions'
        model = 'gpt-4o-mini'

        system_prompt = self.AI_SYSTEM_PROMPT.replace('{icons}', ', '.join(self.VALID_ICONS))

        try:
            resp = http_requests.post(
                api_url,
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                json={
                    'model': model,
                    'response_format': {'type': 'json_object'},
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': f'Extract event information from this {platform} post caption:\n\n{caption}'},
                    ],
                    'temperature': 0.3,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data['choices'][0]['message']['content']
            return JsonResponse(json.loads(content))
        except http_requests.exceptions.Timeout:
            return JsonResponse({'error': 'AI request timed out'}, status=504)
        except http_requests.exceptions.RequestException as e:
            return JsonResponse({'error': str(e)}, status=502)
        except (KeyError, json.JSONDecodeError) as e:
            return JsonResponse({'error': f'Failed to parse AI response: {e}'}, status=500)

@admin.register(Promotion, site=admin_site)
class PromotionAdmin(MultilingualAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'title', 'discount_code', 'valid_until', 'featured', 'is_active', 'created_at')
    list_filter = ('featured', 'is_active', 'has_discount_code', 'valid_until', 'created_at')
    search_fields = ('title', 'discount_code', 'description')
    list_editable = ('featured', 'is_active')
    ordering = ('-created_at',)
    filter_horizontal = ('sections',)

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'featured',
                'is_active',
                'image', 'image_1', 'image_2', 'image_3', 'image_4', 'image_5',
                'thumbnail_image',
                'valid_until',
                'has_discount_code',
                'discount_code',
                'website',
                'phone_number',
                'facebook_url',
                'instagram_url',
                'address',
                'google_maps_url'
            ),
            'classes': ('wide',),
        }),
        ('Sections', {
            'fields': ('sections',),
            'classes': ('wide',),
            'description': 'Select which screen sections this promotion should appear in',
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

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if request.method == 'GET':
            from django.contrib.contenttypes.models import ContentType
            from .models import HomeSectionItem, Promotion
            try:
                promo = Promotion.objects.get(pk=object_id)
                promo_ct = ContentType.objects.get_for_model(Promotion)
                hsi_section_ids = HomeSectionItem.objects.filter(
                    content_type=promo_ct,
                    object_id=promo.id,
                    is_active=True,
                ).values_list('section_id', flat=True)
                promo.sections.add(*hsi_section_ids)
            except Promotion.DoesNotExist:
                pass
        return super().change_view(request, object_id, form_url, extra_context)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        from django.contrib.contenttypes.models import ContentType
        from .models import HomeSectionItem
        promo = form.instance
        promo_ct = ContentType.objects.get_for_model(promo)

        selected_ids = set(promo.sections.values_list('id', flat=True))

        existing_ids = set(
            HomeSectionItem.objects.filter(
                content_type=promo_ct,
                object_id=promo.id,
            ).values_list('section_id', flat=True)
        )
        for section_id in selected_ids - existing_ids:
            HomeSectionItem.objects.create(
                section_id=section_id,
                content_type=promo_ct,
                object_id=promo.id,
                order=0,
                is_active=True,
            )

class BlogSectionInline(admin.TabularInline):
    """Inline admin for collapsible blog sections"""
    model = BlogSection
    extra = 1
    fields = ('order', 'title', 'title_en', 'title_mk', 'content', 'content_en', 'content_mk', 'is_expanded_by_default')
    ordering = ['order']


@admin.register(Blog, site=admin_site)
class BlogAdmin(MultilingualAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'title', 'author', 'category', 'read_time_minutes', 'featured', 'published', 'is_active', 'created_at')
    list_filter = ('category', 'featured', 'published', 'is_active', 'created_at')
    search_fields = ('title', 'subtitle', 'content', 'author', 'category')
    list_editable = ('featured', 'published', 'is_active')
    ordering = ('-created_at',)
    inlines = [BlogSectionInline]
    filter_horizontal = ('home_sections',)

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'category',
                'featured',
                'published',
                'is_active',
                'image', 'image_1', 'image_2', 'image_3', 'image_4', 'image_5',
                'thumbnail_image',
                'read_time_minutes',
                'tags',
                'home_sections',
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
        ('CTA Button (Call to Action)', {
            'fields': (
                'cta_button_url',
                ('cta_button_title', 'cta_button_title_en', 'cta_button_title_mk'),
                ('cta_button_subtitle', 'cta_button_subtitle_en', 'cta_button_subtitle_mk'),
            ),
            'classes': ('wide',),
            'description': 'Optional button that appears in the blog detail. Leave URL empty to hide the button.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

# ============================================================================
# VIEW LOGS - Read-only admin models for viewing user activity
# ============================================================================

@admin.register(EventJoin, site=admin_site)
class EventJoinAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'created_at')
    list_filter = ('created_at', 'event')
    search_fields = ('user__username', 'user__email', 'event__title')
    ordering = ('-created_at',)
    readonly_fields = ('user', 'event', 'created_at')

@admin.register(Wishlist, site=admin_site)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ('user', 'content_type', 'content_object', 'item_type', 'created_at')
    list_filter = ('content_type', 'created_at')
    search_fields = ('user__username', 'user__email')
    ordering = ('-created_at',)
    readonly_fields = ('user', 'content_type', 'object_id', 'created_at')

@admin.register(VerificationCode, site=admin_site)
class VerificationCodeAdmin(admin.ModelAdmin):
    list_display = ('email', 'code', 'is_used', 'created_at', 'expires_at')
    list_filter = ('is_used', 'created_at', 'expires_at')
    search_fields = ('email', 'code')
    ordering = ('-created_at',)
    readonly_fields = ('email', 'code', 'is_used', 'created_at', 'expires_at')

@admin.register(GuestUser, site=admin_site)
class GuestUserAdmin(admin.ModelAdmin):
    list_display = ('guest_id', 'language_preference', 'created_at', 'last_active')
    list_filter = ('language_preference', 'created_at', 'last_active')
    search_fields = ('guest_id',)
    ordering = ('-last_active',)
    readonly_fields = ('guest_id', 'language_preference', 'created_at', 'last_active')

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



# ============================================================================
# HOME SECTION ADMIN - Backend-driven homescreen configuration
# ============================================================================

class HomeSectionItemInline(admin.TabularInline):
    """Inline admin for HomeSectionItems"""
    model = HomeSectionItem
    extra = 1
    fields = ("content_type", "object_id", "order", "is_active")
    ordering = ["order", "-created_at"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit content_type choices to Listing, Event, Promotion, Blog"""
        if db_field.name == "content_type":
            kwargs["queryset"] = ContentType.objects.filter(
                model__in=["listing", "event", "promotion", "blog"]
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(HomeSection, site=admin_site)
class HomeSectionAdmin(admin.ModelAdmin):
    """Admin interface for HomeSection with inline items"""
    list_display = ("label", "card_type", "display_on", "item_count", "order", "tourism_order", "events_order", "is_active", "is_pinned", "created_at")
    list_editable = ("order", "tourism_order", "events_order", "is_active", "is_pinned")
    list_filter = ("card_type", "display_on", "is_active", "is_pinned", "created_at")
    search_fields = ("label", "label_en", "label_mk")
    ordering = ("order", "-created_at")

    fieldsets = (
        ("Basic Information", {
            "fields": ("label", "label_en", "label_mk", "card_type")
        }),
        ("Display Settings", {
            "fields": ("display_on", "order", "tourism_order", "events_order", "is_active", "is_pinned")
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    readonly_fields = ("created_at", "updated_at")
    inlines = [HomeSectionItemInline]
    
    def item_count(self, obj):
        """Display number of items in this section"""
        return obj.item_count
    item_count.short_description = "Items"
    
    # Bulk actions
    actions = ["activate_sections", "deactivate_sections"]
    
    def activate_sections(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} sections activated.")
    activate_sections.short_description = "✅ Activate selected sections"
    
    def deactivate_sections(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} sections deactivated.")
    deactivate_sections.short_description = "❌ Deactivate selected sections"

    def _clear_home_cache(self):
        cache.delete_pattern('*home/sections*') if hasattr(cache, 'delete_pattern') else cache.clear()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self._clear_home_cache()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        self._clear_home_cache()

    def response_change(self, request, obj):
        self._clear_home_cache()
        return super().response_change(request, obj)


# HomeSectionItem is managed via inline in HomeSection - disabled standalone admin
# @admin.register(HomeSectionItem, site=admin_site)
# class HomeSectionItemAdmin(admin.ModelAdmin):
#     """Admin interface for HomeSectionItem (standalone view)"""
#     list_display = ("section", "content_type", "object_id", "item_type", "order", "is_active", "created_at")
#     list_filter = ("section", "content_type", "is_active", "created_at")
#     list_editable = ("order", "is_active")
#     search_fields = ("section__label",)
#     ordering = ("section__order", "order", "-created_at")
#
#     fieldsets = (
#         ("Section", {
#             "fields": ("section",)
#         }),
#         ("Content Reference", {
#             "fields": ("content_type", "object_id"),
#             "description": "Select the type and ID of the content to display (Listing, Event, or Promotion)"
#         }),
#         ("Display Settings", {
#             "fields": ("order", "is_active")
#         }),
#     )
#
#     readonly_fields = ("created_at",)
#
#     def formfield_for_foreignkey(self, db_field, request, **kwargs):
#         """Limit content_type choices to Listing, Event, Promotion"""
#         if db_field.name == "content_type":
#             kwargs["queryset"] = ContentType.objects.filter(
#                 model__in=["listing", "event", "promotion"]
#             )
#         return super().formfield_for_foreignkey(db_field, request, **kwargs)
#
#     def item_type(self, obj):
#         """Display the content type in a readable format"""
#         return obj.content_type.model.title()
#     item_type.short_description = "Type"


# ============================================================================
# TOURISM SCREEN ADMIN
# ============================================================================

@admin.register(TourismCarousel, site=admin_site)
class TourismCarouselAdmin(MultilingualAdminMixin, admin.ModelAdmin):
    """Admin interface for Tourism Carousel items"""
    list_display = ("title", "content_type", "object_id", "item_type", "order", "is_active", "created_at")
    list_editable = ("order", "is_active")
    list_filter = ("content_type", "is_active", "created_at")
    search_fields = ("title", "title_en", "title_mk")
    ordering = ("order", "-created_at")

    fieldsets = (
        ("Carousel Item", {
            "fields": ("title", "title_en", "title_mk")
        }),
        ("Content Reference", {
            "fields": ("content_type", "object_id"),
            "description": "Select the type and ID of the content to display (Listing, Event, or Blog)"
        }),
        ("Display Settings", {
            "fields": ("order", "is_active")
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    readonly_fields = ("created_at", "updated_at")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit content_type choices to Listing, Event, or Blog"""
        if db_field.name == "content_type":
            kwargs["queryset"] = ContentType.objects.filter(
                model__in=["listing", "event", "blog"]
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def item_type(self, obj):
        """Display the content type in a readable format"""
        return obj.content_type.model.title()
    item_type.short_description = "Type"

    # Bulk actions
    actions = ["activate_items", "deactivate_items"] + MultilingualAdminMixin.actions

    def activate_items(self, request, queryset):
        """Activate selected carousel items"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} carousel items activated.")
    activate_items.short_description = "✅ Activate selected items"

    def deactivate_items(self, request, queryset):
        """Deactivate selected carousel items"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} carousel items deactivated.")
    deactivate_items.short_description = "❌ Deactivate selected items"


# TourismCategoryButton - disabled (buttons are hardcoded in frontend)
# @admin.register(TourismCategoryButton, site=admin_site)
# class TourismCategoryButtonAdmin(MultilingualAdminMixin, admin.ModelAdmin):
#     """Admin interface for Tourism Category Buttons"""
#     list_display = ("label", "category", "button_size", "icon", "order", "is_active", "created_at")
#     list_editable = ("order", "is_active")
#     list_filter = ("button_size", "is_active", "category")
#     search_fields = ("label", "label_en", "label_mk", "category__name")
#     ordering = ("button_size", "order", "-created_at")
#
#     fieldsets = (
#         ("Button Configuration", {
#             "fields": ("label", "label_en", "label_mk", "category", "icon", "background_image", "button_size")
#         }),
#         ("Display Settings", {
#             "fields": ("order", "is_active")
#         }),
#         ("Metadata", {
#             "fields": ("created_at",),
#             "classes": ("collapse",)
#         }),
#     )
#
#     readonly_fields = ("created_at",)
#
#     # Bulk actions
#     actions = ["activate_buttons", "deactivate_buttons"] + MultilingualAdminMixin.actions
#
#     def activate_buttons(self, request, queryset):
#         """Activate selected category buttons"""
#         updated = queryset.update(is_active=True)
#         self.message_user(request, f"{updated} category buttons activated.")
#     activate_buttons.short_description = "✅ Activate selected buttons"
#
#     def deactivate_buttons(self, request, queryset):
#         """Deactivate selected category buttons"""
#         updated = queryset.update(is_active=False)
#         self.message_user(request, f"{updated} category buttons deactivated.")
#     deactivate_buttons.short_description = "❌ Deactivate selected buttons"


@admin.register(GalleryPhoto, site=admin_site)
class GalleryPhotoAdmin(admin.ModelAdmin):
    list_display = ['id', 'listing', 'caption', 'order', 'is_active']
    list_editable = ['order', 'is_active']
    list_filter = ['listing', 'is_active']
    search_fields = ['caption', 'listing__title_en']
    autocomplete_fields = ['listing']
    ordering = ['listing', 'order', 'id']
