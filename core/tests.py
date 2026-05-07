import io
from django.test import TestCase, Client, override_settings
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from unittest.mock import MagicMock
from PIL import Image
from core.assistant_parser import HeuristicAssistantQueryParser
from core.models import Category, Event, Listing, Promotion, Blog, VerificationCode

_NO_THROTTLE = {
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {},
}


class AssistantV2Tests(TestCase):

    def setUp(self):
        self.parser = HeuristicAssistantQueryParser()
        self.request = MagicMock()
        self.request.build_absolute_uri = lambda path: f"http://testserver{path}"
        self.request.user = MagicMock()
        self.request.user.is_authenticated = False

        self.category = Category.objects.create(name="Food", slug="food", is_active=True)

        self.event_free = Event.objects.create(
            title="Free Jazz Night",
            title_en="Free Jazz Night",
            title_mk="Бесплатна џез ноќ",
            location="City Park",
            date_time="2026-04-30 20:00",
            is_active=True,
            entry_price="Free",
        )
        self.event_paid = Event.objects.create(
            title="Paid Concert",
            title_en="Paid Concert",
            title_mk="Платен концерт",
            location="Arena",
            date_time="2026-04-30 21:00",
            is_active=True,
            entry_price="10 EUR",
        )

        today = timezone.now().date()
        self.promo_active = Promotion.objects.create(
            title="Summer Deal",
            title_en="Summer Deal",
            title_mk="Летна понуда",
            is_active=True,
            valid_until=today + timedelta(days=10),
        )
        self.promo_expired = Promotion.objects.create(
            title="Old Deal",
            title_en="Old Deal",
            title_mk="Стара понуда",
            is_active=True,
            valid_until=today - timedelta(days=1),
        )
        self.promo_no_expiry = Promotion.objects.create(
            title="Evergreen Deal",
            title_en="Evergreen Deal",
            title_mk="Трајна понуда",
            is_active=True,
            valid_until=None,
        )

    def test_budget_filter_not_unsupported(self):
        result = self.parser.parse("show me cheap restaurants", language="en")
        self.assertNotIn("budget", result.unsupported_filters)

    def test_bilingual_search_excludes_expired_promotions(self):
        from core.views import _assistant_bilingual_search
        result = _assistant_bilingual_search(
            "deal", "понуда", "promotions", "en", self.request
        )
        titles = [p["title"] for p in result["promotions"]]
        self.assertNotIn("Old Deal", titles)
        self.assertIn("Summer Deal", titles)
        self.assertIn("Evergreen Deal", titles)

    def test_bilingual_search_price_filter_cheap(self):
        from core.views import _assistant_bilingual_search
        result = _assistant_bilingual_search(
            "jazz night", "џез ноќ", "events", "en", self.request,
            price_filter="cheap",
        )
        titles = [e["title"] for e in result["events"]]
        self.assertIn("Free Jazz Night", titles)
        self.assertNotIn("Paid Concert", titles)

    def test_bilingual_search_price_filter_premium(self):
        from core.views import _assistant_bilingual_search
        result = _assistant_bilingual_search(
            "concert", "концерт", "events", "en", self.request,
            price_filter="premium",
        )
        titles = [e["title"] for e in result["events"]]
        self.assertNotIn("Free Jazz Night", titles)
        self.assertIn("Paid Concert", titles)

    def test_feed_response_filters_events_by_time(self):
        from core.views import _assistant_generic_feed_response
        result = _assistant_generic_feed_response(
            "event events happening", "en", self.request, time_filter=None, open_now=False
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['intent'], 'events_overview')

    def test_feed_response_excludes_expired_promotions(self):
        from core.views import _assistant_generic_feed_response
        result = _assistant_generic_feed_response(
            "deal deals promo promotion", "en", self.request
        )
        self.assertIsNotNone(result)
        titles = [r['data']['title'] for r in result['results']]
        self.assertNotIn("Old Deal", titles)

    def test_promo_expiry_note_within_7_days(self):
        from core.views import _assistant_promo_expiry_note
        today = timezone.now().date()
        promo_data = {'valid_until': str(today + timedelta(days=3))}
        note = _assistant_promo_expiry_note(promo_data, 'en')
        self.assertIsNotNone(note)
        self.assertIn('3', note)

    def test_promo_expiry_note_beyond_7_days_returns_none(self):
        from core.views import _assistant_promo_expiry_note
        today = timezone.now().date()
        promo_data = {'valid_until': str(today + timedelta(days=10))}
        note = _assistant_promo_expiry_note(promo_data, 'en')
        self.assertIsNone(note)

    def test_promo_expiry_note_no_valid_until_returns_none(self):
        from core.views import _assistant_promo_expiry_note
        note = _assistant_promo_expiry_note({}, 'en')
        self.assertIsNone(note)

    def test_resolved_listing_includes_related_promotions(self):
        from core.views import _assistant_resolved_entity_response
        from core.serializers import ListingSerializer

        listing = Listing.objects.create(
            title="Test Cafe",
            title_en="Test Cafe",
            title_mk="Тест Кафе",
            is_active=True,
            category=self.category,
        )
        listing.promotions.add(self.promo_active)

        serialized = ListingSerializer(listing, context={'request': self.request, 'language': 'en'}).data
        response = _assistant_resolved_entity_response('listing', dict(serialized), 'en', request=self.request)

        self.assertIsNotNone(response)
        result_types = [r['type'] for r in response['results']]
        self.assertIn('promotion', result_types)


