"""
Verify that the database table for TrainingVideo includes expected columns.

Run after pulling model changes:

    python manage.py check_trainingvideo_schema
    python manage.py migrate
"""

from django.core.management.base import BaseCommand
from django.db import connection

from courses.models import TrainingVideo


def _column_names_sqlite(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(f'PRAGMA table_info("{table}")')
        return {row[1] for row in cursor.fetchall()}


def _column_names_postgres(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


class Command(BaseCommand):
    help = "Check TrainingVideo table columns against the current Django model."

    def handle(self, *args, **options):
        table = TrainingVideo._meta.db_table
        expected = {f.column for f in TrainingVideo._meta.concrete_fields if getattr(f, "column", None)}

        vendor = connection.vendor
        if vendor == "sqlite":
            try:
                actual = _column_names_sqlite(table)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"Could not read SQLite schema: {exc}"))
                return
        elif vendor == "postgresql":
            try:
                actual = _column_names_postgres(table)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"Could not read Postgres schema: {exc}"))
                return
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Automatic column listing not implemented for {vendor!r}; run `migrate`."
                )
            )
            return

        missing = sorted(expected - actual)
        extra = sorted(actual - expected)

        self.stdout.write(self.style.NOTICE(f"Table: {table}"))
        self.stdout.write(f"Columns in DB ({len(actual)}): {', '.join(sorted(actual))}")

        if not missing:
            self.stdout.write(self.style.SUCCESS("All expected TrainingVideo columns are present."))
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"Missing columns ({len(missing)}): {', '.join(missing)}\n"
                    "Apply migrations:\n"
                    "  python manage.py migrate courses\n"
                    "If django_migrations is out of sync, inspect migrations and DB backups."
                )
            )

        if extra:
            self.stdout.write(self.style.WARNING(f"Extra columns not in current model: {', '.join(extra)}"))
