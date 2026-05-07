from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_homesection_is_pinned'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='category',
            name='show_in_events',
        ),
        migrations.RemoveField(
            model_name='category',
            name='show_in_search',
        ),
        migrations.RemoveField(
            model_name='category',
            name='show_in_navigation',
        ),
    ]
