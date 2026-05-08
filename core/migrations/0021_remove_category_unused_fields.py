from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_remove_category_dead_fields'),
    ]

    operations = [
        # Remove index from state AND db — RunSQL only dropped from db, leaving state stale.
        # Stale state caused _remake_table (triggered by RemoveField) to re-create the index,
        # which then made RemoveField(level) fail on SQLite.
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
