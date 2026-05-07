from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from unittest.mock import MagicMock
from core.assistant_parser import HeuristicAssistantQueryParser
from core.models import Category, Event, Listing, Promotion, Blog


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
        self.assertIn(self.client.get(base_url).status_code, [200, 301, 302])
        self.assertIn(self.client.get(detail_url).status_code, [200, 301, 302])
        # Writes must be blocked
        self.assertEqual(self.client.post(base_url, {}, content_type='application/json').status_code, 405)
        self.assertEqual(self.client.put(detail_url, {}, content_type='application/json').status_code, 405)
        self.assertEqual(self.client.patch(detail_url, {}, content_type='application/json').status_code, 405)
        self.assertEqual(self.client.delete(detail_url).status_code, 405)

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
