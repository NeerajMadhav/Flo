# app/services/nlp_service.py
"""OpenRouter NLP client — parse, edit, clarify, insight."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import NLPParseError
from app.nlp.prompts import (
    build_clarify_prompt,
    build_edit_prompt,
    build_insight_prompt,
    build_parse_prompt,
)
from app.nlp.schemas import ParsedMessage
from app.services.audit_service import AuditService
from app.services.category_service import CategoryService
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.guardrails import GuardrailCode, explain
from app.utils.logger import get_logger, log_event
from app.utils.sanitizer import sanitize_message

logger = get_logger("flo.nlp")

_LOW_CONFIDENCE = 0.7


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object from an LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        # maybe a JSON array (insights)
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end >= 0:
            return {"_array": json.loads(text[start : end + 1])}
        raise NLPParseError()
    return json.loads(text[start : end + 1])


class NLPService:
    """Calls OpenRouter with the correct prompt for the current bot state."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self._audit = AuditService(session)

    async def _chat(
        self,
        system: str,
        user: str,
        *,
        chain: list[str] | None = None,
        model: str | None = None,
    ) -> str:
        """
        Try models in order: role chain (primary + 3 role fallbacks) then global.
        `model` alone is treated as a 1-item chain (tests / overrides).
        """
        from app.core.concurrency import nlp_slot

        if chain is None:
            if model:
                global_fb = (
                    self.settings.nlp_global_fallback_model
                    or self.settings.nlp_fallback_model
                )
                chain = self.settings.dedupe_models(model, global_fb)
            else:
                chain = self.settings.parse_model_chain()
        models = chain
        last_err: Exception | None = None
        async with nlp_slot():
            for attempt, m in enumerate(models):
                try:
                    async with httpx.AsyncClient(
                        timeout=self.settings.nlp_timeout_seconds
                    ) as client:
                        resp = await client.post(
                            f"{self.settings.openrouter_base_url}/chat/completions",
                            headers={
                                "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": m,
                                "temperature": self.settings.nlp_temperature,
                                "max_tokens": self.settings.nlp_max_tokens,
                                "messages": [
                                    {"role": "system", "content": system},
                                    {"role": "user", "content": user},
                                ],
                            },
                        )
                        if resp.status_code == 429:
                            log_event(
                                logger,
                                "llm.rate_limited",
                                level=logging.WARNING,
                                model=m,
                                attempt=attempt,
                            )
                            # Brief backoff before next model in the chain
                            await asyncio.sleep(min(2.0 * (attempt + 1), 6.0))
                            continue
                        resp.raise_for_status()
                        data = resp.json()
                        content = data["choices"][0]["message"]["content"]
                        if attempt > 0:
                            log_event(
                                logger,
                                "llm.fallback_used",
                                level=logging.WARNING,
                                model=m,
                                primary=models[0],
                                attempt=attempt,
                                chain_len=len(models),
                            )
                        return content
                except Exception as e:
                    last_err = e
                    log_event(
                        logger,
                        "nlp.error",
                        model=m,
                        error=str(e),
                        attempt=attempt,
                    )
                    continue
        await self._audit.record(
            "llm.unavailable",
            level=logging.ERROR,
            source="nlp",
            error=str(last_err) if last_err else "unknown",
            tried=models,
        )
        await self.session.commit()
        raise NLPParseError() from last_err

    async def _record_parse_outcome(
        self, user_id: int, parsed: ParsedMessage, *, mode: str = "parse"
    ) -> None:
        conf = float(parsed.confidence or 0)
        if conf < _LOW_CONFIDENCE and not parsed.needs_clarification:
            # Blueprint: confidence < 0.7 must enter CLARIFYING, never confirm
            parsed.needs_clarification = True
            if not parsed.clarification_question:
                parsed.clarification_question = explain(GuardrailCode.LOW_CONFIDENCE)
        if conf < _LOW_CONFIDENCE:
            await self._audit.record(
                "nlp.parse.low_confidence",
                user_id=user_id,
                level=logging.WARNING,
                source="nlp",
                parse_type=parsed.type,
                confidence=conf,
                mode=mode,
            )
        else:
            log_event(
                logger,
                "nlp.parse.success",
                level=logging.DEBUG,
                user_id=user_id,
                parse_type=parsed.type,
                confidence=conf,
                mode=mode,
            )

    def _clarify_fallback(self) -> ParsedMessage:
        """When both LLM models fail — ask, don't silently treat as unknown."""
        return ParsedMessage(
            type="unknown",
            confidence=0.0,
            needs_clarification=True,
            clarification_question=explain(GuardrailCode.NLP_UNAVAILABLE),
        )

    async def _record_parse_failure(self, user_id: int, *, mode: str) -> None:
        await self._audit.record(
            "nlp.parse.failed",
            user_id=user_id,
            level=logging.ERROR,
            source="nlp",
            new_value={"mode": mode},
        )
        await self.session.commit()

    async def parse(
        self, user_id: int, telegram_user_id: str, raw_message: str
    ) -> ParsedMessage:
        """IDLE-state parse."""
        msg = sanitize_message(raw_message)
        user_svc = UserService(self.session)
        cat_svc = CategoryService(self.session)
        state_svc = StateService(self.session)
        system = build_parse_prompt(
            user_context_block=await user_svc.get_prompt_context(user_id),
            recent_turns_block=await state_svc.get_recent_context(telegram_user_id),
            user_corrections_block=await cat_svc.get_user_corrections_for_prompt(user_id),
            category_list=await cat_svc.get_categories_for_prompt(user_id),
        )
        try:
            content = await self._chat(system, f"<user_message>{msg}</user_message>")
        except NLPParseError:
            return self._clarify_fallback()
        try:
            data = _extract_json(content)
            parsed = ParsedMessage.model_validate(data)
            await self._record_parse_outcome(user_id, parsed, mode="parse")
            return parsed
        except Exception:
            await self._record_parse_failure(user_id, mode="parse")
            return self._clarify_fallback()

    async def parse_edit(
        self, user_id: int, pending_entry: dict[str, Any], raw_message: str
    ) -> ParsedMessage:
        """EDIT-state reparse of a pending entry."""
        cat_svc = CategoryService(self.session)
        system = build_edit_prompt(
            pending_entry_json=json.dumps(pending_entry),
            category_list=await cat_svc.get_categories_for_prompt(user_id),
        )
        try:
            content = await self._chat(system, sanitize_message(raw_message))
        except NLPParseError:
            return self._clarify_fallback()
        try:
            data = _extract_json(content)
            parsed = ParsedMessage.model_validate(data)
            await self._record_parse_outcome(user_id, parsed, mode="edit")
            return parsed
        except Exception:
            await self._record_parse_failure(user_id, mode="edit")
            return self._clarify_fallback()

    async def parse_clarify(
        self,
        user_id: int,
        original_message: str,
        clarification_question: str,
        user_answer: str,
    ) -> ParsedMessage:
        """CLARIFYING-state combine original + answer."""
        user_svc = UserService(self.session)
        cat_svc = CategoryService(self.session)
        system = build_clarify_prompt(
            original_message=original_message,
            clarification_question=clarification_question,
            user_answer=sanitize_message(user_answer),
            user_context_block=await user_svc.get_prompt_context(user_id),
            category_list=await cat_svc.get_categories_for_prompt(user_id),
        )
        try:
            content = await self._chat(system, "Produce the final JSON parse.")
        except NLPParseError:
            return self._clarify_fallback()
        try:
            data = _extract_json(content)
            parsed = ParsedMessage.model_validate(data)
            await self._record_parse_outcome(user_id, parsed, mode="clarify")
            return parsed
        except Exception:
            await self._record_parse_failure(user_id, mode="clarify")
            return self._clarify_fallback()

    async def generate_insights(
        self,
        user_name: str,
        monthly_budget: str,
        stats_block: str,
        goals_block: str,
        period_label: str,
    ) -> list[str]:
        """INSIGHT prompt for weekly/monthly reports."""
        system = build_insight_prompt(
            user_name=user_name,
            monthly_budget=monthly_budget,
            stats_block=stats_block,
            goals_block=goals_block,
            period_label=period_label,
        )
        content = await self._chat(
            system, "generate insights", chain=self.settings.report_model_chain()
        )
        data = _extract_json(content)
        if "_array" in data:
            return [str(x) for x in data["_array"]]
        if isinstance(data, list):
            return [str(x) for x in data]
        return []
