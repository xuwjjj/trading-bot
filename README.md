# Trading Bot

A Telegram trading bot built with Python for market monitoring, AI-assisted analysis, and trade execution workflows.

## Setup

1. Copy `.env.example` to `.env`.
2. Fill in your real tokens and API keys locally.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the bot:

```bash
python -m bot.main
```

## Security

This repository intentionally ignores local secrets:

- `.env`
- `.env.*` (except `.env.example`)
- `.venv/`
- generated data and logs

Do not commit real credentials. Keep them in your local `.env` file only.

## Docker

```bash
docker-compose up --build
```
