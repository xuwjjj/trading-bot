import pandas as pd


class IndicatorsService:
	REQUIRED_COLUMNS = {"high", "low", "close"}

	def calculate_all_indicators(self, df: pd.DataFrame) -> dict:
		missing = self.REQUIRED_COLUMNS.difference(df.columns)
		if missing:
			raise ValueError(f"Missing required market data columns: {', '.join(sorted(missing))}")
		if len(df) < 50:
			raise ValueError("At least 50 candles are required to calculate indicators")

		close = pd.to_numeric(df["close"], errors="coerce")
		high = pd.to_numeric(df["high"], errors="coerce")
		low = pd.to_numeric(df["low"], errors="coerce")
		if close.isna().any() or high.isna().any() or low.isna().any():
			raise ValueError("OHLC data contains invalid values")

		result = {}
		price_changes = close.diff()
		average_gains = price_changes.clip(lower=0).ewm(
			alpha=1 / 14, min_periods=14, adjust=False
		).mean()
		average_losses = -price_changes.clip(upper=0).ewm(
			alpha=1 / 14, min_periods=14, adjust=False
		).mean()
		relative_strength = average_gains / average_losses.replace(0, float("nan"))
		rsi = 100 - 100 / (1 + relative_strength)
		rsi = rsi.mask((average_losses == 0) & (average_gains > 0), 100)
		rsi = rsi.mask((average_losses == 0) & (average_gains == 0), 50)
		result["rsi"] = float(rsi.iloc[-1])

		macd_line = close.ewm(span=12, adjust=False).mean() - close.ewm(
			span=26, adjust=False
		).mean()
		macd_signal = macd_line.ewm(span=9, adjust=False).mean()
		result["macd"] = float(macd_line.iloc[-1])
		result["macd_signal"] = float(macd_signal.iloc[-1])
		result["macd_histogram"] = float((macd_line - macd_signal).iloc[-1])

		previous_close = close.shift(1)
		true_range = pd.concat(
			[high - low, (high - previous_close).abs(), (low - previous_close).abs()],
			axis=1,
		).max(axis=1)
		atr = true_range.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
		result["atr"] = float(atr.iloc[-1])

		bb_middle = close.rolling(window=20).mean()
		bb_deviation = close.rolling(window=20).std(ddof=0)
		result["bb_upper"] = float((bb_middle + 2 * bb_deviation).iloc[-1])
		result["bb_middle"] = float(bb_middle.iloc[-1])
		result["bb_lower"] = float((bb_middle - 2 * bb_deviation).iloc[-1])

		result["sma_20"] = float(close.rolling(window=20).mean().iloc[-1])
		result["sma_50"] = float(close.rolling(window=50).mean().iloc[-1])
		result["ema_20"] = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
		result["support"], result["resistance"] = self._calculate_support_resistance(df)
		result["current_price"] = float(close.iloc[-1])
		result["trend"] = self._analyze_trend(result)
		result["volatility"] = self._calculate_volatility(result["atr"], close)
		result["price_change_24h"] = (
			float((close.iloc[-1] - close.iloc[-24]) / close.iloc[-24] * 100)
			if len(close) >= 24 and close.iloc[-24] != 0
			else 0.0
		)
		return result

	def _calculate_support_resistance(self, df: pd.DataFrame, window: int = 20) -> tuple:
		recent_data = df.tail(window)
		return float(recent_data["low"].min()), float(recent_data["high"].max())

	def _analyze_trend(self, indicators: dict) -> str:
		price = indicators["current_price"]
		sma_20 = indicators["sma_20"]
		sma_50 = indicators["sma_50"]
		macd = indicators["macd"]
		macd_signal = indicators["macd_signal"]
		if price > sma_20 > sma_50 and macd > macd_signal:
			return "صاعد قوي"
		if price > sma_20 and macd > macd_signal:
			return "صاعد"
		if price < sma_20 < sma_50 and macd < macd_signal:
			return "هابط قوي"
		if price < sma_20 and macd < macd_signal:
			return "هابط"
		return "جانبي"

	def _calculate_volatility(self, atr: float, close: pd.Series) -> str:
		average_price = float(close.mean())
		volatility_pct = atr / average_price * 100 if average_price else 0
		if volatility_pct > 3:
			return "عالي"
		if volatility_pct > 1.5:
			return "متوسط"
		return "منخفض"
