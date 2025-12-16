from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.decorators.cache import cache_page
from rest_framework.routers import DefaultRouter
from core.views import (
    CategoryViewSet,
    ListingViewSet,
    EventViewSet,
    PromotionViewSet,
    BlogViewSet,
    WishlistViewSet,
    UserPermissionViewSet,
    HelpSupportViewSet,
    CollaborationContactViewSet,
    HomeSectionViewSet,
    TourismScreenView,
    TranslationResourceView,
    health,
    app_config,
    Register,
    Me,
    LanguageView,
    EditListingView,
    AdminUsersView,
    GuestLoginView,
    SendVerificationCode,
    VerifyCode,
    global_search,
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"listings", ListingViewSet, basename="listing")
router.register(r"events", EventViewSet, basename="event")
router.register(r"promotions", PromotionViewSet, basename="promotion")
router.register(r"blogs", BlogViewSet, basename="blog")
router.register(r"wishlist", WishlistViewSet, basename="wishlist")
router.register(r"home/sections", HomeSectionViewSet, basename="home-section")
router.register(r"admin/permissions", UserPermissionViewSet, basename="permissions")
router.register(r"help-support", HelpSupportViewSet, basename="help-support")
router.register(r"collaboration-contact", CollaborationContactViewSet, basename="collaboration-contact")

urlpatterns = [
    path('api/', include(router.urls)),
    path("api/app/config/", app_config, name="app_config"),
    path("api/tourism/", TourismScreenView.as_view(), name="tourism"),
    path("api/auth/register/", Register.as_view()),
    path("api/auth/send-code/", SendVerificationCode.as_view(), name="send_verification_code"),
    path("api/auth/verify-code/", VerifyCode.as_view(), name="verify_code"),
    path("api/auth/guest/", GuestLoginView.as_view(), name="guest_login"),
    path("api/auth/me/", Me.as_view()),
    path("api/auth/profile/", Me.as_view()),
    path("api/auth/language/", LanguageView.as_view()),
    path("api/i18n/<str:language_code>/<str:namespace>/", TranslationResourceView.as_view(), name="i18n_resource"),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/listings/<int:listing_id>/edit/", EditListingView.as_view(), name="edit_listing"),
    path("api/admin/users/", AdminUsersView.as_view(), name="admin_users"),
    path("api/search/", global_search, name="global_search"),
]

# Conditionally include health check
if settings.HEALTH_CHECK_ENABLED:
    urlpatterns.append(path("api/health/", health))

# Conditionally include admin
if settings.ADMIN_ENABLED:
    urlpatterns.extend([
        path('admin/', admin.site.urls),
    ])
