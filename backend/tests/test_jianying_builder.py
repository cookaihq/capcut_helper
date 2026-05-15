import json
import shutil
import subprocess
import sys
import textwrap

import pytest

from app.core.exceptions import DraftNameConflict
from app.integrations.jianying import builder
from app.schemas.timeline import TimelineSpec
from tests.conftest import SAMPLE1_DURATION, SAMPLE2_DURATION


def _two_video_spec(allow_replace=False):
    return TimelineSpec.model_validate(
        {
            "draft_name": "builder_test",
            "allow_replace": allow_replace,
            "canvas": {"width": 1920, "height": 1080, "fps": 30},
            "tracks": [
                {
                    "type": "video",
                    "segments": [
                        {
                            "material": {"url": "https://x/v1.mp4", "type": "video", "filename": "v1.mp4"},
                            "timeline": {"start": 0, "duration": SAMPLE1_DURATION},
                        },
                        {
                            "material": {"url": "https://x/v2.mp4", "type": "video", "filename": "v2.mp4"},
                            "timeline": {"start": SAMPLE1_DURATION, "duration": SAMPLE2_DURATION},
                        },
                    ],
                }
            ],
        }
    )


def test_create_populate_save_writes_valid_draft(tmp_path, fixture_video_1, fixture_video_2):
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    spec = _two_video_spec()

    script, draft_dir = builder.create_empty_draft(str(draft_root), spec)
    assert draft_dir == draft_root / "builder_test"
    assert draft_dir.is_dir()

    # 模拟「下素材进草稿文件夹」：把 fixture 复制进去
    v1 = draft_dir / "v1.mp4"
    v2 = draft_dir / "v2.mp4"
    shutil.copy(fixture_video_1, v1)
    shutil.copy(fixture_video_2, v2)
    material_paths = {"https://x/v1.mp4": v1, "https://x/v2.mp4": v2}

    builder.populate_draft(script, spec, material_paths)
    builder.save_draft(script)

    content = json.loads((draft_dir / "draft_content.json").read_text("utf-8"))
    assert content["canvas_config"]["width"] == 1920
    assert content["canvas_config"]["height"] == 1080
    assert len(content["tracks"]) == 1
    assert len(content["tracks"][0]["segments"]) == 2
    assert content["tracks"][0]["segments"][0]["target_timerange"] == {
        "start": 0,
        "duration": SAMPLE1_DURATION,
    }


@pytest.mark.skipif(sys.platform != "darwin", reason="只在 macOS 复现：Windows wide-char API 绕过 narrow char 转换")
def test_libmediainfo_opens_non_ascii_path_under_posix_locale(tmp_path, fixture_video_1):
    """回归：POSIX locale + 中文路径必挂；app.main 顶层固定 UTF-8 locale 后能正常 parse。

    用两个子进程对比：(a) 不导入 app.main，POSIX locale 下 parse 应失败；
    (b) 导入 app.main 触发 locale 设置后，同一份路径 parse 应成功。
    任一断言失败都说明 fix 失效或回归了。"""
    chinese_dir = tmp_path / "我的视频_测试"
    chinese_dir.mkdir()
    video = chinese_dir / "v.mp4"
    shutil.copy(fixture_video_1, video)

    base_env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "PYTHONPATH": ":".join(sys.path),
        "LC_ALL": "C",
        "LC_CTYPE": "C",
        "LANG": "C",
    }

    # (a) 不导入 app.main：POSIX locale 下应失败，确认 libmediainfo 行为没变
    baseline_script = textwrap.dedent(f"""
        import locale
        locale.setlocale(locale.LC_CTYPE, 'C')
        from pymediainfo import MediaInfo
        try:
            MediaInfo.parse({str(video)!r})
            print('UNEXPECTED_OK')
        except RuntimeError as e:
            print('EXPECTED_FAIL')
    """)
    baseline = subprocess.run(
        [sys.executable, "-c", baseline_script], env=base_env,
        capture_output=True, text=True, timeout=30,
    )
    assert "EXPECTED_FAIL" in baseline.stdout, (
        f"baseline 没复现失败，libmediainfo 行为可能变了: stdout={baseline.stdout!r} stderr={baseline.stderr!r}"
    )

    # (b) 导入 app.core.locale_fix：顶层 setlocale 后 parse 必须成功
    fixed_script = textwrap.dedent(f"""
        import app.core.locale_fix  # 触发 LC_CTYPE 设置
        from pymediainfo import MediaInfo
        mi = MediaInfo.parse({str(video)!r})
        print('OK tracks=', len(mi.tracks))
    """)
    fixed = subprocess.run(
        [sys.executable, "-c", fixed_script], env=base_env,
        capture_output=True, text=True, timeout=30,
    )
    assert fixed.returncode == 0 and "OK tracks=" in fixed.stdout, (
        f"fix 失效：stdout={fixed.stdout!r} stderr={fixed.stderr!r}"
    )


def test_create_empty_draft_raises_conflict_when_exists(tmp_path):
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    spec = _two_video_spec(allow_replace=False)

    builder.create_empty_draft(str(draft_root), spec)  # 第一次成功
    with pytest.raises(DraftNameConflict):
        builder.create_empty_draft(str(draft_root), spec)  # 第二次重名且不允许覆盖
