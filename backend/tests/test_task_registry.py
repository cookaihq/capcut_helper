from app.core.tasks import TaskRegistry


def test_create_returns_unique_ids():
    reg = TaskRegistry()
    a = reg.create()
    b = reg.create()
    assert a.id != b.id
    assert a.status == "pending"
    assert a.progress == 0


def test_get_returns_state_or_none():
    reg = TaskRegistry()
    st = reg.create()
    assert reg.get(st.id) is st
    assert reg.get("missing") is None


def test_update_mutates_fields():
    reg = TaskRegistry()
    st = reg.create()
    reg.update(st.id, status="done", progress=100, result="/path/to/draft")
    fresh = reg.get(st.id)
    assert fresh.status == "done"
    assert fresh.progress == 100
    assert fresh.result == "/path/to/draft"
