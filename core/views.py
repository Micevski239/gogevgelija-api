from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Category, Listing, Event, Promotion, Blog, EventJoin, Wishlist, UserProfile, UserPermission, HelpSupport, CollaborationContact
from .serializers import CategorySerializer, ListingSerializer, EventSerializer, PromotionSerializer, BlogSerializer, UserSerializer, WishlistSerializer, WishlistCreateSerializer, UserProfileSerializer, UserPermissionSerializer, CreateUserPermissionSerializer, EditListingSerializer, HelpSupportSerializer, HelpSupportCreateSerializer, CollaborationContactSerializer, CollaborationContactCreateSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Get language from user profile or default to 'en'
        language = 'en'
        if self.request.user.is_authenticated and hasattr(self.request.user, 'profile'):
            language = self.request.user.profile.language_preference
        context['language'] = language
        return context

class ListingViewSet(viewsets.ModelViewSet):
    queryset = Listing.objects.all()
    serializer_class = ListingSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Get language from user profile or default to 'en'
        language = 'en'
        if self.request.user.is_authenticated and hasattr(self.request.user, 'profile'):
            language = self.request.user.profile.language_preference
        context['language'] = language
        return context
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get only featured listings"""
        featured_listings = Listing.objects.filter(featured=True)
        serializer = self.get_serializer(featured_listings, many=True)
        return Response(serializer.data)

class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Get language from user profile or default to 'en'
        language = 'en'
        if self.request.user.is_authenticated and hasattr(self.request.user, 'profile'):
            language = self.request.user.profile.language_preference
        context['language'] = language
        return context
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get only featured events"""
        featured_events = Event.objects.filter(featured=True)
        serializer = self.get_serializer(featured_events, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.AllowAny])
    def join(self, request, pk=None):
        """Join an event with proper user tracking"""
        event = self.get_object()
        
        # Check if user is authenticated
        if request.user.is_authenticated:
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
        else:
            # For non-authenticated users, just increment count
            event.join_count += 1
            event.save()
        
        serializer = self.get_serializer(event)
        return Response({
            'message': 'Successfully joined the event!',
            'event': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.AllowAny])
    def unjoin(self, request, pk=None):
        """Unjoin an event (leave the event)"""
        event = self.get_object()
        
        # Check if user is authenticated
        if request.user.is_authenticated:
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
        else:
            # For non-authenticated users, just decrement count (but not below 0)
            if event.join_count > 0:
                event.join_count -= 1
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
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Get language from user profile or default to 'en'
        language = 'en'
        if self.request.user.is_authenticated and hasattr(self.request.user, 'profile'):
            language = self.request.user.profile.language_preference
        context['language'] = language
        return context
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get only featured promotions"""
        featured_promotions = Promotion.objects.filter(featured=True)
        serializer = self.get_serializer(featured_promotions, many=True)
        return Response(serializer.data)

class BlogViewSet(viewsets.ModelViewSet):
    queryset = Blog.objects.filter(published=True)
    serializer_class = BlogSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Get language from user profile or default to 'en'
        language = 'en'
        if self.request.user.is_authenticated and hasattr(self.request.user, 'profile'):
            language = self.request.user.profile.language_preference
        context['language'] = language
        return context
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get only featured blogs"""
        featured_blogs = Blog.objects.filter(featured=True, published=True)
        serializer = self.get_serializer(featured_blogs, many=True)
        return Response(serializer.data)

@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def health(_request):
    return Response({"status": "ok"})

class Register(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request):
        s = UserSerializer(data = request.data)
        s.is_valid(raise_exception=True)
        user = s.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            "user": {"id": user.id, "username": user.username, "email": user.email},
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }, status = status.HTTP_201_CREATED)

class Me(APIView):
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        if request.user.is_authenticated:
            u = request.user
            return Response({"id": u.id, "username": u.username, "email": u.email})
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
        
        # Save user changes
        user.save()
        
        return Response({
            "id": user.id, 
            "username": user.username, 
            "email": user.email
        })

class LanguageView(APIView):
    """View for handling user language preferences"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get current user's language preference"""
        try:
            profile = request.user.profile
            return Response({'language': profile.language_preference})
        except UserProfile.DoesNotExist:
            # Create profile if it doesn't exist
            profile = UserProfile.objects.create(user=request.user)
            return Response({'language': profile.language_preference})
    
    def post(self, request):
        """Update user's language preference"""
        language = request.data.get('language')
        
        if language not in ['en', 'mk']:
            return Response(
                {'error': 'Invalid language. Must be "en" or "mk"'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            profile = request.user.profile
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)
        
        profile.language_preference = language
        profile.save()
        
        return Response({
            'message': 'Language preference updated successfully',
            'language': language
        })

class WishlistViewSet(viewsets.ModelViewSet):
    serializer_class = WishlistSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return wishlist items for the current user only."""
        return Wishlist.objects.filter(user=self.request.user)
    
    def create(self, request, *args, **kwargs):
        """Add an item to the user's wishlist."""
        serializer = WishlistCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        wishlist_item = serializer.save()
        
        # Return the created wishlist item using the main serializer
        response_serializer = WishlistSerializer(wishlist_item)
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
    """ViewSet for managing user permissions (admin only)."""
    serializer_class = UserPermissionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return all permissions. In production, add admin check here."""
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
        
        serializer = EditListingSerializer(listing)
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
        
        serializer = EditListingSerializer(listing, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_listing = serializer.save()
        
        # Return the updated listing with full details
        full_serializer = ListingSerializer(updated_listing, context={'request': request})
        return Response(full_serializer.data)


class AdminUsersView(APIView):
    """View for getting all users (admin functionality)."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get all users. In production, add admin check here."""
        users = User.objects.all().order_by('username')
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)


class HelpSupportViewSet(viewsets.ModelViewSet):
    """ViewSet for Help & Support requests"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Users can only see their own help requests
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
    
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Get available help support categories"""
        categories = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in HelpSupport.CATEGORY_CHOICES
        ]
        return Response(categories)
    
    @action(detail=False, methods=['get'])
    def priorities(self, request):
        """Get available priority levels"""
        priorities = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in HelpSupport.PRIORITY_CHOICES
        ]
        return Response(priorities)


class CollaborationContactViewSet(viewsets.ModelViewSet):
    """ViewSet for Collaboration Contact requests"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Users can only see their own collaboration requests
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
    
    @action(detail=False, methods=['get'])
    def collaboration_types(self, request):
        """Get available collaboration types"""
        types = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in CollaborationContact.COLLABORATION_TYPE_CHOICES
        ]
        return Response(types)
