"""跨平台工具：Windows / macOS"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


SYSTEM = platform.system()  # 'Windows' | 'Darwin' | 'Linux'


def subprocess_flags():
    if SYSTEM == "Windows":
        return subprocess.CREATE_NO_WINDOW
    return 0


def ffmpeg_names() -> tuple[str, str]:
    if SYSTEM == "Windows":
        return "ffmpeg.exe", "ffprobe.exe"
    return "ffmpeg", "ffprobe"


def check_ffmpeg_available(ffmpeg: str, ffprobe: str) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            [ffmpeg, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, creationflags=subprocess_flags(),
        )
        if r.returncode != 0:
            return False, f"无法运行 {ffmpeg}"
        line = (r.stdout or r.stderr or "").splitlines()[0] if (r.stdout or r.stderr) else "OK"
        return True, line
    except FileNotFoundError:
        hint = (
            "未找到 FFmpeg。Windows 请将 ffmpeg.exe 放在程序目录；"
            "macOS 请将 ffmpeg_mac 放在程序目录，或运行: brew install ffmpeg"
        )
        return False, hint


def path_for_ffmpeg(path: str | Path) -> str:
    """传给 FFmpeg 的路径：正斜杠，支持中文/空格"""
    return str(Path(path).resolve()).replace("\\", "/")


def default_font_paths() -> list[str]:
    if SYSTEM == "Windows":
        return [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
    if SYSTEM == "Darwin":
        return [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    return [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]


def find_default_font() -> str:
    for p in default_font_paths():
        if os.path.isfile(p):
            return p
    return ""


def open_folder(path: str | Path):
    path = str(path)
    if not os.path.isdir(path):
        return False
    if SYSTEM == "Windows":
        os.startfile(path)
    elif SYSTEM == "Darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)
    return True


def app_dir() -> Path:
    """程序所在目录（配置与资源）"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _icon_lookup_bases() -> list[Path]:
    bases: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bases.append(Path(meipass))
        bases.append(Path(sys.executable).resolve().parent)
    bases.append(app_dir())
    return bases


def find_packaging_icon(project_dir: str | Path, role: str, ext: str) -> str | None:
    """
    打包用图标路径。role: video | naming；ext: icns / ico / png
    优先 {role}_icon.*，其次 app_icon.*（兼容旧资源）
    """
    d = Path(project_dir)
    suffix = ext if ext.startswith(".") else f".{ext}"
    for name in (f"{role}_icon{suffix}", f"app_icon{suffix}"):
        p = d / name
        if p.is_file():
            return str(p)
    return None


def find_role_icon(role: str, ext: str) -> str:
    """运行时查找图标（窗口角标等）。"""
    suffix = ext if ext.startswith(".") else f".{ext}"
    for base in _icon_lookup_bases():
        for stem in (f"{role}_icon", "app_icon"):
            p = base / f"{stem}{suffix}"
            if p.is_file():
                return str(p)
    return ""


def set_tk_window_icon(root, role: str) -> None:
    """设置 Tk 窗口图标：Windows 优先 .ico，macOS/Linux 用 .png。"""
    try:
        from tkinter import PhotoImage
    except ImportError:
        return
    if SYSTEM == "Windows":
        ico = find_role_icon(role, ".ico")
        if ico:
            try:
                root.iconbitmap(ico)
                return
            except Exception:
                pass
    png = find_role_icon(role, ".png")
    if png:
        try:
            img = PhotoImage(file=png)
            root._habi_icon_image = img  # noqa: prevent GC
            root.iconphoto(True, img)
        except Exception:
            pass


def resource_path(relative: str | Path) -> Path:
    """打包资源路径：开发时用项目目录，PyInstaller 运行时用 _MEIPASS"""
    rel = Path(relative)
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / rel
        return Path(sys.executable).resolve().parent / rel
    return app_dir() / rel


def _bundled_bin_dir() -> Path | None:
    """查找内置 FFmpeg 目录（bin/ 或程序根目录）"""
    ff_name, _ = ffmpeg_names()
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.extend([Path(meipass) / "bin", Path(meipass)])
        candidates.extend([Path(sys.executable).resolve().parent / "bin",
                           Path(sys.executable).resolve().parent])
    else:
        candidates.append(app_dir())
    for base in candidates:
        if not base.is_dir():
            continue
        if (base / ff_name).is_file():
            return base
        if SYSTEM == "Darwin":
            if (base / "ffmpeg_mac").is_file():
                return base
    return None


