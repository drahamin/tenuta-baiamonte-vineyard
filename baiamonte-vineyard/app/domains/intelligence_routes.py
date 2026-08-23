from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize_admin, authorize_write
from ..ai_usage import (
    ai_cost_summary,
    ai_request_profile,
    ai_service_summary,
    save_ai_cost_settings,
    save_ai_request_profile,
)
from ..db import transaction
from ..intelligence import ask_assistant, check_openai_service, save_intake_file
from ..service import estate_id, json_ready
from .advanced_learning import refresh_advanced_learning
from .learning_monitor import learning_monitor


router = APIRouter(tags=["intelligence"])


@router.get("/api/v1/admin/ai", dependencies=[Depends(authorize_admin)])
def admin_ai_console() -> dict[str, Any]:
    """Return provider, usage, cost, and cross-domain learning health in one console."""
    return json_ready({
        "checked_at": datetime.now(),
        "ai_cost": ai_cost_summary(),
        "ai_profile": ai_request_profile(),
        "ai_service": ai_service_summary(),
        "learning": learning_monitor(),
    })


@router.post("/api/v1/admin/ai/rebuild-learning", dependencies=[Depends(authorize_admin)])
def rebuild_advanced_learning() -> dict[str, Any]:
    """Rebuild every durable learning manifest from authoritative historical evidence."""
    return json_ready({
        "rebuilt_at": datetime.now(),
        "processes": refresh_advanced_learning(),
        "learning": learning_monitor(),
    })


@router.put("/api/v1/admin/ai-cost", dependencies=[Depends(authorize_admin)])
def update_ai_cost(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        return save_ai_cost_settings(
            float(payload.get("monthly_budget_usd", 25)),
            float(payload.get("warning_percent", 80)),
            request.headers.get("X-Remote-User-Name") or "api",
        )
    except (TypeError, ValueError) as error:
        raise HTTPException(422, "Enter a valid monthly budget and warning percentage") from error


@router.put("/api/v1/admin/ai-profile", dependencies=[Depends(authorize_admin)])
def update_ai_profile(payload: dict[str, Any], request: Request) -> dict[str, str]:
    try:
        return save_ai_request_profile(
            str(payload.get("effort") or ""),
            str(payload.get("speed") or ""),
            request.headers.get("X-Remote-User-Name") or "api",
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/api/v1/admin/ai-credit-check", dependencies=[Depends(authorize_admin)])
def recheck_ai_credit() -> dict[str, Any]:
    return check_openai_service()


@router.post("/api/v1/assistant/ask", dependencies=[Depends(authorize_write)])
async def assistant_question(payload: dict[str, Any]) -> dict[str, Any]:
    question = str(payload.get("question") or "").strip()
    language = "it" if str(payload.get("language") or "en").lower().startswith("it") else "en"
    focus = str(payload.get("focus") or "vineyard").strip().casefold()
    if focus not in {"vineyard", "laboratory", "treatments", "cellar"}:
        focus = "vineyard"
    if not question:
        raise HTTPException(422, "Enter a vineyard question")
    try:
        return await asyncio.to_thread(ask_assistant, question, language, focus)
    except Exception as error:
        raise HTTPException(502, "Assistant request failed: " + str(error)[:350]) from error


@router.post("/api/v1/assistant/suggestion", dependencies=[Depends(authorize_write)])
def save_assistant_suggestion(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    question = str(payload.get("question") or "").strip()[:4000]
    answer = str(payload.get("answer") or "").strip()[:12000]
    focus = str(payload.get("focus") or "vineyard").strip().casefold()
    if focus not in {"vineyard", "laboratory", "treatments", "cellar"}:
        focus = "vineyard"
    if not question or not answer:
        raise HTTPException(422, "A question and AI suggestion are required")
    combined = f"Question:\n{question}\n\nAI suggestion:\n{answer}\n"
    external_id = hashlib.sha256(combined.encode()).hexdigest()
    record_id = save_intake_file(
        combined.encode(),
        f"{focus}-ai-suggestion.txt",
        "text/plain",
        "assistant",
        f"AI {focus} suggestion",
        combined,
        external_id,
        request.headers.get("X-Remote-User-Name") or "Vineyard Operations",
        None,
    )
    extracted = {
        "classification": "cellar_instruction" if focus == "cellar" else "issue_or_decision",
        "summary": answer[:500],
        "facts": [],
        "uncertainties": ["AI-generated suggestion; verify source readings and assumptions"],
        "suggested_database_records": [{
            "destination_section": "issue",
            "fields": {
                "issue_text": f"AI {focus} suggestion: {answer[:3000]}",
                "priority": "medium",
                "decision_action": "Verify the source records and obtain the required human approval before applying this suggestion.",
            },
        }],
        "required_human_review": "enologist_review_required" if focus == "cellar" else "human_review_required",
        "question": question,
        "answer": answer,
        "focus": focus,
    }
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE intake_items SET classification=%s,ai_summary=%s,extracted_data=%s,review_status='ready_for_review' WHERE id=%s AND estate_id=%s",
            (extracted["classification"], extracted["summary"], json.dumps(extracted), record_id, estate_id()),
        )
    return {"saved": True, "id": record_id, "review_status": "ready_for_review"}
