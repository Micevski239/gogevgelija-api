import json
import random
from pathlib import Path
from datetime import timedelta

from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import authenticate
from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import Category, Listing, Event, Promotion, Blog, EventJoin, Wishlist, UserProfile, UserPermission, HelpSupport, CollaborationContact, GuestUser, VerificationCode
from .serializers import CategorySerializer, ListingSerializer, EventSerializer, PromotionSerializer, BlogSerializer, UserSerializer, WishlistSerializer, WishlistCreateSerializer, UserProfileSerializer, UserPermissionSerializer, CreateUserPermissionSerializer, EditListingSerializer, HelpSupportSerializer, HelpSupportCreateSerializer, CollaborationContactSerializer, CollaborationContactCreateSerializer, GuestUserSerializer
from .utils import get_preferred_language
from .pagination import StandardResultsSetPagination


class IsSuperUser(permissions.BasePermission):
    """
    Permission class that only allows access to superusers.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardResultsSetPagination

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['language'] = get_preferred_language(self.request)
        return context

    @action(detail=False, methods=['get'])
    def for_events(self, request):
        """Get categories that should be shown for events"""
        categories = Category.objects.filter(show_in_events=True).order_by('name')
        page = self.paginate_queryset(categories)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)

class ListingViewSet(viewsets.ModelViewSet):
    queryset = Listing.objects.all()
    serializer_class = ListingSerializer
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = StandardResultsSetPagination

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['language'] = get_preferred_language(self.request)
        return context

    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get only featured listings (no pagination for featured items)"""
        featured_listings = Listing.objects.filter(featured=True)
        serializer = self.get_serializer(featured_listings, many=True)
        return Response(serializer.data)

class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardResultsSetPagination

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['language'] = get_preferred_language(self.request)
        return context

    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get only featured events (no pagination for featured items)"""
        featured_events = Event.objects.filter(featured=True)
        serializer = self.get_serializer(featured_events, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.AllowAny])
    def join(self, request, pk=None):
        """Join an event - requires authenticated user (not guest)"""
        event = self.get_object()

        # Block guest users and unauthenticated users
        if not request.user.is_authenticated:
            return Response({
                'error': 'You must be logged in to join events',
                'requires_auth': True
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Check if user already joined
        existing_join = EventJoin.objects.filter(event=event, user=request.user).first()
        if existing_join:
            return Response({
                'error': 'You have already joined this event'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Create join record
        EventJoin.objects.create(event=event, user=request.user)

        # Update join count
        event.join_count = EventJoin.objects.filter(event=event).count()
        event.save()

        serializer = self.get_serializer(event)
        return Response({
            'message': 'Successfully joined the event!',
            'event': serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[permissions.AllowAny])
    def unjoin(self, request, pk=None):
        """Unjoin an event (leave the event) - requires authenticated user"""
        event = self.get_object()

        # Block guest users and unauthenticated users
        if not request.user.is_authenticated:
            return Response({
                'error': 'You must be logged in to unjoin events',
                'requires_auth': True
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Check if user has joined
        existing_join = EventJoin.objects.filter(event=event, user=request.user).first()
        if not existing_join:
            return Response({
                'error': 'You have not joined this event'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Remove join record
        existing_join.delete()

        # Update join count
        event.join_count = EventJoin.objects.filter(event=event).count()
        event.save()

        serializer = self.get_serializer(event)
        return Response({
            'message': 'Successfully left the event!',
            'event': serializer.data
        }, status=status.HTTP_200_OK)

class PromotionViewSet(viewsets.ModelViewSet):
    queryset = Promotion.objects.all()
    serializer_class = PromotionSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardResultsSetPagination

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['language'] = get_preferred_language(self.request)
        return context

    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get only featured promotions (no pagination for featured items)"""
        featured_promotions = Promotion.objects.filter(featured=True)
        serializer = self.get_serializer(featured_promotions, many=True)
        return Response(serializer.data)

