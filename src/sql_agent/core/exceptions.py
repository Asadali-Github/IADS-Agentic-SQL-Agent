"""
core/exceptions.py

Typed exception hierarchy for the query service.
All exceptions carry an HTTP status code and a machine-readable error_code so
the FastAPI error-mapping layer can translate them into consistent JSON responses
without any string-matching logic.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class AppBaseError(Exception):
    """Root of the application exception hierarchy.

    Every subclass must set a default ``status_code`` (HTTP) and a
    snake_case ``error_code`` string that is safe to expose to clients.
    """

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(
        self,
        message: str = "An unexpected error occurred.",
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        # Optional structured payload forwarded to the JSON response body.
        self.detail = detail or {}

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"{self.__class__.__name__}("
            f"error_code={self.error_code!r}, "
            f"status_code={self.status_code}, "
            f"message={self.message!r})"
        )


# ---------------------------------------------------------------------------
# 400-range — client / input errors
# ---------------------------------------------------------------------------


class ValidationError(AppBaseError):
    """Raised when request payload or query parameters fail validation."""

    status_code = 422
    error_code = "validation_error"

    def __init__(
        self,
        message: str = "Request validation failed.",
        *,
        field: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        if field:
            self.detail["field"] = field


class QueryParseError(AppBaseError):
    """Raised when the natural-language query cannot be parsed or understood."""

    status_code = 400
    error_code = "query_parse_error"

    def __init__(
        self,
        message: str = "Unable to parse the provided query.",
        *,
        raw_query: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        if raw_query is not None:
            self.detail["raw_query"] = raw_query


class AuthenticationError(AppBaseError):
    """Raised when a request is missing or carries invalid credentials."""

    status_code = 401
    error_code = "authentication_error"

    def __init__(
        self,
        message: str = "Authentication required.",
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, detail=detail)


class AuthorizationError(AppBaseError):
    """Raised when a caller is authenticated but lacks permission."""

    status_code = 403
    error_code = "authorization_error"

    def __init__(
        self,
        message: str = "You do not have permission to perform this action.",
        *,
        resource: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        if resource:
            self.detail["resource"] = resource


class ResourceNotFoundError(AppBaseError):
    """Raised when a requested resource does not exist."""

    status_code = 404
    error_code = "not_found"

    def __init__(
        self,
        message: str = "The requested resource was not found.",
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        if resource_type:
            self.detail["resource_type"] = resource_type
        if resource_id:
            self.detail["resource_id"] = resource_id


class RateLimitError(AppBaseError):
    """Raised when a caller exceeds their allowed request rate."""

    status_code = 429
    error_code = "rate_limit_exceeded"

    def __init__(
        self,
        message: str = "Too many requests. Please slow down.",
        *,
        retry_after_seconds: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        if retry_after_seconds is not None:
            self.detail["retry_after_seconds"] = retry_after_seconds


# ---------------------------------------------------------------------------
# 500-range — server / infrastructure errors
# ---------------------------------------------------------------------------


class UpstreamServiceError(AppBaseError):
    """Raised when a call to an upstream service (LLM, vector DB, …) fails."""

    status_code = 502
    error_code = "upstream_service_error"

    def __init__(
        self,
        message: str = "An upstream service returned an unexpected response.",
        *,
        service_name: str | None = None,
        upstream_status_code: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        if service_name:
            self.detail["service_name"] = service_name
        if upstream_status_code is not None:
            self.detail["upstream_status_code"] = upstream_status_code


class LLMError(UpstreamServiceError):
    """Specialisation of UpstreamServiceError for LLM provider failures."""

    error_code = "llm_error"

    def __init__(
        self,
        message: str = "The language model returned an error.",
        *,
        model: str | None = None,
        upstream_status_code: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            service_name="llm",
            upstream_status_code=upstream_status_code,
            detail=detail,
        )
        if model:
            self.detail["model"] = model


class VectorStoreError(UpstreamServiceError):
    """Raised when the vector / retrieval store returns an error."""

    error_code = "vector_store_error"

    def __init__(
        self,
        message: str = "The vector store returned an error.",
        *,
        upstream_status_code: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            service_name="vector_store",
            upstream_status_code=upstream_status_code,
            detail=detail,
        )


class DatabaseError(AppBaseError):
    """Raised on unexpected failures when reading from or writing to the DB."""

    status_code = 500
    error_code = "database_error"

    def __init__(
        self,
        message: str = "A database error occurred.",
        *,
        operation: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        if operation:
            self.detail["operation"] = operation


class ServiceUnavailableError(AppBaseError):
    """Raised when the service is temporarily unable to handle requests
    (e.g. during startup, maintenance, or a dependency outage)."""

    status_code = 503
    error_code = "service_unavailable"

    def __init__(
        self,
        message: str = "The service is temporarily unavailable. Please try again later.",
        *,
        retry_after_seconds: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        if retry_after_seconds is not None:
            self.detail["retry_after_seconds"] = retry_after_seconds


class TimeoutError(AppBaseError):  # noqa: A001  (shadows built-in intentionally)
    """Raised when an internal operation exceeds its allowed time budget."""

    status_code = 504
    error_code = "timeout"

    def __init__(
        self,
        message: str = "The operation timed out.",
        *,
        operation: str | None = None,
        timeout_seconds: float | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        if operation:
            self.detail["operation"] = operation
        if timeout_seconds is not None:
            self.detail["timeout_seconds"] = timeout_seconds


# ---------------------------------------------------------------------------
# Convenience re-export — everything the error-mapping layer needs in one place
# ---------------------------------------------------------------------------

__all__ = [
    "AppBaseError",
    # 4xx
    "ValidationError",
    "QueryParseError",
    "AuthenticationError",
    "AuthorizationError",
    "ResourceNotFoundError",
    "RateLimitError",
    # 5xx
    "UpstreamServiceError",
    "LLMError",
    "VectorStoreError",
    "DatabaseError",
    "ServiceUnavailableError",
    "TimeoutError",
]
