from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("", include("accounts.urls")),
    path("", include("courses.urls")),
    path("", include("quizzes.urls")),
    path("", include("ar_tasks.urls")),
    path("admin-panel/resources/", include("resources.urls")),
    path("admin-panel/", include("study_content.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Serves STATICFILES_DIRS + app static in development (empty list when DEBUG is False).
urlpatterns += staticfiles_urlpatterns()
