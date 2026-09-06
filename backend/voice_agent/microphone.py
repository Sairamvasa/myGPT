import asyncio
import logging
import threading
from typing import AsyncGenerator, Optional
import numpy as np
import sounddevice as sd

logger = logging.getLogger("MyGPT.Voice.Microphone")

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.25
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)


class MicrophoneRecorder:
    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS):
        self.sample_rate = sample_rate
        self.channels = channels
        self._stream: Optional[sd.InputStream] = None
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._is_recording = False

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.debug(f"Microphone status warning: {status}")
        if not self._is_recording:
            return
        raw_bytes = indata.astype(np.int16).tobytes()
        with self._lock:
            self._buffer.extend(raw_bytes)

    def start(self) -> bool:
        with self._lock:
            if self._is_recording:
                logger.warning("Microphone is already recording.")
                return True
            self._buffer.clear()
            self._is_recording = True

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=self._audio_callback,
            )
            self._stream.start()
            logger.info("Microphone recording started.")
            return True
        except Exception as exc:
            logger.error(f"Failed to start microphone stream: {exc}", exc_info=True)
            self._is_recording = False
            self._stream = None
            return False

    def stop(self) -> bytes:
        with self._lock:
            if not self._is_recording and self._stream is None:
                logger.debug("Microphone stop requested when not recording.")
                data = bytes(self._buffer)
                self._buffer.clear()
                return data
            self._is_recording = False

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                logger.error(f"Error closing microphone stream: {exc}")
            finally:
                self._stream = None

        with self._lock:
            recorded_pcm = bytes(self._buffer)
            self._buffer.clear()

        logger.info(f"Microphone recording stopped. Captured {len(recorded_pcm)} bytes.")
        return recorded_pcm

    @property
    def is_recording(self) -> bool:
        return self._is_recording


recorder = MicrophoneRecorder()


async def microphone_stream() -> AsyncGenerator[bytes, None]:
    rec = MicrophoneRecorder()
    if not rec.start():
        return
    try:
        while rec.is_recording:
            await asyncio.sleep(0.2)
            data = rec.stop()
            if data:
                yield data
            rec.start()
    finally:
        rec.stop()
