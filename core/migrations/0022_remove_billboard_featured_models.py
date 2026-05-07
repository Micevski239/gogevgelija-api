from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_remove_category_unused_fields'),
    ]

    operations = [
        migrations.DeleteModel(
            name='BillboardSectionItem',
        ),
        migrations.DeleteModel(
            name='BillboardSection',
        ),
        migrations.DeleteModel(
            name='BillboardItem',
        ),
        migrations.DeleteModel(
            name='FeaturedItem',
        ),
    ]
