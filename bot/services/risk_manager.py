import logging
from datetime import datetime, timedelta
from math import isfinite

from ..config import settings
from ..database import Trade, get_db

logger = logging.getLogger(__name__)


class RiskManagerService:
	def __init__(self):
		self.max_risk_per_trade = settings.max_risk_per_trade
		self.max_daily_loss = settings.max_daily_loss
		self.max_open_positions = settings.max_open_positions

	def validate_trade(self, trade_data: dict, account_balance: float) -> dict:
		try:
			account_balance = float(account_balance)
			entry_price = float(trade_data["entry_price"])
			stop_loss = float(trade_data["stop_loss"])
			take_profit = float(trade_data["take_profit"])
			side = str(trade_data["side"]).lower()
		except (KeyError, TypeError, ValueError):
			return {"valid": False, "reason": "بيانات الصفقة أو رصيد الحساب غير صالحة"}

		if not all(isfinite(value) for value in (account_balance, entry_price, stop_loss, take_profit)):
			return {"valid": False, "reason": "يجب أن تكون القيم أرقامًا صالحة"}
		if account_balance <= 0 or entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
			return {"valid": False, "reason": "يجب أن تكون الأسعار ورصيد الحساب أكبر من صفر"}
		if side not in {"buy", "sell"}:
			return {"valid": False, "reason": "اتجاه الصفقة يجب أن يكون buy أو sell"}
		if (side == "buy" and not stop_loss < entry_price < take_profit) or (
			side == "sell" and not take_profit < entry_price < stop_loss
		):
			return {"valid": False, "reason": "مستويات الوقف والهدف لا تطابق اتجاه الصفقة"}

		db = get_db()
		try:
			open_positions = db.query(Trade).filter(Trade.status == "open").count()
		finally:
			db.close()
		if open_positions >= self.max_open_positions:
			return {
				"valid": False,
				"reason": f"تم الوصول للحد الأقصى للصفقات المفتوحة ({self.max_open_positions})",
			}

		risk = abs(entry_price - stop_loss)
		risk_amount = account_balance * self.max_risk_per_trade
		position_size = risk_amount / risk
		daily_loss = self._get_daily_loss()
		max_loss_amount = account_balance * self.max_daily_loss
		if daily_loss + risk_amount > max_loss_amount:
			return {
				"valid": False,
				"reason": f"الصفقة ستتجاوز حد الخسارة اليومية ({self.max_daily_loss * 100:.1f}%)",
			}

		risk_reward_ratio = abs(take_profit - entry_price) / risk
		if risk_reward_ratio < 1.5:
			return {
				"valid": False,
				"reason": f"نسبة المخاطرة/العائد منخفضة ({risk_reward_ratio:.2f})",
			}
		trade_data["position_size"] = position_size
		return {
			"valid": True,
			"position_size": position_size,
			"risk_reward_ratio": risk_reward_ratio,
		}

	def _get_daily_loss(self) -> float:
		start = datetime.combine(datetime.utcnow().date(), datetime.min.time())
		end = start + timedelta(days=1)
		db = get_db()
		try:
			losses = (
				db.query(Trade.pnl)
				.filter(
					Trade.status == "closed",
					Trade.exit_time >= start,
					Trade.exit_time < end,
					Trade.pnl < 0,
				)
				.all()
			)
			return sum(abs(float(row[0] or 0)) for row in losses)
		finally:
			db.close()

	def check_stop_loss_take_profit(self, trade: Trade, current_price: float) -> dict:
		if trade.stop_loss is None or trade.take_profit is None:
			return {"action": "hold", "reason": "مستويات الوقف والهدف غير محددة"}
		if trade.side == "buy":
			if current_price <= trade.stop_loss:
				return {"action": "close", "reason": "وقف الخسارة"}
			if current_price >= trade.take_profit:
				return {"action": "close", "reason": "جني الأرباح"}
		elif trade.side == "sell":
			if current_price >= trade.stop_loss:
				return {"action": "close", "reason": "وقف الخسارة"}
			if current_price <= trade.take_profit:
				return {"action": "close", "reason": "جني الأرباح"}
		return {"action": "hold", "reason": "استمرار"}

	def emergency_stop(self):
		db = get_db()
		try:
			open_trades = db.query(Trade).filter(Trade.status == "open").all()
			paper_trades = [trade for trade in open_trades if trade.is_paper]
			live_trades = [trade for trade in open_trades if not trade.is_paper]
			now = datetime.utcnow()
			for trade in paper_trades:
				trade.status = "closed"
				trade.exit_price = trade.entry_price
				trade.exit_time = now
				trade.pnl = 0.0
				trade.reason = "إيقاف طوارئ"
			db.commit()
			if live_trades:
				logger.critical(
					"Emergency stop left %s live positions open; exchange closes require current prices",
					len(live_trades),
				)
			logger.warning("تم إيقاف %s صفقة تجريبية", len(paper_trades))
			return {"paper_closed": len(paper_trades), "live_positions_open": len(live_trades)}
		except Exception:
			db.rollback()
			logger.exception("خطأ في الإيقاف الطارئ")
			return {"paper_closed": 0, "live_positions_open": 0}
		finally:
			db.close()
