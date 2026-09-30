# Copilot Instructions for this repository

## Project purpose
This repository contains a Python Telegram trading bot for market monitoring and trading workflow automation.

## Security rules
- Never commit real secrets.
- Keep all production values in a local `.env` file only.
- Use `.env.example` as the template for required environment variables.
- Do not expose Telegram bot tokens, API keys, or database credentials.

## Structure overview
- `bot/` contains the application code.
- `bot/services/` contains market data, risk management, AI analysis, and execution logic.
- `bot/handlers/` contains Telegram command handlers.
- `bot/models/` contains DTO/model definitions.
- `data/` is for runtime-generated logs and database files.

## Running locally
1. Copy `.env.example` to `.env`.
2. Fill in the real values locally.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the bot:
   ```bash
   python -m bot.main
   ```

## Review guidance for AI tools
- Prefer improvements that keep configuration externalized.
- Avoid hardcoding secrets or environment values.
- Keep log generation and database files out of source control.
- Favor small, testable changes in the service layer.
- Preserve the paper-trading safety model unless the user explicitly asks for live execution.
