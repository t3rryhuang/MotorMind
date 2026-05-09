from rest_framework import serializers

from courses.models import Course

from .models import Resource


class CourseBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ("id", "title")


class ResourceListSerializer(serializers.ModelSerializer):
    courses = CourseBriefSerializer(many=True, read_only=True)

    class Meta:
        model = Resource
        fields = (
            "id",
            "title",
            "isbn",
            "resource_type",
            "status",
            "chunk_count",
            "author",
            "publisher",
            "year",
            "number_of_pages",
            "source_title",
            "metadata_lookup_status",
            "metadata_lookup_error",
            "courses",
            "created_at",
        )


class ResourceDetailSerializer(serializers.ModelSerializer):
    courses = CourseBriefSerializer(many=True, read_only=True)

    class Meta:
        model = Resource
        fields = (
            "id",
            "title",
            "isbn",
            "cover_image_url",
            "resource_type",
            "source_title",
            "author",
            "description",
            "edition",
            "publisher",
            "year",
            "number_of_pages",
            "chunk_count",
            "status",
            "vector_collection",
            "original_filename",
            "metadata_lookup_status",
            "metadata_lookup_error",
            "raw_metadata",
            "courses",
            "created_at",
            "updated_at",
            "error_message",
        )


class ResourceSearchSerializer(serializers.Serializer):
    query = serializers.CharField()
    top_k = serializers.IntegerField(required=False, default=5, min_value=1, max_value=50)
    course_id = serializers.IntegerField(required=False, allow_null=True)
    resource_type = serializers.CharField(required=False, allow_blank=True)
    resource_id = serializers.IntegerField(required=False, allow_null=True)
