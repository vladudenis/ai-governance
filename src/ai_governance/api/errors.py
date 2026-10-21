"""Stable error bodies for the HTTP API."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    """One machine-readable error."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ApiError(Exception):
    """An error the route layer turns into a JSON response."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def install_error_handlers(app: FastAPI) -> None:
    """Register handlers that keep the error shape the same for every route."""

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                code="validation_error",
                message="The request body or query parameters are not valid.",
            ).model_dump(),
        )
