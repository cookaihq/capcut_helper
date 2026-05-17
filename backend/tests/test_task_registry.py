from app.core.tasks import TaskRegistry


def test_create_returns_unique_ids_and_records_metadata():
    reg = TaskRegistry()
    a = reg.create("草稿A")
    b = reg.create("草稿B")
    assert a.id != b.id
    assert a.status == "pending"
    assert a.progress == 0
    assert a.draft_name == "草稿A"
    assert isinstance(a.created_at, float)
    assert a.created_at > 0


def test_get_returns_state_or_none():
    reg = TaskRegistry()
    st = reg.create("草稿A")
    assert reg.get(st.id) is st
    assert reg.get("missing") is None


def test_update_mutates_fields():
    reg = TaskRegistry()
    st = reg.create("草稿A")
    reg.update(st.id, status="done", progress=100, result="/path/to/draft")
    fresh = reg.get(st.id)
    assert fresh.status == "done"
    assert fresh.progress == 100
    assert fresh.result == "/path/to/draft"


def test_list_returns_all_tasks():
    reg = TaskRegistry()
    a = reg.create("草稿A")
    b = reg.create("草稿B")
    tasks = reg.list()
    assert {t.id for t in tasks} == {a.id, b.id}


def test_to_dict_includes_new_fields():
    reg = TaskRegistry()
    st = reg.create("草稿A")
    d = st.to_dict()
    assert d["draft_name"] == "草稿A"
    assert "created_at" in d
    assert set(d.keys()) == {
        "id", "status", "progress", "result", "error",
        "draft_name", "created_at", "subtasks",
    }
    assert d["subtasks"] == []
