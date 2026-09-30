import asyncio
import html
import json
import logging
import re
from datetime import datetime, timezone
from io import BytesIO

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
from telegram import Update
from telegram.ext import ContextTypes

from ..services.ai_analyst import AIAnalystService
from ..services.indicators import IndicatorsService
from ..services.market_data import MarketDataService

logger = logging.getLogger(__name__)


class ReportsHandler:
	def __init__(self):
		self.market_data = MarketDataService()
		self.indicators = IndicatorsService()
		self.ai_analyst = AIAnalystService()

	async def generate_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		query = update.callback_query
		if query is None:
			return

		await query.answer()
		try:
			data = (query.data or "").split("|")
			if len(data) != 4 or data[0] != "timeframe":
				raise ValueError("بيانات طلب التقرير غير صالحة")
			_, market_type, symbol, timeframe = data

			await query.edit_message_text("جاري تحليل البيانات...")
			df = await asyncio.to_thread(
				self.market_data.get_market_data,
				market_type,
				symbol,
				timeframe,
			)
			indicators = await asyncio.to_thread(
				self.indicators.calculate_all_indicators, df
			)
			analysis = await asyncio.to_thread(
				self.ai_analyst.generate_analysis,
				symbol,
				market_type,
				indicators,
				timeframe,
			)
			chart_image = await asyncio.to_thread(
				self._create_chart, df, indicators, symbol
			)

			await query.edit_message_text(
				self._format_report(symbol, market_type, indicators, analysis),
				parse_mode="HTML",
			)
			chat = update.effective_chat
			if chat is None:
				raise ValueError("تعذر تحديد المحادثة لإرسال التقرير")
			await context.bot.send_photo(chat_id=chat.id, photo=chart_image)

			trade_commands = self._generate_trade_commands(
				symbol, market_type, indicators, analysis, timeframe
			)
			document = BytesIO(trade_commands.encode("utf-8"))
			filename = re.sub(r"[^A-Za-z0-9_.-]", "_", symbol)
			await context.bot.send_document(
				chat_id=chat.id,
				document=document,
				filename=f"{filename}_trade_commands.json",
				caption="أوامر التداول (JSON)",
			)
		except Exception as exc:
			logger.exception("تعذر إنشاء التقرير")
			error_message = str(exc)
			if "TWELVE_DATA_API_KEY" in error_message:
				user_message = (
					"تقارير الفوركس والذهب تحتاج TWELVE_DATA_API_KEY في ملف .env. "
					"أضف المفتاح ثم أعد تشغيل البوت. تقارير العملات الرقمية لا تحتاجه."
				)
			elif "No market data returned" in error_message:
				user_message = (
					"لم يرجع مزود البيانات شموعًا لهذا الأصل والإطار الزمني. "
					"تحقق من الرمز أو جرّب إطارًا آخر."
				)
			elif "Twelve Data error:" in error_message:
				user_message = (
					"رفض Twelve Data الطلب أو لم يوفر بيانات لهذا الرمز. "
					"تحقق من المفتاح وحدود الخطة والرمز المطلوب."
				)
			else:
				user_message = "تعذر إنشاء التقرير. تحقق من إعدادات مزود البيانات ثم أعد المحاولة."
			await query.edit_message_text(user_message)

	def _create_chart(self, df: pd.DataFrame, indicators: dict, symbol: str) -> BytesIO:
		df_plot = df.set_index("timestamp")
		volume_available = bool(
			"volume" in df_plot.columns and df_plot["volume"].notna().any()
		)
		hlines = {
			"hlines": [indicators["support"], indicators["resistance"]],
			"colors": ["g", "r"],
			"linestyle": ["-.", "-."],
			"linewidths": 1,
		}
		fig, _ = mpf.plot(
			df_plot,
			type="candle",
			style="charles",
			title=f"\n{symbol} - تحليل فني",
			ylabel="السعر",
			volume=volume_available,
			ylabel_lower="الحجم",
			hlines=hlines,
			figsize=(12, 8),
			returnfig=True,
		)
		buffer = BytesIO()
		try:
			fig.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
			buffer.seek(0)
		finally:
			plt.close(fig)
		return buffer

	def _format_report(
		self, symbol: str, market_type: str, indicators: dict, analysis: dict
	) -> str:
		market_names = {
			"crypto": "العملات الرقمية",
			"forex": "الفوركس",
			"gold": "الذهب",
		}
		escape = html.escape
		return f"""
📊 <b>تقرير تحليل فني</b>

<b>الأصل:</b> {escape(symbol)}
<b>السوق:</b> {escape(market_names.get(market_type, market_type))}
<b>السعر الحالي:</b> {float(indicators['current_price']):.4f}
<b>التغير 24 ساعة:</b> {float(indicators['price_change_24h']):.2f}%

📈 <b>المؤشرات الفنية:</b>
• RSI (14): {float(indicators['rsi']):.2f}
• MACD: {float(indicators['macd']):.4f}
• ATR (14): {float(indicators['atr']):.4f}
• Bollinger Bands: {float(indicators['bb_upper']):.4f} / {float(indicators['bb_middle']):.4f} / {float(indicators['bb_lower']):.4f}

🎯 <b>المستويات المهمة:</b>
• الدعم: {float(indicators['support']):.4f}
• المقاومة: {float(indicators['resistance']):.4f}
• الاتجاه: {escape(str(indicators['trend']))}
• التقلب: {escape(str(indicators['volatility']))}

🤖 <b>تحليل الذكاء الاصطناعي:</b>
{escape(str(analysis['analysis_text']))}

💡 <b>التوصية:</b>
• الاتجاه: {escape(str(analysis['direction']))}
• سعر الدخول: {float(analysis['entry_price']):.4f}
• جني الأرباح: {float(analysis['take_profit']):.4f}
• وقف الخسارة: {float(analysis['stop_loss']):.4f}
• نسبة الثقة: {float(analysis['confidence']):.2f}%
• المدة المتوقعة: {escape(str(analysis['expected_duration']))}
• نسبة المخاطرة/العائد: {float(analysis['risk_reward_ratio']):.2f}

⚠️ <i>هذا التحليل للأغراض التعليمية فقط. تداول بمسؤولية.</i>
"""

	def _generate_trade_commands(
		self,
		symbol: str,
		market_type: str,
		indicators: dict,
		analysis: dict,
		timeframe: str = "1h",
	) -> str:
		direction = analysis["direction"]
		commands = {
			"symbol": symbol,
			"market_type": market_type,
			"side": "buy" if direction == "شراء" else "sell" if direction == "بيع" else "wait",
			"entry_price": analysis["entry_price"],
			"take_profit": analysis["take_profit"],
			"stop_loss": analysis["stop_loss"],
			"confidence": analysis["confidence"],
			"expected_duration": analysis["expected_duration"],
			"conditions": {
				"pause_if_loss_exceeds": "5%",
				"resume_condition": "manual_approval",
				"max_hold_time": analysis["expected_duration"],
			},
			"metadata": {
				"generated_at": datetime.now(timezone.utc).isoformat(),
				"timeframe": timeframe,
				"indicators": {
					"rsi": indicators["rsi"],
					"macd": indicators["macd"],
					"atr": indicators["atr"],
				},
			},
		}
		return json.dumps(commands, indent=2, ensure_ascii=False, default=float)
