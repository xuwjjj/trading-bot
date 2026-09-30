import logging
from datetime import datetime

from binance.client import Client

from ..config import settings
from ..database import Trade, get_db

logger = logging.getLogger(__name__)


class TradeExecutorService:
	def __init__(self):
		self.client = Client(
			settings.binance_api_key or None,
			settings.binance_api_secret or None,
		)
		self.is_paper = settings.trading_mode == "paper"

	def execute_trade(self, trade_data: dict) -> dict:
		db = get_db()
		try:
			side = str(trade_data["side"]).lower()
			market_type = str(trade_data["market_type"]).lower()
			if side not in {"buy", "sell"}:
				raise ValueError("side must be buy or sell")
			if not self.is_paper and market_type != "crypto":
				raise NotImplementedError("التنفيذ الحقيقي متاح حاليًا للعملات الرقمية فقط")
			if not self.is_paper and not (
				settings.binance_api_key and settings.binance_api_secret
			):
				raise RuntimeError("مفاتيح Binance غير مضبوطة في ملف .env")

			order = None
			if not self.is_paper:
				order = self._execute_binance_trade(trade_data)

			trade = Trade(
				symbol=trade_data["symbol"],
				market_type=market_type,
				side=side,
				entry_price=float(trade_data["entry_price"]),
				take_profit=trade_data.get("take_profit"),
				stop_loss=trade_data.get("stop_loss"),
				position_size=float(trade_data["position_size"]),
				status="open",
				is_paper=self.is_paper,
				analysis_report=trade_data.get("analysis_report"),
			)
			db.add(trade)
			db.commit()
			db.refresh(trade)
			logger.info("تم تسجيل الصفقة: %s - %s", trade.symbol, trade.side)
			return {
				"success": True,
				"trade_id": trade.id,
				"message": "تم تسجيل الصفقة بنجاح",
				"order": order,
			}
		except Exception as exc:
			db.rollback()
			logger.exception("خطأ في تنفيذ الصفقة")
			return {"success": False, "message": str(exc)}
		finally:
			db.close()

	def _execute_binance_trade(self, trade_data: dict, side: str = None):
		order_side = side or trade_data["side"].lower()
		return self.client.create_order(
			symbol=trade_data["symbol"].upper(),
			side=Client.SIDE_BUY if order_side == "buy" else Client.SIDE_SELL,
			type=Client.ORDER_TYPE_MARKET,
			quantity=float(trade_data["position_size"]),
		)

	def close_trade(self, trade_id: int, exit_price: float, reason: str) -> dict:
		db = get_db()
		try:
			trade = db.query(Trade).filter(Trade.id == trade_id).first()
			if trade is None or trade.status != "open":
				return {"success": False, "message": "الصفقة المفتوحة غير موجودة"}

			if not trade.is_paper:
				if trade.market_type != "crypto":
					raise NotImplementedError("الإغلاق الحقيقي متاح حاليًا للعملات الرقمية فقط")
				closing_side = "sell" if trade.side == "buy" else "buy"
				self._execute_binance_trade(
					{"symbol": trade.symbol, "position_size": trade.position_size},
					side=closing_side,
				)

			exit_price = float(exit_price)
			pnl = (
				(exit_price - trade.entry_price) * trade.position_size
				if trade.side == "buy"
				else (trade.entry_price - exit_price) * trade.position_size
			)
			trade.exit_price = exit_price
			trade.exit_time = datetime.utcnow()
			trade.pnl = pnl
			trade.status = "closed"
			trade.reason = reason
			db.commit()
			return {"success": True, "pnl": pnl, "message": "تم إغلاق الصفقة بنجاح"}
		except Exception as exc:
			db.rollback()
			logger.exception("خطأ في إغلاق الصفقة")
			return {"success": False, "message": str(exc)}
		finally:
			db.close()
