from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.api_gateway.deps import auth_dep
from apps.api_gateway.routers.reports import _ensure_report
from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.delivery.email.sender import SMTPEmailProvider
from interview_analytics_agent.services.manual_delivery import (
    append_delivery_log,
    build_attachments,
    parse_sender_accounts,
    select_sender_account,
    validate_recipients,
)
from interview_analytics_agent.storage import records

router = APIRouter()
AUTH_DEP = Depends(auth_dep)


class SenderAccountInfo(BaseModel):
    account_id: str
    from_email: str


class DeliveryAccountsResponse(BaseModel):
    accounts: list[SenderAccountInfo]


class ManualDeliveryRequest(BaseModel):
    channel: Literal["email", "slack", "telegram"] = "email"
    recipients: list[str] = Field(default_factory=list)
    sender_account: str | None = None
    include_artifacts: list[str] = Field(
        default_factory=lambda: [
            "report_json",
            "report_txt",
            "scorecard_json",
            "decision_json",
            "comparison_json",
            "calibration_json",
            "senior_brief_txt",
        ]
    )
    custom_message: str | None = Field(default=None, max_length=3000)


class ManualDeliveryResponse(BaseModel):
    ok: bool
    meeting_id: str
    channel: str
    sender_account: str | None = None
    recipients: list[str] = Field(default_factory=list)
    provider_result: dict[str, Any] = Field(default_factory=dict)


def _accounts() -> list[dict[str, str]]:
    s = get_settings()
    return parse_sender_accounts(raw=s.delivery_sender_accounts or "", default_email=s.email_from)


@router.get("/delivery/accounts", response_model=DeliveryAccountsResponse)
def list_delivery_accounts(_=AUTH_DEP) -> DeliveryAccountsResponse:
    accounts = [SenderAccountInfo(**item) for item in _accounts()]
    return DeliveryAccountsResponse(accounts=accounts)


@router.post("/meetings/{meeting_id}/delivery/manual", response_model=ManualDeliveryResponse)
def send_manual_delivery(
    meeting_id: str,
    req: ManualDeliveryRequest,
    _=AUTH_DEP,
) -> ManualDeliveryResponse:
    settings = get_settings()
    report = _ensure_report(meeting_id)
    scorecard = report.get("scorecard") if isinstance(report, dict) else None
    if isinstance(scorecard, dict):
        records.write_json(meeting_id, "scorecard.json", scorecard)

    if req.channel != "email":
        append_delivery_log(
            meeting_id=meeting_id,
            payload={
                "channel": req.channel,
                "ok": False,
                "reason": "channel_not_implemented",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"{req.channel}_manual_delivery_not_implemented",
        )

    try:
        recipients = validate_recipients(
            recipients=req.recipients,
            max_recipients=max(1, int(settings.delivery_max_recipients)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        selected = select_sender_account(
            accounts=_accounts(),
            sender_account_id=req.sender_account,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    attachments = build_attachments(meeting_id=meeting_id, artifact_kinds=req.include_artifacts)
    summary = str((report or {}).get("summary") or "")
    recommendation = str((report or {}).get("recommendation") or "")
    message = (req.custom_message or "").strip()
    text_body = (
        f"Meeting ID: {meeting_id}\n"
        f"Summary: {summary}\n"
        f"Recommendation: {recommendation}\n"
        f"{message}\n"
    )
    html_body = (
        "<h3>Interview Summary</h3>"
        f"<p><b>Meeting ID:</b> {meeting_id}</p>"
        f"<p><b>Summary:</b> {summary}</p>"
        f"<p><b>Recommendation:</b> {recommendation}</p>"
        f"<p>{message}</p>"
    )

    provider = SMTPEmailProvider()
    result = provider.send_report(
        meeting_id=meeting_id,
        recipients=recipients,
        subject=f"Interview summary: {meeting_id}",
        html_body=html_body,
        text_body=text_body,
        attachments=attachments,
        from_email=selected["from_email"],
    )
    provider_result = {
        "ok": result.ok,
        "provider": result.provider,
        "message_id": result.message_id,
        "error": result.error,
        "meta": result.meta,
    }

    append_delivery_log(
        meeting_id=meeting_id,
        payload={
            "channel": req.channel,
            "ok": bool(result.ok),
            "sender_account": selected["account_id"],
            "from_email": selected["from_email"],
            "recipients": recipients,
            "attachments": [name for name, _, _ in attachments],
            "provider_result": provider_result,
        },
    )

    return ManualDeliveryResponse(
        ok=bool(result.ok),
        meeting_id=meeting_id,
        channel=req.channel,
        sender_account=selected["account_id"],
        recipients=recipients,
        provider_result=provider_result,
    )
