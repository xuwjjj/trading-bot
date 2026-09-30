import pandas as pd
import requests
from binance.client import Client

from ..config import settings


class MarketDataService:
	TWELVE_DATA_INTERVALS = {
		"1h": "1h",
		"4h": "4h",
		"1d": "1day",
		"1day": "1day",
		"1w": "1week",
		"1week": "1week",
	}

	def __init__(self):
		self.binance_client = Client(
			settings.binance_api_key or None,
			settings.binance_api_secret or None,
		)

	def get_crypto_data(
		self, symbol: str, interval: str = "1h", limit: int = 100
	) -> pd.DataFrame:
		if not 1 <= limit <= 1000:
			raise ValueError("limit must be between 1 and 1000")
		klines = self.binance_client.get_klines(
			symbol=symbol.upper(), interval=interval, limit=limit
		)
		columns = [
			"timestamp", "open", "high", "low", "close", "volume",
			"close_time", "quote_volume", "trades", "taker_buy_base",
			"taker_buy_quote", "ignore",
		]
		df = pd.DataFrame(klines, columns=columns)
		if df.empty:
			raise ValueError(f"No market data returned for {symbol}")
		df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
		for column in ["open", "high", "low", "close", "volume"]:
			df[column] = pd.to_numeric(df[column], errors="coerce")
		return df[["timestamp", "open", "high", "low", "close", "volume"]]

	def get_forex_data(
		self, symbol: str, interval: str = "1h", limit: int = 100
	) -> pd.DataFrame:
		if not settings.twelve_data_api_key:
			raise RuntimeError("TWELVE_DATA_API_KEY غير مضبوط في ملف .env")
		if limit < 1:
			raise ValueError("limit must be greater than zero")
		data_interval = self.TWELVE_DATA_INTERVALS.get(interval)
		if data_interval is None:
			raise ValueError(f"Unsupported Twelve Data interval: {interval}")

		try:
			response = requests.get(
				"https://api.twelvedata.com/time_series",
				params={
					"apikey": settings.twelve_data_api_key,
					"symbol": symbol,
					"interval": data_interval,
					"outputsize": limit,
					"format": "JSON",
				},
				timeout=20,
			)
		except requests.RequestException:
			raise RuntimeError("تعذر الاتصال بمزود بيانات Twelve Data.") from None
		if not response.ok:
			raise RuntimeError(f"Twelve Data returned HTTP {response.status_code}")
		try:
			data = response.json()
		except ValueError:
			raise RuntimeError("أعاد Twelve Data استجابة غير صالحة.") from None
		if "values" not in data:
			raise RuntimeError(
				f"Twelve Data error: {data.get('message', 'No values returned')}"
			)

		df = pd.DataFrame(data["values"]).rename(columns={"datetime": "timestamp"})
		if df.empty:
			raise ValueError(f"No market data returned for {symbol}")
		df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
		for column in ["open", "high", "low", "close"]:
			df[column] = pd.to_numeric(df[column], errors="coerce")
		if "volume" not in df:
			df["volume"] = 0.0
		else:
			df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
		df = df.dropna(subset=["timestamp", "open", "high", "low", "close"])
		df = df.sort_values("timestamp").reset_index(drop=True)
		return df[["timestamp", "open", "high", "low", "close", "volume"]]

	def get_gold_data(self, interval: str = "1h", limit: int = 100) -> pd.DataFrame:
		return self.get_forex_data("XAU/USD", interval, limit)

	def get_market_data(
		self, market_type: str, symbol: str, interval: str = "1h", limit: int = 100
	) -> pd.DataFrame:
		market_type = market_type.lower()
		if market_type == "crypto":
			return self.get_crypto_data(symbol, interval, limit)
		if market_type == "forex":
			return self.get_forex_data(symbol, interval, limit)
		if market_type == "gold":
			return self.get_gold_data(interval, limit)
		raise ValueError(f"Unsupported market type: {market_type}")
