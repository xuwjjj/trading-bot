import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
	Application,
	CallbackQueryHandler,
	CommandHandler,
	ContextTypes,
	MessageHandler,
	filters,
)

from .config import settings
from .handlers.reports import ReportsHandler
from .services.ai_analyst import AIAnalystService

logging.basicConfig(
	format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
	level=getattr(logging, settings.log_level.upper(), logging.INFO),
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class TradingBot:
	def __init__(self):
		if not settings.telegram_token:
			raise ValueError("TELEGRAM_BOT_TOKEN غير مضبوط في ملف .env")
		self.app = Application.builder().token(settings.telegram_token).build()
		self.reports_handler = ReportsHandler()
		self.ai_analyst = AIAnalystService()
		self._setup_handlers()

	def _setup_handlers(self):
		self.app.add_handler(CommandHandler("start", self.start_command))
		self.app.add_handler(CommandHandler("report", self.report_menu))
		self.app.add_handler(CallbackQueryHandler(self.button_handler))
		self.app.add_handler(CommandHandler("settings", self.settings_command))
		self.app.add_handler(CommandHandler("emergency_stop", self.emergency_stop))
		self.app.add_handler(CommandHandler("ask", self.ask_command))
		self.app.add_handler(CommandHandler("newchat", self.new_chat_command))
		self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.chat_message))

	def _is_authorized(self, update: Update) -> bool:
		user = update.effective_user
		return user is not None and user.id in settings.allowed_telegram_ids

	async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		if not self._is_authorized(update):
			if update.effective_message:
				await update.effective_message.reply_text("غير مصرح لك باستخدام هذا البوت")
			return

		mode_label = "التجريبي" if settings.trading_mode == "paper" else "الحقيقي"
		welcome_text = f"""
🤖 <b>مرحباً بك في بوت التداول الذكي</b>

هذا البوت يساعدك في تحليل الأسواق المالية وتنفيذ الصفقات.

<b>الأوامر المتاحة:</b>

/report - توليد تقرير تحليلي
/settings - إعدادات التداول
/ask - اسأل المساعد الذكي
/newchat - بدء محادثة جديدة
/emergency_stop - إيقاف طارئ

⚠️ <i>البوت يعمل حالياً في الوضع {mode_label}</i>
"""
		if update.effective_message:
			await update.effective_message.reply_text(welcome_text, parse_mode="HTML")

	async def report_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		if not self._is_authorized(update):
			return

		keyboard = [[
			InlineKeyboardButton("العملات الرقمية", callback_data="market|crypto"),
			InlineKeyboardButton("الفوركس", callback_data="market|forex"),
			InlineKeyboardButton("الذهب", callback_data="market|gold"),
		]]
		if update.effective_message:
			await update.effective_message.reply_text(
				"اختر السوق للتحليل:",
				reply_markup=InlineKeyboardMarkup(keyboard),
			)

	async def ask_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		message = update.effective_message
		if not self._is_authorized(update):
			if message:
				await message.reply_text("غير مصرح لك باستخدام هذا البوت")
			return
		question = " ".join(context.args).strip()
		if not question:
			if message:
				await message.reply_text("اكتب سؤالك بعد الأمر /ask أو أرسل السؤال مباشرة.")
			return
		await self._answer_question(update, context, question)

	async def chat_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		message = update.effective_message
		if not self._is_authorized(update):
			if message:
				await message.reply_text("غير مصرح لك باستخدام هذا البوت")
			return
		if message and message.text:
			await self._answer_question(update, context, message.text.strip())

	async def _answer_question(
		self, update: Update, context: ContextTypes.DEFAULT_TYPE, question: str
	):
		message = update.effective_message
		if message is None:
			return
		if len(question) > 4000:
			await message.reply_text("السؤال طويل جدًا؛ أرسله على أجزاء أقصر.")
			return
		if not settings.gemini_api_key:
			await message.reply_text("أضف GEMINI_API_KEY إلى ملف .env ثم أعد تشغيل البوت.")
			return

		try:
			await message.chat.send_action(ChatAction.TYPING)
		except Exception:
			logger.debug("Could not send Telegram typing status", exc_info=True)
		history = context.user_data.setdefault("gemini_history", [])
		try:
			answer = await asyncio.to_thread(
				self.ai_analyst.answer_question, question, list(history)
			)
		except RuntimeError as exc:
			logger.warning("Gemini chat request failed: %s", exc)
			await message.reply_text(str(exc))
			return
		except Exception:
			logger.exception("Gemini chat request failed")
			await message.reply_text("تعذر الحصول على إجابة الآن بسبب خطأ غير متوقع.")
			return

		history.extend([
			{"role": "user", "parts": [{"text": question}]},
			{"role": "model", "parts": [{"text": answer}]},
		])
		context.user_data["gemini_history"] = history[-20:]
		await message.reply_text(answer[:4000])

	async def new_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		if not self._is_authorized(update):
			return
		context.user_data.pop("gemini_history", None)
		if update.effective_message:
			await update.effective_message.reply_text("بدأنا محادثة جديدة. اكتب سؤالك.")

	async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		query = update.callback_query
		if query is None:
			return

		if not self._is_authorized(update):
			await query.answer("غير مصرح", show_alert=True)
			return

		data = query.data or ""
		if data.startswith("timeframe|"):
			await self.reports_handler.generate_report(update, context)
			return

		await query.answer()
		if data.startswith("market|"):
			await self._show_symbols_menu(query, data.split("|", 1)[1])
		elif data.startswith("symbol|"):
			parts = data.split("|")
			if len(parts) == 3:
				await self._show_timeframe_menu(query, parts[1], parts[2])
		elif data.startswith("setting|"):
			await query.edit_message_text(
				"لتغيير الإعدادات، عدّل القيم في ملف .env ثم أعد تشغيل البوت."
			)
		elif data == "back":
			await query.edit_message_text(
				"اختر السوق للتحليل:",
				reply_markup=InlineKeyboardMarkup([[
					InlineKeyboardButton("العملات الرقمية", callback_data="market|crypto"),
					InlineKeyboardButton("الفوركس", callback_data="market|forex"),
					InlineKeyboardButton("الذهب", callback_data="market|gold"),
				]]),
			)

	async def _show_symbols_menu(self, query, market_type: str):
		symbols = {
			"crypto": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"],
			"forex": ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"],
			"gold": ["XAU/USD"],
		}
		keyboard = [
			[InlineKeyboardButton(symbol, callback_data=f"symbol|{market_type}|{symbol}")]
			for symbol in symbols.get(market_type, [])
		]
		keyboard.append([InlineKeyboardButton("رجوع", callback_data="back")])
		await query.edit_message_text(
			"اختر الأصل:", reply_markup=InlineKeyboardMarkup(keyboard)
		)

	async def _show_timeframe_menu(self, query, market_type: str, symbol: str):
		keyboard = [
			[
				InlineKeyboardButton("1 ساعة", callback_data=f"timeframe|{market_type}|{symbol}|1h"),
				InlineKeyboardButton("4 ساعات", callback_data=f"timeframe|{market_type}|{symbol}|4h"),
			],
			[
				InlineKeyboardButton("يومي", callback_data=f"timeframe|{market_type}|{symbol}|1day"),
				InlineKeyboardButton("أسبوعي", callback_data=f"timeframe|{market_type}|{symbol}|1week"),
			],
			[InlineKeyboardButton("رجوع", callback_data=f"market|{market_type}")],
		]
		await query.edit_message_text(
			f"اختر الإطار الزمني لـ {symbol}:",
			reply_markup=InlineKeyboardMarkup(keyboard),
		)

	async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		if not self._is_authorized(update):
			return
		keyboard = [
			[InlineKeyboardButton("وضع التداول", callback_data="setting|mode")],
			[InlineKeyboardButton("حد المخاطرة", callback_data="setting|risk")],
			[InlineKeyboardButton("حد الخسارة اليومي", callback_data="setting|daily_loss")],
			[InlineKeyboardButton("عدد الصفقات المفتوحة", callback_data="setting|positions")],
			[InlineKeyboardButton("رجوع", callback_data="back")],
		]
		if update.effective_message:
			await update.effective_message.reply_text(
				"إعدادات التداول",
				reply_markup=InlineKeyboardMarkup(keyboard),
			)

	async def emergency_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
		if not self._is_authorized(update):
			return
		from .services.risk_manager import RiskManagerService

		RiskManagerService().emergency_stop()
		if update.effective_message:
			await update.effective_message.reply_text(
				"تم تسجيل طلب الإيقاف الطارئ. تحقق من منصة التداول لإغلاق أي مراكز حقيقية."
			)

	def run(self):
		logger.info("بدء تشغيل البوت")
		self.app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
	TradingBot().run()
