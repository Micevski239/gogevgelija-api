import logging

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _clear_all_caches():
    try:
        # django-redis supports wildcard — clears every cached API response
        cache.delete_pattern("*")
    except Exception:
        cache.clear()


def _rewarm_after_commit():
    """Wipe stale caches and immediately repopulate /api/home/sections/.

    Runs after the DB transaction commits so the rebuild reads the post-save
    state. The home/sections endpoint is the slowest cold render, so we always
    keep it warm to avoid client-side timeouts on the next mobile request.
    """
    _clear_all_caches()
    try:
        # Imported here to avoid circular import at module load.
        from core.views import warm_home_sections_cache
        warm_home_sections_cache()
    except Exception:
        logger.exception("Failed to re-warm home sections cache after admin save")


def _schedule_rewarm():
    transaction.on_commit(_rewarm_after_commit)


@receiver(post_save, sender='core.Listing')
@receiver(post_save, sender='core.Event')
@receiver(post_save, sender='core.Promotion')
@receiver(post_save, sender='core.Blog')
@receiver(post_save, sender='core.HomeSection')
@receiver(post_save, sender='core.HomeSectionItem')
@receiver(post_save, sender='core.Category')
def clear_api_cache_on_save(sender, **kwargs):
    _schedule_rewarm()


@receiver(post_delete, sender='core.Listing')
@receiver(post_delete, sender='core.Event')
@receiver(post_delete, sender='core.Promotion')
@receiver(post_delete, sender='core.Blog')
@receiver(post_delete, sender='core.HomeSection')
@receiver(post_delete, sender='core.HomeSectionItem')
@receiver(post_delete, sender='core.Category')
def clear_api_cache_on_delete(sender, **kwargs):
    _schedule_rewarm()
