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


def test_local_cli_model_arguments(monkeypatch):
    from types import SimpleNamespace
    from src import synthesizer

    calls = []
    monkeypatch.setattr(synthesizer, "_resolve_bin", lambda path, name: name)
    monkeypatch.setenv("BRIEFING_CLAUDE_MODEL", "claude-test")
    monkeypatch.setenv("BRIEFING_CODEX_MODEL", "codex-test")

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[0] == "claude":
            return SimpleNamespace(returncode=1, stdout="", stderr="failed")
        from pathlib import Path
        Path(command[command.index("-o") + 1]).write_text("ok")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(synthesizer.subprocess, "run", fake_run)
    assert synthesizer.call_local_cli("system", "prompt") == ("ok", "codex")
    assert calls[0][calls[0].index("--model") + 1] == "claude-test"
    assert calls[1][calls[1].index("-m") + 1] == "codex-test"
