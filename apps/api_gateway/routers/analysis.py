from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from apps.api_gateway.deps import auth_dep
from apps.api_gateway.routers.reports import _ensure_report
from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.time import utc_now_iso
from interview_analytics_agent.processing.calibration import build_calibration_report
from interview_analytics_agent.processing.comparison import build_comparison_report
from interview_analytics_agent.processing.rubric_tuning import (
    load_weight_overrides,
    maybe_update_weights_from_calibration,
)
from interview_analytics_agent.services.report_artifacts import write_report_artifacts
from interview_analytics_agent.storage import records
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.repositories import MeetingRepository

router = APIRouter()
AUTH_DEP = Depends(auth_dep)


class ScorecardResponse(BaseModel):
    meeting_id: str
    scorecard: dict[str, Any]


class ComparisonRequest(BaseModel):
    meeting_ids: list[str] = Field(min_length=2, max_length=50)


class ComparisonResponse(BaseModel):
    report: dict[str, Any]


class CalibrationReviewRequest(BaseModel):
    reviewer_id: str = Field(min_length=2, max_length=128)
    scores: dict[str, float] = Field(default_factory=dict)
    decision: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=4000)


class CalibrationResponse(BaseModel):
    meeting_id: str
    calibration: dict[str, Any]


class InterviewScenariosResponse(BaseModel):
    status: str
    scenarios_dir: str
    available_examples: list[str]
    note: str


class DecisionResponse(BaseModel):
    meeting_id: str
    decision: dict[str, Any]


class SeniorBriefResponse(BaseModel):
    meeting_id: str
    text: str
    artifacts: dict[str, str | None]


def _meeting_exists(meeting_id: str) -> bool:
    with db_session() as session:
        mrepo = MeetingRepository(session)
        return mrepo.get(meeting_id) is not None


def _scorecard_for_meeting(meeting_id: str) -> dict[str, Any]:
    report = _ensure_report(meeting_id)
    scorecard = report.get("scorecard")
    if not isinstance(scorecard, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="scorecard_not_available",
        )
    records.write_json(meeting_id, "scorecard.json", scorecard)
    return scorecard


def _reviews_path(meeting_id: str) -> Path:
    return records.artifact_path(meeting_id, "calibration_reviews.json")


def _calibration_path(meeting_id: str) -> Path:
    return records.artifact_path(meeting_id, "calibration_report.json")


def _load_reviews(meeting_id: str) -> list[dict[str, Any]]:
    path = _reviews_path(meeting_id)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    return out