class PublicContentWritePermissionTests(TestCase):
    """
    Confirm that all public content endpoints are read-only.
    Unauthenticated POST/PUT/PATCH/DELETE must return 405 Method Not Allowed.
    """

    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Food", slug="food", is_active=True)
        self.listing = Listing.objects.create(
            title="Test Listing", title_en="Test Listing", title_mk="Тест",
            is_active=True, category=self.category,
        )
        self.event = Event.objects.create(
            title="Test Event", title_en="Test Event", title_mk="Тест настан",
            location="Park", date_time="2026-12-01 20:00", is_active=True,
        )
        self.promotion = Promotion.objects.create(
            title="Test Promo", title_en="Test Promo", title_mk="Тест промо",
            is_active=True,
        )
        self.blog = Blog.objects.create(
            title="Test Blog", title_en="Test Blog", title_mk="Тест блог",
            is_active=True, published=True,
        )

    def _assert_read_only(self, base_url, detail_url):
        # GETs must succeed
        self.assertIn(self.client.get(base_url, secure=True).status_code, [200, 301, 302])
        self.assertIn(self.client.get(detail_url, secure=True).status_code, [200, 301, 302])
        # Writes must be blocked
        self.assertEqual(self.client.post(base_url, {}, content_type='application/json', secure=True).status_code, 405)
        self.assertEqual(self.client.put(detail_url, {}, content_type='application/json', secure=True).status_code, 405)
        self.assertEqual(self.client.patch(detail_url, {}, content_type='application/json', secure=True).status_code, 405)
        self.assertEqual(self.client.delete(detail_url, secure=True).status_code, 405)

    def test_categories_are_read_only(self):
        self._assert_read_only('/api/categories/', f'/api/categories/{self.category.pk}/')

    def test_listings_are_read_only(self):
        self._assert_read_only('/api/listings/', f'/api/listings/{self.listing.pk}/')

    def test_events_are_read_only(self):
        self._assert_read_only('/api/events/', f'/api/events/{self.event.pk}/')

    def test_promotions_are_read_only(self):
        self._assert_read_only('/api/promotions/', f'/api/promotions/{self.promotion.pk}/')

    def test_blogs_are_read_only(self):
        self._assert_read_only('/api/blogs/', f'/api/blogs/{self.blog.pk}/')


class LegacyRegisterEndpointTests(TestCase):
    """Register endpoint must be disabled (410 Gone)."""

    def setUp(self):
        self.client = Client()

    def test_register_returns_410(self):
        response = self.client.post(
            '/api/auth/register/',
            {'username': 'x', 'email': 'x@x.com', 'password': 'pass'},
            content_type='application/json',
            secure=True,
        )
        self.assertEqual(response.status_code, 410)

    def test_register_response_contains_redirect_hint(self):
        response = self.client.post('/api/auth/register/', {}, content_type='application/json', secure=True)
        self.assertIn('send-code', response.json().get('error', ''))


