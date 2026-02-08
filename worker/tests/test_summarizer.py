from __future__ import annotations

from app.summarizer import DeterministicSummarizer


def test_summarizer_returns_valid_shape_and_is_deterministic() -> None:
    transcript = (
        "We reviewed the Q1 launch timeline and identified two blockers. "
        "Engineering needs to finalize API pagination by Friday. "
        "Design should deliver final onboarding copy tomorrow. "
        "Next week we will run a shared QA pass before release."
    )

    summarizer = DeterministicSummarizer(max_bullets=5)
    first = summarizer.summarize(transcript)
    second = summarizer.summarize(transcript)

    assert first == second
    assert isinstance(first["bullets"], list)
    assert 3 <= len(first["bullets"]) <= 5
    assert all(isinstance(item, str) and item for item in first["bullets"])
    assert isinstance(first["next_step"], str)
    assert first["next_step"]
