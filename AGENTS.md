# AGENTS.md

This repository is a Python Telegram trading bot.

## Key points
- The app should not contain real credentials in source control.
- Use `.env` locally; `.env.example` is the safe template.
- This project is for AI review and safe iteration, not for publishing live secrets.

## Recommended workflow
1. Keep all sensitive values in local config only.
2. Update `.env.example` when adding new required settings.
3. Keep code changes scoped and documented.
4. Prefer service-layer improvements and validation before execution changes.

## Run
```bash
pip install -r requirements.txt
python -m bot.main
```

## Safety note
Do not commit real Telegram tokens, exchange API keys, or environment files.