class BlogViewSet(viewsets.ModelViewSet):
    queryset = Blog.objects.filter(published=True)
    serializer_class = BlogSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardResultsSetPagination

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['language'] = get_preferred_language(self.request)
        return context

    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get only featured blogs (no pagination for featured items)"""
        featured_blogs = Blog.objects.filter(featured=True, published=True)
        serializer = self.get_serializer(featured_blogs, many=True)
        return Response(serializer.data)

@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def health(_request):
    return Response({"status": "ok"})

class SendVerificationCode(APIView):
    """Send a verification code to the user's email"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        name = request.data.get('name')  # Optional, for registration

        if not email:
            return Response(
                {"error": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generate a 6-digit code
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])

        # Set expiration (15 minutes from now)
        expires_at = timezone.now() + timedelta(minutes=15)

        # Store the verification code
        VerificationCode.objects.create(
            email=email,
            code=code,
            expires_at=expires_at
        )

        # Send email asynchronously in a background thread to avoid blocking the HTTP response
        import threading
        from django.core.mail import send_mail

        def send_verification_email():
            """Send email in background thread"""
            subject = "Your GoGevgelija Verification Code"

            # Plain text message
            message = f"""
Hello{f' {name}' if name else ''},

Your verification code is: {code}

This code will expire in 15 minutes.

If you didn't request this code, please ignore this email.

Best regards,
The GoGevgelija Team
            """.strip()

            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=True,
                )
                print(f"✅ Verification code email sent to {email}: {code}")
            except Exception as e:
                print(f"⚠️ Failed to send email to {email}: {str(e)}")
                # Email failed but code is still in database

        # Start background thread for email sending
        email_thread = threading.Thread(target=send_verification_email, daemon=True)
        email_thread.start()

        # Return response immediately without waiting for email
        return Response({
            "message": "Verification code sent to your email",
            "email": email,
            # Include code in response for DEBUG mode only
            "debug_code": code if settings.DEBUG else None
        }, status=status.HTTP_200_OK)


