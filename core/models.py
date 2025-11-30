from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill, ResizeToFit
import uuid
import os

class GuestUser(models.Model):
    """Model for guest users who browse without registering"""
    guest_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, help_text="Unique identifier for guest user")
    language_preference = models.CharField(
        max_length=2,
        choices=[('en', 'English'), ('mk', 'Macedonian')],
        default='en',
        help_text="Guest user's preferred language"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_active']

    def __str__(self):
        return f"Guest {self.guest_id} - {self.language_preference}"

class VerificationCode(models.Model):
    """Model to store email verification codes for passwordless authentication"""
    email = models.EmailField(help_text="Email address for verification")
    code = models.CharField(max_length=6, help_text="6-digit verification code")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="When the code expires")
    is_used = models.BooleanField(default=False, help_text="Whether the code has been used")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} - {self.code} - {'used' if self.is_used else 'active'}"

    def is_valid(self):
        """Check if code is still valid (not expired and not used)"""
        from django.utils import timezone
        return not self.is_used and self.expires_at > timezone.now()


class UserProfile(models.Model):
    AVATAR_CHOICES = [
        ('default', 'Default (Initial)'),
        ('avatar1', 'Avatar 1'),
        ('avatar2', 'Avatar 2'),
        ('avatar3', 'Avatar 3'),
        ('avatar4', 'Avatar 4'),
        ('avatar5', 'Avatar 5'),
        ('avatar6', 'Avatar 6'),
        ('avatar7', 'Avatar 7'),
        ('avatar8', 'Avatar 8'),
        ('avatar9', 'Avatar 9'),
        ('avatar10', 'Avatar 10'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    language_preference = models.CharField(
        max_length=2,
        choices=[('en', 'English'), ('mk', 'Macedonian')],
        default='en',
        help_text="User's preferred language"
    )
    avatar = models.CharField(
        max_length=20,
        choices=AVATAR_CHOICES,
        default='default',
        help_text="Selected profile avatar"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.language_preference}"


def _image_upload_path(prefix: str, filename: str) -> str:
    """Generate a unique path for uploaded images under the given prefix."""
    _, ext = os.path.splitext(filename)
    ext = ext.lower() or '.jpg'
    return f"{prefix}/{uuid.uuid4().hex}{ext}"


def category_image_upload_to(instance, filename):
    """Generate a unique path for category images."""
    return _image_upload_path("categories", filename)


class Category(models.Model):
    APPLIES_TO_CHOICES = [
        ('listing', 'Listing'),
        ('event', 'Event'),
        ('both', 'Both'),
    ]

    # Basic Information
    name = models.CharField(max_length=100, help_text="Category name (will be translated by modeltranslation)")
    slug = models.SlugField(max_length=120, blank=True, null=True, help_text="URL-friendly identifier (auto-generated from name if empty)")
    icon = models.CharField(max_length=50, help_text="Ionicon name (e.g., 'restaurant-outline')")
    image = models.ImageField(
        upload_to=category_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional category image stored in the media bucket"
    )
    color = models.CharField(max_length=7, blank=True, help_text="Brand color for category in hex format (e.g., '#FF5722')")

    # Hierarchy
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        help_text="Parent category (leave empty for root categories)"
    )
    level = models.PositiveIntegerField(default=0, help_text="Hierarchy level (0=root, 1=subcategory, etc.)")
    order = models.PositiveIntegerField(default=0, help_text="Display order within parent category")

    # Visibility & Behavior
    is_active = models.BooleanField(default=True, help_text="Whether category is active and visible")
    show_in_search = models.BooleanField(default=True, help_text="Show in search screen")
    show_in_navigation = models.BooleanField(default=True, help_text="Show in navigation menus")
    trending = models.BooleanField(default=False, help_text="Mark as trending category (can be combined with featured)")
    featured = models.BooleanField(default=False, help_text="Mark as featured category")

    # Scope
    applies_to = models.CharField(
        max_length=10,
        choices=APPLIES_TO_CHOICES,
        default='both',
        help_text="Whether this category applies to listings, events, or both"
    )

    # Legacy field (for backward compatibility)
    show_in_events = models.BooleanField(default=True, help_text="[Legacy] Whether this category should be available for events")

    # Metadata
    description = models.TextField(blank=True, help_text="Category description (will be translated by modeltranslation)")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['level', 'order', 'name']
        indexes = [
            models.Index(fields=['parent', 'is_active']),
            models.Index(fields=['level', 'order']),
        ]

    def __str__(self):
        return self.name_en or self.name_mk or self.name

    def save(self, *args, **kwargs):
        # Auto-generate slug from name if not provided
        if not self.slug:
            from django.utils.text import slugify
            # Try to use English name first (modeltranslation will have created name_en)
            base_name = getattr(self, 'name_en', None) or getattr(self, 'name_mk', None) or self.name
            base_slug = slugify(base_name)
            slug = base_slug
            counter = 1
            while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        # Auto-calculate level based on parent
        if self.parent:
            self.level = self.parent.level + 1
        else:
            self.level = 0

        super().save(*args, **kwargs)

    def get_item_count(self):
        """
        Calculate the number of items (listings + events) in this category and all subcategories.
        PERFORMANCE FIX: Changed from @property to method to avoid automatic calculation on every access.
        Call this explicitly when needed.
        """
        from django.db.models import Q, Count

        # Get all descendant category IDs (including self) - optimized with single query
        descendant_ids = self.get_descendants_optimized(include_self=True)

        # Count listings and events in a single query using aggregation
        from django.db.models import Count, Q
        counts = {
            'listings': Listing.objects.filter(
                category_id__in=descendant_ids,
                is_active=True
            ).count(),
            'events': Event.objects.filter(
                category_id__in=descendant_ids,
                is_active=True
            ).count()
        }

        return counts['listings'] + counts['events']

    def get_descendants_optimized(self, include_self=False):
        """
        Get all descendant category IDs - OPTIMIZED VERSION using iterative approach
        to avoid recursive database queries.
        """
        descendants = [self.id] if include_self else []
        queue = [self.id]

        # Fetch all categories in one query
        all_children = {cat.parent_id: [] for cat in Category.objects.all()}
        for cat in Category.objects.all():
            if cat.parent_id:
                all_children.setdefault(cat.parent_id, []).append(cat.id)

        # Iterative traversal instead of recursive
        while queue:
            current_id = queue.pop(0)
            children_ids = all_children.get(current_id, [])
            descendants.extend(children_ids)
            queue.extend(children_ids)

        return descendants

    def get_descendants(self, include_self=False):
        """
        DEPRECATED: Use get_descendants_optimized() instead.
        Kept for backward compatibility but causes N+1 queries.
        """
        descendants = [self.id] if include_self else []
        children = Category.objects.filter(parent=self)
        for child in children:
            descendants.extend(child.get_descendants(include_self=True))
        return descendants

    def get_ancestors(self):
        """Get all ancestor categories from root to parent"""
        ancestors = []
        current = self.parent
        while current:
            ancestors.insert(0, current)
            current = current.parent
        return ancestors


def listing_image_upload_to(instance, filename):
    """Generate a unique path for listing images."""
    return _image_upload_path("listings", filename)


def promotion_image_upload_to(instance, filename):
    """Generate a unique path for promotion images."""
    return _image_upload_path("promotions", filename)


def event_image_upload_to(instance, filename):
    """Generate a unique path for event images."""
    return _image_upload_path("events", filename)


def blog_image_upload_to(instance, filename):
    """Generate a unique path for blog images."""
    return _image_upload_path("blogs", filename)


class Listing(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, help_text="Listing description")
    address = models.CharField(max_length=500)
    open_time = models.CharField(
        max_length=100,
        help_text="e.g., 'Open until 23:00' or 'Mon-Fri 9:00-18:00'",
        blank=True,
        null=True,
    )
    working_hours = models.JSONField(
        default=dict,
        help_text="Working hours structure, e.g., {'monday': '09:00-18:00', 'tuesday': '09:00-18:00', ...}",
        blank=True,
        null=True,
    )
    working_hours_mk = models.JSONField(
        default=dict,
        help_text="Working hours in Macedonian, e.g., {'понedelник': '09:00-18:00', 'вторник': '09:00-18:00', ...}",
        blank=True,
        null=True,
    )
    show_open_status = models.BooleanField(
        default=False,
        help_text="Enable this to show Open/Closed status based on working hours"
    )
    manual_open_status = models.BooleanField(
        default=True,
        null=True,
        blank=True,
        help_text="Manually set Open/Closed status (used when working hours are not defined). True = Open, False = Closed, Null = Use working hours"
    )
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, help_text="Select category from available categories")
    tags = models.JSONField(default=list, help_text="List of tags, e.g., ['Grill', 'Family', 'Outdoor']", blank=True, null=True)
    tags_mk = models.JSONField(default=list, help_text="List of tags in Macedonian, e.g., ['Скара', 'Семејно', 'Надворешно']", blank=True, null=True)
    amenities_title = models.CharField(
        max_length=100,
        default="Amenities",
        help_text="Custom title for the amenities section (e.g., 'Features', 'What We Offer', 'Services')",
        blank=True,
    )
    amenities_title_mk = models.CharField(
        max_length=100,
        default="Погодности",
        help_text="Custom title for the amenities section in Macedonian",
        blank=True,
    )
    amenities = models.JSONField(
        default=list,
        help_text="List of amenities with optional icon, e.g., [{'icon': 'wifi', 'text': 'Free Wi-Fi'}]",
        blank=True,
        null=True,
    )
    amenities_mk = models.JSONField(
        default=list,
        help_text="List of amenities in Macedonian, e.g., [{'icon': 'wifi', 'text': 'Бесплатен Wi-Fi'}]",
        blank=True,
        null=True,
    )
    image = models.ImageField(
        upload_to=listing_image_upload_to,
        blank=True,
        null=True,
        help_text="Listing image stored in the media bucket"
    )
    image_1 = models.ImageField(
        upload_to=listing_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional listing image"
    )
    image_2 = models.ImageField(
        upload_to=listing_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional listing image"
    )
    image_3 = models.ImageField(
        upload_to=listing_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional listing image"
    )
    image_4 = models.ImageField(
        upload_to=listing_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional listing image"
    )
    image_5 = models.ImageField(
        upload_to=listing_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional listing image"
    )

    # Manual thumbnail for card displays
    thumbnail_image = models.ImageField(
        upload_to=listing_image_upload_to,
        blank=True,
        null=True,
        help_text="Custom thumbnail for list/card views (recommended: 430x430px). If not set, auto-generated from main image."
    )

    # Optimized image variants (auto-generated)
    image_thumbnail = ImageSpecField(
        source='image',
        processors=[ResizeToFill(162, 162)],  # 54pt * 3 for retina displays
        format='WEBP',
        options={'quality': 95}  # Higher quality for small images
    )
    image_medium = ImageSpecField(
        source='image',
        processors=[ResizeToFit(430, 430)],
        format='WEBP',
        options={'quality': 90}
    )

    phone_number = models.CharField(max_length=20, blank=True, null=True, help_text="Contact phone number")
    facebook_url = models.URLField(max_length=500, blank=True, null=True, help_text="Facebook page URL")
    instagram_url = models.URLField(max_length=500, blank=True, null=True, help_text="Instagram profile URL")
    website_url = models.URLField(max_length=500, blank=True, null=True, help_text="Official website URL")
    google_maps_url = models.URLField(max_length=500, blank=True, null=True, help_text="Google Maps URL for directions (optional - if not provided, will use address field)")
    featured = models.BooleanField(default=False, help_text="Show in featured section")
    trending = models.BooleanField(default=False, help_text="Mark as trending - will be displayed in trending tab on search screen")
    is_active = models.BooleanField(default=True, help_text="Show this listing in the app. Uncheck to hide from users.")
    promotions = models.ManyToManyField('Promotion', blank=True, related_name='listings', help_text="Select promotions associated with this listing (optional)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        # PERFORMANCE FIX: Add database indexes for frequently queried fields
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['featured', '-created_at']),
            models.Index(fields=['trending', '-created_at']),
            models.Index(fields=['is_active', '-created_at']),
        ]

    def __str__(self):
        return self.title


