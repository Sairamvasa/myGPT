import asyncio
import io
import logging
import os
import tempfile
import wave
from typing import Optional, Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from voice_agent.config import settings
from voice_agent.stt import WhisperSTT, get_language_name
from voice_agent.agent import VoiceAgent
from voice_agent.tts import MultilingualTTS
from database import save_message
from auth import get_current_user, verify_chat_ownership
from llm import LLMError
from file_utils import MAX_UPLOAD_BYTES

logger = logging.getLogger("MyGPT.Voice.API")

router = APIRouter(prefix="/voice", tags=["voice"])

_state = {
    "stt": None,
    "tts_engine": None,
    "api_tts_engine": None,
    "ready": False,
    "last_error": None,
}
_state_lock = asyncio.Lock()


def _build_api_tts_engine() -> Optional[Callable[[str, str], bytes]]:
    engine_name = (getattr(settings, "mobile_tts_engine", "gtts") or "gtts").lower()
    if engine_name == "none":
        return None
    if engine_name == "gtts":
        try:
            from gtts import gTTS

            def _synth(text: str, lang: str) -> bytes:
                gtts_lang = lang if lang in ("en", "hi", "te", "ta", "kn", "ml", "mr", "bn", "gu", "pa", "es", "fr", "de", "pt", "ru", "it", "ja", "ko", "zh-CN", "ar") else "en"
                buf = io.BytesIO()
                gTTS(text=text, lang=gtts_lang).write_to_fp(buf)
                return buf.getvalue()

            logger.info("API TTS engine: gTTS")
            return _synth
        except Exception as exc:
            logger.warning(f"gTTS not available ({exc}); API TTS disabled.")
            return None
    logger.warning(f"Unknown mobile_tts_engine '{engine_name}'; API TTS disabled.")
    return None


async def ensure_ready() -> dict:
    if _state["ready"]:
        return _state
    async with _state_lock:
        if _state["ready"]:
            return _state
        try:
            logger.info("Initializing voice providers...")
            stt = WhisperSTT(model_name=getattr(settings, "whisper_model", "base"))
            tts = MultilingualTTS()
            api_tts = _build_api_tts_engine()
            _state.update({
                "stt": stt,
                "tts_engine": tts,
                "api_tts_engine": api_tts,
                "ready": True,
                "last_error": None,
            })
            logger.info("Voice providers ready.")
        except Exception as exc:
            logger.error(f"Voice provider init failed: {exc}")
            _state["last_error"] = str(exc)
            raise
    return _state


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "MyGPT Voice Agent",
        "version": "1.0",
        "providers_ready": _state.get("ready", False),
    }


def _save_upload_to_wav(upload: UploadFile) -> tuple[str, int]:
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Uploaded audio exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )

    suffix = ".bin"
    name = (upload.filename or "").lower()
    if name.endswith(".wav"):
        suffix = ".wav"
    elif name.endswith(".webm"):
        suffix = ".webm"
    elif name.endswith(".ogg"):
        suffix = ".ogg"
    elif name.endswith(".mp3"):
        suffix = ".mp3"
    elif name.endswith(".m4a"):
        suffix = ".m4a"
    elif name.endswith(".mp4"):
        suffix = ".mp4"

    fd, path = tempfile.mkstemp(suffix=suffix, prefix="mygpt_voice_")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(data)
    return path, len(data)


def _normalise_language(language: Optional[str]) -> str:
    if not language:
        return "auto"
    language = language.strip().lower()
    return language or "auto"


