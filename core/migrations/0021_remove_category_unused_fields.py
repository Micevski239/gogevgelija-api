from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_remove_category_dead_fields'),
    ]

    operations = [
        # Drop the index on level+order before the column is removed.
        # RunSQL (not RemoveIndex) because Django 5.x RemoveField already handles state cleanup,
        # and RemoveIndex would fail if the state doesn't track the index separately.
        # IF EXISTS handles both fresh DBs (PostgreSQL) and existing dev DBs (SQLite).
        migrations.RunSQL(
            sql='DROP INDEX IF EXISTS "core_catego_level_ede8af_idx"',
            reverse_sql='',
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