class Event(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, help_text="Event description")
    date_time = models.CharField(max_length=100, help_text="e.g., 'Fri, 20:00' or 'Dec 25, 18:00'")
    location = models.CharField(max_length=255, help_text="Event venue/location")
    image = models.ImageField(
        upload_to=event_image_upload_to,
        blank=True,
        null=True,
        help_text="Primary event image stored in the media bucket"
    )
    image_1 = models.ImageField(
        upload_to=event_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional event image"
    )
    image_2 = models.ImageField(
        upload_to=event_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional event image"
    )
    image_3 = models.ImageField(
        upload_to=event_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional event image"
    )
    image_4 = models.ImageField(
        upload_to=event_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional event image"
    )
    image_5 = models.ImageField(
        upload_to=event_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional event image"
    )

    # Manual thumbnail for card displays
    thumbnail_image = models.ImageField(
        upload_to=event_image_upload_to,
        blank=True,
        null=True,
        help_text="Custom thumbnail for list/card views (recommended: 430x430px). If not set, auto-generated from main image."
    )

    # Optimized image variants (auto-generated)
    image_thumbnail = ImageSpecField(
        source='image',
        processors=[ResizeToFill(162, 162)],  # 54pt * 3 for retina displays
        format='WEBP',
        options={'quality': 95}  # Higher quality for small images
    )
    image_medium = ImageSpecField(
        source='image',
        processors=[ResizeToFit(430, 430)],
        format='WEBP',
        options={'quality': 90}
    )

    entry_price = models.CharField(max_length=50, default="Free", blank=True, null=True, help_text="Entry price (e.g., 'Free', '10 EUR', '500 MKD')")
    entry_price_mk = models.CharField(max_length=50, blank=True, null=True, help_text="Entry price in Macedonian (e.g., 'Бесплатно', '10 ЕУР', '500 МКД')")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, help_text="Select category from available categories")
    age_limit = models.CharField(max_length=50, default="All ages welcome", blank=True, null=True, help_text="Age restriction (e.g., 'All ages welcome', '18+', '21+')")
    age_limit_mk = models.CharField(max_length=50, blank=True, null=True, help_text="Age restriction in Macedonian (e.g., 'Добредојдени се сите возрасти', '18+', '21+')")
    expectations = models.JSONField(default=list, help_text="List of expectations with icons, e.g., [{'icon': 'musical-notes', 'text': 'Live entertainment'}, {'icon': 'restaurant', 'text': 'Food available'}]")
    expectations_mk = models.JSONField(default=list, help_text="List of expectations in Macedonian with icons, e.g., [{'icon': 'musical-notes', 'text': 'Музика во живо'}, {'icon': 'restaurant', 'text': 'Достапна храна'}]")
    join_count = models.PositiveIntegerField(default=0, help_text="Number of users who joined this event")
    featured = models.BooleanField(default=False, help_text="Show in featured events")
    is_active = models.BooleanField(default=True, help_text="Show this event in the app. Uncheck to hide from users.")
    show_join_button = models.BooleanField(default=True, help_text="Show 'Join Event' button. If unchecked, show 'Contact' button instead.")
    phone_number = models.CharField(max_length=20, blank=True, null=True, help_text="Contact phone number (shown when join button is disabled)")
    facebook_url = models.URLField(max_length=500, blank=True, null=True, help_text="Facebook page URL")
    instagram_url = models.URLField(max_length=500, blank=True, null=True, help_text="Instagram profile URL")
    website_url = models.URLField(max_length=500, blank=True, null=True, help_text="Official website URL")
    google_maps_url = models.URLField(max_length=500, blank=True, null=True, help_text="Google Maps URL for directions (optional - if not provided, will use location field)")
    listings = models.ManyToManyField('Listing', blank=True, related_name='events', help_text="Select listings associated with this event (optional)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        # PERFORMANCE FIX: Add database indexes for frequently queried fields
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['featured', '-date_time']),
            models.Index(fields=['is_active', '-date_time']),
        ]

    def __str__(self):
        return f"{self.title} - {self.date_time}"


