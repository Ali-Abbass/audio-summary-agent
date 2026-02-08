from __future__ import annotations

import re
from collections import Counter


class DeterministicSummarizer:
    _stop_words = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "he",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "that",
        "the",
        "to",
        "was",
        "were",
        "will",
        "with",
        "we",
        "you",
        "your",
    }

    def __init__(self, max_bullets: int = 5) -> None:
        self._max_bullets = max(3, min(5, max_bullets))

    def summarize(self, transcript: str) -> dict[str, object]:
        cleaned = self._normalize_text(transcript)
        if not cleaned:
            return {
                "bullets": [
                    "No clear transcript content was captured.",
                    "No reliable key points could be extracted.",
                    "A fresh recording is recommended for better summarization.",
                ],
                "next_step": "Record again in a quieter environment.",
            }

        sentences = self._split_sentences(cleaned)
        bullets = self._select_bullets(cleaned, sentences)
        next_step = self._derive_next_step(sentences, bullets)
        return {"bullets": bullets, "next_step": next_step}

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _split_sentences(self, text: str) -> list[str]:
        pieces = re.split(r"(?<=[.!?])\s+", text)
        sentences = [piece.strip() for piece in pieces if piece.strip()]
        return sentences

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[a-zA-Z']+", text.lower())

    def _score_sentence(self, sentence: str, frequencies: Counter[str]) -> float:
        words = [word for word in self._tokenize(sentence) if word not in self._stop_words]
        if not words:
            return 0.0
        return sum(frequencies[word] for word in words) / len(words)

    def _select_bullets(self, text: str, sentences: list[str]) -> list[str]:
        if len(sentences) >= 3:
            tokens = [word for word in self._tokenize(text) if word not in self._stop_words]
            frequencies = Counter(tokens)
            scored = [
                (index, sentence, self._score_sentence(sentence, frequencies))
                for index, sentence in enumerate(sentences)
            ]
            scored.sort(key=lambda item: (-item[2], item[0]))

            target_count = min(self._max_bullets, len(sentences))
            target_count = max(3, min(target_count, 5))
            top = scored[:target_count]
            top.sort(key=lambda item: item[0])
            bullets = [self._ensure_sentence(item[1]) for item in top]
            return bullets[:5]

        words = text.split()
        if not words:
            return [
                "No clear transcript content was captured.",
                "No reliable key points could be extracted.",
                "A fresh recording is recommended for better summarization.",
            ]

        chunk_size = max(6, len(words) // 3)
        chunks: list[str] = []
        for idx in range(0, len(words), chunk_size):
            chunk = " ".join(words[idx : idx + chunk_size]).strip()
            if chunk:
                chunks.append(self._ensure_sentence(chunk))
        while len(chunks) < 3:
            chunks.append(chunks[-1] if chunks else "No additional key point detected.")
        return chunks[: min(self._max_bullets, 5)]

    def _derive_next_step(self, sentences: list[str], bullets: list[str]) -> str:
        keywords = ("next", "follow up", "action", "todo", "need to", "plan", "should")
        for sentence in sentences:
            lower = sentence.lower()
            if any(keyword in lower for keyword in keywords):
                return self._ensure_sentence(sentence)
        if bullets:
            return f"Take action on: {bullets[0]}"
        return "Review the transcript and choose one concrete follow-up action."

    def _ensure_sentence(self, text: str) -> str:
        sentence = text.strip()
        if sentence and sentence[-1] not in ".!?":
            sentence += "."
        return sentence