_voice_agent = VoiceAgent()


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    language: Optional[str] = Form(default="auto"),
    user_id: int = Depends(get_current_user),
):
    state = await ensure_ready()
    stt = state["stt"]
    lang = _normalise_language(language)

    path, size = _save_upload_to_wav(audio)
    logger.info(f"Received audio upload: {path} ({size} bytes, lang={lang})")

    try:
        if size < 4000:
            return JSONResponse(
                status_code=400,
                content={"error": "Audio too short. Please record at least half a second."},
            )

        try:
            result = await asyncio.wait_for(
                stt.transcribe(path, language=lang if lang != "auto" else None),
                timeout=45.0,
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={"error": "Transcription timed out. Please try again."},
            )

        text = (result.text or "").strip()
        detected = result.language or "en"

        return JSONResponse(
            content={
                "text": text,
                "language": detected,
                "language_name": get_language_name(detected),
                "probability": float(getattr(result, "probability", 1.0) or 1.0),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Transcribe failed: {exc}")
        return JSONResponse(status_code=500, content={"error": "Transcription failed."})
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


@router.post("/chat")
async def chat(
    text: str = Form(...),
    language: Optional[str] = Form(default="auto"),
    speak: bool = Form(default=False),
    chat_id: Optional[int] = Form(default=None),
    user_id: int = Depends(get_current_user),
):
    if chat_id is not None:
        verify_chat_ownership(chat_id, user_id)

    lang = _normalise_language(language)
    user_text = (text or "").strip()
    if not user_text:
        return JSONResponse(
            status_code=400,
            content={"error": "Empty text."},
        )

    state = await ensure_ready()
    tts_engine = state.get("api_tts_engine")

    try:
        result = _voice_agent.process(user_text, chat_id, user_id, lang)
        response = result["response"]
    except LLMError as e:
        logger.error(f"Voice chat LLM error: {e}")
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error": True,
                "code": e.kind,
                "message": e.user_message,
                "retry_after_seconds": e.retry_after,
            },
        )
    except Exception as exc:
        logger.error(f"Voice chat failed: {exc}")
        raise HTTPException(status_code=500, detail="Voice chat failed.")

    if chat_id is not None:
        save_message(chat_id, "user", user_text)
        save_message(chat_id, "assistant", response)

    audio_b64 = None
    if speak and tts_engine and response:
        try:
            import base64
            audio_bytes = await asyncio.to_thread(
                tts_engine, response, lang if lang != "auto" else "en"
            )
            audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        except Exception as exc:
            logger.warning(f"TTS failed: {exc}")

    return JSONResponse(
        content={
            "user_text": user_text,
            "response": response,
            "language": lang if lang != "auto" else "en",
            "chat_id": chat_id,
            "audio_base64": audio_b64,
            "audio_format": "mp3" if audio_b64 else None,
        }
    )


@router.post("/voice")
async def voice(
    audio: UploadFile = File(...),
    language: Optional[str] = Form(default="auto"),
    speak: bool = Form(default=False),
    chat_id: Optional[int] = Form(default=None),
    user_id: int = Depends(get_current_user),
):
    if chat_id is not None:
        verify_chat_ownership(chat_id, user_id)

    state = await ensure_ready()
    stt = state["stt"]
    tts_engine = state.get("api_tts_engine")
    lang = _normalise_language(language)

    path, size = _save_upload_to_wav(audio)
    logger.info(f"Voice request: {path} ({size} bytes, lang={lang})")

    try:
        if size < 4000:
            return JSONResponse(
                status_code=400,
                content={"error": "Audio too short. Please hold the microphone and speak."},
            )

        try:
            stt_result = await asyncio.wait_for(
                stt.transcribe(path, language=lang if lang != "auto" else None),
                timeout=45.0,
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={"error": "Transcription timed out. Please try again."},
            )

        user_text = (stt_result.text or "").strip()
        detected_lang = stt_result.language or "en"
        if not user_text:
            return JSONResponse(
                content={
                    "user_text": "",
                    "response": "",
                    "language": detected_lang,
                    "message": "No speech detected. Please try again.",
                }
            )

        if lang == "auto":
            from voice_agent.stt import detect_script_language
            script_lang = detect_script_language(user_text)
            if script_lang:
                detected_lang = script_lang

        try:
            result = _voice_agent.process(user_text, chat_id, user_id, detected_lang)
            response = result["response"]
        except LLMError as e:
            logger.error(f"Voice request LLM error: {e}")
            raise HTTPException(
                status_code=e.status_code,
                detail={
                    "error": True,
                    "code": e.kind,
                    "message": e.user_message,
                    "retry_after_seconds": e.retry_after,
                },
            )
        except Exception as exc:
            logger.error(f"Voice request failed: {exc}")
            raise HTTPException(status_code=500, detail="Voice processing failed.")

        if chat_id is not None:
            save_message(chat_id, "user", user_text)
            save_message(chat_id, "assistant", response)

        audio_b64 = None
        if speak and tts_engine and response:
            try:
                import base64
                audio_bytes = await asyncio.to_thread(
                    tts_engine, response, detected_lang
                )
                audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
            except Exception as exc:
                logger.warning(f"TTS failed: {exc}")

        return JSONResponse(
            content={
                "user_text": user_text,
                "user_language": detected_lang,
                "response": response,
                "language": detected_lang,
                "language_name": get_language_name(detected_lang),
                "chat_id": chat_id,
                "audio_base64": audio_b64,
                "audio_format": "mp3" if audio_b64 else None,
            }
        )
    except HTTPException:
        raise
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


@router.get("/tts")
async def tts(
    text: str,
    language: str = "en",
    user_id: int = Depends(get_current_user),
):
    state = await ensure_ready()
    engine = state.get("api_tts_engine")
    if engine is None:
        raise HTTPException(status_code=503, detail="Server-side TTS is disabled.")
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text.")
    try:
        audio_bytes = await asyncio.to_thread(engine, text, language)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as exc:
        logger.error(f"TTS synthesis failed: {exc}")
        raise HTTPException(status_code=500, detail="TTS synthesis failed.")


@router.post("/clear")
async def clear_conversation(
    user_id: int = Depends(get_current_user),
):
    return {"status": "cleared", "note": "Voice uses existing chat history."}