class Promotion(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, help_text="Promotion description")
    has_discount_code = models.BooleanField(default=False, help_text="Whether this promotion has a discount code")
    discount_code = models.CharField(max_length=50, blank=True, help_text="Promo code for discount (only used if has_discount_code is True)")
    tags = models.JSONField(default=list, help_text="List of tags, e.g., ['Today', 'Dine-in', '50% off']")
    tags_mk = models.JSONField(default=list, help_text="List of tags in Macedonian, e.g., ['Денес', 'За јадење', '50% попуст']")
    image = models.ImageField(
        upload_to=promotion_image_upload_to,
        blank=True,
        null=True,
        help_text="Primary promotion image stored in the media bucket"
    )
    image_1 = models.ImageField(
        upload_to=promotion_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional promotion image"
    )
    image_2 = models.ImageField(
        upload_to=promotion_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional promotion image"
    )
    image_3 = models.ImageField(
        upload_to=promotion_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional promotion image"
    )
    image_4 = models.ImageField(
        upload_to=promotion_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional promotion image"
    )
    image_5 = models.ImageField(
        upload_to=promotion_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional promotion image"
    )

    # Manual thumbnail for card displays
    thumbnail_image = models.ImageField(
        upload_to=promotion_image_upload_to,
        blank=True,
        null=True,
        help_text="Custom thumbnail for list/card views (recommended: 430x430px). If not set, auto-generated from main image."
    )

    # Optimized image variants (auto-generated)
    image_thumbnail = ImageSpecField(
        source='image',
        processors=[ResizeToFill(162, 162)],  # 54pt * 3 for retina displays
        format='WEBP',
        options={'quality': 95}  # Higher quality for small images
    )
    image_medium = ImageSpecField(
        source='image',
        processors=[ResizeToFit(430, 430)],
        format='WEBP',
        options={'quality': 90}
    )

    valid_until = models.DateField(null=True, blank=True, help_text="Promotion expiry date")
    featured = models.BooleanField(default=False, help_text="Show in featured promotions")
    is_active = models.BooleanField(default=True, help_text="Show this promotion in the app. Uncheck to hide from users.")
    website = models.URLField(max_length=500, blank=True, help_text="Website URL")
    phone_number = models.CharField(max_length=20, blank=True, null=True, help_text="Contact phone number")
    facebook_url = models.URLField(max_length=500, blank=True, help_text="Facebook page URL")
    instagram_url = models.URLField(max_length=500, blank=True, help_text="Instagram profile URL")
    address = models.CharField(max_length=500, blank=True, help_text="Physical address")
    google_maps_url = models.URLField(max_length=500, blank=True, null=True, help_text="Google Maps URL for directions (optional - if not provided, will use address field)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        # PERFORMANCE FIX: Add database indexes for frequently queried fields
        # Note: Promotion has no category field, only featured, is_active, dates
        indexes = [
            models.Index(fields=['featured', 'is_active', '-created_at']),
            models.Index(fields=['is_active', '-created_at']),
        ]

    def __str__(self):
        return f"{self.title} - {self.discount_code}"


class Blog(models.Model):
    CATEGORY_CHOICES = [
        ('guide', 'Travel Guide'),
        ('food', 'Food & Dining'),
        ('culture', 'Culture & History'),
        ('events', 'Events & Activities'),
        ('tips', 'Travel Tips'),
        ('news', 'Local News'),
        ('lifestyle', 'Lifestyle'),
        ('other', 'Other'),
    ]
    
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=500, blank=True, help_text="Brief subtitle or summary")
    content = models.TextField(help_text="Full blog post content")
    author = models.CharField(max_length=100, default="GoGevgelija Team")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    tags = models.JSONField(default=list, help_text="List of tags, e.g., ['Travel', 'Food', 'Culture']")
    image = models.ImageField(
        upload_to=blog_image_upload_to,
        blank=True,
        null=True,
        help_text="Primary blog image stored in the media bucket"
    )
    image_1 = models.ImageField(
        upload_to=blog_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional blog image"
    )
    image_2 = models.ImageField(
        upload_to=blog_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional blog image"
    )
    image_3 = models.ImageField(
        upload_to=blog_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional blog image"
    )
    image_4 = models.ImageField(
        upload_to=blog_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional blog image"
    )
    image_5 = models.ImageField(
        upload_to=blog_image_upload_to,
        blank=True,
        null=True,
        help_text="Optional additional blog image"
    )

    # Manual thumbnail for card displays
    thumbnail_image = models.ImageField(
        upload_to=blog_image_upload_to,
        blank=True,
        null=True,
        help_text="Custom thumbnail for list/card views (recommended: 430x430px). If not set, auto-generated from main image."
    )

    # Optimized image variants (auto-generated)
    image_thumbnail = ImageSpecField(
        source='image',
        processors=[ResizeToFill(162, 162)],  # 54pt * 3 for retina displays
        format='WEBP',
        options={'quality': 95}  # Higher quality for small images
    )
    image_medium = ImageSpecField(
        source='image',
        processors=[ResizeToFit(430, 430)],
        format='WEBP',
        options={'quality': 90}
    )

    read_time_minutes = models.PositiveIntegerField(default=5, help_text="Estimated reading time in minutes")
    featured = models.BooleanField(default=False, help_text="Show in featured blogs")
    published = models.BooleanField(default=True, help_text="Whether the blog is published")
    is_active = models.BooleanField(default=True, help_text="Show this blog in the app. Uncheck to hide from users.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        # PERFORMANCE FIX: Add database indexes for frequently queried fields
        indexes = [
            models.Index(fields=['category', 'is_active', 'published']),
            models.Index(fields=['featured', 'published', '-created_at']),
            models.Index(fields=['is_active', 'published', '-created_at']),
        ]

    def __str__(self):
        return self.title


class EventJoin(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='event_joins')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='joined_users')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'event')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} joined {self.event.title}"


