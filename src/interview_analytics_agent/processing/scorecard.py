"""
Comparable interview scorecard builder (evidence-first).

Goal:
- make interview summaries objective and comparable for senior reviewers
- require explicit evidence snippets per competency
"""

from __future__ import annotations

from typing import Any

from interview_analytics_agent.processing.pii import mask_pii

DEFAULT_RUBRIC_ID = "interview_core_v1"
SCALE_MIN = 1.0
SCALE_MAX = 5.0


_RUBRIC: list[dict[str, Any]] = [
    {
        "id": "problem_solving",
        "title": "Problem Solving",
        "weight": 0.2,
        "keywords": (
            "почему",
            "why",
            "tradeoff",
            "компромисс",
            "подход",
            "approach",
            "решил",
            "solve",
            "decision",
        ),
    },
    {
        "id": "technical_depth",
        "title": "Technical Depth",
        "weight": 0.2,
        "keywords": (
            "алгоритм",
            "сложност",
            "latency",
            "throughput",
            "cache",
            "database",
            "sql",
            "python",
            "architecture",
        ),
    },
    {
        "id": "system_design",
        "title": "System Design",
        "weight": 0.15,
        "keywords": (
            "масштаб",
            "scale",
            "service",
            "микросервис",
            "queue",
            "event",
            "design",
            "boundary",
            "sla",
        ),
    },
    {
        "id": "communication",
        "title": "Communication",
        "weight": 0.15,
        "keywords": (
            "объясн",
            "ясно",
            "clear",
            "summary",
            "пример",
            "example",
            "уточн",
            "question",
        ),
    },
    {
        "id": "collaboration",
        "title": "Collaboration",
        "weight": 0.1,
        "keywords": (
            "команда",
            "team",
            "review",
            "feedback",
            "mentoring",
            "stakeholder",
            "conflict",
        ),
    },
    {
        "id": "ownership",
        "title": "Ownership",
        "weight": 0.1,
        "keywords": (
            "ответствен",
            "ownership",
            "инициатив",
            "incident",
            "postmortem",
            "deadline",
            "delivery",
        ),
    },
    {
        "id": "role_fit",
        "title": "Role Fit",
        "weight": 0.1,
        "keywords": (
            "продукт",
            "бизнес",
            "value",
            "customer",
            "roadmap",
            "priority",
            "senior",
            "impact",
        ),
    },
]


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def _safe_quote(text: str, *, limit: int = 220) -> str:
    cleaned = " ".join((text or "").split())
    cleaned = mask_pii(cleaned)
    if len(cleaned) > limit:
        return cleaned[:limit].rstrip() + "..."
    return cleaned


def _segment_rows(
    *,
    enhanced_transcript: str,
    transcript_segments: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if transcript_segments:
        rows: list[dict[str, Any]] = []
        for seg in transcript_segments:
            text = str(seg.get("enhanced_text") or seg.get("raw_text") or "").strip()
            if not text:
                continue
            rows.append(
                {
                    "seq": int(seg.get("seq") or 0),
                    "speaker": seg.get("speaker"),
                    "start_ms": seg.get("start_ms"),
                    "end_ms": seg.get("end_ms"),
                    "text": text,
                }
            )
        if rows:
            return rows

    rows = []
    for idx, raw in enumerate((enhanced_transcript or "").splitlines(), start=1):
        text = raw.strip()
        if not text:
            continue
        rows.append(
            {
                "seq": idx,
                "speaker": None,
                "start_ms": None,
                "end_ms": None,
                "text": text,
            }
        )
    return rows


def _collect_evidence(
    *,
    rows: list[dict[str, Any]],
    keywords: tuple[str, ...],
    max_items: int = 3,
) -> tuple[list[dict[str, Any]], int]:
    evidence: list[dict[str, Any]] = []
    total_hits = 0
    key_norm = tuple(_norm(k) for k in keywords if _norm(k))
    for row in rows:
        text = str(row.get("text") or "")
        text_norm = _norm(text)
        if not text_norm:
            continue
        matches = [kw for kw in key_norm if kw in text_norm]
        if not matches:
            continue
        total_hits += len(matches)
        if len(evidence) < max_items:
            evidence.append(
                {
                    "seq": int(row.get("seq") or 0),
                    "speaker": row.get("speaker"),
                    "start_ms": row.get("start_ms"),
                    "end_ms": row.get("end_ms"),
                    "quote": _safe_quote(text),
                    "matched_keywords": matches,
                }
            )
    return evidence, total_hits


def _risk_penalty(report: dict[str, Any] | None) -> float:
    risks = ((report or {}).get("risk_flags") or [])
    risk_count = len([r for r in risks if str(r).strip()])
    return min(0.8, 0.12 * risk_count)


def _competency_score(
    *,
    evidence_count: int,
    keyword_hits: int,
    risk_penalty: float,
) -> tuple[float | None, float, str]:
    if evidence_count <= 0:
        return None, 0.15, "insufficient_evidence"

    raw_score = 2.2 + min(1.6, 0.45 * evidence_count) + min(1.2, 0.08 * keyword_hits)
    score = max(SCALE_MIN, min(SCALE_MAX, raw_score - risk_penalty))
    confidence = max(0.2, min(0.95, 0.35 + 0.12 * evidence_count + 0.02 * keyword_hits))
    return round(score, 2), round(confidence, 2), "ok"


def build_interview_scorecard(
    *,
    enhanced_transcript: str,
    meeting_context: dict[str, Any] | None,
    report: dict[str, Any] | None,
    transcript_segments: list[dict[str, Any]] | None = None,
    rubric_id: str = DEFAULT_RUBRIC_ID,
) -> dict[str, Any]:
    rows = _segment_rows(enhanced_transcript=enhanced_transcript, transcript_segments=transcript_segments)
    penalty = _risk_penalty(report)

    competencies: list[dict[str, Any]] = []
    weighted_sum = 0.0
    weighted_total = 0.0
    confidence_weighted = 0.0

    for item in _RUBRIC:
        evidence, hits = _collect_evidence(rows=rows, keywords=item["keywords"])
        score, confidence, status = _competency_score(
            evidence_count=len(evidence),
            keyword_hits=hits,
            risk_penalty=penalty,
        )

        if score is not None:
            weight = float(item["weight"])
            weighted_sum += score * weight
            weighted_total += weight
            confidence_weighted += confidence * weight

        competencies.append(
            {
                "competency_id": item["id"],
                "title": item["title"],
                "weight": item["weight"],
                "status": status,
                "score": score,
                "confidence": confidence,
                "evidence": evidence,
                "keyword_hits": hits,
            }
        )

    overall_score = round(weighted_sum / weighted_total, 2) if weighted_total > 0 else None
    overall_confidence = (
        round(confidence_weighted / weighted_total, 2) if weighted_total > 0 else 0.0
    )

    insufficient = [c["competency_id"] for c in competencies if c["status"] != "ok"]
    context = dict(meeting_context or {})

    return {
        "version": "v1",
        "rubric_id": rubric_id,
        "objective_mode": True,
        "scale": {"min": SCALE_MIN, "max": SCALE_MAX},
        "candidate_label": context.get("candidate_name") or context.get("candidate_id"),
        "position_label": context.get("position") or context.get("role"),
        "overall_score": overall_score,
        "overall_confidence": overall_confidence,
        "insufficient_evidence_competencies": insufficient,
        "competencies": competencies,
        "report_goal": "objective_comparable_summary",
        "report_audience": "senior_interviewers",
    }