def _save_reviews(meeting_id: str, reviews: list[dict[str, Any]]) -> None:
    path = _reviews_path(meeting_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(reviews, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _rebuild_brief(meeting_id: str) -> dict[str, str | None]:
    report = _ensure_report(meeting_id)
    with db_session() as session:
        repo = MeetingRepository(session)
        m = repo.get(meeting_id)
        if not m:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
        return write_report_artifacts(
            meeting_id=meeting_id,
            raw_text=m.raw_transcript or "",
            clean_text=m.enhanced_transcript or "",
            report=report if isinstance(report, dict) else {},
        )


@router.get("/meetings/{meeting_id}/scorecard", response_model=ScorecardResponse)
def get_scorecard(meeting_id: str, _=AUTH_DEP) -> ScorecardResponse:
    if not _meeting_exists(meeting_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    scorecard = _scorecard_for_meeting(meeting_id)
    return ScorecardResponse(meeting_id=meeting_id, scorecard=scorecard)


@router.get("/meetings/{meeting_id}/decision", response_model=DecisionResponse)
def get_decision(meeting_id: str, _=AUTH_DEP) -> DecisionResponse:
    if not _meeting_exists(meeting_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    report = _ensure_report(meeting_id)
    decision = report.get("decision") if isinstance(report, dict) else None
    if not isinstance(decision, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="decision_not_available",
        )
    records.write_json(meeting_id, "decision.json", decision)
    return DecisionResponse(meeting_id=meeting_id, decision=decision)


@router.post("/analysis/comparison", response_model=ComparisonResponse)
def build_comparison(req: ComparisonRequest, _=AUTH_DEP) -> ComparisonResponse:
    rows: list[dict[str, Any]] = []
    for meeting_id in req.meeting_ids:
        if not _meeting_exists(meeting_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"meeting_not_found:{meeting_id}",
            )
        report = _ensure_report(meeting_id)
        scorecard = report.get("scorecard") if isinstance(report, dict) else None
        rows.append(
            {
                "meeting_id": meeting_id,
                "report": report if isinstance(report, dict) else {},
                "scorecard": scorecard if isinstance(scorecard, dict) else {},
            }
        )

    comparison = build_comparison_report(rows)
    for meeting_id in req.meeting_ids:
        records.write_json(meeting_id, "comparison.json", comparison)
    return ComparisonResponse(report=comparison)


@router.get("/analysis/comparison", response_model=ComparisonResponse)
def build_comparison_from_query(
    meeting_ids: str = Query(min_length=3, description="Comma-separated meeting ids"),
    _=AUTH_DEP,
) -> ComparisonResponse:
    parsed = [item.strip() for item in meeting_ids.split(",") if item.strip()]
    return build_comparison(ComparisonRequest(meeting_ids=parsed))


@router.get("/meetings/{meeting_id}/calibration", response_model=CalibrationResponse)
def get_calibration(meeting_id: str, _=AUTH_DEP) -> CalibrationResponse:
    if not _meeting_exists(meeting_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    scorecard = _scorecard_for_meeting(meeting_id)
    reviews = _load_reviews(meeting_id)
    calibration = build_calibration_report(scorecard=scorecard, senior_reviews=reviews)
    weights = load_weight_overrides()
    if weights:
        calibration["rubric_weights"] = weights
    records.write_json(meeting_id, "calibration_report.json", calibration)
    return CalibrationResponse(meeting_id=meeting_id, calibration=calibration)


@router.post("/meetings/{meeting_id}/calibration/review", response_model=CalibrationResponse)
def submit_calibration_review(
    meeting_id: str,
    req: CalibrationReviewRequest,
    _=AUTH_DEP,
) -> CalibrationResponse:
    if not _meeting_exists(meeting_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")

    reviews = _load_reviews(meeting_id)
    reviews.append(
        {
            "reviewer_id": req.reviewer_id.strip(),
            "scores": req.scores,
            "decision": req.decision,
            "notes": req.notes,
            "created_at": utc_now_iso(),
        }
    )
    _save_reviews(meeting_id, reviews)
    scorecard = _scorecard_for_meeting(meeting_id)
    updated = maybe_update_weights_from_calibration(scorecard=scorecard, reviews=reviews)
    calibration = build_calibration_report(scorecard=scorecard, senior_reviews=reviews)
    if updated:
        calibration["rubric_weights_updated"] = True
        calibration["rubric_weights"] = updated
    else:
        weights = load_weight_overrides()
        if weights:
            calibration["rubric_weights"] = weights
    records.write_json(meeting_id, "calibration_report.json", calibration)
    return CalibrationResponse(meeting_id=meeting_id, calibration=calibration)


@router.get("/analysis/rubric-weights")
def get_rubric_weights(_=AUTH_DEP) -> dict[str, Any]:
    return load_weight_overrides()


@router.get("/meetings/{meeting_id}/senior-brief", response_model=SeniorBriefResponse)
def get_senior_brief(meeting_id: str, _=AUTH_DEP) -> SeniorBriefResponse:
    if not _meeting_exists(meeting_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    artifacts = _rebuild_brief(meeting_id)
    text = records.read_text(meeting_id, "senior_brief.txt")
    return SeniorBriefResponse(meeting_id=meeting_id, text=text, artifacts=artifacts)


@router.post("/meetings/{meeting_id}/senior-brief/rebuild", response_model=SeniorBriefResponse)
def rebuild_senior_brief(meeting_id: str, _=AUTH_DEP) -> SeniorBriefResponse:
    return get_senior_brief(meeting_id)


@router.get("/interview-scenarios", response_model=InterviewScenariosResponse)
def list_interview_scenarios(_=AUTH_DEP) -> InterviewScenariosResponse:
    settings = get_settings()
    base = Path(settings.interview_scenarios_dir).expanduser().resolve()
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
    examples = sorted(p.name for p in base.glob("*.json") if p.is_file())
    return InterviewScenariosResponse(
        status="placeholder",
        scenarios_dir=str(base),
        available_examples=examples,
        note=(
            "Reserved for future interview scenario examples; "
            "runtime scoring does not use scenarios yet by request."
        ),
    )