class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist_items')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'content_type', 'object_id')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.content_object}"
    
    @property
    def item_type(self):
        return self.content_type.model
    
    @property
    def item_data(self):
        return self.content_object

class UserPermission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listing_permissions')
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='user_permissions')
    can_edit = models.BooleanField(default=True, help_text="Whether user can edit this listing")
    granted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='granted_permissions', help_text="Admin who granted this permission")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('user', 'listing')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} can edit {self.listing.title}"


class HelpSupport(models.Model):
    CATEGORY_CHOICES = [
        ('general', 'General Inquiry'),
        ('technical', 'Technical Issue'),
        ('listing', 'Listing Problem'),
        ('event', 'Event Issue'),
        ('account', 'Account Problem'),
        ('feedback', 'Feedback'),
        ('bug', 'Bug Report'),
        ('feature', 'Feature Request'),
        ('other', 'Other'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='help_requests', help_text="User who submitted the request")
    name = models.CharField(max_length=100, help_text="User's name")
    email = models.EmailField(help_text="User's email address")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='general', help_text="Type of help request")
    subject = models.CharField(max_length=255, help_text="Brief subject/title of the issue")
    message = models.TextField(help_text="Detailed description of the issue or request")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium', help_text="Priority level")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open', help_text="Current status of the request")
    admin_response = models.TextField(blank=True, help_text="Admin response to the request")
    responded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='help_responses', help_text="Admin who responded")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True, help_text="When the issue was resolved")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Help & Support Request"
        verbose_name_plural = "Help & Support Requests"
    
    def __str__(self):
        return f"{self.subject} - {self.user.username} ({self.status})"
    
    def save(self, *args, **kwargs):
        # Auto-set resolved_at when status changes to resolved
        if self.status == 'resolved' and not self.resolved_at:
            from django.utils import timezone
            self.resolved_at = timezone.now()
        super().save(*args, **kwargs)


