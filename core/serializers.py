from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.utils import translation
from .models import Category, Listing, Event, Promotion, Blog, EventJoin, Wishlist, UserProfile, UserPermission, HelpSupport, CollaborationContact, GuestUser


class CategorySerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ["id", "name", "icon", "image_url", "trending", "created_at"]
    
    def get_name(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'name_{language}', obj.name_en or obj.name)

class ListingSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    open_time = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    amenities_title = serializers.SerializerMethodField()
    amenities = serializers.SerializerMethodField()
    working_hours = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    show_open_status = serializers.SerializerMethodField()
    is_open = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True)
    image = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    promotions = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = [
            "id", "title", "description", "address", "open_time",
            "category", "tags", "amenities_title", "amenities", "working_hours", "show_open_status", "is_open",
            "image", "images", "phone_number",
            "facebook_url", "instagram_url", "website_url",
            "featured", "promotions", "created_at", "updated_at", "can_edit"
        ]
    
    def get_title(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'title_{language}', obj.title_en or obj.title)
    
    def get_description(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'description_{language}', obj.description_en or obj.description)
    
    def get_address(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'address_{language}', obj.address_en or obj.address)
    
    def get_open_time(self, obj):
        language = self.context.get('language', 'en')
        translated_value = getattr(obj, f'open_time_{language}', None)
        if translated_value:
            return translated_value
        fallback = getattr(obj, 'open_time_en', None) or obj.open_time
        return fallback or ''
    
    def get_tags(self, obj):
        language = self.context.get('language', 'en')
        if language == 'mk' and obj.tags_mk:
            return obj.tags_mk or []
        return obj.tags or []

    def get_amenities_title(self, obj):
        language = self.context.get('language', 'en')
        if language == 'mk':
            return getattr(obj, 'amenities_title_mk', 'Погодности') or getattr(obj, 'amenities_title', 'Погодности')
        return getattr(obj, 'amenities_title', 'Amenities')

    def get_amenities(self, obj):
        language = self.context.get('language', 'en')
        if language == 'mk' and obj.amenities_mk:
            return obj.amenities_mk or []
        return obj.amenities or []

    def get_working_hours(self, obj):
        language = self.context.get('language', 'en')
        if language == 'mk' and obj.working_hours_mk:
            return obj.working_hours_mk or {}
        return obj.working_hours or {}

    def get_show_open_status(self, obj):
        """Get show_open_status field with safe default."""
        return getattr(obj, 'show_open_status', False)

    def get_is_open(self, obj):
        """Calculate if the listing is currently open based on working hours."""
        try:
            # Check if the field exists (migration might not have been run yet)
            if not hasattr(obj, 'show_open_status') or not obj.show_open_status:
                return None

            working_hours = obj.working_hours
            if not working_hours or not isinstance(working_hours, dict):
                print(f"[is_open] Listing {obj.id} ({obj.title}): No working hours defined")
                return None

            # Unwrap nested working_hours structure if present
            if 'working_hours' in working_hours and isinstance(working_hours['working_hours'], dict):
                working_hours = working_hours['working_hours']

            from datetime import datetime
            import pytz

            # Get current time in Macedonia timezone (Europe/Skopje)
            try:
                tz = pytz.timezone('Europe/Skopje')
                now = datetime.now(tz)
            except:
                # Fallback to UTC if timezone not available
                now = datetime.now()

            # Get current day name in lowercase
            day_name = now.strftime('%A').lower()
            day_name_short = now.strftime('%a').lower()

            # Debug: print the working_hours structure
            print(f"[is_open] Listing {obj.id} ({obj.title}): working_hours keys = {list(working_hours.keys())}")
            print(f"[is_open] Looking for day: {day_name} or {day_name_short}")

            # Check if today's hours exist in working_hours
            if day_name not in working_hours and day_name_short not in working_hours:
                print(f"[is_open] Listing {obj.id} ({obj.title}): No hours for {day_name}")
                return False  # No hours defined for today

            hours_str = working_hours.get(day_name) or working_hours.get(day_name_short)
            if not hours_str or not isinstance(hours_str, str):
                print(f"[is_open] Listing {obj.id} ({obj.title}): Invalid hours format: {hours_str}")
                return False

            if hours_str.lower() in ['closed', 'затворено']:
                print(f"[is_open] Listing {obj.id} ({obj.title}): CLOSED (marked as closed)")
                return False

            # Parse the hours string (e.g., "09:00-18:00" or "09:00 - 18:00")
            hours_str = hours_str.replace(' ', '')
            if '-' in hours_str:
                open_time_str, close_time_str = hours_str.split('-')
                open_hour, open_min = map(int, open_time_str.split(':'))
                close_hour, close_min = map(int, close_time_str.split(':'))

                current_time = now.hour * 60 + now.minute
                open_time = open_hour * 60 + open_min
                close_time = close_hour * 60 + close_min

                # Handle cases where closing time is after midnight
                if close_time < open_time:
                    # e.g., 22:00-02:00
                    is_open = current_time >= open_time or current_time < close_time
                else:
                    is_open = open_time <= current_time < close_time

                status = "OPEN" if is_open else "CLOSED"
                print(f"[is_open] Listing {obj.id} ({obj.title}): {status} (hours: {hours_str}, current: {now.strftime('%H:%M')})")
                return is_open

            print(f"[is_open] Listing {obj.id} ({obj.title}): Invalid hours format (no dash): {hours_str}")
            return False
        except Exception as e:
            # If any error occurs, return None instead of crashing
            print(f"[is_open] Listing {obj.id} ERROR: {str(e)}")
            return None

    def get_can_edit(self, obj):
        """Check if the current user has permission to edit this listing."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        
        # Check if user has permission to edit this specific listing
        return UserPermission.objects.filter(
            user=request.user,
            listing=obj,
            can_edit=True
        ).exists()

    def get_image(self, obj):
        images = self._build_image_urls(obj)
        return images[0] if images else None

    def get_images(self, obj):
        return self._build_image_urls(obj)

    def _build_image_urls(self, obj):
        request = self.context.get('request')
        urls = []
        for field_name in ["image", "image_1", "image_2", "image_3", "image_4", "image_5"]:
            image_field = getattr(obj, field_name, None)
            if not image_field:
                continue
            try:
                url = image_field.url
            except ValueError:
                continue
            if request:
                urls.append(request.build_absolute_uri(url))
            else:
                urls.append(url)
        return urls

    def get_promotions(self, obj):
        """Return serialized promotions associated with this listing."""
        promotions = obj.promotions.all()
        if not promotions.exists():
            return []
        # Use PromotionSerializer but need to pass context for language support
        return PromotionSerializer(promotions, many=True, context=self.context).data

class EventSerializer(serializers.ModelSerializer):
    has_joined = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    entry_price = serializers.SerializerMethodField()
    age_limit = serializers.SerializerMethodField()
    expectations = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True)
    
    class Meta:
        model = Event
        fields = [
            "id", "title", "description", "date_time", "location",
            "cover_image", "entry_price", "category", "age_limit", "expectations",
            "join_count", "has_joined", "featured", "created_at", "updated_at"
        ]
    
    def get_has_joined(self, obj):
        """Check if the current user has joined this event."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        from .models import EventJoin
        return EventJoin.objects.filter(event=obj, user=request.user).exists()
    
    def get_title(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'title_{language}', obj.title_en or obj.title)
    
    def get_description(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'description_{language}', obj.description_en or obj.description)
    
    def get_location(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'location_{language}', obj.location_en or obj.location)
    
    def get_entry_price(self, obj):
        language = self.context.get('language', 'en')
        if language == 'mk' and obj.entry_price_mk:
            return obj.entry_price_mk
        return obj.entry_price
    
    def get_age_limit(self, obj):
        language = self.context.get('language', 'en')
        if language == 'mk' and obj.age_limit_mk:
            return obj.age_limit_mk
        return obj.age_limit
    
    def get_expectations(self, obj):
        language = self.context.get('language', 'en')
        if language == 'mk' and obj.expectations_mk:
            return obj.expectations_mk
        return obj.expectations

class PromotionSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    listings = serializers.SerializerMethodField()

    class Meta:
        model = Promotion
        fields = [
            "id", "title", "description", "has_discount_code", "discount_code", "tags",
            "image", "valid_until", "featured", "website", "phone_number", "facebook_url",
            "instagram_url", "address", "listings", "created_at", "updated_at"
        ]

    def get_title(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'title_{language}', obj.title_en or obj.title)

    def get_description(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'description_{language}', obj.description_en or obj.description)

    def get_address(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'address_{language}', obj.address_en or obj.address)

    def get_tags(self, obj):
        language = self.context.get('language', 'en')
        if language == 'mk' and obj.tags_mk:
            return obj.tags_mk
        return obj.tags

    def get_image(self, obj):
        """Return full URL for promotion image."""
        if not obj.image:
            return None
        try:
            url = obj.image.url
        except ValueError:
            # Image exists in DB but file missing
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(url)
        return url

    def get_listings(self, obj):
        """Return serialized listings associated with this promotion."""
        # To avoid circular import, we'll return minimal listing info
        listings = obj.listings.all()
        if not listings.exists():
            return []
        return [
            {
                'id': listing.id,
                'title': getattr(listing, f'title_{self.context.get("language", "en")}', listing.title),
                'address': getattr(listing, f'address_{self.context.get("language", "en")}', listing.address),
                'image': self._get_listing_image(listing),
            }
            for listing in listings
        ]

    def _get_listing_image(self, listing):
        """Helper to get listing image URL."""
        if not listing.image:
            return None
        try:
            url = listing.image.url
        except ValueError:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(url)
        return url

class BlogSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    subtitle = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()
    author = serializers.SerializerMethodField()
    
    class Meta:
        model = Blog
        fields = [
            "id", "title", "subtitle", "content", "author", "category", 
            "tags", "cover_image", "read_time_minutes", "featured", 
            "published", "created_at", "updated_at"
        ]
    
    def get_title(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'title_{language}', obj.title_en or obj.title)
    
    def get_subtitle(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'subtitle_{language}', obj.subtitle_en or obj.subtitle)
    
    def get_content(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'content_{language}', obj.content_en or obj.content)
    
    def get_author(self, obj):
        language = self.context.get('language', 'en')
        return getattr(obj, f'author_{language}', obj.author_en or obj.author)

class GuestUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestUser
        fields = ["guest_id", "language_preference", "created_at", "last_active"]
        read_only_fields = ["guest_id", "created_at", "last_active"]

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["language_preference", "avatar"]

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    profile = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "profile"]
    
    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email",""),
            password=validated_data["password"],
        )
        # Create user profile with default language
        UserProfile.objects.create(user=user)
        return user

class WishlistSerializer(serializers.ModelSerializer):
    item_type = serializers.CharField(read_only=True)
    item_data = serializers.SerializerMethodField()
    
    class Meta:
        model = Wishlist
        fields = ["id", "item_type", "item_data", "created_at"]
        read_only_fields = ["user", "created_at"]
    
    def get_item_data(self, obj):
        """Serialize the actual content object based on its type."""
        content_object = obj.content_object
        if isinstance(content_object, Listing):
            return ListingSerializer(content_object).data
        elif isinstance(content_object, Event):
            return EventSerializer(content_object).data
        elif isinstance(content_object, Promotion):
            return PromotionSerializer(content_object).data
        elif isinstance(content_object, Blog):
            return BlogSerializer(content_object).data
        return None

class WishlistCreateSerializer(serializers.Serializer):
    """Serializer for creating wishlist items."""
    item_type = serializers.ChoiceField(choices=['listing', 'event', 'promotion', 'blog'])
    item_id = serializers.IntegerField()
    
    def create(self, validated_data):
        user = self.context['request'].user
        item_type = validated_data['item_type']
        item_id = validated_data['item_id']
        
        # Get the content type for the model
        model_mapping = {
            'listing': Listing,
            'event': Event,
            'promotion': Promotion,
            'blog': Blog,
        }
        
        model_class = model_mapping[item_type]
        content_type = ContentType.objects.get_for_model(model_class)
        
        # Check if the item exists
        try:
            content_object = model_class.objects.get(id=item_id)
        except model_class.DoesNotExist:
            raise serializers.ValidationError(f"{item_type.capitalize()} with id {item_id} does not exist.")
        
        # Create or get the wishlist item
        wishlist_item, created = Wishlist.objects.get_or_create(
            user=user,
            content_type=content_type,
            object_id=item_id,
        )
        
        if not created:
            raise serializers.ValidationError("Item is already in wishlist.")
        
        return wishlist_item


class UserPermissionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    listing = ListingSerializer(read_only=True)
    granted_by = UserSerializer(read_only=True)
    
    class Meta:
        model = UserPermission
        fields = ["id", "user", "listing", "can_edit", "granted_by", "created_at", "updated_at"]


class CreateUserPermissionSerializer(serializers.Serializer):
    """Serializer for creating user permissions."""
    user_id = serializers.IntegerField()
    listing_id = serializers.IntegerField()
    can_edit = serializers.BooleanField(default=True)
    
    def create(self, validated_data):
        granted_by = self.context['request'].user
        
        # Get the user and listing
        try:
            user = User.objects.get(id=validated_data['user_id'])
            listing = Listing.objects.get(id=validated_data['listing_id'])
        except (User.DoesNotExist, Listing.DoesNotExist):
            raise serializers.ValidationError("User or Listing does not exist.")
        
        # Create or update the permission
        permission, created = UserPermission.objects.update_or_create(
            user=user,
            listing=listing,
            defaults={
                'can_edit': validated_data['can_edit'],
                'granted_by': granted_by
            }
        )
        
        return permission


