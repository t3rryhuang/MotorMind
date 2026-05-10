from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0005_trainingvideo_transcript_paragraph_starts"),
    ]

    operations = [
        migrations.AddField(
            model_name="course",
            name="icon_name",
            field=models.CharField(
                blank=True,
                default="diagnostics",
                help_text="Basename of SVG under static/images/course-icons/ (no extension).",
                max_length=80,
            ),
        ),
    ]
