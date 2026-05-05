from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_blog_home_sections"),
    ]

    operations = [
        migrations.AlterField(
            model_name="verificationcode",
            name="email",
            field=models.EmailField(db_index=True, help_text="Email address for verification", max_length=254),
        ),
        migrations.AlterField(
            model_name="verificationcode",
            name="code",
            field=models.CharField(help_text="Hashed verification code", max_length=128),
        ),
    ]