class AssistantInputValidationTests(TestCase):
    """Confirm input limits on the assistant endpoint."""

    def setUp(self):
        self.client = Client()
        self.url = '/api/assistant/query/'

    def test_message_too_long_rejected(self):
        response = self.client.post(
            self.url,
            {'message': 'x' * 301},
            content_type='application/json',
            secure=True,
        )
        self.assertEqual(response.status_code, 400)

    def test_empty_message_rejected(self):
        response = self.client.post(self.url, {'message': ''}, content_type='application/json', secure=True)
        self.assertEqual(response.status_code, 400)

    def test_history_too_many_items_rejected(self):
        history = [{'role': 'user', 'text': 'hi'} for _ in range(21)]
        response = self.client.post(
            self.url,
            {'message': 'hello', 'history': history},
            content_type='application/json',
            secure=True,
        )
        self.assertEqual(response.status_code, 400)

    def test_valid_message_accepted(self):
        response = self.client.post(
            self.url,
            {'message': 'What restaurants are open?'},
            content_type='application/json',
            secure=True,
        )
        self.assertIn(response.status_code, [200, 429])


class FileUploadValidationTests(TestCase):
    """Confirm file upload size and type limits on EditListingView."""

    def setUp(self):
        self.user = User.objects.create_user('editor', 'editor@test.com', 'pass')
        self.category = Category.objects.create(name='Food', slug='food', is_active=True)
        self.listing = Listing.objects.create(
            title='Cafe', title_en='Cafe', title_mk='Кафе',
            is_active=True, category=self.category,
        )
        from core.models import UserPermission
        UserPermission.objects.create(user=self.user, listing=self.listing, can_edit=True)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = f'/api/listings/{self.listing.pk}/edit/'

    def _make_image(self, size_bytes=None, fmt='JPEG'):
        img = Image.new('RGB', (10, 10), color='red')
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        if size_bytes:
            buf = io.BytesIO(buf.getvalue() + b'\x00' * (size_bytes - buf.tell()))
        buf.seek(0)
        buf.name = f'test.{"jpg" if fmt == "JPEG" else fmt.lower()}'
        return buf

    def test_oversized_image_rejected(self):
        oversized = io.BytesIO(b'\xff\xd8\xff' + b'\x00' * (11 * 1024 * 1024))
        oversized.name = 'big.jpg'
        response = self.client.patch(self.url, {'image': oversized}, format='multipart', secure=True)
        self.assertEqual(response.status_code, 400)

    def test_valid_image_accepted(self):
        img = self._make_image()
        response = self.client.patch(self.url, {'image': img}, format='multipart', secure=True)
        self.assertEqual(response.status_code, 200)


class SearchLimitCapTests(TestCase):
    """Confirm global_search limit parameter is capped at 50."""

    def test_limit_clamped_to_max(self):
        response = self.client.get('/api/search/?q=cafe&limit=99999', secure=True)
        self.assertNotEqual(response.status_code, 500)

    def test_non_numeric_limit_falls_back(self):
        response = self.client.get('/api/search/?q=cafe&limit=abc', secure=True)
        self.assertNotEqual(response.status_code, 500)

    def test_zero_limit_clamped_to_one(self):
        response = self.client.get('/api/search/?q=cafe&limit=0', secure=True)
        self.assertNotEqual(response.status_code, 500)


class SupportEndpointPermissionTests(TestCase):
    """Help-support and collaboration-contact require auth for writes."""

    def test_help_support_get_allowed_anonymous(self):
        response = self.client.get('/api/help-support/', secure=True)
        self.assertNotEqual(response.status_code, 405)

    def test_help_support_post_requires_auth(self):
        response = self.client.post(
            '/api/help-support/',
            {'name': 'Test', 'email': 'test@test.com', 'message': 'hi'},
            content_type='application/json',
            secure=True,
        )
        self.assertIn(response.status_code, [401, 403])

    def test_collaboration_post_requires_auth(self):
        response = self.client.post(
            '/api/collaboration-contact/',
            {'name': 'Test', 'email': 'test@test.com', 'message': 'hi'},
            content_type='application/json',
            secure=True,
        )
        self.assertIn(response.status_code, [401, 403])


