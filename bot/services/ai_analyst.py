import json
import logging
import math
from urllib.parse import quote

import requests

from ..config import settings

logger = logging.getLogger(__name__)


class AIAnalystService:
	def _generate_text(
		self,
		contents: list[dict],
		system_instruction: str,
		max_output_tokens: int = 512,
	) -> str:
		if not settings.gemini_api_key:
			raise RuntimeError("GEMINI_API_KEY غير مضبوط في ملف .env")

		model = quote(settings.gemini_model, safe="-._")
		url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
		try:
			response = requests.post(
				url,
				params={"key": settings.gemini_api_key},
				json={
					"systemInstruction": {"parts": [{"text": system_instruction}]},
					"contents": contents,
					"generationConfig": {
						"temperature": 0.3,
						"maxOutputTokens": max_output_tokens,
						"thinkingConfig": {"thinkingLevel": "LOW"},
					},
				},
				timeout=(3, 25),
			)
		except requests.RequestException:
			raise RuntimeError("تعذر الاتصال بـGemini أو انتهت مهلة الطلب.") from None

		if not response.ok:
			logger.warning("Gemini API returned HTTP %s", response.status_code)
			if response.status_code in {401, 403}:
				raise RuntimeError("مفتاح Gemini غير صالح أو أن Gemini API غير مفعّل.")
			if response.status_code == 404:
				raise RuntimeError("نموذج Gemini غير متاح؛ تحقق من GEMINI_MODEL.")
			if response.status_code == 429:
				raise RuntimeError("تم تجاوز حصة Gemini مؤقتًا؛ حاول لاحقًا.")
			raise RuntimeError(f"تعذر على Gemini معالجة الطلب (HTTP {response.status_code}).")

		try:
			payload = response.json()
			parts = payload["candidates"][0]["content"]["parts"]
			text = "".join(part.get("text", "") for part in parts).strip()
		except (ValueError, KeyError, IndexError, TypeError):
			raise RuntimeError("أعاد Gemini استجابة غير متوقعة.") from None

		if not text:
			raise RuntimeError("لم يُرجع Gemini نصًا للإجابة.")
		return text

	def answer_question(self, question: str, history: list[dict] | None = None) -> str:
		contents = []
		for turn in (history or [])[-8:]:
			role = turn.get("role")
			if role not in {"user", "model"}:
				continue
			text = " ".join(
				part.get("text", "")
				for part in turn.get("parts", [])
				if isinstance(part.get("text"), str)
			)
			if text:
				contents.append({"role": role, "parts": [{"text": text[:1200]}]})
		contents.append({"role": "user", "parts": [{"text": question[:3000]}]})
		return self._generate_text(
			contents,
			"أنت مساعد عربي ودود داخل بوت تيليجرام. أجب بوضوح واختصار وباللغة التي يسأل بها المستخدم. "
			"أجب عن الأسئلة العامة، واشرح الأسواق بمعلومات تعليمية لا تُعد ضمانًا للربح أو نصيحة مالية شخصية. "
			"لا تدّعِ تنفيذ صفقات أو الوصول إلى بيانات مباشرة ما لم تُقدّم لك ضمن المحادثة.",
			max_output_tokens=512,
		)

	def generate_analysis(
		self, symbol: str, market_type: str, indicators: dict, timeframe: str
	) -> dict:
		current_price = float(indicators.get("current_price", 0.0) or 0.0)
		try:
			prompt = f"""
حلل بيانات {symbol} في سوق {market_type} على الإطار {timeframe}.
قدّم تحليلًا احتماليًا تعليميًا لا يمثل ضمانًا للنتائج، وأجب بكائن JSON فقط.

المؤشرات: {json.dumps(indicators, ensure_ascii=False, default=float)}

استخدم المفاتيح: analysis_text, direction, entry_price, take_profit,
stop_loss, confidence, expected_duration, key_levels, risk_reward_ratio.
direction يجب أن يكون إحدى القيم: شراء، بيع، انتظار.
confidence يجب أن يكون رقمًا بين 0 و100 دون علامة %.
"""
			response_text = self._generate_text(
				[{"role": "user", "parts": [{"text": prompt}]}],
				"أنت محلل فني. لا تقدّم توصية مضمونة، وأخرج JSON صالحًا فقط.",
				max_output_tokens=768,
			)
			if response_text.startswith("```"):
				response_text = response_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
			analysis = json.loads(response_text)
			if not isinstance(analysis, dict):
				raise ValueError("Gemini response is not a JSON object")

			analysis.setdefault("analysis_text", "لا يوجد نص للتحليل")
			analysis.setdefault("direction", "انتظار")
			analysis.setdefault("entry_price", current_price)
			analysis.setdefault("take_profit", current_price)
			analysis.setdefault("stop_loss", current_price)
			analysis.setdefault("confidence", 0)
			analysis.setdefault("expected_duration", "غير محدد")
			analysis.setdefault("key_levels", [])
			analysis.setdefault("risk_reward_ratio", 0)
			numeric_defaults = {
				"entry_price": current_price,
				"take_profit": current_price,
				"stop_loss": current_price,
				"confidence": 0.0,
				"risk_reward_ratio": 0.0,
			}
			for field, default in numeric_defaults.items():
				value = analysis.get(field, default)
				if isinstance(value, str):
					value = value.strip().replace("%", "").replace(",", "")
				try:
					number = float(value)
				except (TypeError, ValueError):
					number = default
				analysis[field] = number if math.isfinite(number) else default
			analysis["confidence"] = min(100.0, max(0.0, analysis["confidence"]))
			if not isinstance(analysis["key_levels"], list):
				analysis["key_levels"] = []
			return analysis
		except Exception as exc:
			logger.exception("تعذر إنشاء تحليل Gemini")
			failure_message = (
				str(exc)
				if isinstance(exc, RuntimeError)
				else "أعاد Gemini استجابة تحليل غير صالحة."
			)
			return {
				"analysis_text": f"تعذر تحليل Gemini: {failure_message}",
				"direction": "انتظار",
				"entry_price": current_price,
				"take_profit": current_price,
				"stop_loss": current_price,
				"confidence": 0,
				"expected_duration": "غير محدد",
				"key_levels": [],
				"risk_reward_ratio": 0,
			}