class VerifyCode(APIView):
    """Verify the code and either log in or register the user"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        code = request.data.get('code')
        name = request.data.get('name')  # For registration

        if not email or not code:
            return Response(
                {"error": "Email and code are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find the most recent unused code for this email
        try:
            verification = VerificationCode.objects.filter(
                email=email,
                code=code,
                is_used=False
            ).latest('created_at')
        except VerificationCode.DoesNotExist:
            return Response(
                {"error": "Invalid verification code"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if code is expired
        if not verification.is_valid():
            return Response(
                {"error": "Verification code has expired"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Mark code as used
        verification.is_used = True
        verification.save()

        # Check if user exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Register new user
            if not name:
                return Response(
                    {"error": "Name is required for registration"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create user with email as username (or derive username from email)
            username = email.split('@')[0]
            counter = 1
            original_username = username
            while User.objects.filter(username=username).exists():
                username = f"{original_username}{counter}"
                counter += 1

            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=name
            )
            # No password needed for passwordless auth
            user.set_unusable_password()
            user.save()

            # Create user profile
            UserProfile.objects.create(user=user)

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        # Get profile data
        profile_data = {}
        try:
            profile = user.profile
            profile_data = {
                "language_preference": profile.language_preference,
                "avatar": profile.avatar
            }
        except UserProfile.DoesNotExist:
            # Create profile if it doesn't exist
            profile = UserProfile.objects.create(user=user)
            profile_data = {
                "language_preference": profile.language_preference,
                "avatar": profile.avatar
            }

        return Response({
            "user": {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "profile": profile_data
            },
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }, status=status.HTTP_200_OK)


class Register(APIView):
    """Legacy endpoint - kept for backwards compatibility"""
    permission_classes = [permissions.AllowAny]
    def post(self, request):
        s = UserSerializer(data = request.data)
        s.is_valid(raise_exception=True)
        user = s.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            "user": {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email
            },
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }, status = status.HTTP_201_CREATED)

class GuestLoginView(APIView):
    """View for creating guest user sessions"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """Create a new guest user and return guest_id"""
        guest_user = GuestUser.objects.create()
        serializer = GuestUserSerializer(guest_user)
        return Response({
            "guest_id": str(guest_user.guest_id),
            "language_preference": guest_user.language_preference,
            "is_guest": True
        }, status=status.HTTP_201_CREATED)

    def get(self, request):
        """Get guest user info by guest_id from query params"""
        guest_id = request.query_params.get('guest_id')
        if not guest_id:
            return Response(
                {"error": "guest_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            guest_user = GuestUser.objects.get(guest_id=guest_id)
            # Update last_active timestamp
            guest_user.save()
            serializer = GuestUserSerializer(guest_user)
            return Response(serializer.data)
        except GuestUser.DoesNotExist:
            return Response(
                {"error": "Guest user not found"},
                status=status.HTTP_404_NOT_FOUND
            )

class Me(APIView):
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        if request.user.is_authenticated:
            u = request.user
            # Include profile data in response
            profile_data = {}
            try:
                profile = u.profile
                profile_data = {
                    "language_preference": profile.language_preference,
                    "avatar": profile.avatar
                }
            except UserProfile.DoesNotExist:
                pass

            return Response({
                "id": u.id,
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "email": u.email,
                "profile": profile_data
            })
        else:
            return Response({"id": None, "username": None, "email": None, "authenticated": False})
    
    def put(self, request):
        """Update user profile"""
        user = request.user
        data = request.data

        # Update username if provided
        if 'username' in data and data['username']:
            # Check if username already exists
            if User.objects.filter(username=data['username']).exclude(id=user.id).exists():
                return Response(
                    {"error": "Username already exists"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user.username = data['username']

        # Handle password change if provided
        if 'new_password' in data and data['new_password']:
            # Verify current password if provided
            if 'current_password' in data and data['current_password']:
                if not user.check_password(data['current_password']):
                    return Response(
                        {"error": "Current password is incorrect"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Set new password
            user.set_password(data['new_password'])

        # Handle avatar change if provided
        if 'avatar' in data:
            try:
                profile = user.profile
            except UserProfile.DoesNotExist:
                profile = UserProfile.objects.create(user=user)

            # Validate avatar choice
            valid_avatars = [choice[0] for choice in UserProfile.AVATAR_CHOICES]
            if data['avatar'] in valid_avatars:
                profile.avatar = data['avatar']
                profile.save()
            else:
                return Response(
                    {"error": f"Invalid avatar. Must be one of: {', '.join(valid_avatars)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Save user changes
        user.save()

        # Include profile data in response
        profile_data = {}
        try:
            profile = user.profile
            profile_data = {
                "language_preference": profile.language_preference,
                "avatar": profile.avatar
            }
        except UserProfile.DoesNotExist:
            pass

        return Response({
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "profile": profile_data
        })

class LanguageView(APIView):
    """View for handling user and guest language preferences"""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """Get current user's or guest's language preference"""
        # Check if it's a guest user
        guest_id = request.query_params.get('guest_id')
        if guest_id:
            try:
                guest_user = GuestUser.objects.get(guest_id=guest_id)
                return Response({'language': guest_user.language_preference, 'is_guest': True})
            except GuestUser.DoesNotExist:
                return Response(
                    {'error': 'Guest user not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Authenticated user
        if request.user.is_authenticated:
            try:
                profile = request.user.profile
                return Response({'language': profile.language_preference, 'is_guest': False})
            except UserProfile.DoesNotExist:
                # Create profile if it doesn't exist
                profile = UserProfile.objects.create(user=request.user)
                return Response({'language': profile.language_preference, 'is_guest': False})

        return Response(
            {'error': 'No user or guest_id provided'},
            status=status.HTTP_400_BAD_REQUEST
        )

    def post(self, request):
        """Update user's or guest's language preference"""
        return self._handle_update(request)

    def put(self, request):
        """Allow PUT as an alias for POST for clients expecting RESTful updates."""
        return self._handle_update(request)

    def _handle_update(self, request):
        """Shared logic for mutating language preference."""
        language = request.data.get('language')

        if language not in ['en', 'mk']:
            return Response(
                {'error': 'Invalid language. Must be "en" or "mk"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if it's a guest user
        guest_id = request.data.get('guest_id')
        if guest_id:
            try:
                guest_user = GuestUser.objects.get(guest_id=guest_id)
                guest_user.language_preference = language
                guest_user.save()
                return Response({
                    'message': 'Language preference updated successfully',
                    'language': language,
                    'is_guest': True
                })
            except GuestUser.DoesNotExist:
                return Response(
                    {'error': 'Guest user not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Authenticated user
        if request.user.is_authenticated:
            try:
                profile = request.user.profile
            except UserProfile.DoesNotExist:
                profile = UserProfile.objects.create(user=request.user)

            profile.language_preference = language
            profile.save()

            return Response({
                'message': 'Language preference updated successfully',
                'language': language,
                'is_guest': False
            })

        return Response(
            {'error': 'No user or guest_id provided'},
            status=status.HTTP_400_BAD_REQUEST
        )


class TranslationResourceView(APIView):
    """Expose translation resources so the mobile app can load them dynamically."""
    permission_classes = [permissions.AllowAny]

    _ALLOWED_NAMESPACES = {"common", "screens", "navigation"}

    def get(self, request, language_code: str, namespace: str):
        available_languages = {code for code, _ in settings.LANGUAGES}
        language = language_code.lower()
        ns = namespace.lower()

        if language not in available_languages:
            return Response({'error': 'Language not supported'}, status=status.HTTP_404_NOT_FOUND)

        if ns not in self._ALLOWED_NAMESPACES:
            return Response({'error': 'Namespace not found'}, status=status.HTTP_404_NOT_FOUND)

        translations_root = getattr(settings, 'TRANSLATIONS_DIR', None)
        if not translations_root:
            return Response({'error': 'Translations directory not configured'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        resource_path = Path(translations_root) / language / f'{ns}.json'
        if not resource_path.exists():
            return Response({'error': 'Resource not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            payload = json.loads(resource_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            return Response({'error': 'Invalid translation resource'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(payload)

class WishlistViewSet(viewsets.ModelViewSet):
    serializer_class = WishlistSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return wishlist items for the current user only."""
        return Wishlist.objects.filter(user=self.request.user)

    def get_serializer_context(self):
        """Add language context for nested serializers."""
        context = super().get_serializer_context()
        context['language'] = get_preferred_language(self.request)
        return context

    def create(self, request, *args, **kwargs):
        """Add an item to the user's wishlist."""
        serializer = WishlistCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        wishlist_item = serializer.save()

        # Return the created wishlist item using the main serializer with language context
        response_serializer = WishlistSerializer(wishlist_item, context=self.get_serializer_context())
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'])
    def remove(self, request):
        """Remove an item from wishlist by item_type and item_id."""
        item_type = request.data.get('item_type')
        item_id = request.data.get('item_id')
        
        if not item_type or not item_id:
            return Response(
                {"error": "Both item_type and item_id are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the content type for the model
        model_mapping = {
            'listing': Listing,
            'event': Event,
            'promotion': Promotion,
            'blog': Blog,
        }
        
        if item_type not in model_mapping:
            return Response(
                {"error": "Invalid item_type. Must be 'listing', 'event', 'promotion', or 'blog'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        model_class = model_mapping[item_type]
        content_type = ContentType.objects.get_for_model(model_class)
        
        try:
            wishlist_item = Wishlist.objects.get(
                user=request.user,
                content_type=content_type,
                object_id=item_id
            )
            wishlist_item.delete()
            return Response({"message": "Item removed from wishlist."}, status=status.HTTP_200_OK)
        except Wishlist.DoesNotExist:
            return Response(
                {"error": "Item not found in wishlist."},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['post'])
    def check(self, request):
        """Check if an item is in the user's wishlist."""
        item_type = request.data.get('item_type')
        item_id = request.data.get('item_id')
        
        if not item_type or not item_id:
            return Response(
                {"error": "Both item_type and item_id are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the content type for the model
        model_mapping = {
            'listing': Listing,
            'event': Event,
            'promotion': Promotion,
            'blog': Blog,
        }
        
        if item_type not in model_mapping:
            return Response(
                {"error": "Invalid item_type. Must be 'listing', 'event', 'promotion', or 'blog'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        model_class = model_mapping[item_type]
        content_type = ContentType.objects.get_for_model(model_class)
        
        is_wishlisted = Wishlist.objects.filter(
            user=request.user,
            content_type=content_type,
            object_id=item_id
        ).exists()
        
        return Response({"is_wishlisted": is_wishlisted}, status=status.HTTP_200_OK)


class UserPermissionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing user permissions (superuser only)."""
    serializer_class = UserPermissionSerializer
    permission_classes = [IsSuperUser]
    
    def get_queryset(self):
        """Return all permissions. Only accessible by superusers."""
        return UserPermission.objects.all()
    
    def create(self, request, *args, **kwargs):
        """Create a new user permission."""
        serializer = CreateUserPermissionSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        permission = serializer.save()
        
        # Return the created permission using the main serializer
        response_serializer = UserPermissionSerializer(permission)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'])
    def by_user(self, request):
        """Get permissions for a specific user."""
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response(
                {"error": "user_id parameter is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        permissions = UserPermission.objects.filter(user_id=user_id)
        serializer = self.get_serializer(permissions, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_listing(self, request):
        """Get permissions for a specific listing."""
        listing_id = request.query_params.get('listing_id')
        if not listing_id:
            return Response(
                {"error": "listing_id parameter is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        permissions = UserPermission.objects.filter(listing_id=listing_id)
        serializer = self.get_serializer(permissions, many=True)
        return Response(serializer.data)


class EditListingView(APIView):
    """View for editing listings (requires permission)."""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get(self, request, listing_id):
        """Get listing details for editing."""
        try:
            listing = Listing.objects.get(id=listing_id)
        except Listing.DoesNotExist:
            return Response(
                {"error": "Listing not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if user has permission to edit this listing
        if not UserPermission.objects.filter(
            user=request.user, 
            listing=listing, 
            can_edit=True
        ).exists():
            return Response(
                {"error": "You don't have permission to edit this listing"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = EditListingSerializer(listing, context={'request': request})
        return Response(serializer.data)
    
    def patch(self, request, listing_id):
        """Update listing (requires permission)."""
        try:
            listing = Listing.objects.get(id=listing_id)
        except Listing.DoesNotExist:
            return Response(
                {"error": "Listing not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if user has permission to edit this listing
        if not UserPermission.objects.filter(
            user=request.user, 
            listing=listing, 
            can_edit=True
        ).exists():
            return Response(
                {"error": "You don't have permission to edit this listing"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = EditListingSerializer(
            listing,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        updated_listing = serializer.save()
        
        # Return the updated listing with full details
        full_serializer = ListingSerializer(updated_listing, context={'request': request})
        return Response(full_serializer.data)


class AdminUsersView(APIView):
    """View for getting all users (superuser only)."""
    permission_classes = [IsSuperUser]
    
    def get(self, request):
        """Get all users. Only accessible by superusers."""
        users = User.objects.all().order_by('username')
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)


class HelpSupportViewSet(viewsets.ModelViewSet):
    """ViewSet for Help & Support requests"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Superusers can see all requests, regular users only see their own
        if self.request.user.is_superuser:
            return HelpSupport.objects.all()
        return HelpSupport.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return HelpSupportCreateSerializer
        return HelpSupportSerializer
    
    def perform_create(self, serializer):
        # Pre-fill name and email from user profile if available
        user = self.request.user
        defaults = {}
        
        # Get name from user profile or username
        if hasattr(user, 'profile'):
            defaults['name'] = f"{user.first_name} {user.last_name}".strip() or user.username
        else:
            defaults['name'] = user.username
            
        # Get email
        defaults['email'] = user.email or ''
        
        # Apply defaults if not provided in request data
        for field, default_value in defaults.items():
            if field not in serializer.validated_data or not serializer.validated_data[field]:
                serializer.validated_data[field] = default_value
        
        serializer.save(user=user)
    
    def perform_update(self, serializer):
        # Only superusers can update admin-specific fields
        if not self.request.user.is_superuser:
            # Remove admin fields from validated_data for regular users
            admin_fields = ['status', 'admin_response', 'responded_by', 'resolved_at']
            for field in admin_fields:
                serializer.validated_data.pop(field, None)
        serializer.save()
    
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Get available help support categories with translations"""
        language = get_preferred_language(request)
        
        # Define translations
        category_translations = {
            'en': {
                'general': 'General Inquiry',
                'technical': 'Technical Issue',
                'listing': 'Listing Problem',
                'event': 'Event Issue',
                'account': 'Account Problem',
                'feedback': 'Feedback',
                'bug': 'Bug Report',
                'feature': 'Feature Request',
                'other': 'Other',
            },
            'mk': {
                'general': 'Општо прашање',
                'technical': 'Технички проблем',
                'listing': 'Проблем со листинг',
                'event': 'Проблем со настан',
                'account': 'Проблем со сметка',
                'feedback': 'Повратни информации',
                'bug': 'Пријава на грешка',
                'feature': 'Барање за функција',
                'other': 'Друго',
            }
        }
        
        translations = category_translations.get(language, category_translations['en'])
        categories = [
            {'value': choice[0], 'label': translations.get(choice[0], choice[1])} 
            for choice in HelpSupport.CATEGORY_CHOICES
        ]
        return Response(categories)
    
    @action(detail=False, methods=['get'])
    def priorities(self, request):
        """Get available priority levels with translations"""
        language = get_preferred_language(request)
        
        # Define translations
        priority_translations = {
            'en': {
                'low': 'Low',
                'medium': 'Medium',
                'high': 'High',
                'urgent': 'Urgent',
            },
            'mk': {
                'low': 'Низок',
                'medium': 'Среден',
                'high': 'Висок',
                'urgent': 'Итен',
            }
        }
        
        translations = priority_translations.get(language, priority_translations['en'])
        priorities = [
            {'value': choice[0], 'label': translations.get(choice[0], choice[1])} 
            for choice in HelpSupport.PRIORITY_CHOICES
        ]
        return Response(priorities)


class CollaborationContactViewSet(viewsets.ModelViewSet):
    """ViewSet for Collaboration Contact requests"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Superusers can see all requests, regular users only see their own
        if self.request.user.is_superuser:
            return CollaborationContact.objects.all()
        return CollaborationContact.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CollaborationContactCreateSerializer
        return CollaborationContactSerializer
    
    def perform_create(self, serializer):
        # Pre-fill name and email from user profile if available
        user = self.request.user
        defaults = {}
        
        # Get name from user profile or username
        if hasattr(user, 'profile'):
            defaults['name'] = f"{user.first_name} {user.last_name}".strip() or user.username
        else:
            defaults['name'] = user.username
            
        # Get email
        defaults['email'] = user.email or ''
        
        # Apply defaults if not provided in request data
        for field, default_value in defaults.items():
            if field not in serializer.validated_data or not serializer.validated_data[field]:
                serializer.validated_data[field] = default_value
        
        serializer.save(user=user)
    
    def perform_update(self, serializer):
        # Only superusers can update admin-specific fields
        if not self.request.user.is_superuser:
            # Remove admin fields from validated_data for regular users
            admin_fields = ['status', 'admin_notes', 'reviewed_by', 'review_date']
            for field in admin_fields:
                serializer.validated_data.pop(field, None)
        serializer.save()
    
    @action(detail=False, methods=['get'])
    def collaboration_types(self, request):
        """Get available collaboration types with translations"""
        # Get language preference from user profile
        language = 'en'
        if request.user.is_authenticated and hasattr(request.user, 'profile'):
            language = request.user.profile.language_preference
        
        # Define translations
        collaboration_type_translations = {
            'en': {
                'business': 'Business Partnership',
                'event': 'Event Collaboration',
                'marketing': 'Marketing Partnership',
                'tourism': 'Tourism Partnership',
                'other': 'Other Collaboration',
            },
            'mk': {
                'business': 'Деловно партнерство',
                'event': 'Колаборација за настани',
                'marketing': 'Маркетинг партнерство',
                'tourism': 'Туристичко партнерство',
                'other': 'Друга колаборација',
            }
        }
        
        translations = collaboration_type_translations.get(language, collaboration_type_translations['en'])
        types = [
            {'value': choice[0], 'label': translations.get(choice[0], choice[1])} 
            for choice in CollaborationContact.COLLABORATION_TYPE_CHOICES
        ]
        return Response(types)
