from app.core.exceptions import (
    AppException,
    DraftRootNotConfigured,
    DraftNameConflict,
    TaskNotFound,
    MaterialDownloadError,
)


def test_app_exception_carries_message_and_data():
    exc = AppException("出错了", data={"k": "v"})
    assert exc.message == "出错了"
    assert exc.data == {"k": "v"}
    assert exc.code == 1000
    assert exc.status_code == 400


def test_subclasses_have_distinct_codes_and_status():
    assert (DraftRootNotConfigured("x").code, DraftRootNotConfigured("x").status_code) == (1001, 400)
    assert (DraftNameConflict("x").code, DraftNameConflict("x").status_code) == (1002, 409)
    assert (TaskNotFound("x").code, TaskNotFound("x").status_code) == (1003, 404)
    assert (MaterialDownloadError("x").code, MaterialDownloadError("x").status_code) == (1004, 502)
