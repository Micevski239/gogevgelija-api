import json
import logging
import re
import secrets
import string
from pathlib import Path
from datetime import timedelta

import requests
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.throttling import AnonRateThrottle
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import authenticate
from django.db import models
from django.db import transaction
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import Category, Listing, Event, Promotion, Blog, EventJoin, Wishlist, UserProfile, UserPermission, HelpSupport, CollaborationContact, GuestUser, VerificationCode, HomeSection, HomeSectionItem, TourismCarousel, TourismCategoryButton, GalleryPhoto
from .serializers import CategorySerializer, ListingSerializer, EventSerializer, PromotionSerializer, BlogSerializer, UserSerializer, WishlistSerializer, WishlistCreateSerializer, UserProfileSerializer, UserPermissionSerializer, CreateUserPermissionSerializer, EditListingSerializer, HelpSupportSerializer, HelpSupportCreateSerializer, CollaborationContactSerializer, CollaborationContactCreateSerializer, GuestUserSerializer, HomeSectionSerializer, TourismCarouselSerializer, TourismCategoryButtonSerializer, AssistantQuerySerializer, GalleryPhotoSerializer
from .assistant_ai import AssistantAIError, get_assistant_ai_provider
from .assistant_parser import get_assistant_query_parser
from .utils import get_preferred_language
from .pagination import StandardResultsSetPagination

assistant_query_logger = logging.getLogger("assistant_queries")
core_logger = logging.getLogger("core")


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not local or not domain:
        return "***"
    visible_local = local[:1]
    return f"{visible_local}***@{domain}"


def _hash_verification_code(email: str, code: str) -> str:
    return salted_hmac("verification-code", f"{email}:{code}").hexdigest()


class VerificationCodeSendThrottle(AnonRateThrottle):
    scope = "verification_code_send"


class VerificationCodeVerifyThrottle(AnonRateThrottle):
    scope = "verification_code_verify"


class IsSuperUser(permissions.BasePermission):
    """
    Permission class that only allows access to superusers.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        """Filter queryset based on query parameters"""
        queryset = Category.objects.filter(is_active=True)

        applies_to = self.request.query_params.get('applies_to', None)
        if applies_to:
            queryset = queryset.filter(applies_to__in=[applies_to, 'both'])

        return queryset.order_by('order', 'name')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['language'] = get_preferred_language(self.request)
        return context

    @action(detail=False, methods=['get'], url_path='for-listings')
    def for_listings(self, request):
        """Get categories applicable to listings"""
        categories = Category.objects.filter(
            applies_to__in=['listing', 'both'],
            is_active=True
        ).order_by('order', 'name')

        page = self.paginate_queryset(categories)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='for-events')
    def for_events(self, request):
        """Get categories applicable to events"""
        categories = Category.objects.filter(
            applies_to__in=['event', 'both'],
            is_active=True
        ).order_by('order', 'name')

        page = self.paginate_queryset(categories)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)

    @method_decorator(cache_page(60 * 15))  # Cache for 15 minutes (categories rarely change)
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured categories"""
        categories = Category.objects.filter(
            featured=True,
            is_active=True
        ).order_by('order', 'name')

        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes (consistent with trending listings)
    @action(detail=False, methods=['get'])
    def trending(self, request):
        """Get trending categories"""
        categories = Category.objects.filter(
            trending=True,
            is_active=True
        ).order_by('order', 'name')

        page = self.paginate_queryset(categories)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)

class ListingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Listing.objects.filter(is_active=True)
    serializer_class = ListingSerializer
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        """
        Filter queryset based on query parameters.
        PERFORMANCE FIX: Added select_related and prefetch_related to avoid N+1 queries.
        Listings are ordered by random_order field for fair rotation (shuffled by cron job).
        """
        queryset = Listing.objects.filter(is_active=True) \
            .select_related('category') \
            .order_by('random_order') \
            .prefetch_related('promotions', 'events', 'user_permissions')

        # Filter by category — accepts single id or comma-separated list (e.g. "1,2,3").
        category = self.request.query_params.get('category', None)
        if category:
            ids = [i for i in category.split(',') if i.strip().isdigit()]
            if len(ids) > 1:
                queryset = queryset.filter(category_id__in=ids)
            elif ids:
                queryset = queryset.filter(category_id=ids[0])

        # Order: featured first, then random order for fair rotation
        return queryset.order_by('-featured', 'random_order')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['language'] = get_preferred_language(self.request)
        return context

    @method_decorator(cache_page(60 * 10))  # Cache for 10 minutes
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get only featured listings (no pagination for featured items)"""
        featured_listings = Listing.objects.filter(featured=True, is_active=True) \
            .select_related('category') \
            .prefetch_related('promotions', 'events')
        serializer = self.get_serializer(featured_listings, many=True)
        return Response(serializer.data)

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    @action(detail=False, methods=['get'])
    def trending(self, request):
        """Get only trending listings (no pagination for trending items)"""
        trending_listings = Listing.objects.filter(trending=True, is_active=True) \
            .select_related('category') \
            .prefetch_related('promotions', 'events')
        serializer = self.get_serializer(trending_listings, many=True)
        return Response(serializer.data)

class EventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Event.objects.filter(is_active=True)
    serializer_class = EventSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        """
        PERFORMANCE FIX: Added select_related and prefetch_related to avoid N+1 queries.
        Also prefetch event joins for current user to optimize has_joined checks.
        """
        queryset = Event.objects.filter(is_active=True) \
            .select_related('category') \
            .prefetch_related('listings')

        # Prefetch user's event joins if authenticated
        if self.request.user.is_authenticated:
            from django.db.models import Prefetch
            queryset = queryset.prefetch_related(
                Prefetch(
                    'joined_users',  # FIX: Use correct related_name from EventJoin model
                    queryset=EventJoin.objects.filter(user=self.request.user),
                    to_attr='user_joins'
                )
            )

        return queryset.order_by('-featured', '-created_at')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['language'] = get_preferred_language(self.request)
        return context

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def list(self, request, *args, **kwargs):
        """Get all events with caching"""
        return super().list(request, *args, **kwargs)

    @method_decorator(cache_page(60 * 3))  # Cache for 3 minutes (events change more frequently)
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get only featured events (no pagination for featured items)"""
        featured_events = Event.objects.filter(featured=True, is_active=True) \
            .select_related('category') \
            .prefetch_related('listings')

        # Prefetch user joins for has_joined optimization
        if request.user.is_authenticated:
            from django.db.models import Prefetch
            featured_events = featured_events.prefetch_related(
                Prefetch(
                    'joined_users',  # FIX: Use correct related_name from EventJoin model
                    queryset=EventJoin.objects.filter(user=request.user),
                    to_attr='user_joins'
                )
            )

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

        # PERFORMANCE FIX: Update join count using F() expression instead of counting all joins
        from django.db.models import F
        Event.objects.filter(pk=event.pk).update(join_count=F('join_count') + 1)
        event.refresh_from_db()  # Refresh to get updated count

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

        # PERFORMANCE FIX: Update join count using F() expression instead of counting all joins
        from django.db.models import F
        Event.objects.filter(pk=event.pk).update(join_count=F('join_count') - 1)
        event.refresh_from_db()  # Refresh to get updated count

        serializer = self.get_serializer(event)
        return Response({
            'message': 'Successfully left the event!',
            'event': serializer.data
        }, status=status.HTTP_200_OK)

class PromotionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Promotion.objects.filter(is_active=True)
    serializer_class = PromotionSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        """
        PERFORMANCE FIX: Added prefetch_related to avoid N+1 queries.
        Note: Promotion has no category ForeignKey, only CharField choices for Blog.
        """
        return Promotion.objects.filter(is_active=True) \
            .prefetch_related('listings') \
            .order_by('-created_at')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['language'] = get_preferred_language(self.request)
        return context

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def list(self, request, *args, **kwargs):
        """Get all promotions with caching"""
        return super().list(request, *args, **kwargs)

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get only featured promotions (no pagination for featured items)"""
        featured_promotions = Promotion.objects.filter(featured=True, is_active=True) \
            .prefetch_related('listings')
        serializer = self.get_serializer(featured_promotions, many=True)
        return Response(serializer.data)

class BlogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Blog.objects.filter(published=True, is_active=True)
    serializer_class = BlogSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        """
        PERFORMANCE FIX: Optimized query ordering.
        Note: Blog.category is a CharField (not ForeignKey), so no select_related needed.
        """
        return Blog.objects.filter(published=True, is_active=True) \
            .order_by('-created_at')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['language'] = get_preferred_language(self.request)
        return context

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def list(self, request, *args, **kwargs):
        """Get all blogs with caching"""
        return super().list(request, *args, **kwargs)

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get only featured blogs (no pagination for featured items)"""
        featured_blogs = Blog.objects.filter(featured=True, published=True, is_active=True)
        serializer = self.get_serializer(featured_blogs, many=True)
        return Response(serializer.data)