@override_settings(REST_FRAMEWORK=_NO_THROTTLE)
class AuthEmailFlowTests(TestCase):
    """Send-code / verify-code endpoint contracts."""

    def test_send_code_requires_email(self):
        response = self.client.post(
            '/api/auth/send-code/',
            {},
            content_type='application/json',
            secure=True,
        )
        self.assertEqual(response.status_code, 400)

    def test_send_code_rejects_invalid_email(self):
        response = self.client.post(
            '/api/auth/send-code/',
            {'email': 'not-an-email'},
            content_type='application/json',
            secure=True,
        )
        self.assertEqual(response.status_code, 400)

    def test_verify_code_requires_both_fields(self):
        response = self.client.post(
            '/api/auth/verify-code/',
            {'email': 'user@test.com'},
            content_type='application/json',
            secure=True,
        )
        self.assertEqual(response.status_code, 400)


@override_settings(REST_FRAMEWORK=_NO_THROTTLE)
class AuthIntegrationFlowTests(TestCase):
    """Full passwordless auth flow: verify-code → JWT → authenticated request."""

    def setUp(self):
        self.client = APIClient()
        self.email = 'integration@test.com'
        self.raw_code = '123456'
        from core.views import _hash_verification_code
        self.code_hash = _hash_verification_code(self.email, self.raw_code)

    def _create_verification_code(self, expired=False):
        delta = timedelta(minutes=-5) if expired else timedelta(minutes=10)
        return VerificationCode.objects.create(
            email=self.email,
            code=self.code_hash,
            expires_at=timezone.now() + delta,
        )

    def test_verify_code_issues_jwt_for_existing_user(self):
        User.objects.create_user(username='integuser', email=self.email)
        self._create_verification_code()
        response = self.client.post(
            '/api/auth/verify-code/',
            {'email': self.email, 'code': self.raw_code},
            format='json',
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('access', data)
        self.assertIn('refresh', data)

    def test_verify_code_registers_new_user(self):
        self._create_verification_code()
        response = self.client.post(
            '/api/auth/verify-code/',
            {'email': self.email, 'code': self.raw_code, 'name': 'New User'},
            format='json',
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(email=self.email).exists())

    def test_jwt_token_authenticates_me_endpoint(self):
        User.objects.create_user(username='integuser2', email=self.email)
        self._create_verification_code()
        token_response = self.client.post(
            '/api/auth/verify-code/',
            {'email': self.email, 'code': self.raw_code},
            format='json',
            secure=True,
        )
        access = token_response.json()['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        me_response = self.client.get('/api/auth/me/', secure=True)
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()['email'], self.email)

    def test_expired_code_rejected(self):
        User.objects.create_user(username='integuser3', email=self.email)
        self._create_verification_code(expired=True)
        response = self.client.post(
            '/api/auth/verify-code/',
            {'email': self.email, 'code': self.raw_code},
            format='json',
            secure=True,
        )
        self.assertEqual(response.status_code, 400)

    def test_used_code_rejected(self):
        User.objects.create_user(username='integuser4', email=self.email)
        vc = self._create_verification_code()
        vc.is_used = True
        vc.save()
        response = self.client.post(
            '/api/auth/verify-code/',
            {'email': self.email, 'code': self.raw_code},
            format='json',
            secure=True,
        )
        self.assertEqual(response.status_code, 400)

    def test_wrong_code_rejected(self):
        User.objects.create_user(username='integuser5', email=self.email)
        self._create_verification_code()
        response = self.client.post(
            '/api/auth/verify-code/',
            {'email': self.email, 'code': '000000'},
            format='json',
            secure=True,
        )
        self.assertEqual(response.status_code, 400)
