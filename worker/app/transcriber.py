from __future__ import annotations

import os
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel


class WhisperTranscriber:
    provider = "faster-whisper"

    def __init__(self, model_size: str = "small") -> None:
        self._model_size = model_size
        self._model: WhisperModel | None = None

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe_bytes(self, audio_bytes: bytes, suffix: str = ".webm") -> str:
        model = self._get_model()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        try:
            segments, _ = model.transcribe(str(tmp_path), vad_filter=True)
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
            return text.strip()
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