def get_ffmpeg_path() -> str:
    ff, _ = resolve_ffmpeg()
    return ff


def get_ffprobe_path() -> str:
    _, fp = resolve_ffmpeg()
    return fp


def resolve_ffmpeg() -> tuple[str, str]:
    """返回可用的 ffmpeg/ffprobe 路径，优先内置二进制，其次 PATH"""
    bdir = _bundled_bin_dir()
    if bdir:
        if SYSTEM == "Windows":
            return str(bdir / "ffmpeg.exe"), str(bdir / "ffprobe.exe")
        mac_ff = bdir / "ffmpeg_mac"
        mac_fp = bdir / "ffprobe_mac"
        ff = str(mac_ff if mac_ff.is_file() else bdir / "ffmpeg")
        fp = str(mac_fp if mac_fp.is_file() else bdir / "ffprobe")
        return ff, fp

    ff, fp = ffmpeg_names()
    for name in (ff, "ffmpeg"):
        if shutil.which(name):
            ff = name
            break
    for name in (fp, "ffprobe"):
        if shutil.which(name):
            fp = name
            break
    return ff, fp


def config_path(filename: str) -> Path:
    return app_dir() / filename


def habi_naming_tool_config_path() -> Path:
    """规范命名工具配置路径"""
    if SYSTEM == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home())) / "HabiNamingTool"
    elif SYSTEM == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "HabiNamingTool"
    else:
        base = Path.home() / ".config" / "HabiNamingTool"
    base.mkdir(parents=True, exist_ok=True)
    return base / "naming_config.json"


def resolve_naming_tool_launcher(project_root: Path | None = None) -> Path | None:
    """
    定位规范命名工具可执行路径。
    Windows: 同目录 HabiNamingTool.exe
    macOS .app: 与主程序同级的 HabiNamingTool.app/Contents/MacOS/HabiNamingTool
    开发环境: project_root/naming_tool.py
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if SYSTEM == "Windows":
            candidate = exe.parent / "HabiNamingTool.exe"
            return candidate if candidate.is_file() else None
        if SYSTEM == "Darwin":
            # .../HabiVideoTool.app/Contents/MacOS/HabiVideoTool
            macos_dir = exe.parent
            bundle = macos_dir.parent.parent  # .app
            release_dir = bundle.parent
            for candidate in (
                release_dir / "HabiNamingTool.app" / "Contents" / "MacOS" / "HabiNamingTool",
                macos_dir / "HabiNamingTool",
                release_dir / "HabiNamingTool",
            ):
                if candidate.is_file():
                    return candidate
            naming_app = release_dir / "HabiNamingTool.app"
            if naming_app.is_dir():
                return naming_app  # 用 open -a 启动
            return None
        return None
    root = project_root or Path(__file__).resolve().parent.parent
    script = root / "naming_tool.py"
    return script if script.is_file() else None


def resolve_video_tool_launcher(project_root: Path | None = None) -> Path | None:
    """
    定位视频批处理工具可执行路径。
    Windows: 同目录 HabiVideoTool.exe
    macOS: 与主程序同级的 HabiVideoTool.app/Contents/MacOS/HabiVideoTool
    开发环境: project_root/video_batch_tool_v21.py（或 higo 入口）
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if SYSTEM == "Windows":
            candidate = exe.parent / "HabiVideoTool.exe"
            return candidate if candidate.is_file() else None
        if SYSTEM == "Darwin":
            macos_dir = exe.parent
            bundle = macos_dir.parent.parent
            release_dir = bundle.parent
            for candidate in (
                release_dir / "HabiVideoTool.app" / "Contents" / "MacOS" / "HabiVideoTool",
                macos_dir / "HabiVideoTool",
                release_dir / "HabiVideoTool",
            ):
                if candidate.is_file():
                    return candidate
            video_app = release_dir / "HabiVideoTool.app"
            if video_app.is_dir():
                return video_app
            return None
        return None
    root = project_root or Path(__file__).resolve().parent.parent
    for name in ("video_batch_tool_v21.py", "video_batch_tool_higo.py"):
        script = root / name
        if script.is_file():
            return script
    return None


def habi_tool_config_path() -> Path:
    """视频工具命名配置（旧版兼容）"""
    if SYSTEM == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home())) / "HabiVideoTool"
    elif SYSTEM == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "HabiVideoTool"
    else:
        base = Path.home() / ".config" / "HabiVideoTool"
    base.mkdir(parents=True, exist_ok=True)
    return base / "config.json"
