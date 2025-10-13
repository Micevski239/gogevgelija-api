from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
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

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    language_preference = models.CharField(
        max_length=2,
        choices=[('en', 'English'), ('mk', 'Macedonian')],
        default='en',
        help_text="User's preferred language"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.language_preference}"
    

class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)
    icon = models.CharField(max_length=50, help_text="Ionicon name (e.g., 'restaurant-outline')")
    image_url = models.URLField(max_length=1000, blank=True, null=True, help_text="Optional category image URL")
    trending = models.BooleanField(default=False, help_text="Show as trending category")
    show_in_events = models.BooleanField(default=True, help_text="Whether this category should be available for events")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
def listing_image_upload_to(instance, filename):
    """Generate a unique path for listing images."""
    _, ext = os.path.splitext(filename)
    ext = ext.lower() or '.jpg'
    return f"listings/{uuid.uuid4().hex}{ext}"

def promotion_image_upload_to(instance, filename):
    """Generate a unique path for promotion images."""
    _, ext = os.path.splitext(filename)
    ext = ext.lower() or '.jpg'
    return f"promotions/{uuid.uuid4().hex}{ext}"


class Listing(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, help_text="Listing description")
    address = models.CharField(max_length=500)
    open_time = models.CharField(max_length=100, help_text="e.g., 'Open until 23:00' or 'Mon-Fri 9:00-18:00'")
    working_hours = models.JSONField(
        default=dict,
        help_text="Working hours structure, e.g., {'monday': '09:00-18:00', 'tuesday': '09:00-18:00', ...}"
    )
    working_hours_mk = models.JSONField(
        default=dict,
        help_text="Working hours in Macedonian, e.g., {'понedelник': '09:00-18:00', 'вторник': '09:00-18:00', ...}"
    )
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, help_text="Select category from available categories")
    tags = models.JSONField(default=list, help_text="List of tags, e.g., ['Grill', 'Family', 'Outdoor']")
    tags_mk = models.JSONField(default=list, help_text="List of tags in Macedonian, e.g., ['Скара', 'Семејно', 'Надворешно']")
    image = models.ImageField(
        upload_to=listing_image_upload_to,
        blank=True,
        null=True,
        help_text="Listing image stored in the media bucket"
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True, help_text="Contact phone number")
    facebook_url = models.URLField(max_length=500, blank=True, null=True, help_text="Facebook page URL")
    instagram_url = models.URLField(max_length=500, blank=True, null=True, help_text="Instagram profile URL")
    website_url = models.URLField(max_length=500, blank=True, null=True, help_text="Official website URL")
    featured = models.BooleanField(default=False, help_text="Show in featured section")
    promotions = models.ManyToManyField('Promotion', blank=True, related_name='listings', help_text="Select promotions associated with this listing (optional)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title


class Event(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, help_text="Event description")
    date_time = models.CharField(max_length=100, help_text="e.g., 'Fri, 20:00' or 'Dec 25, 18:00'")
    location = models.CharField(max_length=255, help_text="Event venue/location")
    cover_image = models.URLField(max_length=1000, help_text="URL to the event cover image")
    entry_price = models.CharField(max_length=50, default="Free", help_text="Entry price (e.g., 'Free', '10 EUR', '500 MKD')")
    entry_price_mk = models.CharField(max_length=50, blank=True, help_text="Entry price in Macedonian (e.g., 'Бесплатно', '10 ЕУР', '500 МКД')")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, help_text="Select category from available categories")
    age_limit = models.CharField(max_length=50, default="All ages welcome", help_text="Age restriction (e.g., 'All ages welcome', '18+', '21+')")
    age_limit_mk = models.CharField(max_length=50, blank=True, help_text="Age restriction in Macedonian (e.g., 'Добредојдени се сите возрасти', '18+', '21+')")
    expectations = models.JSONField(default=list, help_text="List of expectations with icons, e.g., [{'icon': 'musical-notes', 'text': 'Live entertainment'}, {'icon': 'restaurant', 'text': 'Food available'}]")
    expectations_mk = models.JSONField(default=list, help_text="List of expectations in Macedonian with icons, e.g., [{'icon': 'musical-notes', 'text': 'Музика во живо'}, {'icon': 'restaurant', 'text': 'Достапна храна'}]")
    join_count = models.PositiveIntegerField(default=0, help_text="Number of users who joined this event")
    featured = models.BooleanField(default=False, help_text="Show in featured events")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
    
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
        help_text="Promotion image stored in the media bucket"
    )
    valid_until = models.DateField(null=True, blank=True, help_text="Promotion expiry date")
    featured = models.BooleanField(default=False, help_text="Show in featured promotions")
    website = models.URLField(max_length=500, blank=True, help_text="Website URL")
    phone_number = models.CharField(max_length=20, blank=True, null=True, help_text="Contact phone number")
    facebook_url = models.URLField(max_length=500, blank=True, help_text="Facebook page URL")
    instagram_url = models.URLField(max_length=500, blank=True, help_text="Instagram profile URL")
    address = models.CharField(max_length=500, blank=True, help_text="Physical address")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
    
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
    cover_image = models.URLField(max_length=1000, help_text="URL to the blog cover image")
    read_time_minutes = models.PositiveIntegerField(default=5, help_text="Estimated reading time in minutes")
    featured = models.BooleanField(default=False, help_text="Show in featured blogs")
    published = models.BooleanField(default=True, help_text="Whether the blog is published")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
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
