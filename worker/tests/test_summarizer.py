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


def test_summarizer_keeps_bullets_between_three_and_five_and_concise() -> None:
    transcript = (
        "I met with the team to discuss onboarding issues and support tickets and we identified that account setup is "
        "confusing for first-time users and we should simplify the first-run flow and update help text. "
        "We also need a clearer ownership model for triaging issues and we should define escalation rules by Friday."
    )

    summarizer = DeterministicSummarizer(max_bullets=5)
    summary = summarizer.summarize(transcript)

    bullets = summary["bullets"]
    assert isinstance(bullets, list)
    assert 3 <= len(bullets) <= 5
    assert all(len(str(item).split()) <= 22 for item in bullets)
    assert isinstance(summary["next_step"], str)
    assert summary["next_step"]


def test_summarizer_does_not_echo_entire_transcript_as_single_bullet() -> None:
    transcript = (
        "We reviewed priorities for onboarding migration and support workflow improvements and we captured decisions on "
        "ownership, timeline, communication, and rollout risks with action items for next week."
    )

    summarizer = DeterministicSummarizer(max_bullets=5)
    summary = summarizer.summarize(transcript)

    transcript_words = len(transcript.split())
    longest_bullet_words = max(len(item.split()) for item in summary["bullets"])
    assert longest_bullet_words < transcript_words
