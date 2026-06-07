from datetime import datetime

from src.synthesizer import extract_json, format_tw_date


def test_extract_json_from_wrapped_text() -> None:
    payload = 'Here you go {"headline":"A","sections":{"geo":[]},"keywords":[]}'
    assert extract_json(payload)["headline"] == "A"


def test_format_tw_date_uses_traditional_weekday() -> None:
    assert format_tw_date(datetime(2026, 6, 5)) == "2026年06月05日 星期五"
