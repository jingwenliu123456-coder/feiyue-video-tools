"""批处理 / 裂变运行控制：空格暂停、Esc 停止。"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from typing import Any, Literal

from modules.platform_utils import is_mac


PollAction = Literal["continue", "pause", "stop"]


class BatchRunController:
    """批处理线程内检查；主线程通过快捷键切换状态。"""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.active = False
        self._paused = False
        self._stop = False
        self._lock = threading.Lock()

    def begin(self) -> None:
        with self._lock:
            if self.active:
                return
            self.active = True
            self._paused = False
            self._stop = False
        self._ui_status("运行中 · 空格=暂停/继续 · Esc=停止")

    def end(self) -> None:
        with self._lock:
            self.active = False
            self._paused = False
            self._stop = False
        self._ui_status("")

    @property
    def should_stop(self) -> bool:
        with self._lock:
            return bool(self._stop)

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return bool(self._paused)

    def toggle_pause(self) -> None:
        with self._lock:
            if not self.active:
                return
            self._paused = not self._paused
            paused = self._paused
        if paused:
            self._ui_status("已暂停 · 空格=继续 · Esc=停止")
            try:
                self.app.log("批处理已暂停（空格继续）" if is_mac() else "⏸ 批处理已暂停（空格继续）")
            except Exception:
                pass
        else:
            self._ui_status("运行中 · 空格=暂停/继续 · Esc=停止")
            try:
                self.app.log("批处理继续" if is_mac() else "▶ 批处理继续")
            except Exception:
                pass

    def request_stop(self) -> None:
        with self._lock:
            if not self.active:
                return
            self._stop = True
            self._paused = False
        self._ui_status("正在停止…")
        try:
            self.app.log("用户请求停止（当前编码结束后退出）" if is_mac() else "⏹ 用户请求停止（当前编码结束后退出）")
        except Exception:
            pass

    def wait_if_paused(self) -> bool:
        """在文件/方案间隙等待；返回 True 表示应停止。"""
        while True:
            with self._lock:
                if self._stop:
                    return True
                if not self._paused:
                    return False
            time.sleep(0.2)

    def poll_ffmpeg(self) -> PollAction:
        with self._lock:
            if self._stop:
                return "stop"
            if self._paused:
                return "pause"
        return "continue"

    def _ui_status(self, suffix: str) -> None:
        root = getattr(self.app, "root", None)
        status_var = getattr(self.app, "status_var", None)
        if root is None or status_var is None:
            return

        def _apply() -> None:
            try:
                base = str(status_var.get() or "")
                if " · 空格=" in base:
                    base = base.split(" · 空格=")[0].strip()
                status_var.set(f"{base} · {suffix}".strip(" ·") if suffix else base)
            except Exception:
                pass

        try:
            root.after(0, _apply)
        except Exception:
            pass


def suspend_process(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return False
    try:
        os_kill = os.kill
        os_kill(pid, signal.SIGSTOP)
        return True
    except (OSError, ProcessLookupError, AttributeError):
        return False


def resume_process(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return False
    try:
        os_kill = os.kill
        os_kill(pid, signal.SIGCONT)
        return True
    except (OSError, ProcessLookupError, AttributeError):
        return False


def terminate_process(proc: Any, *, grace_sec: float = 2.0) -> None:
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=grace_sec)
            return
        except Exception:
            pass
        proc.kill()
        try:
            proc.wait(timeout=1.0)
        except Exception:
            pass
    except (OSError, ProcessLookupError):
        pass
