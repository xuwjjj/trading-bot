import os

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator

load_dotenv()


class Settings(BaseModel):
	model_config = ConfigDict(validate_default=True)

	telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
	allowed_telegram_ids: set[int] = Field(
		default_factory=lambda: {
			int(value.strip())
			for value in os.getenv(
				"ALLOWED_TELEGRAM_IDS", os.getenv("ALLOWED_TELEGRAM_ID", "0")
			).split(",")
			if value.strip()
		}
	)

	gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
	gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
	binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
	binance_api_secret: str = os.getenv("BINANCE_API_SECRET", "")
	twelve_data_api_key: str = os.getenv("TWELVE_DATA_API_KEY", "")
	oanda_api_key: str = os.getenv("OANDA_API_KEY", "")
	oanda_account_id: str = os.getenv("OANDA_ACCOUNT_ID", "")

	trading_mode: str = os.getenv("TRADING_MODE", "paper").lower()
	max_risk_per_trade: float = Field(
		default=float(os.getenv("MAX_RISK_PER_TRADE", "0.02")), gt=0, le=1
	)
	max_daily_loss: float = Field(
		default=float(os.getenv("MAX_DAILY_LOSS", "0.05")), gt=0, le=1
	)
	max_open_positions: int = Field(
		default=int(os.getenv("MAX_OPEN_POSITIONS", "5")), ge=1
	)
	default_position_size: float = Field(
		default=float(os.getenv("DEFAULT_POSITION_SIZE", "0.01")), gt=0
	)

	database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/trades.db")
	log_level: str = os.getenv("LOG_LEVEL", "INFO")

	@field_validator("trading_mode")
	@classmethod
	def validate_trading_mode(cls, value: str) -> str:
		value = value.strip().lower()
		if value not in {"paper", "live"}:
			raise ValueError("TRADING_MODE must be either 'paper' or 'live'")
		return value


settings = Settings()
