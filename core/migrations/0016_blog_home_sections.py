import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("core", "0015_listing_amenities_title_listing_amenities_title_mk_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="HomeSection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(help_text="Section title displayed on HomeScreen (e.g., 'Upcoming Events', 'Top Promotions')", max_length=100)),
                ("label_en", models.CharField(blank=True, help_text="Section title in English", max_length=100)),
                ("label_mk", models.CharField(blank=True, help_text="Section title in Macedonian", max_length=100)),
                ("card_type", models.CharField(choices=[("small", "Small Cards"), ("big", "Big Cards"), ("carousel", "Carousel")], default="small", help_text="Visual style: small (vertical list), big (horizontal scroll), or carousel (auto-scrolling slideshow)", max_length=10)),
                ("display_on", models.CharField(choices=[("home", "Home"), ("tourism", "Tourism"), ("events", "Events"), ("home,tourism", "Home & Tourism"), ("home,events", "Home & Events"), ("tourism,events", "Tourism & Events"), ("home,tourism,events", "All Screens")], default="home,tourism,events", help_text="Which screens should this section appear on", max_length=25)),
                ("order", models.PositiveIntegerField(default=0, help_text="Display order on HomeScreen (lower numbers appear first)")),
                ("is_active", models.BooleanField(default=True, help_text="Show this section on the HomeScreen")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Home Section",
                "verbose_name_plural": "Home Sections",
                "ordering": ["order", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="HomeSectionItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("object_id", models.PositiveIntegerField(help_text="ID of the referenced object")),
                ("order", models.PositiveIntegerField(default=0, help_text="Display order within the section (lower numbers appear first)")),
                ("is_active", models.BooleanField(default=True, help_text="Show this item in the section")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("content_type", models.ForeignKey(help_text="Type of content (Listing, Event, Promotion, or Blog)", limit_choices_to={"model__in": ("listing", "event", "promotion", "blog")}, on_delete=django.db.models.deletion.CASCADE, to="contenttypes.contenttype")),
                ("section", models.ForeignKey(help_text="The section this item belongs to", on_delete=django.db.models.deletion.CASCADE, related_name="items", to="core.homesection")),
            ],
            options={
                "verbose_name": "Home Section Item",
                "verbose_name_plural": "Home Section Items",
                "ordering": ["order", "-created_at"],
                "unique_together": {("section", "content_type", "object_id")},
            },
        ),
        migrations.AddIndex(
            model_name="homesection",
            index=models.Index(fields=["is_active", "order"], name="core_homese_is_acti_2ef31d_idx"),
        ),
        migrations.AddIndex(
            model_name="homesectionitem",
            index=models.Index(fields=["section", "is_active", "order"], name="core_homese_section_2ca60f_idx"),
        ),
        migrations.AddIndex(
            model_name="homesectionitem",
            index=models.Index(fields=["content_type", "object_id"], name="core_homese_content_197534_idx"),
        ),
        migrations.AddField(
            model_name="blog",
            name="home_sections",
            field=models.ManyToManyField(
                blank=True,
                help_text="Sections this blog should appear in",
                related_name="direct_blogs",
                to="core.homesection",
            ),
        ),
    ]
