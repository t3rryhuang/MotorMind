"""Course card icon slugs (files under static/images/course-icons/)."""

# (stored value without .svg, human label)
COURSE_ICON_CHOICES = (
    ("diagnostics", "Diagnostics"),
    ("short-circuit", "Short circuit"),
    ("fuse", "Fuse"),
    ("battery", "Battery"),
    ("multimeter", "Multimeter"),
    ("can-bus", "CAN bus"),
    ("sensor", "Sensor"),
    ("wiring", "Wiring"),
    ("ar-practical", "AR practical"),
    ("quiz", "Quiz"),
)

COURSE_ICON_SLUGS = frozenset(slug for slug, _ in COURSE_ICON_CHOICES)

DEFAULT_COURSE_ICON = "diagnostics"