@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def health(_request):
    return Response({"status": "ok"})

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def app_config(_request):
    """
    Returns app configuration including version requirements.
    Controlled via environment variables — no redeploy needed to toggle force_update.
      APP_MIN_SUPPORTED_VERSION, APP_LATEST_VERSION, APP_FORCE_UPDATE
    """
    return Response({
        "status": "ok",
        "min_supported_version": settings.APP_MIN_SUPPORTED_VERSION,
        "latest_version": settings.APP_LATEST_VERSION,
        "force_update": settings.APP_FORCE_UPDATE,
        "update_message": {
            "en": "A new version of GoGevgelija is available! Update now for the latest features.",
            "mk": "Нова верзија на GoGevgelija е достапна! Ажурирајте сега за најновите функции.",
        },
    })


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def currency_rates(_request):
    cache_key = "currency-rates-latest"
    cached_payload = cache.get(cache_key)
    if cached_payload:
        return Response(cached_payload)

    try:
        response = requests.get(
            settings.CURRENCY_RATES_URL,
            timeout=settings.CURRENCY_RATES_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        core_logger.exception("Failed to fetch currency rates from upstream provider")
        return Response(
            {"error": "Unable to fetch currency rates right now"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if data.get("result") != "success":
        return Response(
            {"error": "Currency provider returned an invalid response"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    tracked_codes = ("EUR", "USD", "GBP", "CHF", "TRY", "RSD", "BGN", "ALL", "CAD", "AUD", "JPY", "SEK")
    rates: dict[str, float] = {}
    for code in tracked_codes:
        rate = data.get("rates", {}).get(code)
        if rate:
            rates[code] = 1 / rate

    payload = {
        "rates": rates,
        "lastUpdated": data.get("time_last_update_utc") or timezone.now().isoformat(),
    }
    cache.set(cache_key, payload, 60 * 30)
    return Response(payload)

class SendVerificationCode(APIView):
    """Send a verification code to the user's email"""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [VerificationCodeSendThrottle]

    def post(self, request):
        email = _normalize_email(request.data.get('email'))
        name = request.data.get('name')  # Optional, for registration

        if not email:
            return Response(
                {"error": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            validate_email(email)
        except ValidationError:
            return Response(
                {"error": "A valid email address is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate a 6-digit code
        code = ''.join(secrets.choice(string.digits) for _ in range(6))

        # Set expiration (15 minutes from now)
        expires_at = timezone.now() + timedelta(minutes=15)
        code_hash = _hash_verification_code(email, code)
        masked_email = _mask_email(email)

        subject = "Your GoGevgelija Verification Code"
        message = f"""
Hello{f' {name}' if name else ''},

Your verification code is: {code}

This code will expire in 15 minutes.

If you didn't request this code, please ignore this email.

Best regards,
The GoGevgelija Team
        """.strip()

        try:
            with transaction.atomic():
                VerificationCode.objects.filter(email=email, is_used=False).update(is_used=True)
                VerificationCode.objects.create(
                    email=email,
                    code=code_hash,
                    expires_at=expires_at,
                )
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
        except Exception:
            core_logger.exception("Failed to send verification code email for %s", masked_email)
            return Response(
                {"error": "Unable to send verification code right now"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        core_logger.info("Verification code email sent to %s", masked_email)

        return Response({
            "message": "Verification code sent to your email",
            "email": email,
            # Include code in response for DEBUG mode only
            "debug_code": code if settings.DEBUG else None
        }, status=status.HTTP_200_OK)


class VerifyCode(APIView):
    """Verify the code and either log in or register the user"""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [VerificationCodeVerifyThrottle]

    def post(self, request):
        email = _normalize_email(request.data.get('email'))
        code = (request.data.get('code') or '').strip()
        name = (request.data.get('name') or '').strip()  # For registration

        if not email or not code:
            return Response(
                {"error": "Email and code are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            validate_email(email)
        except ValidationError:
            return Response(
                {"error": "A valid email address is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        verification = VerificationCode.objects.filter(
            email=email,
            is_used=False,
        ).order_by('-created_at').first()
        if not verification:
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

        if not constant_time_compare(verification.code, _hash_verification_code(email, code)):
            return Response(
                {"error": "Invalid verification code"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Mark code as used
        verification.is_used = True
        verification.save()

        matching_users = User.objects.filter(email__iexact=email).order_by('date_joined')
        if matching_users.count() > 1:
            core_logger.warning("Duplicate user emails detected for %s", _mask_email(email))
            return Response(
                {"error": "This email is linked to multiple accounts. Please contact support."},
                status=status.HTTP_409_CONFLICT,
            )

        user = matching_users.first()
        if user is None:
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
    """Legacy endpoint — disabled. Use /api/auth/send-code/ + /api/auth/verify-code/ instead."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        return Response(
            {"error": "This endpoint is no longer available. Please use the verification code flow: POST /api/auth/send-code/ then POST /api/auth/verify-code/"},
            status=status.HTTP_410_GONE,
        )


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT serializer that includes user profile data"""

    def validate(self, attrs):
        data = super().validate(attrs)

        # Add user profile data to the response
        user = self.user
        data['user'] = {
            'id': user.id,
            'username': user.username,
            'email': user.email
        }

        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom JWT login view that includes user profile data in response"""
    serializer_class = CustomTokenObtainPairSerializer


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
        # CRITICAL FIX: Verify user is authenticated before accessing profile
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED
            )

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

    _ALLOWED_NAMESPACES = {"common", "screens", "navigation", "legal"}

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


ASSISTANT_BORDER_CAMERA_URL = "https://roads.org.mk/patna-mreza/video-kameri/"
ASSISTANT_ENTITY_SCREEN_MAP = {
    'listing': 'listing_detail',
    'event': 'event_detail',
    'promotion': 'promotion_detail',
    'blog': 'blog_detail',
}


def _localized_text(language, en_text, mk_text):
    return mk_text if language == 'mk' else en_text


def _normalize_assistant_message(message):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]+", " ", message.lower())).strip()


def _assistant_augmented_message(normalized_message, understanding):
    canonical_terms = (understanding or {}).get('canonical_terms') or []
    if not canonical_terms:
        return normalized_message
    return " ".join(part for part in [normalized_message, " ".join(canonical_terms)] if part).strip()


def _assistant_action(action_type, label, screen=None, params=None, url=None):
    payload = {
        'type': action_type,
        'label': label,
    }
    if screen:
        payload['screen'] = screen
    if params:
        payload['params'] = params
    if url:
        payload['url'] = url
    return payload


def _assistant_response(
    answer,
    intent,
    confidence,
    results=None,
    actions=None,
    suggestions=None,
    resolved_context=None,
):
    return {
        'answer': answer,
        'intent': intent,
        'confidence': confidence,
        'results': results or [],
        'actions': actions or [],
        'suggestions': suggestions or [],
        'resolved_context': resolved_context,
    }


def _assistant_context_payload(screen=None, entity_type=None, entity_id=None, entity_label=None):
    if not entity_type or not entity_id:
        return None
    return {
        'screen': screen or ASSISTANT_ENTITY_SCREEN_MAP.get(entity_type),
        'entity_type': entity_type,
        'entity_id': entity_id,
        'entity_label': entity_label,
    }


def _assistant_result_to_context(result_type, data, screen=None):
    entity_label = data.get('title') or data.get('name') or data.get('subject')
    return _assistant_context_payload(
        screen=screen or ASSISTANT_ENTITY_SCREEN_MAP.get(result_type),
        entity_type=result_type,
        entity_id=data.get('id'),
        entity_label=entity_label,
    )


def _assistant_message_mentions(normalized_message, keywords):
    return any(keyword in normalized_message for keyword in keywords)


def _assistant_default_suggestions(language):
    return [
        _localized_text(language, "Show me hotels", "Покажи ми сместување"),
        _localized_text(language, "What events are coming up?", "Кои настани се претстојни?"),
        _localized_text(language, "Any deals right now?", "Има ли актуелни понуди?"),
        _localized_text(language, "How do I change language?", "Како да го сменам јазикот?"),
    ]


def _assistant_context_suggestions(language, context_entity):
    if not context_entity:
        return _assistant_default_suggestions(language)

    entity_type = context_entity['entity_type']
    if entity_type == 'listing':
        return [
            _localized_text(language, "Is this place open now?", "Дали ова место е отворено сега?"),
            _localized_text(language, "Call this place", "Јави се на ова место"),
            _localized_text(language, "Show promotions here", "Покажи промоции за ова место"),
            _localized_text(language, "How do I get there?", "Како да стигнам таму?"),
        ]
    if entity_type == 'event':
        return [
            _localized_text(language, "When is this event?", "Кога е овој настан?"),
            _localized_text(language, "What is the entry price?", "Која е цената за влез?"),
            _localized_text(language, "How do I get there?", "Како да стигнам таму?"),
            _localized_text(language, "Where is this event available?", "Каде е достапен овој настан?"),
        ]
    if entity_type == 'promotion':
        return [
            _localized_text(language, "What is the discount code?", "Кој е кодот за попуст?"),
            _localized_text(language, "Where can I use this?", "Каде можам да го користам ова?"),
            _localized_text(language, "Call them", "Јави им се"),
            _localized_text(language, "When does this expire?", "Кога истекува ова?"),
        ]
    if entity_type == 'blog':
        return [
            _localized_text(language, "Summarize this article", "Сумирај ја оваа статија"),
            _localized_text(language, "Open the related link", "Отвори го поврзаниот линк"),
            _localized_text(language, "What is this article about?", "За што е оваа статија?"),
        ]
    return _assistant_default_suggestions(language)


def _assistant_current_context_payload(context_entity):
    if not context_entity:
        return None
    return _assistant_context_payload(
        screen=context_entity.get('screen'),
        entity_type=context_entity.get('entity_type'),
        entity_id=context_entity.get('entity_id'),
        entity_label=context_entity.get('entity_label') or context_entity.get('data', {}).get('title'),
    )


def _assistant_finalize_response(payload, language, context_entity=None, understanding=None):
    payload.setdefault('results', [])
    payload.setdefault('actions', [])
    payload.setdefault('suggestions', _assistant_context_suggestions(language, context_entity))
    payload.setdefault('resolved_context', _assistant_current_context_payload(context_entity))
    if understanding is not None:
        payload.setdefault('understanding', understanding)
    return payload


def _assistant_log_query(request, message, language, context_data, history, understanding, response_payload):
    if not getattr(settings, 'ASSISTANT_QUERY_LOGGING_ENABLED', True):
        return

    results = response_payload.get('results') or []
    resolved_context = response_payload.get('resolved_context') or {}
    log_payload = {
        'message': message,
        'language': language,
        'actor': {
            'is_authenticated': bool(getattr(request.user, 'is_authenticated', False)),
            'user_id': request.user.id if getattr(request.user, 'is_authenticated', False) else None,
        },
        'request_context': {
            'screen': context_data.get('screen'),
            'entity_type': context_data.get('entity_type'),
            'entity_id': context_data.get('entity_id'),
        },
        'history_count': len(history or []),
        'understanding': {
            'provider': understanding.get('provider'),
            'confidence': understanding.get('confidence'),
            'intent': understanding.get('intent'),
            'tool': understanding.get('tool'),
            'faq_intent': understanding.get('faq_intent'),
            'entity_type': understanding.get('entity_type'),
            'content_type': understanding.get('content_type'),
            'category_key': understanding.get('category_key'),
            'filters': understanding.get('filters') or {},
            'unsupported_filters': understanding.get('unsupported_filters') or [],
            'canonical_terms': understanding.get('canonical_terms') or [],
            'matched_terms': understanding.get('matched_terms') or [],
            'search_query': understanding.get('search_query'),
        },
        'response': {
            'intent': response_payload.get('intent'),
            'confidence': response_payload.get('confidence'),
            'results_count': len(results),
            'result_types': [item.get('type') for item in results[:5] if item.get('type')],
            'actions_count': len(response_payload.get('actions') or []),
            'resolved_context': {
                'screen': resolved_context.get('screen'),
                'entity_type': resolved_context.get('entity_type'),
                'entity_id': resolved_context.get('entity_id'),
            },
        },
    }

    assistant_query_logger.info(json.dumps(log_payload, ensure_ascii=False))


def _assistant_external_ai_context(context_data, context_entity):
    payload = {
        'screen': (context_data or {}).get('screen'),
        'entity_type': (context_data or {}).get('entity_type'),
        'entity_id': (context_data or {}).get('entity_id'),
    }

    if context_entity:
        payload.update(_assistant_current_context_payload(context_entity) or {})
        payload['entity_title'] = context_entity.get('entity_label') or context_entity.get('data', {}).get('title')

    return {key: value for key, value in payload.items() if value not in (None, '', [])}


_ASSISTANT_CATALOG_CACHE_KEY = "assistant:catalog:v1"
_ASSISTANT_CATALOG_TTL = 3600   # 60 min — catalog rarely changes intraday
_ASSISTANT_PLAN_CACHE_TTL = 1800  # 30 min — repeated queries stay cached longer


def _assistant_build_catalog():
    """Return cached slug list + top-entity catalog fed into Groq's planner prompt.

    Kept small and cached to avoid per-request DB work.
    """
    from django.core.cache import cache

    cached = cache.get(_ASSISTANT_CATALOG_CACHE_KEY)
    if cached:
        return cached

    category_slugs = list(
        Category.objects
        .filter(is_active=True)
        .exclude(slug__isnull=True)
        .exclude(slug__exact='')
        .values_list('slug', flat=True)
        .order_by('order', 'name')[:80]
    )

    entities = []
    for listing in Listing.objects.filter(is_active=True).only('id', 'title', 'title_mk')[:60]:
        entities.append({
            'type': 'listing',
            'id': listing.id,
            'title': listing.title or '',
            'title_mk': getattr(listing, 'title_mk', '') or '',
        })
    for event in Event.objects.filter(is_active=True).only('id', 'title', 'title_mk')[:20]:
        entities.append({
            'type': 'event',
            'id': event.id,
            'title': event.title or '',
            'title_mk': getattr(event, 'title_mk', '') or '',
        })
    for promo in Promotion.objects.filter(is_active=True).only('id', 'title', 'title_mk')[:15]:
        entities.append({
            'type': 'promotion',
            'id': promo.id,
            'title': promo.title or '',
            'title_mk': getattr(promo, 'title_mk', '') or '',
        })

    payload = {'category_slugs': category_slugs, 'entities': entities}
    cache.set(_ASSISTANT_CATALOG_CACHE_KEY, payload, _ASSISTANT_CATALOG_TTL)
    return payload


def _assistant_plan_cache_key(message, language, context_data):
    import hashlib
    context_sig = json.dumps(
        {
            'entity_type': (context_data or {}).get('entity_type'),
            'entity_id': (context_data or {}).get('entity_id'),
        },
        sort_keys=True,
    )
    raw = f"{(message or '').strip().lower()}|{language}|{context_sig}"
    digest = hashlib.sha1(raw.encode('utf-8')).hexdigest()
    return f"assistant:plan:{digest}"


def _assistant_time_filter_range(time_filter):
    """Return (start, end) datetime range for a time_filter hint, or (None, None)."""
    if not time_filter:
        return None, None
    now = timezone.localtime()
    if time_filter == 'tonight':
        start = now.replace(hour=17, minute=0, second=0, microsecond=0)
        end = (now + timedelta(days=1)).replace(hour=4, minute=0, second=0, microsecond=0)
        return start, end
    if time_filter == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end
    if time_filter == 'this_week':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        return start, end
    if time_filter == 'weekend':
        weekday = now.weekday()  # Mon=0..Sun=6
        days_to_sat = (5 - weekday) % 7
        start = (now + timedelta(days=days_to_sat)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=2)
        return start, end
    return None, None


def _assistant_lookup_resolved_entity(entity_type, entity_id, language, request):
    """Hydrate a single entity Groq said matches, return a serialized payload dict or None."""
    if not entity_type or not entity_id:
        return None
    ctx = {'request': request, 'language': language}
    try:
        if entity_type == 'listing':
            obj = Listing.objects.filter(id=entity_id, is_active=True).first()
            return ListingSerializer(obj, context=ctx).data if obj else None
        if entity_type == 'event':
            obj = Event.objects.filter(id=entity_id, is_active=True).first()
            return EventSerializer(obj, context=ctx).data if obj else None
        if entity_type == 'promotion':
            obj = Promotion.objects.filter(id=entity_id, is_active=True).first()
            return PromotionSerializer(obj, context=ctx).data if obj else None
        if entity_type == 'blog':
            obj = Blog.objects.filter(id=entity_id, is_active=True, published=True).first()
            return BlogSerializer(obj, context=ctx).data if obj else None
    except Exception as exc:  # pragma: no cover — defensive
        core_logger.warning("Assistant resolved_entity lookup failed: %s", exc)
    return None


def _assistant_resolved_entity_response(entity_type, data, language, request=None):
    """Compose a single-entity response. For listings, appends related active promotions."""
    builders = {
        'listing': _assistant_listing_answer,
        'event': _assistant_event_answer,
        'promotion': _assistant_promotion_answer,
        'blog': _assistant_blog_answer,
    }
    builder = builders.get(entity_type)
    answer = builder(data, language) if builder else None
    if not answer:
        return None

    results = [{'type': entity_type, 'data': data}]

    if entity_type == 'listing' and data.get('id') and request is not None:
        today = timezone.now().date()
        listing_obj = Listing.objects.filter(id=data['id']).prefetch_related('promotions').first()
        if listing_obj:
            related_promos = listing_obj.promotions.filter(
                is_active=True,
            ).filter(
                models.Q(valid_until__gte=today) | models.Q(valid_until__isnull=True)
            )[:2]
            ctx = {'request': request, 'language': language}
            for promo in related_promos:
                promo_data = PromotionSerializer(promo, context=ctx).data
                results.append({'type': 'promotion', 'data': promo_data})

    return _assistant_response(
        answer=answer,
        intent=f"{entity_type}_match",
        confidence='high',
        results=results,
        actions=[],
        suggestions=_assistant_context_suggestions(
            language,
            {
                'entity_type': entity_type,
                'entity_id': data.get('id'),
                'entity_label': data.get('title'),
                'screen': ASSISTANT_ENTITY_SCREEN_MAP.get(entity_type),
                'data': data,
            },
        ),
        resolved_context=_assistant_result_to_context(entity_type, data),
    )


def _assistant_category_by_hint(category_slug, language, request, limit=5):
    """Look up a category by slug, return its top listings as a response payload."""
    if not category_slug:
        return None
    category = Category.objects.filter(slug=category_slug, is_active=True).first()
    if not category:
        return None
    listings = Listing.objects.filter(category=category, is_active=True).select_related('category')[:limit]
    serialized = ListingSerializer(listings, many=True, context={'request': request, 'language': language}).data
    if not serialized:
        return None
    display_name = getattr(category, 'name_mk' if language == 'mk' else 'name_en', None) or category.name
    answer = _localized_text(
        language,
        f"Here are {display_name} places I found.",
        f"Еве места од категоријата {display_name}.",
    )
    return {
        'answer': answer,
        'intent': f"category_{category_slug}",
        'confidence': 'high',
        'results': [{'type': 'listing', 'data': item} for item in serialized],
        'actions': [],
        'suggestions': _assistant_default_suggestions(language),
    }


def _assistant_bilingual_search(query_en, query_mk, content_type, language, request, time_filter=None, open_now=False, price_filter=None, limit=3):
    """Search across bilingual fields with EN + MK terms combined, apply optional filters.

    Strategy: prefer title+description matches; only fall back to category-name matches when
    nothing else hits. This prevents broad category labels (e.g. "Services") from surfacing
    irrelevant listings for specific queries (e.g. "my car broke down").
    """
    from django.db.models import Q

    terms = [t.strip() for t in [query_en, query_mk] if t and t.strip()]
    if not terms:
        return {'listings': [], 'events': [], 'promotions': [], 'blogs': [], 'total_count': 0, 'query': ''}

    # Also search individual words from multi-word phrases so "good cocktail" matches "cocktail bar"
    extra = [w for t in terms for w in t.split() if len(w) >= 3 and w not in terms]
    terms = list(dict.fromkeys(terms + extra))

    def or_match(fields):
        q = Q()
        for term in terms:
            for field in fields:
                q |= Q(**{f"{field}__icontains": term})
        return q

    CONTENT_FIELDS = ['title', 'title_en', 'title_mk', 'address', 'description', 'description_en', 'description_mk']
    CATEGORY_FIELDS = ['category__name', 'category__name_en', 'category__name_mk']

    def listing_qs(match_q):
        return Listing.objects.filter(match_q, is_active=True).select_related('category').distinct()

    def serialize_listings(qs):
        ctx = {'request': request, 'language': language}
        if open_now:
            batch = list(qs[:limit * 2])
            serialized_all = ListingSerializer(batch, many=True, context=ctx).data
            return [l for l in serialized_all if l.get('is_open')][:limit]
        return ListingSerializer(qs[:limit], many=True, context=ctx).data

    ctx = {'request': request, 'language': language}
    results = {'listings': [], 'events': [], 'promotions': [], 'blogs': []}

    if content_type in ('all', 'listings'):
        # Try content-only match first; fall back to including category names only if empty
        qs = listing_qs(or_match(CONTENT_FIELDS))
        if not qs.exists():
            qs = listing_qs(or_match(CONTENT_FIELDS + CATEGORY_FIELDS))
        results['listings'] = serialize_listings(qs)

    if content_type in ('all', 'events'):
        event_content_fields = ['title', 'title_en', 'title_mk', 'location', 'description', 'description_en', 'description_mk']
        event_category_fields = ['category__name', 'category__name_en', 'category__name_mk']
        qs = Event.objects.filter(or_match(event_content_fields), is_active=True).select_related('category').distinct()
        if not qs.exists():
            qs = Event.objects.filter(or_match(event_content_fields + event_category_fields), is_active=True).select_related('category').distinct()
        start, end = _assistant_time_filter_range(time_filter)
        if start and end:
            qs = qs.filter(date_time__gte=start, date_time__lt=end)
        if price_filter == 'cheap':
            qs = qs.filter(entry_price__iregex=r'(?i)(^|\b)(free|бесплатно|0(\s|$))')
        elif price_filter == 'premium':
            qs = qs.exclude(entry_price__iregex=r'(?i)(^|\b)(free|бесплатно|0(\s|$))').exclude(
                entry_price__isnull=True
            ).exclude(entry_price='')
        results['events'] = EventSerializer(qs[:limit], many=True, context=ctx).data

    if content_type in ('all', 'promotions'):
        today = timezone.now().date()
        qs = Promotion.objects.filter(
            or_match(['title', 'title_en', 'title_mk', 'description', 'description_en', 'description_mk', 'discount_code']),
            is_active=True,
        ).filter(
            models.Q(valid_until__gte=today) | models.Q(valid_until__isnull=True)
        ).order_by('valid_until').distinct()
        results['promotions'] = PromotionSerializer(qs[:limit], many=True, context=ctx).data

    if content_type in ('all', 'blogs'):
        qs = Blog.objects.filter(
            or_match(['title', 'title_en', 'title_mk', 'subtitle', 'subtitle_en', 'subtitle_mk',
                      'content', 'content_en', 'content_mk']),
            is_active=True, published=True,
        ).distinct()
        results['blogs'] = BlogSerializer(qs[:limit], many=True, context=ctx).data

    total = sum(len(v) for v in results.values())
    return {**results, 'total_count': total, 'query': query_en or query_mk or ''}


def _assistant_bilingual_search_response(plan, language, request, context_entity):
    query_en = (plan.get('normalized_query_en') or '').strip()
    query_mk = (plan.get('normalized_query_mk') or '').strip()
    content_type = (plan.get('content_type') or 'all').strip().lower()
    time_filter = plan.get('time_filter')
    open_now = bool(plan.get('open_now_requested'))
    price_filter = plan.get('price_filter')

    search = _assistant_bilingual_search(
        query_en, query_mk, content_type, language, request,
        time_filter=time_filter, open_now=open_now, price_filter=price_filter, limit=3,
    )
    total = search['total_count']
    display_query = query_en or query_mk or (plan.get('tool_query') or '').strip()

    if total == 0:
        return _assistant_response(
            answer=_localized_text(
                language,
                f"I couldn't find anything for \"{display_query}\". Try different words or a category.",
                f"Не најдов ништо за „{display_query}“. Обидете се со други зборови или категорија.",
            ),
            intent='fallback',
            confidence='low',
            suggestions=_assistant_context_suggestions(language, context_entity),
            resolved_context=_assistant_current_context_payload(context_entity),
        )

    flattened = []
    for plural in ('listings', 'events', 'promotions', 'blogs'):
        singular = plural[:-1]
        flattened.extend({'type': singular, 'data': item} for item in search[plural])

    top = flattened[0]
    actions = [
        _assistant_action(
            'navigate',
            _localized_text(language, "Open Search Results", "Отвори резултати од пребарување"),
            screen='SearchResults',
            params={'query': display_query},
        )
    ]

    if total == 1:
        builders = {
            'listing': _assistant_listing_answer,
            'event': _assistant_event_answer,
            'promotion': _assistant_promotion_answer,
            'blog': _assistant_blog_answer,
        }
        builder = builders.get(top['type'])
        answer = builder(top['data'], language) if builder else _localized_text(language, "I found one match.", "Пронајдов еден резултат.")
        return _assistant_response(
            answer=answer,
            intent=f"{top['type']}_match",
            confidence='high',
            results=[top],
            actions=actions,
            suggestions=_assistant_context_suggestions(
                language,
                {
                    'entity_type': top['type'],
                    'entity_id': top['data'].get('id'),
                    'entity_label': top['data'].get('title'),
                    'screen': ASSISTANT_ENTITY_SCREEN_MAP.get(top['type']),
                    'data': top['data'],
                },
            ),
            resolved_context=_assistant_result_to_context(top['type'], top['data']),
        )

    return _assistant_response(
        answer=_localized_text(
            language,
            f'I found {total} results for "{display_query}". Here are the top matches.',
            f'Пронајдов {total} резултати за „{display_query}“. Еве ги најрелевантните.',
        ),
        intent='search_results',
        confidence='medium',
        results=flattened,
        actions=actions,
        suggestions=_assistant_search_suggestions(language, display_query),
        resolved_context=_assistant_current_context_payload(context_entity),
    )


def _build_goai_results_summary(tool_response) -> str:
    results = (tool_response or {}).get('results') or []
    if not results:
        return ''
    lines = []
    for r in results[:6]:
        rtype = r.get('type', '')
        data = r.get('data') or {}
        title = data.get('title') or data.get('name') or '?'
        if rtype == 'listing':
            cat_data = data.get('category') or {}
            cat = cat_data.get('name') if isinstance(cat_data, dict) else ''
            lines.append(f"- listing: {title}" + (f" ({cat})" if cat else ""))
        elif rtype == 'event':
            date = (data.get('date_time') or '')[:10]
            lines.append(f"- event: {title}" + (f" on {date}" if date else ""))
        elif rtype == 'promotion':
            lines.append(f"- promotion: {title}")
        elif rtype == 'blog':
            lines.append(f"- blog: {title}")
        else:
            lines.append(f"- {rtype}: {title}")
    return "\n".join(lines)


def _plan_from_parser(parsed: dict, message: str) -> dict:
    """Convert a parser understanding dict to a plan dict compatible with _assistant_execute_ai_plan."""
    time_filter = None
    if parsed.get('filters', {}).get('today'):
        time_filter = 'today'
    return {
        'tool': parsed.get('tool') or 'search',
        'tool_query': parsed.get('search_query') or message,
        'wiki_query': parsed.get('wiki_query') or '',
        'confidence': parsed.get('confidence') or 'medium',
        'intent': parsed.get('intent') or 'unknown',
        'content_type': parsed.get('content_type') or 'all',
        'normalized_query_en': parsed.get('search_query') or message,
        'normalized_query_mk': '',
        'category_hint': parsed.get('category_key'),
        'entity_type_hint': parsed.get('entity_type'),
        'time_filter': time_filter,
        'price_filter': None,
        'open_now_requested': bool(parsed.get('filters', {}).get('open_now')),
        'followup_of_entity_id': None,
        'clarification_question': None,
    }


def _assistant_try_parser_first_response(message, language, history, request, context_entity, parsed_dict):
    """Execute a DB or wiki tool using the parser result, then call generate_display_message for quality.
    Saves one LLM call (plan_query) compared to the full pipeline."""
    from .assistant_ai import get_assistant_ai_provider, AssistantAIError

    plan = _plan_from_parser(parsed_dict, message)
    tool_response = _assistant_execute_ai_plan(plan, message, language, request, context_entity)
    if not tool_response:
        return None

    provider = get_assistant_ai_provider()
    if provider and plan.get('tool') not in ('faq', 'clarify'):
        results_summary = _build_goai_results_summary(tool_response)
        wiki_context = tool_response.pop('wiki_context', '')
        try:
            goai_answer = provider.generate_display_message(
                user_message=message,
                language=language,
                tool=plan.get('tool', ''),
                results_summary=results_summary,
                wiki_context=wiki_context,
                history=history,
            )
            if goai_answer:
                tool_response['answer'] = goai_answer
        except AssistantAIError as exc:
            core_logger.warning("GoAI display message generation failed (parser-first): %s", exc)

    return tool_response


def _assistant_execute_ai_plan(plan, message, language, request, context_entity):
    plan = plan or {}
    tool = plan.get('tool')
    tool_query = (plan.get('tool_query') or message).strip()
    normalized_tool_query = _normalize_assistant_message(tool_query)
    content_type = (plan.get('content_type') or 'all').strip().lower()

    # V3: resolved-entity shortcut — Groq already matched a known entity by name.
    resolved_id = plan.get('resolved_entity_id')
    resolved_type = plan.get('resolved_entity_type') or plan.get('entity_type_hint')
    if resolved_id and resolved_type:
        data = _assistant_lookup_resolved_entity(resolved_type, resolved_id, language, request)
        if data:
            # If the user asked about hours on a resolved listing, use the hours-specific answer.
            if resolved_type == 'listing' and _assistant_message_mentions(
                normalized_tool_query,
                ['open', 'hours', 'working time', 'when', 'отвор', 'работно време', 'часови'],
            ):
                return _assistant_response(
                    answer=_assistant_listing_hours_answer(data, language),
                    intent='listing_hours',
                    confidence='high',
                    results=[{'type': 'listing', 'data': data}],
                    suggestions=_assistant_context_suggestions(language, context_entity),
                    resolved_context=_assistant_result_to_context('listing', data),
                )
            resp = _assistant_resolved_entity_response(resolved_type, data, language, request=request)
            if resp:
                return resp

    if tool == 'wiki':
        from .wiki import search_wiki
        wiki_query = (plan.get('wiki_query') or '').strip()
        wiki_context = search_wiki(
            wiki_query or plan.get('normalized_query_en') or tool_query,
            plan.get('normalized_query_mk') or '',
        )
        resp = _assistant_response(
            answer='',
            intent='wiki',
            confidence=plan.get('confidence') or 'high',
            suggestions=_assistant_default_suggestions(language),
        )
        if wiki_context:
            resp['wiki_context'] = wiki_context
        return resp

    if tool == 'chat':
        return _assistant_response(
            answer='',
            intent='chat',
            confidence=plan.get('confidence') or 'high',
            suggestions=_assistant_default_suggestions(language),
        )

    if tool == 'clarify':
        clarification_question = (plan.get('clarification_question') or '').strip()
        if clarification_question:
            return _assistant_response(
                answer=clarification_question,
                intent='clarify',
                confidence=plan.get('confidence') or 'low',
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )
        return None

    if tool == 'context':
        return _assistant_context_response(normalized_tool_query, language, context_entity)

    if tool == 'faq':
        return _assistant_faq_response(normalized_tool_query, language)

    if tool == 'category':
        # V2: prefer slug hint over keyword matching
        hint_resp = _assistant_category_by_hint(plan.get('category_hint'), language, request)
        if hint_resp:
            return hint_resp
        return _assistant_category_response(normalized_tool_query, language, request)

    if tool == 'feed':
        return _assistant_generic_feed_response(
            normalized_tool_query, language, request,
            time_filter=plan.get('time_filter'),
            open_now=bool(plan.get('open_now_requested')),
        )

    if tool == 'search':
        # V2: bilingual search using Groq's normalized EN+MK terms, with time / open-now filters
        if plan.get('normalized_query_en') or plan.get('normalized_query_mk'):
            return _assistant_bilingual_search_response(plan, language, request, context_entity)
        return _build_assistant_search_response(tool_query, language, request, context_entity, content_type=content_type)

    return None


def _assistant_try_external_ai_response(message, language, context_data, history, request, context_entity):
    from django.core.cache import cache

    provider = get_assistant_ai_provider()
    if not provider:
        return None

    ai_context = _assistant_external_ai_context(context_data, context_entity)
    catalog = _assistant_build_catalog()

    plan = None
    # Only cache when there is no context entity — context-dependent queries are volatile.
    cacheable = not context_entity
    cache_key = _assistant_plan_cache_key(message, language, context_data) if cacheable else None
    if cache_key:
        plan = cache.get(cache_key)

    if plan is None:
        try:
            plan = provider.plan_query(
                message=message,
                language=language,
                context=ai_context,
                history=history,
                catalog=catalog,
            )
        except AssistantAIError as exc:
            core_logger.warning("Assistant external AI planning failed: %s", exc)
            core_logger.info("assistant.metric fallback=groq_error")
            return None
        if cache_key:
            cache.set(cache_key, plan, _ASSISTANT_PLAN_CACHE_TTL)

    tool_response = _assistant_execute_ai_plan(plan, message, language, request, context_entity)
    if not tool_response:
        core_logger.info("assistant.metric fallback=empty_tool_result tool=%s", plan.get('tool'))
        return None

    if plan.get('tool') not in ('faq', 'clarify'):
        results_summary = _build_goai_results_summary(tool_response)
        wiki_context = tool_response.pop('wiki_context', '')
        try:
            goai_answer = provider.generate_display_message(
                user_message=message,
                language=language,
                tool=plan.get('tool', ''),
                results_summary=results_summary,
                wiki_context=wiki_context,
                history=history,
            )
            if goai_answer:
                tool_response['answer'] = goai_answer
        except AssistantAIError as exc:
            core_logger.warning("GoAI display message generation failed: %s", exc)

    understanding = {
        'provider': provider.provider_name,
        'confidence': plan.get('confidence'),
        'intent': plan.get('intent'),
        'content_type': plan.get('content_type'),
        'search_query': plan.get('normalized_query_en') or plan.get('tool_query') or message,
        'tool': plan.get('tool'),
        'detected_language': plan.get('detected_language'),
        'normalized_query_en': plan.get('normalized_query_en'),
        'normalized_query_mk': plan.get('normalized_query_mk'),
        'category_hint': plan.get('category_hint'),
        'entity_type_hint': plan.get('entity_type_hint'),
        'resolved_entity_id': plan.get('resolved_entity_id'),
        'resolved_entity_type': plan.get('resolved_entity_type'),
        'time_filter': plan.get('time_filter'),
        'price_filter': plan.get('price_filter'),
        'open_now_requested': plan.get('open_now_requested'),
        'followup_of_entity_id': plan.get('followup_of_entity_id'),
    }

    tool_response['understanding'] = understanding
    return tool_response


def _assistant_load_context_entity(context_data, language, request):
    if not context_data:
        return None

    entity_type = context_data.get('entity_type')
    entity_id = context_data.get('entity_id')
    if not entity_type or not entity_id:
        return None

    serializer_context = {'request': request, 'language': language}
    queryset = None
    serializer_class = None

    if entity_type == 'listing':
        queryset = Listing.objects.filter(id=entity_id, is_active=True)
        serializer_class = ListingSerializer
    elif entity_type == 'event':
        queryset = Event.objects.filter(id=entity_id, is_active=True)
        serializer_class = EventSerializer
    elif entity_type == 'promotion':
        queryset = Promotion.objects.filter(id=entity_id, is_active=True)
        serializer_class = PromotionSerializer
    elif entity_type == 'blog':
        queryset = Blog.objects.filter(id=entity_id, is_active=True, published=True)
        serializer_class = BlogSerializer

    if queryset is None or serializer_class is None:
        return None

    instance = queryset.first()
    if not instance:
        return None

    serialized = serializer_class(instance, context=serializer_context).data
    return {
        'screen': context_data.get('screen') or ASSISTANT_ENTITY_SCREEN_MAP.get(entity_type),
        'entity_type': entity_type,
        'entity_id': entity_id,
        'entity_label': context_data.get('entity_label') or serialized.get('title'),
        'data': serialized,
    }


def _assistant_entity_actions(entity_type, data, language):
    actions = []
    phone_number = data.get('phone_number')
    if phone_number:
        actions.append(
            _assistant_action(
                'external',
                _localized_text(language, "Call", "Јави се"),
                url=f"tel:{phone_number}",
            )
        )

    if data.get('google_maps_url'):
        actions.append(
            _assistant_action(
                'external',
                _localized_text(language, "Open Map", "Отвори мапа"),
                url=data['google_maps_url'],
            )
        )

    external_url = None
    if entity_type == 'listing':
        external_url = data.get('website_url')
    elif entity_type == 'event':
        external_url = data.get('website_url')
    elif entity_type == 'promotion':
        external_url = data.get('website')
    elif entity_type == 'blog':
        external_url = data.get('cta_button_url')

    if external_url:
        actions.append(
            _assistant_action(
                'external',
                _localized_text(language, "Open Link", "Отвори линк"),
                url=external_url,
            )
        )

    return actions


def _assistant_listing_hours_answer(listing, language):
    if listing.get('show_open_status') and listing.get('is_open') is not None:
        status_text = _localized_text(
            language,
            "This place is marked as open right now." if listing.get('is_open') else "This place is marked as closed right now.",
            "Ова место е означено како отворено во моментов." if listing.get('is_open') else "Ова место е означено како затворено во моментов.",
        )
        return status_text

    working_hours = listing.get('working_hours') or {}
    if isinstance(working_hours, dict):
        if 'working_hours' in working_hours and isinstance(working_hours['working_hours'], dict):
            working_hours = working_hours['working_hours']

        now = timezone.localtime()
        today_key = now.strftime('%A').lower()
        short_key = now.strftime('%a').lower()
        today_hours = working_hours.get(today_key) or working_hours.get(short_key)
        if today_hours:
            return _localized_text(
                language,
                f"Today's hours are {today_hours}.",
                f"Денешното работно време е {today_hours}.",
            )

    return _localized_text(
        language,
        "I couldn't find opening hours for this place.",
        "Не пронајдов работно време за ова место.",
    )


def _assistant_related_results_response(answer, intent, result_type, items, language, context_entity, actions=None):
    return _assistant_response(
        answer=answer,
        intent=intent,
        confidence='high' if items else 'medium',
        results=[{'type': result_type, 'data': item} for item in items],
        actions=actions or [],
        suggestions=_assistant_context_suggestions(language, context_entity),
        resolved_context=_assistant_current_context_payload(context_entity),
    )


def _assistant_context_response(normalized_message, language, context_entity):
    if not context_entity:
        return None

    entity_type = context_entity['entity_type']
    data = context_entity['data']
    actions = _assistant_entity_actions(entity_type, data, language)

    if entity_type == 'listing':
        if _assistant_message_mentions(normalized_message, ['open', 'hours', 'working time', 'when', 'отвор', 'работно време', 'часови']):
            return _assistant_response(
                answer=_assistant_listing_hours_answer(data, language),
                intent='listing_hours',
                confidence='high',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['call', 'phone', 'contact', 'number', 'јави', 'телефон', 'контакт', 'број']):
            if data.get('phone_number'):
                return _assistant_response(
                    answer=_localized_text(
                        language,
                        f"You can call {data['title']} on {data['phone_number']}.",
                        f"Можете да се јавите во {data['title']} на {data['phone_number']}.",
                    ),
                    intent='listing_contact',
                    confidence='high',
                    actions=actions,
                    suggestions=_assistant_context_suggestions(language, context_entity),
                    resolved_context=_assistant_current_context_payload(context_entity),
                )
            return _assistant_response(
                answer=_localized_text(
                    language,
                    "I couldn't find a phone number for this place.",
                    "Не пронајдов телефонски број за ова место.",
                ),
                intent='listing_contact',
                confidence='medium',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['map', 'direction', 'where', 'there', 'address', 'route', 'мапа', 'насока', 'каде', 'адреса']):
            if data.get('google_maps_url') or data.get('address'):
                answer = _localized_text(
                    language,
                    f"{data['title']} is at {data.get('address') or 'the saved address in the app'}.",
                    f"{data['title']} се наоѓа на {data.get('address') or 'зачуваната адреса во апликацијата'}.",
                )
                return _assistant_response(
                    answer=answer,
                    intent='listing_directions',
                    confidence='high',
                    actions=actions,
                    suggestions=_assistant_context_suggestions(language, context_entity),
                    resolved_context=_assistant_current_context_payload(context_entity),
                )

        if _assistant_message_mentions(normalized_message, ['promotion', 'deal', 'offer', 'discount', 'промоција', 'понуда', 'попуст']):
            promotions = data.get('promotions') or []
            if promotions:
                return _assistant_related_results_response(
                    answer=_localized_text(
                        language,
                        f"I found {len(promotions)} promotions for {data['title']}.",
                        f"Пронајдов {len(promotions)} промоции за {data['title']}.",
                    ),
                    intent='listing_promotions',
                    result_type='promotion',
                    items=promotions,
                    language=language,
                    context_entity=context_entity,
                    actions=actions,
                )
            return _assistant_response(
                answer=_localized_text(
                    language,
                    "I couldn't find active promotions for this place right now.",
                    "Во моментов не пронајдов активни промоции за ова место.",
                ),
                intent='listing_promotions',
                confidence='medium',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['event', 'events', 'happening', 'настан', 'настани']):
            events = data.get('events') or []
            if events:
                return _assistant_related_results_response(
                    answer=_localized_text(
                        language,
                        f"I found {len(events)} events linked to {data['title']}.",
                        f"Пронајдов {len(events)} настани поврзани со {data['title']}.",
                    ),
                    intent='listing_events',
                    result_type='event',
                    items=events,
                    language=language,
                    context_entity=context_entity,
                    actions=actions,
                )
            return _assistant_response(
                answer=_localized_text(
                    language,
                    "I couldn't find events linked to this place right now.",
                    "Во моментов не пронајдов настани поврзани со ова место.",
                ),
                intent='listing_events',
                confidence='medium',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['this place', 'about this', 'tell me about', 'details', 'info', 'information', 'ова место', 'кажи ми за', 'инфо', 'информации']):
            return _assistant_response(
                answer=_assistant_listing_answer(data, language),
                intent='listing_summary',
                confidence='high',
                results=[{'type': 'listing', 'data': data}],
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

    if entity_type == 'event':
        if _assistant_message_mentions(normalized_message, ['when', 'date', 'time', 'calendar', 'кога', 'датум', 'време']):
            return _assistant_response(
                answer=_localized_text(
                    language,
                    f"{data['title']} is scheduled for {data.get('date_time') or 'the listed date in the app'}.",
                    f"{data['title']} е закажан за {data.get('date_time') or 'наведениот датум во апликацијата'}.",
                ),
                intent='event_time',
                confidence='high',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['price', 'ticket', 'entry', 'cost', 'цена', 'влез', 'билет']):
            answer = _localized_text(
                language,
                f"The listed entry price is {data['entry_price']}." if data.get('entry_price') else "I couldn't find an entry price for this event.",
                f"Наведената цена за влез е {data['entry_price']}." if data.get('entry_price') else "Не пронајдов цена за влез за овој настан.",
            )
            return _assistant_response(
                answer=answer,
                intent='event_price',
                confidence='high' if data.get('entry_price') else 'medium',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['age', 'limit', 'adult', 'child', 'возраст', 'ограничување']):
            answer = _localized_text(
                language,
                f"The age limit is {data['age_limit']}." if data.get('age_limit') else "I couldn't find an age limit for this event.",
                f"Возрасното ограничување е {data['age_limit']}." if data.get('age_limit') else "Не пронајдов возрасно ограничување за овој настан.",
            )
            return _assistant_response(
                answer=answer,
                intent='event_age_limit',
                confidence='high' if data.get('age_limit') else 'medium',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['map', 'direction', 'where', 'location', 'address', 'мапа', 'насока', 'каде', 'локација']):
            return _assistant_response(
                answer=_localized_text(
                    language,
                    f"{data['title']} is happening at {data.get('location') or 'the saved location in the app'}.",
                    f"{data['title']} се одржува во {data.get('location') or 'зачуваната локација во апликацијата'}.",
                ),
                intent='event_location',
                confidence='high',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['listing', 'place', 'venue', 'available', 'where can i find', 'место', 'локација', 'достапен']):
            listings = data.get('listings') or []
            if listings:
                return _assistant_related_results_response(
                    answer=_localized_text(
                        language,
                        f"I found {len(listings)} places linked to this event.",
                        f"Пронајдов {len(listings)} места поврзани со овој настан.",
                    ),
                    intent='event_listings',
                    result_type='listing',
                    items=listings,
                    language=language,
                    context_entity=context_entity,
                    actions=actions,
                )

        if _assistant_message_mentions(normalized_message, ['call', 'phone', 'contact', 'јави', 'телефон', 'контакт']):
            answer = _localized_text(
                language,
                f"You can call on {data['phone_number']}." if data.get('phone_number') else "I couldn't find a phone number for this event.",
                f"Можете да се јавите на {data['phone_number']}." if data.get('phone_number') else "Не пронајдов телефонски број за овој настан.",
            )
            return _assistant_response(
                answer=answer,
                intent='event_contact',
                confidence='high' if data.get('phone_number') else 'medium',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['this event', 'about this', 'tell me about', 'details', 'info', 'information', 'овој настан', 'кажи ми за', 'инфо', 'информации']):
            return _assistant_response(
                answer=_assistant_event_answer(data, language),
                intent='event_summary',
                confidence='high',
                results=[{'type': 'event', 'data': data}],
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

    if entity_type == 'promotion':
        if _assistant_message_mentions(normalized_message, ['code', 'discount code', 'coupon', 'код', 'код за попуст', 'купон']):
            answer = _localized_text(
                language,
                f"The discount code is {data['discount_code']}." if data.get('has_discount_code') and data.get('discount_code') else "I couldn't find a discount code for this promotion.",
                f"Кодот за попуст е {data['discount_code']}." if data.get('has_discount_code') and data.get('discount_code') else "Не пронајдов код за попуст за оваа промоција.",
            )
            return _assistant_response(
                answer=answer,
                intent='promotion_code',
                confidence='high' if data.get('has_discount_code') and data.get('discount_code') else 'medium',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['expire', 'expiry', 'valid until', 'end', 'истек', 'истекува', 'важи до']):
            answer = _localized_text(
                language,
                f"This promotion is valid until {data['valid_until']}." if data.get('valid_until') else "I couldn't find an expiry date for this promotion.",
                f"Оваа промоција важи до {data['valid_until']}." if data.get('valid_until') else "Не пронајдов датум на истек за оваа промоција.",
            )
            return _assistant_response(
                answer=answer,
                intent='promotion_expiry',
                confidence='high' if data.get('valid_until') else 'medium',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['where can i use', 'where to use', 'listing', 'place', 'store', 'каде можам', 'каде да го користам', 'место']):
            listings = data.get('listings') or []
            if listings:
                return _assistant_related_results_response(
                    answer=_localized_text(
                        language,
                        f"You can use this promotion at {len(listings)} places in the app.",
                        f"Оваа промоција можете да ја користите на {len(listings)} места во апликацијата.",
                    ),
                    intent='promotion_listings',
                    result_type='listing',
                    items=listings,
                    language=language,
                    context_entity=context_entity,
                    actions=actions,
                )
            return _assistant_response(
                answer=_localized_text(
                    language,
                    "I couldn't find linked places for this promotion.",
                    "Не пронајдов поврзани места за оваа промоција.",
                ),
                intent='promotion_listings',
                confidence='medium',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['call', 'phone', 'contact', 'јави', 'телефон', 'контакт']):
            answer = _localized_text(
                language,
                f"You can call on {data['phone_number']}." if data.get('phone_number') else "I couldn't find a phone number for this promotion.",
                f"Можете да се јавите на {data['phone_number']}." if data.get('phone_number') else "Не пронајдов телефонски број за оваа промоција.",
            )
            return _assistant_response(
                answer=answer,
                intent='promotion_contact',
                confidence='high' if data.get('phone_number') else 'medium',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['map', 'direction', 'where', 'address', 'мапа', 'насока', 'каде', 'адреса']):
            answer = _localized_text(
                language,
                f"This promotion is linked to {data.get('address') or 'the saved address in the app'}.",
                f"Оваа промоција е поврзана со {data.get('address') or 'зачуваната адреса во апликацијата'}.",
            )
            return _assistant_response(
                answer=answer,
                intent='promotion_location',
                confidence='high',
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['this promotion', 'about this', 'tell me about', 'details', 'info', 'information', 'оваа промоција', 'кажи ми за', 'инфо', 'информации']):
            return _assistant_response(
                answer=_assistant_promotion_answer(data, language),
                intent='promotion_summary',
                confidence='high',
                results=[{'type': 'promotion', 'data': data}],
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

    if entity_type == 'blog':
        if _assistant_message_mentions(normalized_message, ['summary', 'summarize', 'about', 'article', 'article about', 'summary', 'сумирај', 'статија', 'за што']):
            return _assistant_response(
                answer=_assistant_blog_answer(data, language),
                intent='blog_summary',
                confidence='high',
                results=[{'type': 'blog', 'data': data}],
                actions=actions,
                suggestions=_assistant_context_suggestions(language, context_entity),
                resolved_context=_assistant_current_context_payload(context_entity),
            )

        if _assistant_message_mentions(normalized_message, ['open link', 'related link', 'website', 'cta', 'отвори линк', 'поврзан линк']):
            if data.get('cta_button_url'):
                return _assistant_response(
                    answer=_localized_text(
                        language,
                        "I found a related link for this article.",
                        "Пронајдов поврзан линк за оваа статија.",
                    ),
                    intent='blog_link',
                    confidence='high',
                    actions=actions,
                    suggestions=_assistant_context_suggestions(language, context_entity),
                    resolved_context=_assistant_current_context_payload(context_entity),
                )

    return None


def _assistant_search_suggestions(language, query):
    return [
        _localized_text(language, "Show full search results", "Покажи ги сите резултати"),
        _localized_text(language, f"More like {query}", f"Повеќе како {query}"),
        _localized_text(language, "Ask about another place", "Прашај за друго место"),
    ]


def _compact_text(value, max_length=140):
    if not value:
        return ""
    text = str(value).strip()
    if len(text) <= max_length:
        return text
    return f"{text[:max_length - 3].rstrip()}..."


def _assistant_promo_expiry_note(promo_data, language):
    """Return a localized expiry warning if the promo expires within 7 days, else None."""
    valid_until_str = promo_data.get('valid_until')
    if not valid_until_str:
        return None
    try:
        from datetime import date as date_type
        valid_until = (
            date_type.fromisoformat(str(valid_until_str))
            if not isinstance(valid_until_str, date_type)
            else valid_until_str
        )
        days_left = (valid_until - timezone.now().date()).days
        if 0 <= days_left <= 7:
            return _localized_text(
                language,
                f"Expires in {days_left} day{'s' if days_left != 1 else ''}",
                f"Истекува за {days_left} {'ден' if days_left == 1 else 'дена'}",
            )
    except (ValueError, TypeError, AttributeError):
        pass
    return None


def _assistant_listing_answer(listing, language):
    category_name = listing.get('category', {}).get('name') if isinstance(listing.get('category'), dict) else None
    parts = [listing.get('title')]
    if category_name:
        parts.append(_localized_text(language, f"is a {category_name}", f"е {category_name.lower()}"))
    if listing.get('address'):
        parts.append(_localized_text(language, f"at {listing['address']}", f"на {listing['address']}"))
    if listing.get('phone_number'):
        parts.append(_localized_text(language, f"Phone: {listing['phone_number']}", f"Телефон: {listing['phone_number']}"))
    return ". ".join(part for part in parts if part) + "."


def _assistant_event_answer(event, language):
    parts = [event.get('title')]
    if event.get('date_time'):
        parts.append(_localized_text(language, f"is happening on {event['date_time']}", f"се одржува на {event['date_time']}"))
    if event.get('location'):
        parts.append(_localized_text(language, f"at {event['location']}", f"во {event['location']}"))
    if event.get('entry_price'):
        parts.append(_localized_text(language, f"Entry: {event['entry_price']}", f"Влез: {event['entry_price']}"))
    return ". ".join(part for part in parts if part) + "."


def _assistant_promotion_answer(promotion, language):
    parts = [promotion.get('title')]
    description = _compact_text(promotion.get('description'))
    if description:
        parts.append(description)
    if promotion.get('has_discount_code') and promotion.get('discount_code'):
        parts.append(_localized_text(language, f"Code: {promotion['discount_code']}", f"Код: {promotion['discount_code']}"))
    if promotion.get('valid_until'):
        parts.append(_localized_text(language, f"Valid until {promotion['valid_until']}", f"Важи до {promotion['valid_until']}"))
    expiry_note = _assistant_promo_expiry_note(promotion, language)
    if expiry_note:
        parts.append(expiry_note)
    return ". ".join(part for part in parts if part) + "."


def _assistant_blog_answer(blog, language):
    parts = [blog.get('title')]
    subtitle = _compact_text(blog.get('subtitle') or blog.get('content'))
    if subtitle:
        parts.append(subtitle)
    if blog.get('author'):
        parts.append(_localized_text(language, f"By {blog['author']}", f"Од {blog['author']}"))
    return ". ".join(part for part in parts if part) + "."


def _serialize_search_results(query, content_type='all', limit=20, language='en', request=None):
    from django.db.models import Q

    cleaned_query = query.strip()
    empty = {
        'listings': [],
        'events': [],
        'promotions': [],
        'blogs': [],
        'total_count': 0,
        'query': cleaned_query,
    }
    if len(cleaned_query) < 2:
        return empty

    results = {}

    if content_type in ['all', 'listings']:
        listings = Listing.objects.filter(
            Q(title__icontains=cleaned_query) |
            Q(title_en__icontains=cleaned_query) |
            Q(title_mk__icontains=cleaned_query) |
            Q(address__icontains=cleaned_query) |
            Q(description__icontains=cleaned_query) |
            Q(description_en__icontains=cleaned_query) |
            Q(description_mk__icontains=cleaned_query) |
            Q(category__name__icontains=cleaned_query) |
            Q(category__name_en__icontains=cleaned_query) |
            Q(category__name_mk__icontains=cleaned_query),
            is_active=True
        ).distinct()[:limit]
        results['listings'] = ListingSerializer(listings, many=True, context={'request': request, 'language': language}).data

    if content_type in ['all', 'events']:
        events = Event.objects.filter(
            Q(title__icontains=cleaned_query) |
            Q(title_en__icontains=cleaned_query) |
            Q(title_mk__icontains=cleaned_query) |
            Q(location__icontains=cleaned_query) |
            Q(description__icontains=cleaned_query) |
            Q(description_en__icontains=cleaned_query) |
            Q(description_mk__icontains=cleaned_query) |
            Q(category__name__icontains=cleaned_query) |
            Q(category__name_en__icontains=cleaned_query) |
            Q(category__name_mk__icontains=cleaned_query),
            is_active=True
        ).distinct()[:limit]
        results['events'] = EventSerializer(events, many=True, context={'request': request, 'language': language}).data

    if content_type in ['all', 'promotions']:
        promotions = Promotion.objects.filter(
            Q(title__icontains=cleaned_query) |
            Q(title_en__icontains=cleaned_query) |
            Q(title_mk__icontains=cleaned_query) |
            Q(description__icontains=cleaned_query) |
            Q(description_en__icontains=cleaned_query) |
            Q(description_mk__icontains=cleaned_query) |
            Q(discount_code__icontains=cleaned_query),
            is_active=True
        ).distinct()[:limit]
        results['promotions'] = PromotionSerializer(promotions, many=True, context={'request': request, 'language': language}).data

    if content_type in ['all', 'blogs']:
        blogs = Blog.objects.filter(
            Q(title__icontains=cleaned_query) |
            Q(title_en__icontains=cleaned_query) |
            Q(title_mk__icontains=cleaned_query) |
            Q(subtitle__icontains=cleaned_query) |
            Q(subtitle_en__icontains=cleaned_query) |
            Q(subtitle_mk__icontains=cleaned_query) |
            Q(content__icontains=cleaned_query) |
            Q(content_en__icontains=cleaned_query) |
            Q(content_mk__icontains=cleaned_query),
            is_active=True,
            published=True
        ).distinct()[:limit]
        results['blogs'] = BlogSerializer(blogs, many=True, context={'request': request, 'language': language}).data

    total = sum(len(items) for items in results.values())
    return {
        'listings': results.get('listings', []),
        'events': results.get('events', []),
        'promotions': results.get('promotions', []),
        'blogs': results.get('blogs', []),
        'total_count': total,
        'query': cleaned_query,
    }


def _assistant_results_from_category_terms(category_terms, language, request, limit=3):
    listing_filters = models.Q()
    for term in category_terms:
        listing_filters |= (
            models.Q(category__name__icontains=term) |
            models.Q(category__name_en__icontains=term) |
            models.Q(category__name_mk__icontains=term)
        )

    queryset = Listing.objects.filter(listing_filters, is_active=True).distinct()[:limit]
    return ListingSerializer(queryset, many=True, context={'request': request, 'language': language}).data


def _assistant_faq_response(normalized_message, language):
    faq_map = [
        {
            'keywords': ['language', 'change language', 'смени јазик', 'јазик'],
            'intent': 'language_help',
            'answer': _localized_text(
                language,
                "To change language, tap the globe icon in the header or open Profile and choose Language.",
                "За промена на јазик, допрете ја иконата со глобус во заглавјето или отворете Профил и изберете Јазик."
            ),
            'actions': [],
        },
        {
            'keywords': ['wishlist', 'favorite', 'favourite', 'омилени', 'листа на желби'],
            'intent': 'wishlist_help',
            'answer': _localized_text(
                language,
                "Tap the heart icon on any place, event, promotion, or article to save it. You can open everything later from Wishlist.",
                "Допрете ја иконата со срце на место, настан, промоција или статија за да ја зачувате. Подоцна сè можете да отворите од Листа на желби."
            ),
            'actions': [
                _assistant_action('navigate', _localized_text(language, "Open Wishlist", "Отвори листа на желби"), screen='Wishlist')
            ],
        },
        {
            'keywords': ['support', 'contact support', 'bug', 'problem', 'issue', 'поддршка', 'помош и поддршка', 'проблем'],
            'intent': 'support_help',
            'answer': _localized_text(
                language,
                "You can contact support from the Help & Support screen and describe your issue there.",
                "Можете да контактирате поддршка преку екранот Помош и поддршка и таму да го опишете проблемот."
            ),
            'actions': [
                _assistant_action('navigate', _localized_text(language, "Contact Support", "Контактирај поддршка"), screen='HelpSupport')
            ],
        },
        {
            'keywords': ['collaboration', 'partner', 'business', 'partnership', 'соработка', 'колаборација', 'партнерство'],
            'intent': 'collaboration_help',
            'answer': _localized_text(
                language,
                "If you want to work with GoGevgelija, open the collaboration form and send your proposal.",
                "Ако сакате да соработувате со GoGevgelija, отворете го формуларот за соработка и испратете го вашиот предлог."
            ),
            'actions': [
                _assistant_action('navigate', _localized_text(language, "Open Collaboration Form", "Отвори формулар за соработка"), screen='CollaborationContact')
            ],
        },
        {
            'keywords': ['currency', 'exchange', 'rate', 'валута', 'курс', 'менувачница'],
            'intent': 'currency_help',
            'answer': _localized_text(
                language,
                "You can check the latest exchange rates in the Currency screen inside the app.",
                "Најновите девизни курсеви можете да ги проверите на екранот Валути во апликацијата."
            ),
            'actions': [
                _assistant_action('navigate', _localized_text(language, "Open Currency", "Отвори валути"), screen='Currency')
            ],
        },
        {
            'keywords': ['border', 'camera', 'граница', 'камери'],
            'intent': 'border_help',
            'answer': _localized_text(
                language,
                "You can open the border cameras link from the app to check the current situation.",
                "Можете да го отворите линкот за гранични камери од апликацијата за да ја проверите моменталната состојба."
            ),
            'actions': [
                _assistant_action('external', _localized_text(language, "Open Border Cameras", "Отвори гранични камери"), url=ASSISTANT_BORDER_CAMERA_URL)
            ],
        },
        {
            'keywords': ['guest', 'sign up', 'register', 'login', 'најава', 'регистрација', 'гостин'],
            'intent': 'account_help',
            'answer': _localized_text(
                language,
                "Guests can browse the app, but creating an account unlocks saved favorites, profile settings, and account-based support features.",
                "Гостите можат да ја разгледуваат апликацијата, но со креирање профил добивате зачувани омилени, профилни поставки и функции за поддршка поврзани со сметка."
            ),
            'actions': [],
        },
        {
            'keywords': ['what can you do', 'who are you', 'assistant', 'што можеш', 'кој си', 'асистент'],
            'intent': 'intro',
            'answer': _localized_text(
                language,
                "I can help with places, events, promotions, tourism shortcuts, and basic app questions like language, wishlist, support, and collaboration.",
                "Можам да помогнам со места, настани, промоции, туристички кратенки и основни прашања за апликацијата како јазик, листа на желби, поддршка и соработка."
            ),
            'actions': [],
        },
    ]

    for item in faq_map:
        if any(keyword in normalized_message for keyword in item['keywords']):
            return {
                'answer': item['answer'],
                'intent': item['intent'],
                'confidence': 'high',
                'results': [],
                'actions': item['actions'],
                'suggestions': _assistant_default_suggestions(language),
            }

    return None


def _assistant_category_response(normalized_message, language, request):
    category_rules = [
        {
            'keywords': ['hotel', 'hotels', 'accommodation', 'stay', 'sleep', 'сместување', 'хотел'],
            'intent': 'accommodation',
            'terms': ['Sleep & Rest', 'Accommodation', 'Hotel'],
            'answer': _localized_text(
                language,
                "Here are a few accommodation options I found.",
                "Еве неколку опции за сместување што ги пронајдов."
            ),
        },
        {
            'keywords': ['food', 'restaurant', 'restaurants', 'eat', 'cafe', 'coffee', 'кафе', 'храна', 'ресторан'],
            'intent': 'food',
            'terms': ['Food', 'Restaurant', 'Cafe'],
            'answer': _localized_text(
                language,
                "Here are a few food and cafe places you can check.",
                "Еве неколку места за храна и кафе што можете да ги проверите."
            ),
        },
        {
            'keywords': ['dentist', 'dental', 'стоматолог', 'забар'],
            'intent': 'dental',
            'terms': ['Dental Clinic', 'Dentist'],
            'answer': _localized_text(
                language,
                "Here are dental options available in the app.",
                "Еве стоматолошки опции достапни во апликацијата."
            ),
        },
        {
            'keywords': ['gas', 'petrol', 'fuel', 'бензин', 'пумпа'],
            'intent': 'fuel',
            'terms': ['Petrol Station'],
            'answer': _localized_text(
                language,
                "Here are petrol station options I found.",
                "Еве бензински пумпи што ги пронајдов."
            ),
        },
        {
            'keywords': ['service', 'auto', 'mechanic', 'сервис', 'авто'],
            'intent': 'services',
            'terms': ['Auto services', 'Services'],
            'answer': _localized_text(
                language,
                "Here are service-related places from the app.",
                "Еве сервисни места од апликацијата."
            ),
        },
    ]

    for rule in category_rules:
        if any(keyword in normalized_message for keyword in rule['keywords']):
            results = _assistant_results_from_category_terms(rule['terms'], language, request)
            if results:
                return {
                    'answer': rule['answer'],
                    'intent': rule['intent'],
                    'confidence': 'high',
                    'results': [{'type': 'listing', 'data': item} for item in results],
                    'actions': [],
                    'suggestions': _assistant_default_suggestions(language),
                }

    return None


def _assistant_generic_feed_response(normalized_message, language, request, time_filter=None, open_now=False):
    if any(keyword in normalized_message for keyword in ['event', 'events', 'happening', 'настан', 'настани']):
        qs = Event.objects.filter(is_active=True)
        start, end = _assistant_time_filter_range(time_filter)
        if start and end:
            qs = qs.filter(date_time__gte=start, date_time__lt=end)
        serialized = EventSerializer(qs[:3], many=True, context={'request': request, 'language': language}).data
        if serialized:
            return {
                'answer': _localized_text(
                    language,
                    "Here are some upcoming events from the app.",
                    "Еве неколку претстојни настани од апликацијата.",
                ),
                'intent': 'events_overview',
                'confidence': 'medium',
                'results': [{'type': 'event', 'data': item} for item in serialized],
                'actions': [],
                'suggestions': _assistant_default_suggestions(language),
            }

    if any(keyword in normalized_message for keyword in ['deal', 'deals', 'promo', 'promotion', 'offer', 'понуда', 'промоција', 'попуст']):
        today = timezone.now().date()
        qs = Promotion.objects.filter(
            is_active=True,
        ).filter(
            models.Q(valid_until__gte=today) | models.Q(valid_until__isnull=True)
        ).order_by('valid_until')[:3]
        serialized = PromotionSerializer(qs, many=True, context={'request': request, 'language': language}).data
        if serialized:
            return {
                'answer': _localized_text(
                    language,
                    "Here are some active deals from the app.",
                    "Еве неколку активни понуди од апликацијата.",
                ),
                'intent': 'promotions_overview',
                'confidence': 'medium',
                'results': [{'type': 'promotion', 'data': item} for item in serialized],
                'actions': [],
                'suggestions': _assistant_default_suggestions(language),
            }

    return None


def _build_assistant_search_response(query, language, request, context_entity=None, content_type='all'):
    search_data = _serialize_search_results(query, content_type, 3, language, request)
    total_count = search_data['total_count']
    if total_count == 0:
        return _assistant_response(
            answer=_localized_text(
                language,
                "I couldn't find a clear match for that. Try asking about a place, event, deal, currency, support, or language settings.",
                "Не најдов јасно совпаѓање за тоа. Обидете се да прашате за место, настан, понуда, валути, поддршка или поставки за јазик."
            ),
            intent='fallback',
            confidence='low',
            suggestions=_assistant_context_suggestions(language, context_entity),
            resolved_context=_assistant_current_context_payload(context_entity),
        )

    flattened_results = []
    for result_type in ['listings', 'events', 'promotions', 'blogs']:
        singular_type = result_type[:-1] if result_type.endswith('s') else result_type
        flattened_results.extend({'type': singular_type, 'data': item} for item in search_data[result_type])

    top_result = flattened_results[0]
    actions = [
        _assistant_action(
            'navigate',
            _localized_text(language, "Open Search Results", "Отвори резултати од пребарување"),
            screen='SearchResults',
            params={'query': search_data['query']},
        )
    ]

    if total_count == 1:
        detailed_answers = {
            'listing': _assistant_listing_answer,
            'event': _assistant_event_answer,
            'promotion': _assistant_promotion_answer,
            'blog': _assistant_blog_answer,
        }
        answer_builder = detailed_answers.get(top_result['type'])
        answer = answer_builder(top_result['data'], language) if answer_builder else _localized_text(language, "I found one matching result.", "Пронајдов еден соодветен резултат.")
        return _assistant_response(
            answer=answer,
            intent=f"{top_result['type']}_match",
            confidence='high',
            results=[top_result],
            actions=actions,
            suggestions=_assistant_context_suggestions(
                language,
                {
                    'entity_type': top_result['type'],
                    'entity_id': top_result['data'].get('id'),
                    'entity_label': top_result['data'].get('title'),
                    'screen': ASSISTANT_ENTITY_SCREEN_MAP.get(top_result['type']),
                    'data': top_result['data'],
                },
            ),
            resolved_context=_assistant_result_to_context(top_result['type'], top_result['data']),
        )

    return _assistant_response(
        answer=_localized_text(
            language,
            f'I found {total_count} results related to "{search_data["query"]}". Here are the top matches.',
            f'Пронајдов {total_count} резултати поврзани со "{search_data["query"]}". Еве ги најрелевантните.'
        ),
        intent='search_results',
        confidence='medium',
        results=flattened_results,
        actions=actions,
        suggestions=_assistant_search_suggestions(language, search_data['query']),
        resolved_context=_assistant_current_context_payload(context_entity),
    )


class _AssistantAnonThrottle(__import__('rest_framework.throttling', fromlist=['AnonRateThrottle']).AnonRateThrottle):
    scope = 'assistant_anon'


class _AssistantUserThrottle(__import__('rest_framework.throttling', fromlist=['UserRateThrottle']).UserRateThrottle):
    scope = 'assistant_user'


class AssistantQueryView(APIView):
    """In-app assistant. Groq understands; our code speaks."""
    permission_classes = [permissions.AllowAny]
    parser_classes = [JSONParser]
    throttle_classes = [_AssistantAnonThrottle, _AssistantUserThrottle]

    def post(self, request):
        serializer = AssistantQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = serializer.validated_data['message'].strip()
        context_data = serializer.validated_data.get('context') or {}
        history = serializer.validated_data.get('history') or []
        language = get_preferred_language(request)
        context_entity = _assistant_load_context_entity(context_data, language, request)

        # Step 1: Always run the parser first — it's free and fast.
        parser = get_assistant_query_parser()
        parsed = parser.parse(message, language=language, context=context_data, history=history)
        understanding = parsed.as_dict()
        core_logger.info("assistant.metric parser_tool=%s parser_confidence=%s", parsed.tool, parsed.confidence)

        # Step 2: Greetings/identity — no LLM needed at all.
        if parsed.tool == 'chat':
            core_logger.info("assistant.metric route=chat_no_llm")
            chat_resp = _assistant_response(
                answer='',
                intent='chat',
                confidence='high',
                suggestions=_assistant_default_suggestions(language),
            )
            response_payload = _assistant_finalize_response(chat_resp, language, context_entity, understanding)
            _assistant_log_query(request, message, language, context_data, history, understanding, response_payload)
            return Response(response_payload)

        # Step 3: High/medium confidence DB or wiki query — skip plan_query, use 1 LLM call max.
        if parsed.confidence in ('high', 'medium') and parsed.tool in ('faq', 'category', 'feed', 'context', 'search', 'wiki'):
            core_logger.info("assistant.metric route=parser_first tool=%s", parsed.tool)
            parser_response = _assistant_try_parser_first_response(
                message, language, history, request, context_entity, understanding,
            )
            if parser_response:
                response_payload = _assistant_finalize_response(parser_response, language, context_entity, understanding)
                _assistant_log_query(request, message, language, context_data, history, understanding, response_payload)
                return Response(response_payload)

        # Step 4: Low confidence or unknown — full LLM pipeline (plan_query + execute + display_message).
        core_logger.info("assistant.metric route=full_llm_pipeline")
        external_response = _assistant_try_external_ai_response(
            message,
            language,
            context_data,
            history,
            request,
            context_entity,
        )
        if external_response:
            understanding = external_response.get('understanding') or understanding
            response_payload = _assistant_finalize_response(external_response, language, context_entity, understanding)
            _assistant_log_query(request, message, language, context_data, history, understanding, response_payload)
            return Response(response_payload)

        # Step 5: LLM unavailable or failed — pure parser fallback, 0 LLM calls.
        core_logger.info("assistant.metric route=parser_fallback_only")
        normalized_message = _assistant_augmented_message(
            _normalize_assistant_message(message),
            understanding,
        )

        context_response = _assistant_context_response(normalized_message, language, context_entity)
        if context_response:
            response_payload = _assistant_finalize_response(context_response, language, context_entity, understanding)
            _assistant_log_query(request, message, language, context_data, history, understanding, response_payload)
            return Response(response_payload)

        faq_response = _assistant_faq_response(normalized_message, language)
        if faq_response:
            response_payload = _assistant_finalize_response(faq_response, language, context_entity, understanding)
            _assistant_log_query(request, message, language, context_data, history, understanding, response_payload)
            return Response(response_payload)

        category_response = _assistant_category_response(normalized_message, language, request)
        if category_response:
            response_payload = _assistant_finalize_response(category_response, language, context_entity, understanding)
            _assistant_log_query(request, message, language, context_data, history, understanding, response_payload)
            return Response(response_payload)

        feed_response = _assistant_generic_feed_response(normalized_message, language, request)
        if feed_response:
            response_payload = _assistant_finalize_response(feed_response, language, context_entity, understanding)
            _assistant_log_query(request, message, language, context_data, history, understanding, response_payload)
            return Response(response_payload)

        if history and not context_entity and _assistant_message_mentions(normalized_message, ['this', 'it', 'them', 'that', 'ова', 'тоа', 'тие']):
            previous_user_messages = [
                item.get('text', '').strip()
                for item in reversed(history)
                if item.get('role') == 'user' and item.get('text')
            ]
            if previous_user_messages:
                message = f"{previous_user_messages[0]} {message}".strip()

        effective_search_query = understanding.get('search_query') or message
        search_response = _build_assistant_search_response(effective_search_query, language, request, context_entity)
        response_payload = _assistant_finalize_response(search_response, language, context_entity, understanding)
        _assistant_log_query(request, message, language, context_data, history, understanding, response_payload)
        return Response(response_payload)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def global_search(request):
    """
    Global search across all content types.
    GET /api/search/?q=pizza&type=all

    Query parameters:
    - q: Search query (required, min 2 characters)
    - type: Content type to search (optional: all, listings, events, promotions, blogs)
    - limit: Max results per type (optional, default: 20)
    """
    query = request.query_params.get('q', '').strip()
    content_type = request.query_params.get('type', 'all')
    try:
        limit = max(1, min(int(request.query_params.get('limit', 20)), 50))
    except (ValueError, TypeError):
        limit = 20
    language = get_preferred_language(request)
    return Response(_serialize_search_results(query, content_type, limit, language, request))



# ============================================================================
# HOME SECTION VIEWSET - Backend-driven homescreen sections
# ============================================================================

class HomeSectionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for HomeSection - read-only for mobile clients.
    Returns active sections with their items for dynamic HomeScreen rendering.

    Endpoints:
    - GET /api/home/sections/ - List all active sections with items
    - GET /api/home/sections/{id}/ - Get single section with items
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = HomeSectionSerializer

    def get_queryset(self):
        """Return only active sections for home screen with their items prefetched"""
        return HomeSection.objects.filter(
            is_active=True,
            display_on__contains='home',
        ).prefetch_related(
            "items",
            "items__content_type"
        ).order_by("order", "-created_at")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['language'] = get_preferred_language(self.request)
        return context

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes (most requested endpoint)
    def list(self, request, *args, **kwargs):
        """Get all active home sections with caching"""
        response = super().list(request, *args, **kwargs)
        # Drop sections with no renderable items so the frontend never shows a blank screen
        if isinstance(response.data, dict) and 'results' in response.data:
            response.data['results'] = [s for s in response.data['results'] if s.get('items')]
            response.data['count'] = len(response.data['results'])
        return response


# ============================================================================
# TOURISM SCREEN VIEWSET - Dedicated tourism/visitor screen
# ============================================================================

class TourismScreenView(APIView):
    """
    Single endpoint for the Tourism screen.
    Returns all data needed for the tourism screen:
    - Hero carousel (configurable items from Listings/Events)
    - Category buttons (4 small + 4 big buttons to categories)
    - Dynamic sections (using HomeSection model for flexible content)

    Endpoint:
    - GET /api/tourism/ - Get complete tourism screen data
    """
    permission_classes = [permissions.AllowAny]

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def get(self, request):
        """Return complete tourism screen data"""
        language = get_preferred_language(request)

        # Get carousel items
        carousel_items = TourismCarousel.objects.filter(
            is_active=True
        ).select_related('content_type').order_by('order')

        # Get category buttons
        category_buttons = TourismCategoryButton.objects.filter(
            is_active=True
        ).select_related('category').order_by('button_size', 'order')

        if settings.DEBUG:
            core_logger.debug(
                "Tourism API: carousel_items=%d category_buttons=%d",
                carousel_items.count(), category_buttons.count(),
            )

        # Get dynamic sections (filtered by display_on field for tourism screen)
        sections = HomeSection.objects.filter(
            is_active=True,
            display_on__contains='tourism',
        ).prefetch_related(
            "items",
            "items__content_type"
        ).order_by("tourism_order", "-created_at")

        # Build context for serializers
        context = {
            'request': request,
            'language': language
        }

        # Serialize data
        data = {
            'carousel': TourismCarouselSerializer(
                carousel_items,
                many=True,
                context=context
            ).data,
            'category_buttons': TourismCategoryButtonSerializer(
                category_buttons,
                many=True,
                context=context
            ).data,
            'sections': HomeSectionSerializer(
                sections,
                many=True,
                context=context
            ).data
        }

        # Filter out carousel items with no content
        data['carousel'] = [item for item in data['carousel'] if item['data'] is not None]

        return Response(data)


# ============================================================================
# EVENTS SCREEN VIEW - Dynamic sections for Events screen
# ============================================================================

class EventsScreenView(APIView):
    """
    Returns dynamic sections for the Events screen.
    Uses the same HomeSection model filtered by display_on containing 'events'.

    Endpoint:
    - GET /api/events-screen/ - Get sections for the events screen
    """
    permission_classes = [permissions.AllowAny]

    @method_decorator(cache_page(60 * 5))
    def get(self, request):
        language = get_preferred_language(request)

        sections = HomeSection.objects.filter(
            is_active=True,
            display_on__contains='events',
        ).prefetch_related(
            "items",
            "items__content_type"
        ).order_by("order", "-created_at")

        context = {
            'request': request,
            'language': language,
        }

        data = {
            'sections': HomeSectionSerializer(
                sections,
                many=True,
                context=context,
            ).data,
        }

        return Response(data)


class GalleryView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        language = get_preferred_language(request)
        # Only city-level photos (not assigned to a specific listing)
        photos = GalleryPhoto.objects.filter(is_active=True, listing__isnull=True).order_by('order', 'id')
        serializer = GalleryPhotoSerializer(
            photos, many=True, context={'request': request, 'language': language}
        )
        return Response(serializer.data)


class ListingGalleryView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, listing_id):
        listing = get_object_or_404(Listing, pk=listing_id, is_active=True)
        language = get_preferred_language(request)
        req = request

        def _abs(url):
            if url and req:
                return req.build_absolute_uri(url)
            return url or ''

        photos = []

        # 1. Listing's own images (image, image_1..5)
        for field_name in ['image', 'image_1', 'image_2', 'image_3', 'image_4', 'image_5']:
            field = getattr(listing, field_name, None)
            if field:
                try:
                    url = field.url
                except (ValueError, AttributeError):
                    continue
                photos.append({
                    'id': f'listing_{field_name}',
                    'image_url': _abs(url),
                    'thumbnail_url': _abs(url),
                    'caption': '',
                    'order': len(photos),
                    'source': 'listing',
                })

        # 2. Extra photos assigned to this listing via admin
        extra = GalleryPhoto.objects.filter(listing=listing, is_active=True).order_by('order', 'id')
        for photo in extra:
            image_url = _get_optimized_image_url(photo, 'image', req)
            thumb_url = _get_optimized_image_url(photo, 'image_thumbnail', req)
            cap = photo.caption_mk if (language == 'mk' and photo.caption_mk) else photo.caption
            photos.append({
                'id': photo.pk,
                'image_url': image_url,
                'thumbnail_url': thumb_url or image_url,
                'caption': cap,
                'order': photo.order,
                'source': 'extra',
            })

        return Response(photos)
