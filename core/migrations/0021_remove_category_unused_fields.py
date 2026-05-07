from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_remove_category_dead_fields'),
    ]

    operations = [
        # Remove the index on level+order before dropping the level column (SQLite requires this)
        migrations.RemoveIndex(
            model_name='category',
            name='core_catego_level_ede8af_idx',
        ),
        # Hierarchy fields (removed from model earlier)
        migrations.RemoveField(
            model_name='category',
            name='parent',
        ),
        migrations.RemoveField(
            model_name='category',
            name='level',
        ),
        # Unused display fields
        migrations.RemoveField(
            model_name='category',
            name='image',
        ),
        migrations.RemoveField(
            model_name='category',
            name='color',
        ),
        # Description and its modeltranslation columns
        migrations.RemoveField(
            model_name='category',
            name='description',
        ),
        migrations.RemoveField(
            model_name='category',
            name='description_en',
        ),
        migrations.RemoveField(
            model_name='category',
            name='description_mk',
        ),
    ]
