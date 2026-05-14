from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppException(Exception):
    code = 1000
    status_code = 400

    def __init__(self, message: str, data: Any = None):
        self.message = message
        self.data = data
        super().__init__(message)


class DraftRootNotConfigured(AppException):
    code = 1001
    status_code = 400


class DraftNameConflict(AppException):
    code = 1002
    status_code = 409


class TaskNotFound(AppException):
    code = 1003
    status_code = 404


class MaterialDownloadError(AppException):
    code = 1004
    status_code = 502


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def _app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "data": exc.data},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"code": 422, "message": "时间线规格非法", "data": jsonable_encoder(exc.errors())},
        )
