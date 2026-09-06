import asyncio
import logging
import os
import tempfile
import time
import wave
from typing import Optional

from voice_agent.microphone import recorder
from voice_agent.stt import WhisperSTT, get_language_name
from voice_agent.tts import MultilingualTTS
from voice_agent.config import settings

logger = logging.getLogger("MyGPT.Voice.Pipeline")

stt_provider: Optional[WhisperSTT] = None
tts_provider: Optional[MultilingualTTS] = None
current_future = None
auto_stop_task: Optional[asyncio.Task] = None
_agent_ref = None
_pipeline_loop = None
_pipeline_ready = False


def _get_pipeline_loop():
    return _pipeline_loop


def _schedule_coroutine(coro):
    global _pipeline_loop
    if _pipeline_loop is None or _pipeline_loop.is_closed():
        logger.error("Pipeline event loop is not available.")
        return None
    return asyncio.run_coroutine_threadsafe(coro, _pipeline_loop)


async def _auto_stop_timer(max_seconds: float = 15.0):
    try:
        await asyncio.sleep(max_seconds)
        if recorder.is_recording:
            logger.info("Auto-stopping recording after max timeout.")
            handle_stop_recording()
    except asyncio.CancelledError:
        pass


def handle_start_recording():
    global auto_stop_task, _pipeline_ready
    logger.info("UI/API triggered: START RECORDING")

    if not _pipeline_ready:
        logger.warning("Pipeline not ready yet.")
        return False

    if tts_provider:
        tts_provider.stop()

    success = recorder.start()
    if success:
        logger.info("State IDLE -> LISTENING")
        if auto_stop_task and not auto_stop_task.done():
            auto_stop_task.cancel()
        auto_stop_task = _schedule_coroutine(_auto_stop_timer(15.0))
        return True
    else:
        logger.info("State IDLE -> ERROR (microphone unavailable)")
        return False


def handle_stop_recording():
    global auto_stop_task, current_future
    logger.info("UI/API triggered: STOP RECORDING")

    if auto_stop_task and not auto_stop_task.done():
        auto_stop_task.cancel()

    pcm_bytes = recorder.stop()
    logger.info("State LISTENING -> TRANSCRIBING")

    current_future = _schedule_coroutine(_process_audio_pipeline(pcm_bytes))
    return current_future


def handle_stop_speaking():
    logger.info("UI/API triggered: STOP SPEAKING")
    if tts_provider:
        tts_provider.stop()


def handle_clear_chat():
    logger.info("UI/API triggered: CLEAR CHAT")
    if tts_provider:
        tts_provider.stop()
    if recorder.is_recording:
        recorder.stop()
    if _agent_ref and hasattr(_agent_ref, "memory"):
        _agent_ref.memory.clear()


def _write_wav_and_validate(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> str:
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="mygpt_recording_")
    os.close(fd)
    try:
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
    except Exception as exc:
        logger.error(f"Failed to write WAV file: {exc}")
        raise RuntimeError(f"Failed to write audio file: {exc}") from exc

    file_size = os.path.getsize(wav_path)
    duration = len(pcm_bytes) / (sample_rate * channels * 2)
    logger.info(f"Audio file: {wav_path}")
    logger.info(f"Audio size: {file_size} bytes")
    logger.info(f"Audio duration: {duration:.2f}s")

    if file_size == 0 or duration < 0.3:
        raise ValueError("Audio file is empty or too short (< 0.3s).")

    return wav_path


async def _process_audio_pipeline(pcm_bytes: bytes):
    wav_path = None
    try:
        if not pcm_bytes or len(pcm_bytes) < 3200:
            logger.warning("Empty or insufficient audio captured.")
            return {"error": "No speech detected", "user_text": "", "response": ""}

        selected_lang = getattr(settings, "language", "auto")

        try:
            wav_path = _write_wav_and_validate(pcm_bytes)
        except Exception as exc:
            logger.error(f"Audio validation failed: {exc}")
            return {"error": str(exc), "user_text": "", "response": ""}

        try:
            result = await asyncio.wait_for(
                stt_provider.transcribe(wav_path, language=selected_lang if selected_lang != "auto" else None),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            return {"error": "Transcription timed out.", "user_text": "", "response": ""}

        user_text = result.text
        detected_lang = result.language

        if not user_text:
            return {"error": "No speech detected", "user_text": "", "response": ""}

        logger.info(f"Detected language: {detected_lang}")
        logger.info(f"Transcription: {user_text}")

        try:
            response = await asyncio.wait_for(
                _agent_ref.handle(
                    user_text, language=selected_lang, detected_language=detected_lang
                ),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            return {"error": "AI request timed out.", "user_text": user_text, "response": ""}
        except Exception as exc:
            logger.error(f"AI service failed: {exc}")
            return {"error": f"AI service failed: {exc}", "user_text": user_text, "response": ""}

        logger.info(f"Agent response received: '{response}'")

        try:
            await asyncio.wait_for(
                tts_provider.speak(response, language=detected_lang),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.error("Voice output timed out.")
        except Exception as exc:
            logger.error(f"Voice output failed: {exc}")

        return {"user_text": user_text, "response": response, "language": detected_lang}

    except Exception as exc:
        logger.error(f"Error in conversation pipeline: {exc}", exc_info=True)
        return {"error": str(exc), "user_text": "", "response": ""}
    finally:
        if wav_path and os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except OSError:
                pass


async def run_pipeline(agent) -> None:
    global stt_provider, tts_provider, _agent_ref, _pipeline_loop, _pipeline_ready
    _pipeline_loop = asyncio.get_running_loop()
    _agent_ref = agent

    logger.info("Initializing MyGPT Voice Pipeline...")
    stt_provider = WhisperSTT(model_name=getattr(settings, "whisper_model", "base"))
    tts_provider = MultilingualTTS()
    _pipeline_ready = True
    logger.info("Voice Pipeline initialized.")

    while True:
        await asyncio.sleep(3600)
