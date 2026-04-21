from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_listing_amenities_title_listing_amenities_title_mk_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="blog",
            name="sections",
            field=models.ManyToManyField(
                blank=True,
                help_text="Sections this blog should appear in",
                related_name="direct_blogs",
                to="core.homesection",
            ),
        ),
        migrations.AlterField(
            model_name="homesectionitem",
            name="content_type",
            field=models.ForeignKey(
                help_text="Type of content (Listing, Event, Promotion, or Blog)",
                limit_choices_to={
                    "model__in": ("listing", "event", "promotion", "blog")
                },
                on_delete=models.deletion.CASCADE,
                to="contenttypes.contenttype",
            ),
        ),
    ]
