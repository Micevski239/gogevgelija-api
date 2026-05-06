# GoGevgelija — Task List

> Tell me everything that's left and I'll add it here. We go one by one.

## Pending

<!-- all done -->

## Useful Commands

### List all listing IDs in Home sections

```bash
cd /srv/app/gogevgelija-api && python3 manage.py shell -c "
from core.models import HomeSectionItem, HomeSection, Listing
from django.contrib.contenttypes.models import ContentType

listing_ct = ContentType.objects.get_for_model(Listing)
sections = HomeSection.objects.filter(display_on__contains='home')
for section in sections:
    items = HomeSectionItem.objects.filter(section=section, content_type=listing_ct)
    ids = list(items.values_list('object_id', flat=True))
    print(f'{section.label}: {ids}')
"
```

### Test shuffle_sections command

```bash
# Run the shuffle
python3 manage.py shuffle_sections

# Verify orders changed
python3 manage.py shell -c "
from core.models import HomeSection, HomeSectionItem
for s in HomeSection.objects.filter(display_on__contains='home').order_by('order'):
    items = HomeSectionItem.objects.filter(section=s).values_list('order', 'object_id')
    print(f'{s.order} {s.label}: {list(items)}')
"
```

Run shuffle again and compare — numbers should be different.

### Crontab — shuffle sections every 6 hours

```
0 */6 * * * /srv/app/gogevgelija-api/venv/bin/python /srv/app/gogevgelija-api/manage.py shuffle_sections >> /var/log/shuffle_sections.log 2>&1
```

## Done

1. Replace profile icon with settings icon in header
2. Use the navbar (AppHeader) in gallery screen
3. Make better UI/UX in gallery (portrait cells, gradient captions, card shadows, better empty state)
4. Menu — JSONField on Listing (menu/menu_mk), sections with heading + items + optional price, JSON textarea editor in EditListing, grouped display in ListingDetail
5. Listing gallery — GalleryPhoto gets optional listing FK, ListingGalleryView combines listing images + extra admin photos, Gallery pill button on listing carousel, ListingGalleryScreen with same grid UI

## Done

1. Replace profile icon with settings icon in header
2. Use the navbar (AppHeader) in gallery screen
3. Make better UI/UX in gallery (portrait cells, gradient captions, card shadows, better empty state)

### Check if listings are active

```bash
python3 manage.py shell -c "
from core.models import Listing
for lid in [42, 33]:
    l = Listing.objects.get(id=lid)
    print(f'ID {lid} - {l.title} - is_active: {l.is_active}')
"
```
