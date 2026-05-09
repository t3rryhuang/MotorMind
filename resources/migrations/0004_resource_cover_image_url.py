from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("resources", "0003_resource_number_of_pages"),
    ]

    operations = [
        migrations.AddField(
            model_name="resource",
            name="cover_image_url",
            field=models.URLField(
                blank=True,
                help_text="Cached book cover URL (e.g. Open Library), keyed by ISBN.",
                max_length=500,
            ),
        ),
    ]
