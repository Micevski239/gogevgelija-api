import logging

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


# Each model only invalidates cache entries that actually depend on it.
# Patterns match URL fragments inside Django cache_page keys.
_MODEL_CACHE_PATTERNS = {
    'core.Listing':               ('*listings*', '*home/sections*', '*tourism*', '*search*'),
    'core.Event':                 ('*events*', '*home/sections*', '*tourism*'),
    'core.Promotion':             ('*promotions*', '*home/sections*'),
    'core.Blog':                  ('*blogs*', '*home/sections*'),
    'core.Category':              ('*categories*', '*listings*', '*events*'),
    'core.HomeSection':           ('*home/sections*', '*tourism*'),
    'core.HomeSectionItem':       ('*home/sections*', '*tourism*'),
    'core.GalleryPhoto':          ('*gallery*',),
    'core.TourismCarousel':       ('*tourism*',),
    'core.TourismCategoryButton': ('*tourism*',),
}

# Models that affect the manual home_sections cache — those get re-warmed (overwrite)
# in addition to the wildcard delete above.
_REWARM_HOME_MODELS = frozenset({
    'core.Listing', 'core.Event', 'core.Promotion', 'core.Blog',
    'core.HomeSection', 'core.HomeSectionItem', 'core.Category',
})


def _delete_patterns(patterns):
    if not hasattr(cache, 'delete_pattern'):
        return
    for pattern in patterns:
        try:
            cache.delete_pattern(pattern)
        except Exception:
            logger.exception("delete_pattern(%r) failed", pattern)


def _invalidate_for_model(model_label: str):
    patterns = _MODEL_CACHE_PATTERNS.get(model_label, ())
    _delete_patterns(patterns)
    if model_label in _REWARM_HOME_MODELS:
        try:
            from core.views import warm_home_sections_cache
            warm_home_sections_cache()
        except Exception:
            logger.exception("Failed to re-warm home sections cache after %s change", model_label)


def _schedule_invalidate(sender):
    label = f"{sender._meta.app_label}.{sender.__name__}"
    transaction.on_commit(lambda: _invalidate_for_model(label))


@receiver(post_save, sender='core.Listing')
@receiver(post_delete, sender='core.Listing')
@receiver(post_save, sender='core.Event')
@receiver(post_delete, sender='core.Event')
@receiver(post_save, sender='core.Promotion')
@receiver(post_delete, sender='core.Promotion')
@receiver(post_save, sender='core.Blog')
@receiver(post_delete, sender='core.Blog')
@receiver(post_save, sender='core.Category')
@receiver(post_delete, sender='core.Category')
@receiver(post_save, sender='core.HomeSection')
@receiver(post_delete, sender='core.HomeSection')
@receiver(post_save, sender='core.HomeSectionItem')
@receiver(post_delete, sender='core.HomeSectionItem')
@receiver(post_save, sender='core.GalleryPhoto')
@receiver(post_delete, sender='core.GalleryPhoto')
@receiver(post_save, sender='core.TourismCarousel')
@receiver(post_delete, sender='core.TourismCarousel')
@receiver(post_save, sender='core.TourismCategoryButton')
@receiver(post_delete, sender='core.TourismCategoryButton')
def invalidate_caches(sender, **kwargs):
    _schedule_invalidate(sender)
