from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache


def _clear_all_caches():
    try:
        # django-redis supports wildcard — clears every cached API response
        cache.delete_pattern("*")
    except Exception:
        cache.clear()


@receiver(post_save, sender='core.Listing')
@receiver(post_save, sender='core.Event')
@receiver(post_save, sender='core.Promotion')
@receiver(post_save, sender='core.Blog')
@receiver(post_save, sender='core.HomeSection')
@receiver(post_save, sender='core.HomeSectionItem')
@receiver(post_save, sender='core.Category')
def clear_api_cache(sender, **kwargs):
    _clear_all_caches()
