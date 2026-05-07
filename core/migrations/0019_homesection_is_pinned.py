from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_billboarditem_billboardsection_billboardsectionitem_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='homesection',
            name='is_pinned',
            field=models.BooleanField(
                default=False,
                help_text='Pin this section at its current order position — excluded from automatic shuffle',
            ),
        ),
    ]
