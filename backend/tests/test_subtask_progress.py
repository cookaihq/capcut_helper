"""Subtask 模型 + TaskRegistry.update_subtask 的进度推进逻辑测试。"""
from app.core.tasks import (
    Subtask,
    TaskRegistry,
    _derive_subtask_progress,
    _recompute_task_progress,
    subtask_id_for_url,
)
from app.schemas.timeline import Material


def _mats(*urls):
    return [Material(url=u, type="video", filename=u.rsplit("/", 1)[-1]) for u in urls]


# ============ subtask_id_for_url ============

def test_subtask_id_is_stable_8_hex_chars():
    """同一 URL 任意时刻派生出的 id 相同；不同 URL 派生出的 id 不同。
    下游 downloader 的 _safe_filename 取同样前缀，做素材 dedup 用。"""
    a = subtask_id_for_url("https://x/a.mp4")
    assert len(a) == 8
    assert all(c in "0123456789abcdef" for c in a)
    assert a == subtask_id_for_url("https://x/a.mp4")
    assert a != subtask_id_for_url("https://x/b.mp4")


# ============ init_subtasks ============

def test_init_subtasks_creates_one_per_material():
    reg = TaskRegistry()
    task = reg.create("d")
    subs = reg.init_subtasks(task.id, _mats("https://x/a.mp4", "https://x/b.mp4"))
    assert len(subs) == 2
    assert {s.name for s in subs} == {"a.mp4", "b.mp4"}
    assert all(s.status == "pending" and s.progress == 0 for s in subs)


def test_init_subtasks_replaces_existing():
    """重复 init（如重启草稿任务）应替换而不是追加，避免脏数据。"""
    reg = TaskRegistry()
    task = reg.create("d")
    reg.init_subtasks(task.id, _mats("https://x/a.mp4"))
    reg.init_subtasks(task.id, _mats("https://x/b.mp4", "https://x/c.mp4"))
    assert [s.name for s in reg.get(task.id).subtasks] == ["b.mp4", "c.mp4"]


# ============ _derive_subtask_progress（纯函数） ============

def test_derive_progress_done_is_100():
    assert _derive_subtask_progress(Subtask(id="a", name="a", url="u", status="done", bytes_downloaded=500, total_bytes=1000)) == 100


def test_derive_progress_with_content_length_caps_at_99():
    """bytes == total 但还没 done：仍报 99，避免误导 UI 说「完成」实际还在收尾。"""
    sub = Subtask(id="a", name="a", url="u", status="downloading", bytes_downloaded=1000, total_bytes=1000)
    assert _derive_subtask_progress(sub) == 99


def test_derive_progress_with_content_length_proportional():
    sub = Subtask(id="a", name="a", url="u", status="downloading", bytes_downloaded=500, total_bytes=1000)
    assert _derive_subtask_progress(sub) == 50


def test_derive_progress_no_content_length_estimates_from_bytes():
    """无 Content-Length（如 chunked）：按 1MB ≈ 10% 估算，cap 95。"""
    # 0.5 MB → 5%
    sub = Subtask(id="a", name="a", url="u", status="downloading", bytes_downloaded=512 * 1024, total_bytes=None)
    assert _derive_subtask_progress(sub) == 5
    # 100 MB → cap 95
    sub.bytes_downloaded = 100 * 1024 * 1024
    assert _derive_subtask_progress(sub) == 95


def test_derive_progress_failed_preserves_previous_value():
    """failed 不归零，保留最后一次 progress 让 UI 看到「卡在哪」。"""
    sub = Subtask(id="a", name="a", url="u", status="failed", progress=42, bytes_downloaded=400, total_bytes=1000)
    assert _derive_subtask_progress(sub) == 42


# ============ update_subtask + _recompute_task_progress ============

def test_update_subtask_recomputes_task_progress_in_downloading_range():
    """downloading 阶段：整体 progress = 10 + 80 * avg(subtask)"""
    reg = TaskRegistry()
    task = reg.create("d")
    reg.init_subtasks(task.id, _mats("https://x/a.mp4", "https://x/b.mp4"))
    reg.update(task.id, status="downloading", progress=10)

    # a 下到 50%，b 还没开始 → avg = 25 → progress = 10 + 80*0.25 = 30
    reg.update_subtask(task.id, "https://x/a.mp4",
                       status="downloading", bytes_downloaded=500, total_bytes=1000)
    assert reg.get(task.id).progress == 30

    # a done(100), b 下到 50% → avg = 75 → progress = 10 + 80*0.75 = 70
    reg.update_subtask(task.id, "https://x/a.mp4",
                       status="done", bytes_downloaded=1000, total_bytes=1000)
    reg.update_subtask(task.id, "https://x/b.mp4",
                       status="downloading", bytes_downloaded=500, total_bytes=1000)
    assert reg.get(task.id).progress == 70


def test_update_subtask_no_op_when_status_not_downloading():
    """非 downloading 阶段更新子任务，整体 progress 不被覆盖（draft_service 用 update() 显式写）。"""
    reg = TaskRegistry()
    task = reg.create("d")
    reg.init_subtasks(task.id, _mats("https://x/a.mp4"))
    reg.update(task.id, status="building", progress=70)
    reg.update_subtask(task.id, "https://x/a.mp4",
                       status="done", bytes_downloaded=1000, total_bytes=1000)
    assert reg.get(task.id).progress == 70


def test_update_subtask_returns_none_for_unknown_url():
    reg = TaskRegistry()
    task = reg.create("d")
    reg.init_subtasks(task.id, _mats("https://x/a.mp4"))
    assert reg.update_subtask(task.id, "https://x/zzz.mp4", status="done") is None


def test_update_subtask_persists_error_field():
    reg = TaskRegistry()
    task = reg.create("d")
    reg.init_subtasks(task.id, _mats("https://x/a.mp4"))
    reg.update(task.id, status="downloading", progress=10)
    reg.update_subtask(task.id, "https://x/a.mp4", status="failed", error="HTTP 500")
    sub = reg.get(task.id).subtasks[0]
    assert sub.status == "failed"
    assert sub.error == "HTTP 500"


# ============ Subtask 在 to_dict 中被序列化 ============

def test_task_to_dict_includes_subtasks():
    reg = TaskRegistry()
    task = reg.create("d")
    reg.init_subtasks(task.id, _mats("https://x/a.mp4"))
    d = reg.get(task.id).to_dict()
    assert isinstance(d["subtasks"], list) and len(d["subtasks"]) == 1
    sub = d["subtasks"][0]
    assert sub["name"] == "a.mp4"
    assert sub["status"] == "pending"
    assert sub["progress"] == 0
    assert sub["bytes_downloaded"] == 0
    assert sub["total_bytes"] is None
    assert sub["error"] is None
