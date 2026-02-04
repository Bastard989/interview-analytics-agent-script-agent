"""
FastAPI Depends.

Сюда выносим:
- проверку авторизации (Bearer JWT / X-API-Key)
- (в будущем) correlation_id, request_id и т.д.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

from interview_analytics_agent.common.errors import ErrCode, UnauthorizedError
from interview_analytics_agent.common.logging import get_project_logger
from interview_analytics_agent.common.security import (
    AuthContext,
    is_service_jwt_claims,
    require_auth,
)

log = get_project_logger()


def _request_meta(request: Request | None) -> tuple[str, str, str | None]:
    if request is None:
        return "unknown", "UNKNOWN", None
    endpoint = request.url.path
    method = request.method
    client_ip = request.client.host if request.client else None
    return endpoint, method, client_ip


def _audit_allow(
    *,
    request: Request | None,
    ctx: AuthContext,
    reason: str,
) -> None:
    endpoint, method, client_ip = _request_meta(request)
    log.info(
        "security_audit_allow",
        extra={
            "payload": {
                "endpoint": endpoint,
                "method": method,
                "subject": ctx.subject,
                "auth_type": ctx.auth_type,
                "reason": reason,
                "client_ip": client_ip,
            }
        },
    )


def _audit_deny(
    *,
    request: Request | None,
    status_code: int,
    reason: str,
    error_code: str,
    auth_type: str | None = None,
    subject: str | None = None,
) -> None:
    endpoint, method, client_ip = _request_meta(request)
    log.warning(
        "security_audit_deny",
        extra={
            "payload": {
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "reason": reason,
                "error_code": error_code,
                "auth_type": auth_type or "unknown",
                "subject": subject or "unknown",
                "client_ip": client_ip,
            }
        },
    )


def _authenticate_request(
    *,
    authorization: str | None,
    x_api_key: str | None,
    request: Request | None,
) -> AuthContext:
    try:
        return require_auth(authorization=authorization, x_api_key=x_api_key)
    except UnauthorizedError as e:
        _audit_deny(
            request=request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            reason=e.message,
            error_code=e.code,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": e.code, "message": e.message},
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def auth_dep(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthContext:
    """
    Проверка авторизации для HTTP.
    """
    ctx = _authenticate_request(
        authorization=authorization,
        x_api_key=x_api_key,
        request=request,
    )
    _audit_allow(request=request, ctx=ctx, reason="auth_ok")
    return ctx


def service_auth_dep(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthContext:
    ctx = _authenticate_request(
        authorization=authorization,
        x_api_key=x_api_key,
        request=request,
    )
    if ctx.auth_type == "service_api_key":
        _audit_allow(request=request, ctx=ctx, reason="service_api_key")
        return ctx
    if ctx.auth_type == "jwt" and is_service_jwt_claims(ctx.claims):
        _audit_allow(request=request, ctx=ctx, reason="service_jwt_claims")
        return ctx

    _audit_deny(
        request=request,
        status_code=status.HTTP_403_FORBIDDEN,
        reason="not_service_identity",
        error_code=ErrCode.FORBIDDEN,
        auth_type=ctx.auth_type,
        subject=ctx.subject,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": ErrCode.FORBIDDEN, "message": "Требуется service-авторизация"},
    )
