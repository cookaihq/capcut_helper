from fastapi import APIRouter, Request

from app.services.update_checker import check_for_update

router = APIRouter()


@router.get("/update/check")
async def check_update(request: Request):
    info = await check_for_update(request.app.state.version)
    return {"code": 0, "message": "ok", "data": info.model_dump()}
