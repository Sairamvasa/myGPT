from abc import ABC, abstractmethod
import asyncio
import io
import logging
import os
import re
import wave
from typing import Any, Dict, Optional, Tuple, Union
import numpy as np

logger = logging.getLogger("MyGPT.Voice.STT")

SUPPORTED_LANGUAGES: Dict[str, str] = {
    "auto": "Auto Detect",
    "en": "English",
    "te": "Telugu (తెలుగు)",
    "hi": "Hindi (हिंदी)",
    "ta": "Tamil (தமிழ்)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "ml": "Malayalam (മലയാളം)",
    "mr": "Marathi (मराठी)",
    "bn": "Bengali (বাংলা)",
    "ur": "Urdu (اردو)",
    "gu": "Gujarati (ગુજરાતી)",
    "pa": "Punjabi (ਪੰਜਾਬੀ)",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "zh": "Chinese",
    "ja": "Japanese",
    "ar": "Arabic",
    "ru": "Russian",
    "pt": "Portuguese",
}


def get_language_name(code: str) -> str:
    return SUPPORTED_LANGUAGES.get(code.lower(), code.upper())


def detect_script_language(text: str) -> Optional[str]:
    if not text:
        return None
    counts = {
        "te": len(re.findall(r"[\u0C00-\u0C7F]", text)),
        "hi": len(re.findall(r"[\u0900-\u097F]", text)),
        "ta": len(re.findall(r"[\u0B80-\u0BFF]", text)),
        "kn": len(re.findall(r"[\u0C80-\u0CFF]", text)),
        "ml": len(re.findall(r"[\u0D00-\u0D7F]", text)),
        "bn": len(re.findall(r"[\u0980-\u09FF]", text)),
        "gu": len(re.findall(r"[\u0A80-\u0AFF]", text)),
        "pa": len(re.findall(r"[\u0A00-\u0A7F]", text)),
        "ur": len(re.findall(r"[\u0600-\u06FF]", text)),
    }
    max_lang, count = max(counts.items(), key=lambda item: item[1])
    if count > 0:
        return max_lang
    return None


class TranscriptionResult:
    def __init__(self, text: str, language: str = "en", probability: float = 1.0):
        self.text = text.strip()
        self.language = language.lower() if language else "en"
        self.probability = float(probability)

    def __iter__(self):
        return iter((self.text, self.language))

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return f"TranscriptionResult(text='{self.text}', language='{self.language}', prob={self.probability:.2f})"

    def __bool__(self) -> bool:
        return bool(self.text)

    def __len__(self) -> int:
        return len(self.text)

    def __getitem__(self, item):
        return (self.text, self.language)[item]


class STTProvider(ABC):
    @abstractmethod
    async def transcribe(
        self,
        audio: Union[bytes, bytearray, np.ndarray, str, io.BytesIO],
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        raise NotImplementedError


class WhisperSTT(STTProvider):
    def __init__(self, model_name: str = "base", device: str = "cpu"):
        self.model = None
        self.engine_type = None
        self._buffer = bytearray()
        self._sample_rate = 16000

        try:
            from faster_whisper import WhisperModel
            logger.info(f"Initializing faster-whisper multilingual model '{model_name}' on {device}...")
            self.model = WhisperModel(model_name, device=device, download_root=".whisper_models")
            self.engine_type = "faster-whisper"
            logger.info(f"Successfully initialized faster-whisper ({model_name}).")
        except Exception as exc:
            logger.warning(f"faster-whisper unavailable or failed ({exc}). Falling back to transformers Whisper pipeline.")
            try:
                from transformers import pipeline
                hf_model = f"openai/whisper-{model_name if model_name in ('tiny', 'base', 'small', 'medium', 'large') else 'tiny'}"
                self.model = pipeline("automatic-speech-recognition", model=hf_model)
                self.engine_type = "transformers"
                logger.info(f"Successfully initialized transformers Whisper ({hf_model}).")
            except Exception as exc2:
                logger.error(f"Failed to load any Whisper STT backend: {exc2}")

    def _prepare_audio(
        self, audio: Union[bytes, bytearray, np.ndarray, str, io.BytesIO]
    ) -> Union[np.ndarray, str, io.BytesIO, None]:
        if audio is None:
            return None
        if isinstance(audio, str):
            if os.path.exists(audio) and os.path.getsize(audio) > 0:
                return audio
            return None
        if isinstance(audio, np.ndarray):
            if audio.size == 0:
                return None
            if audio.dtype != np.float32:
                if np.issubdtype(audio.dtype, np.integer):
                    audio = audio.astype(np.float32) / 32768.0
                else:
                    audio = audio.astype(np.float32)
            return audio.flatten()
        if hasattr(audio, "read"):
            return audio
        if isinstance(audio, (bytes, bytearray)):
            if len(audio) < 2:
                return None
            pcm = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
            return pcm
        return None

    async def transcribe(
        self,
        audio: Union[bytes, bytearray, np.ndarray, str, io.BytesIO],
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        if self.model is None:
            return TranscriptionResult("", "en", 0.0)

        pcm_to_transcribe = None

        if isinstance(audio, (bytes, bytearray)):
            self._buffer.extend(audio)
            min_bytes = self._sample_rate * 2
            if len(self._buffer) < min_bytes:
                return TranscriptionResult("", "en", 0.0)
            chunk = bytes(self._buffer)
            self._buffer.clear()
            pcm_to_transcribe = self._prepare_audio(chunk)
        else:
            pcm_to_transcribe = self._prepare_audio(audio)

        if pcm_to_transcribe is None:
            return TranscriptionResult("", "en", 0.0)

        whisper_lang = None
        if language and language.lower() not in ("auto", "none", ""):
            whisper_lang = language.lower()

        loop = asyncio.get_running_loop()
        try:
            if self.engine_type == "faster-whisper":
                segments, info = await loop.run_in_executor(
                    None,
                    lambda: self.model.transcribe(
                        pcm_to_transcribe,
                        language=whisper_lang,
                        beam_size=5,
                        vad_filter=True,
                    ),
                )
                transcription = " ".join([segment.text for segment in segments]).strip()
                detected_lang = getattr(info, "language", whisper_lang or "en")
                prob = getattr(info, "language_probability", 1.0)
            elif self.engine_type == "transformers":
                if isinstance(pcm_to_transcribe, np.ndarray):
                    audio_input = {"raw": pcm_to_transcribe, "sampling_rate": self._sample_rate}
                else:
                    audio_input = pcm_to_transcribe

                kwargs = {}
                if whisper_lang:
                    kwargs["generate_kwargs"] = {"language": whisper_lang}

                res = await loop.run_in_executor(
                    None,
                    lambda: self.model(audio_input, **kwargs),
                )
                if isinstance(res, dict):
                    transcription = res.get("text", "").strip()
                else:
                    transcription = str(res).strip()
                detected_lang = whisper_lang or "en"
                prob = 1.0
            else:
                return TranscriptionResult("", "en", 0.0)

            script_lang = detect_script_language(transcription)
            final_lang = script_lang if script_lang and not whisper_lang else detected_lang

            if transcription:
                lang_name = get_language_name(final_lang)
                logger.info(f"Transcription [{final_lang} - {lang_name}] (conf: {prob:.2f}): '{transcription}'")
            return TranscriptionResult(transcription, final_lang, prob)

        except Exception as exc:
            logger.error(f"Whisper transcription error: {exc}", exc_info=True)
            return TranscriptionResult("", "en", 0.0)