class EditListingSerializer(serializers.ModelSerializer):
    working_hours_mk = serializers.JSONField(required=False)
    tags_mk = serializers.ListField(required=False, allow_empty=True)
    amenities_mk = serializers.JSONField(required=False)
    image = serializers.ImageField(required=False, allow_null=True)
    image_1 = serializers.ImageField(required=False, allow_null=True)
    image_2 = serializers.ImageField(required=False, allow_null=True)
    image_3 = serializers.ImageField(required=False, allow_null=True)
    image_4 = serializers.ImageField(required=False, allow_null=True)
    image_5 = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Listing
        fields = [
            # Base fields (non-translatable)
            "image", "image_1", "image_2", "image_3", "image_4", "image_5",
            "working_hours", "category", "tags", "amenities", "phone_number", 
            "facebook_url", "instagram_url", "website_url",
            # Bilingual fields
            "title_en", "title_mk", "description_en", "description_mk",
            "address_en", "address_mk", "open_time_en", "open_time_mk",
            "working_hours_mk", "tags_mk", "amenities_mk"
        ]
    
    def to_representation(self, instance):
        """Include current bilingual field values in response."""
        data = super().to_representation(instance)
        request = self.context.get('request')
        for field_name in ["image", "image_1", "image_2", "image_3", "image_4", "image_5"]:
            url = ''
            image_field = getattr(instance, field_name)
            if image_field:
                try:
                    url = image_field.url
                except ValueError:
                    url = ''
            if url and request:
                url = request.build_absolute_uri(url)
            data[field_name] = url

        # Add current values for bilingual fields with proper None handling
        data['title_en'] = getattr(instance, 'title_en', None) or ''
        data['title_mk'] = getattr(instance, 'title_mk', None) or ''
        data['description_en'] = getattr(instance, 'description_en', None) or ''
        data['description_mk'] = getattr(instance, 'description_mk', None) or ''
        data['address_en'] = getattr(instance, 'address_en', None) or ''
        data['address_mk'] = getattr(instance, 'address_mk', None) or ''
        data['open_time_en'] = getattr(instance, 'open_time_en', None) or ''
        data['open_time_mk'] = getattr(instance, 'open_time_mk', None) or ''
        data['working_hours_mk'] = getattr(instance, 'working_hours_mk', None) or {}
        data['tags_mk'] = getattr(instance, 'tags_mk', None) or []
        data['amenities_mk'] = getattr(instance, 'amenities_mk', None) or []
        
        return data
    
    def update(self, instance, validated_data):
        """Update listing with validation for bilingual fields."""
        image_fields = {
            field_name: validated_data.pop(field_name, serializers.empty)
            for field_name in ["image", "image_1", "image_2", "image_3", "image_4", "image_5"]
        }
        for attr, value in validated_data.items():
            if attr in {"working_hours", "working_hours_mk"}:
                if value in (None, ""):
                    value = {}
            if attr in {"tags", "tags_mk", "amenities", "amenities_mk"}:
                if value in (None, ""):
                    value = []
            if attr in {"open_time", "open_time_en", "open_time_mk"}:
                if value is None:
                    value = ''
            setattr(instance, attr, value)
        for field_name, value in image_fields.items():
            if value is serializers.empty:
                continue
            if value is None:
                existing = getattr(instance, field_name)
                if existing:
                    existing.delete(save=False)
                setattr(instance, field_name, None)
            else:
                setattr(instance, field_name, value)
        instance.save()
        return instance


class HelpSupportSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    responded_by = serializers.StringRelatedField(read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = HelpSupport
        fields = [
            'id', 'user', 'name', 'email', 'category', 'category_display',
            'subject', 'message', 'priority', 'priority_display', 
            'status', 'status_display', 'admin_response', 'responded_by',
            'created_at', 'updated_at', 'resolved_at'
        ]
        read_only_fields = ('user', 'admin_response', 'responded_by', 'status', 'resolved_at', 'created_at', 'updated_at')
    
    def create(self, validated_data):
        # Auto-assign the current user
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class HelpSupportCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating help support requests"""
    
    class Meta:
        model = HelpSupport
        fields = ['name', 'email', 'category', 'subject', 'message', 'priority']
    
    def create(self, validated_data):
        # Auto-assign the current user
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class CollaborationContactSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    reviewed_by = serializers.StringRelatedField(read_only=True)
    collaboration_type_display = serializers.CharField(source='get_collaboration_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = CollaborationContact
        fields = [
            'id', 'user', 'name', 'email', 'phone', 'company_name',
            'collaboration_type', 'collaboration_type_display',
            'proposal', 'timeline', 'status', 'status_display', 'admin_notes', 
            'reviewed_by', 'created_at', 'updated_at', 'review_date'
        ]
        read_only_fields = ('user', 'admin_notes', 'reviewed_by', 'status', 'review_date', 'created_at', 'updated_at')
    
    def create(self, validated_data):
        # Auto-assign the current user
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class CollaborationContactCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating collaboration contact requests"""
    
    class Meta:
        model = CollaborationContact
        fields = [
            'name', 'email', 'phone', 'company_name',
            'collaboration_type', 'proposal', 'timeline'
        ]
    
    def create(self, validated_data):
        # Auto-assign the current user
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
