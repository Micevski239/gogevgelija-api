from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0022_remove_billboard_featured_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='listing',
            name='blurhash',
            field=models.CharField(blank=True, help_text='Blurhash placeholder string for image (auto-generated)', max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='blurhash',
            field=models.CharField(blank=True, help_text='Blurhash placeholder string for image (auto-generated)', max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='promotion',
            name='blurhash',
            field=models.CharField(blank=True, help_text='Blurhash placeholder string for image (auto-generated)', max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='blog',
            name='blurhash',
            field=models.CharField(blank=True, help_text='Blurhash placeholder string for image (auto-generated)', max_length=100, null=True),
        ),
    ]
