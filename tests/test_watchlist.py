from datetime import date

from src.watchlist import rotate_half


def test_rotate_half_returns_first_half_on_even_utc_ordinal() -> None:
    topics = ["one", "two", "three", "four"]

    assert rotate_half(topics, today=date(2026, 7, 29)) == ["one", "two"]


def test_rotate_half_returns_second_half_on_odd_utc_ordinal() -> None:
    topics = ["one", "two", "three", "four"]

    assert rotate_half(topics, today=date(2026, 7, 30)) == ["three", "four"]


def test_rotate_half_assigns_extra_odd_length_topic_to_first_half() -> None:
    topics = ["one", "two", "three", "four", "five"]

    assert rotate_half(topics, today=date(2026, 7, 29)) == ["one", "two", "three"]
    assert rotate_half(topics, today=date(2026, 7, 30)) == ["four", "five"]
