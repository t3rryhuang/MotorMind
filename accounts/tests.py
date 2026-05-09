from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Profile
from courses.models import Course
from resources.models import Resource


class CourseResourceAttachDetachTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tres", password="pw")
        self.user.profile.role = Profile.Role.TEACHER
        self.user.profile.save(update_fields=["role"])
        self.course = Course.objects.create(
            title="Electrical 101",
            description="",
            created_by=self.user,
        )
        self.resource = Resource.objects.create(
            title="Shop manual",
            resource_type=Resource.ResourceType.PDF,
            uploaded_file=SimpleUploadedFile("m.pdf", b"%PDF-1.4"),
            status=Resource.Status.UPLOADED,
        )
        self.client = Client()
        self.client.login(username="tres", password="pw")

    def test_attach_and_detach(self):
        url_attach = reverse(
            "accounts:course_resource_attach",
            kwargs={"course_id": self.course.pk},
        )
        resp = self.client.post(
            url_attach,
            {"resource_id": str(self.resource.pk)},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(self.resource, self.course.resources.all())

        url_detach = reverse(
            "accounts:course_resource_detach",
            kwargs={"course_id": self.course.pk, "resource_id": self.resource.pk},
        )
        resp2 = self.client.post(url_detach, follow=False)
        self.assertEqual(resp2.status_code, 302)
        self.assertNotIn(self.resource, self.course.resources.all())
        self.assertTrue(Resource.objects.filter(pk=self.resource.pk).exists())
