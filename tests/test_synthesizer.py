from datetime import datetime

from src.sources import SOURCES
from src.synthesizer import BRIEFING_TOOL, build_fallback_briefing, extract_json, extract_schema, format_tw_date


def test_extract_json_from_wrapped_text() -> None:
    payload = 'Here you go {"headline":"A","sections":{"geo":[]},"keywords":[]}'
    assert extract_json(payload)["headline"] == "A"


def test_format_tw_date_uses_traditional_weekday() -> None:
    assert format_tw_date(datetime(2026, 6, 5)) == "2026年06月05日 星期五"


def test_new_retail_and_pos_boards_are_required_and_fallback_compatible() -> None:
    schema = extract_schema(BRIEFING_TOOL)
    assert {"retail_hospitality_ai", "pos_kiosk_dynamics", "retail_market_data"} <= set(schema["required"])
    assert "pos_kiosk_dynamics" in SOURCES
    retired_keys = {"industry" + "_trends", "pos" + "_competitors", "pos" + "_retail"}
    assert not retired_keys & set(schema["properties"])

    fallback = build_fallback_briefing({}, "2026年06月05日 星期五")
    assert fallback["retail_hospitality_ai"] == []
    assert fallback["pos_kiosk_dynamics"] == []
    assert fallback["retail_market_data"] == []
