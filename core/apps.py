import logging
import os
import sys
import threading
import time

from django.apps import AppConfig


_SKIP_WARM_COMMANDS = {
    'migrate', 'makemigrations', 'collectstatic', 'createsuperuser',
    'shell', 'shell_plus', 'test', 'dbshell', 'check', 'showmigrations',
    'loaddata', 'dumpdata',
}


def _warm_caches_on_startup():
    log = logging.getLogger(__name__)
    # Brief delay so DB pool / Redis connections settle and the worker is fully booted.
    time.sleep(2)
    try:
        from core.views import warm_home_sections_cache
        warm_home_sections_cache()
        log.info("Home sections cache warmed on startup")
    except Exception:
        log.exception("Failed to warm home sections cache on startup")


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        import core.signals  # noqa: F401

        # Only warm in long-running server processes (gunicorn workers, runserver child).
        argv1 = sys.argv[1] if len(sys.argv) > 1 else ''
        if argv1 in _SKIP_WARM_COMMANDS:
            return
        # Under runserver's autoreloader, only the child has RUN_MAIN=true. Skip the parent.
        if os.environ.get('RUN_MAIN') == 'false':
            return

        threading.Thread(target=_warm_caches_on_startup, daemon=True).start()
