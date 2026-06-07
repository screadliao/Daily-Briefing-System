# Daily Briefing System

Auto-generate a weekday morning briefing for Scread and deliver it to email and/or Notion.

## Flow

```text
fetcher -> synthesizer -> formatter -> delivery
```

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python main.py --dry-run --save-html preview.html
```

`--dry-run` prints JSON and skips delivery.

If `ANTHROPIC_API_KEY` is missing during dry run, the system falls back to a deterministic local summary so the pipeline remains testable.
