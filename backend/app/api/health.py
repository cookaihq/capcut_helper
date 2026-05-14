from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "service": "capcut_helper",
            "version": request.app.state.version,
            "port": request.app.state.port,
        },
    }
