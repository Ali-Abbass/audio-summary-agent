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
        self._max_bullet_words = 22
        self._max_next_step_words = 18

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
        bullets = self._finalize_bullets(self._select_bullets(cleaned, sentences))
        next_step = self._shorten_sentence(
            self._derive_next_step(sentences, bullets),
            self._max_next_step_words,
        )
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
            bullets = [item[1] for item in top]
            return bullets[:5]

        clauses = self._extract_clauses(text)
        if not clauses:
            return []
        return clauses[: min(self._max_bullets, 5)]

    def _derive_next_step(self, sentences: list[str], bullets: list[str]) -> str:
        keywords = ("next", "follow up", "action", "todo", "need to", "plan", "should")
        for sentence in sentences:
            lower = sentence.lower()
            if any(keyword in lower for keyword in keywords):
                return sentence
        if bullets:
            return f"Take action on: {bullets[0]}"
        return "Review the transcript and choose one concrete follow-up action."

    def _extract_clauses(self, text: str) -> list[str]:
        parts = re.split(r"[.;,:!?]\s+|\s+-\s+", text)
        clauses: list[str] = []
        for part in parts:
            candidate = part.strip()
            if len(candidate.split()) < 4:
                continue
            clauses.append(candidate)
        return clauses

    def _finalize_bullets(self, bullets: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for bullet in bullets:
            cleaned = self._shorten_sentence(bullet, self._max_bullet_words)
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            normalized.append(cleaned)
            seen.add(key)
            if len(normalized) >= self._max_bullets:
                break

        fallback = [
            "The speaker shared a clear main topic.",
            "Several supporting details were provided.",
            "A concrete follow-up action is needed.",
        ]
        for item in fallback:
            if len(normalized) >= 3:
                break
            normalized.append(item)

        return normalized[: self._max_bullets]

    def _shorten_sentence(self, text: str, max_words: int) -> str:
        words = text.strip().split()
        if not words:
            return ""
        if len(words) > max_words:
            words = words[:max_words]
        shortened = " ".join(words).rstrip(",;:-")
        return self._ensure_sentence(shortened)

    def _ensure_sentence(self, text: str) -> str:
        sentence = text.strip()
        if sentence and sentence[-1] not in ".!?":
            sentence += "."
        return sentence
