from app.core.config import Config, load_config, save_config


def test_default_config_values():
    cfg = Config()
    assert cfg.draft_root is None
    assert cfg.port_range == [9527, 9536]
    assert cfg.cors_origins == ["http://localhost:3182", "http://localhost:3183"]


def test_load_returns_default_when_file_absent(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert cfg.draft_root is None


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    save_config(Config(draft_root="/some/path", port_range=[9000, 9001]), path)
    loaded = load_config(path)
    assert loaded.draft_root == "/some/path"
    assert loaded.port_range == [9000, 9001]
