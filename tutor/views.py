"""
JSON API for the course AI tutor (Gemini + optional ElevenLabs).
"""

from __future__ import annotations

import base64
import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from courses.models import Course

from .models import TutorConversation, TutorMessage
from .services.llm import generate_tutor_reply
from .services.speech_cleanup import clean_text_for_speech
from .services.tts import synthesize_speech

logger = logging.getLogger(__name__)


def _parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _course_tutor_access(request, course: Course) -> bool:
    """Match course detail access: any authenticated user may open a course."""
    return request.user.is_authenticated


@login_required
@require_POST
def tutor_message(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not _course_tutor_access(request, course):
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

    body = _parse_json(request)
    if not isinstance(body, dict):
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    raw_msg = (body.get("message") or "").strip()
    if not raw_msg:
        return JsonResponse({"success": False, "error": "message is required"}, status=400)

    speak = bool(body.get("speak"))
    conv_id = body.get("conversation_id")
    conversation = None
    if conv_id is not None and str(conv_id).strip().isdigit():
        conversation = TutorConversation.objects.filter(
            pk=int(conv_id),
            course_id=course.pk,
            student_id=request.user.pk,
        ).first()
    if conversation is None:
        conversation = TutorConversation.objects.create(
            course=course,
            student=request.user,
            title="Course tutor chat",
        )

    TutorMessage.objects.create(
        conversation=conversation,
        role=TutorMessage.Role.USER,
        content=raw_msg[:16000],
    )

    result = generate_tutor_reply(
        course,
        request.user,
        conversation,
        raw_msg[:16000],
        spoken_mode=speak,
    )
    warnings = list(result.get("warnings") or [])
    audio_base64 = None
    audio_mime_type = None

    if not result.get("success"):
        return JsonResponse(
            {
                "success": False,
                "conversation_id": conversation.pk,
                "reply": "",
                "audio_base64": None,
                "audio_mime_type": None,
                "citations": [],
                "warnings": warnings,
                "error": result.get("error") or "Tutor failed.",
            },
            status=400,
        )

    reply_text = (result.get("reply") or "").strip()
    TutorMessage.objects.create(
        conversation=conversation,
        role=TutorMessage.Role.ASSISTANT,
        content=reply_text,
        metadata={"source": "gemini"},
    )

    if speak and reply_text:
        speech_text = clean_text_for_speech(reply_text)
        if settings.DEBUG:
            print("TTS text:", speech_text)
        audio_bytes, tts_err = synthesize_speech(speech_text)
        if tts_err:
            warnings.append(tts_err)
        elif audio_bytes:
            audio_base64 = base64.b64encode(audio_bytes).decode("ascii")
            audio_mime_type = "audio/mpeg"
            logger.info(
                "course tutor TTS payload mp3_bytes=%s b64_len=%s",
                len(audio_bytes),
                len(audio_base64),
            )

    return JsonResponse(
        {
            "success": True,
            "conversation_id": conversation.pk,
            "reply": reply_text,
            "audio_base64": audio_base64,
            "audio_mime_type": audio_mime_type,
            "citations": [],
            "warnings": warnings,
            "error": "",
        }
    )


@login_required
@require_POST
def tutor_speech(request, course_id):
    """TTS-only endpoint for replay or ad-hoc speech."""
    course = get_object_or_404(Course, pk=course_id)
    if not _course_tutor_access(request, course):
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

    body = _parse_json(request)
    if not isinstance(body, dict):
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    text = (body.get("text") or "").strip()
    if not text:
        return JsonResponse({"success": False, "error": "text is required"}, status=400)

    speech_text = clean_text_for_speech(text)
    if settings.DEBUG:
        print("TTS text:", speech_text)

    audio_bytes, tts_err = synthesize_speech(speech_text)
    if tts_err or not audio_bytes:
        return JsonResponse(
            {
                "success": False,
                "audio_base64": None,
                "audio_mime_type": None,
                "error": tts_err or "No audio generated.",
            },
            status=400,
        )

    return JsonResponse(
        {
            "success": True,
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "audio_mime_type": "audio/mpeg",
            "error": "",
        }
    )
