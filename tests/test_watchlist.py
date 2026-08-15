from datetime import date

from src import watchlist
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


def test_retired_watchlist_is_removed() -> None:
    name = "SECURITY" + "_ICG_COMPETITOR_WATCHLIST"
    filename = "security" + "_icg_competitor_watchlist.json"
    assert not hasattr(watchlist, name)
    assert not (watchlist.PROJECT_ROOT / filename).exists()
