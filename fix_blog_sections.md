Run this on the server:

```bash
python manage.py shell -c "from django.db import connection; c = connection.cursor(); c.execute('ALTER TABLE core_blog_sections RENAME TO core_blog_home_sections'); connection.connection.commit(); print('done')"
```

Then restart:

```bash
sudo systemctl restart gunicorn
```

git pull && python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('done')" && sudo systemctl restart gunicorn
