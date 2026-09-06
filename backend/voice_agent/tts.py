from abc import ABC, abstractmethod
import asyncio
import io
import logging
import re
import urllib.parse
from typing import Optional
import httpx
import numpy as np
try:
    import sounddevice as sd
except (ImportError, OSError):
    sd = None

logger = logging.getLogger("MyGPT.Voice.TTS")


def detect_text_language(text: str, default: str = "en") -> str:
    if not text:
        return default
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
    return default


class TTSProvider(ABC):
    @abstractmethod
    async def speak(self, text: str, language: Optional[str] = None) -> None:
        pass


class MultilingualTTS(TTSProvider):
    def __init__(self):
        self.pyttsx3_engine = None
        self.voices = []
        self._stop_requested = False
        try:
            import pyttsx3
            self.pyttsx3_engine = pyttsx3.init()
            self.voices = self.pyttsx3_engine.getProperty("voices") or []
        except Exception as e:
            logger.warning(f"pyttsx3 initialization failed: {e}")

        self.client = httpx.AsyncClient(timeout=15)

    def _select_pyttsx3_voice(self, lang_code: str) -> None:
        if not self.pyttsx3_engine or not self.voices:
            return
        lang_code = lang_code.lower()
        target_voice_id = None

        for voice in self.voices:
            name = (getattr(voice, "name", "") or "").lower()
            vid = (getattr(voice, "id", "") or "").lower()
            langs = [str(l).lower() for l in (getattr(voice, "languages", []) or [])]

            if any(lang_code in l for l in langs) or lang_code in name or lang_code in vid:
                target_voice_id = voice.id
                break

        if target_voice_id:
            try:
                self.pyttsx3_engine.setProperty("voice", target_voice_id)
            except Exception:
                pass

    def stop(self) -> None:
        self._stop_requested = True
    if sd is not None:
        try:
            sd.stop()
        except Exception:
            pass
        if self.pyttsx3_engine:
            try:
                self.pyttsx3_engine.stop()
            except Exception:
                pass
        logger.info("Speech playback interrupted by user.")

    async def _speak_online(self, text: str, lang: str) -> bool:
        try:
            import av

            sentences = re.split(r"(?<=[.?!;।\n])\s+", text)
            chunks = []
            current = ""
            for s in sentences:
                s = s.strip()
                if not s:
                    continue
                if len(current) + len(s) + 1 < 180:
                    current = f"{current} {s}".strip()
                else:
                    if current:
                        chunks.append(current)
                    current = s
            if current:
                chunks.append(current)

            if not chunks:
                chunks = [text[:180]]

            for chunk in chunks:
                if self._stop_requested:
                    return True

                encoded = urllib.parse.quote(chunk)
                url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded}&tl={lang}&client=tw-ob"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
                }
                resp = await self.client.get(url, headers=headers)
                if resp.status_code != 200:
                    return False

                if self._stop_requested:
                    return True

                loop = asyncio.get_running_loop()

                def decode_and_play():
                    if self._stop_requested:
                        return
                    container = av.open(io.BytesIO(resp.content))
                    frames = []
                    sample_rate = 24000
                    for frame in container.decode(audio=0):
                        if self._stop_requested:
                            return
                        sample_rate = frame.sample_rate
                        frames.append(frame.to_ndarray())
                    if not frames or self._stop_requested:
                        return
                    audio_data = np.concatenate(frames, axis=1)
                    if audio_data.ndim == 2:
                        audio_data = audio_data[0]
                    if np.issubdtype(audio_data.dtype, np.integer):
                        audio_data = audio_data.astype(np.float32) / 32768.0
                    if self._stop_requested:
                        return
                    if sd is None:
                        logger.warning("Audio playback unavailable on server.")
                        return

                    sd.play(audio_data, samplerate=sample_rate)

                    while sd.get_stream().active:
                        if self._stop_requested:
                            sd.stop()
                            break
                        sd.sleep(50)

                await loop.run_in_executor(None, decode_and_play)

            return True
        except Exception as e:
            logger.debug(f"Online TTS failed ({e}), using local voice fallback.")
            return False

    async def _speak_pyttsx3(self, text: str, lang: str) -> None:
        if self.pyttsx3_engine is None or self._stop_requested:
            return
        self._select_pyttsx3_voice(lang)
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self.pyttsx3_engine.say, text)
            await loop.run_in_executor(None, self.pyttsx3_engine.runAndWait)
        except Exception as e:
            logger.error(f"pyttsx3 speak failed: {e}")

    async def speak(self, text: str, language: Optional[str] = None) -> None:
        if not text or not text.strip():
            return
        self._stop_requested = False

        lang = language if (language and language.lower() not in ("auto", "none")) else detect_text_language(text)
        logger.info(f"Speaking in [{lang}]: '{text[:50]}...'")

        success = await self._speak_online(text, lang)
        if not success and not self._stop_requested:
            await self._speak_pyttsx3(text, lang)


Pyttsx3TTS = MultilingualTTS
