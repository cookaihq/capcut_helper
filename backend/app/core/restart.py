"""跨平台「重启自身」工具。

POST /api/v1/system/restart 调用：先 spawn 一个 detached 的新进程副本，
再退出当前进程。新旧进程之间没有 IPC 协调——新进程走正常启动流程，从配置
文件读最新 port_range / cors_origins，因此「修改端口段」也能真正生效。

为什么 detached：父进程马上要 os._exit，必须让子进程脱离父进程的进程组 /
session / 控制终端，否则父进程退出时 OS 会把整组子进程也一起带走（macOS /
Linux 的 SIGHUP 行为，Windows 的 console process group 行为）。
"""
from __future__ import annotations

import logging
import subprocess
import sys
from typing import List

logger = logging.getLogger(__name__)


def _build_spawn_command() -> List[str]:
    """构造启动新实例的命令行。

    打包态（PyInstaller / pyoxidizer 会设置 sys.frozen）下，sys.executable 就是
    可执行入口本身（macOS 是 .app/Contents/MacOS/CapcutHelper，Windows 是 .exe）。
    dev 态下，sys.executable 是 python 解释器，需要补 `-m app` 启动模块。
    sys.argv[1:] 保留以转发 URL Scheme 参数等启动入参。
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, *sys.argv[1:]]
    return [sys.executable, "-m", "app", *sys.argv[1:]]


def _popen_kwargs() -> dict:
    """让子进程完全脱离父进程：detach + 标准流断开。"""
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        # DETACHED_PROCESS：不继承父进程的 console
        # CREATE_NEW_PROCESS_GROUP：脱离父进程的 process group，免被 Ctrl-C / 退出连带
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        )
    else:
        # 新建 session：脱离父 controlling terminal，父进程退出时不会收到 SIGHUP
        kwargs["start_new_session"] = True
    return kwargs


def spawn_new_instance() -> None:
    """启动一个 detached 的新实例。失败抛异常由调用方决定是否仍然退出。"""
    cmd = _build_spawn_command()
    logger.info("spawning new instance: %s", cmd)
    subprocess.Popen(cmd, **_popen_kwargs())  # noqa: S603 — 命令来自 sys.executable，可信