class CollaborationContact(models.Model):
    COLLABORATION_TYPE_CHOICES = [
        ('business', 'Business Partnership'),
        ('event', 'Event Collaboration'),
        ('marketing', 'Marketing Partnership'),
        ('tourism', 'Tourism Partnership'),
        ('other', 'Other Collaboration'),
    ]
    
    STATUS_CHOICES = [
        ('new', 'New'),
        ('reviewing', 'Under Review'),
        ('interested', 'Interested'),
        ('scheduled', 'Meeting Scheduled'),
        ('declined', 'Declined'),
        ('completed', 'Collaboration Started'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='collaboration_requests', help_text="User who submitted the collaboration request")
    
    # Contact Information
    name = models.CharField(max_length=100, help_text="Contact person's name")
    email = models.EmailField(help_text="Contact email address")
    phone = models.CharField(max_length=20, blank=True, help_text="Phone number (optional)")
    company_name = models.CharField(max_length=150, help_text="Company or organization name")
    
    # Collaboration Details
    collaboration_type = models.CharField(max_length=20, choices=COLLABORATION_TYPE_CHOICES, help_text="Type of collaboration")
    proposal = models.TextField(help_text="Detailed collaboration proposal")
    timeline = models.CharField(max_length=100, blank=True, help_text="Preferred timeline")
    
    # Admin Management
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='new', help_text="Current status of the collaboration request")
    admin_notes = models.TextField(blank=True, help_text="Internal admin notes")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_collaborations', help_text="Admin who reviewed this request")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    review_date = models.DateTimeField(null=True, blank=True, help_text="When the request was reviewed")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Collaboration Contact"
        verbose_name_plural = "Collaboration Contacts"
    
    def __str__(self):
        return f"{self.company_name} - {self.name} ({self.collaboration_type})"
    
    def save(self, *args, **kwargs):
        # Auto-set review_date when status changes from 'new'
        if self.status != 'new' and not self.review_date:
            from django.utils import timezone
            self.review_date = timezone.now()
        super().save(*args, **kwargs)
