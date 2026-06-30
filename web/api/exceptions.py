"""
Custom HTTP exceptions and FastAPI exception handlers.
RFC 7807 Problem Details format.
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details."""
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
    extra: Dict[str, Any] = {}


class GPONException(Exception):
    """Base GPON API exception."""
    def __init__(
        self,
        title: str,
        detail: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.title = title
        self.detail = detail
        self.status_code = status_code
        self.extra = extra or {}
        super().__init__(detail)


class OLTConnectionError(GPONException):
    def __init__(self, host: str, detail: str):
        super().__init__(
            title="OLT Connection Failed",
            detail=f"Cannot connect to OLT {host}: {detail}",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            extra={"olt_host": host},
        )


class ONTNotFoundError(GPONException):
    def __init__(self, identifier: str, olt_host: Optional[str] = None):
        super().__init__(
            title="ONT Not Found",
            detail=f"ONT '{identifier}' not found" + (f" on OLT {olt_host}" if olt_host else ""),
            status_code=status.HTTP_404_NOT_FOUND,
            extra={"identifier": identifier, "olt_host": olt_host},
        )


class ValidationError(GPONException):
    def __init__(self, detail: str, field: Optional[str] = None):
        super().__init__(
            title="Validation Error",
            detail=detail,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            extra={"field": field} if field else {},
        )


class DiagnosisTaskError(GPONException):
    def __init__(self, task_id: str, detail: str):
        super().__init__(
            title="Diagnosis Task Failed",
            detail=detail,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            extra={"task_id": task_id},
        )


# ──────────────────────────────────────────────
# Exception Handlers
# ──────────────────────────────────────────────
def register_exception_handlers(app: FastAPI):
    @app.exception_handler(GPONException)
    async def gpon_exception_handler(request: Request, exc: GPONException):
        logger.warning(f"GPONException: {exc.title} - {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content=ProblemDetail(
                title=exc.title,
                status=exc.status_code,
                detail=exc.detail,
                instance=str(request.url),
                extra=exc.extra,
            ).model_dump(),
        )

    @app.exception_handler(status.HTTP_422_UNPROCESSABLE_ENTITY)
    async def validation_exception_handler(request: Request, exc):
        logger.warning(f"Validation error: {exc}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ProblemDetail(
                title="Validation Error",
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
                instance=str(request.url),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ProblemDetail(
                title="Internal Server Error",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred",
                instance=str(request.url),
            ).model_dump(),
        )