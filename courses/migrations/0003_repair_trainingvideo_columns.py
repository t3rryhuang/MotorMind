"""
Repair TrainingVideo columns if the DB is missing them.

Handles SQLite/Postgres when django_migrations shows 0002 applied but the
actual table was restored, copied, or migrated incompletely (OperationalError:
no such column thumbnail_url).
"""

from django.db import connection, migrations


def _sqlite_columns(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(f'PRAGMA table_info("{table}")')
        return {row[1] for row in cursor.fetchall()}


def _postgres_columns(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            """,
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


def repair_missing_trainingvideo_columns(apps, schema_editor):
    TrainingVideo = apps.get_model("courses", "TrainingVideo")
    table = TrainingVideo._meta.db_table
    vendor = connection.vendor

    if vendor == "sqlite":
        existing = _sqlite_columns(table)
        with connection.cursor() as cursor:
            if "thumbnail_url" not in existing:
                cursor.execute(
                    f'ALTER TABLE "{table}" ADD COLUMN "thumbnail_url" varchar(500) NOT NULL DEFAULT ""'
                )
            if "transcript_source" not in existing:
                cursor.execute(
                    f'ALTER TABLE "{table}" ADD COLUMN "transcript_source" varchar(100) NOT NULL DEFAULT ""'
                )
            if "youtube_description" not in existing:
                cursor.execute(
                    f'ALTER TABLE "{table}" ADD COLUMN "youtube_description" TEXT NOT NULL DEFAULT ""'
                )
        return

    if vendor == "postgresql":
        existing = _postgres_columns(table)
        with connection.cursor() as cursor:
            if "thumbnail_url" not in existing:
                cursor.execute(
                    f'ALTER TABLE "{table}" ADD COLUMN "thumbnail_url" varchar(500) NOT NULL DEFAULT \'\''
                )
            if "transcript_source" not in existing:
                cursor.execute(
                    f'ALTER TABLE "{table}" ADD COLUMN "transcript_source" varchar(100) NOT NULL DEFAULT \'\''
                )
            if "youtube_description" not in existing:
                cursor.execute(
                    f'ALTER TABLE "{table}" ADD COLUMN "youtube_description" TEXT NOT NULL DEFAULT \'\''
                )


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0002_training_video_youtube_fields"),
    ]

    operations = [
        migrations.RunPython(repair_missing_trainingvideo_columns, migrations.RunPython.noop),
    ]
