"""跨平台工具：Windows / macOS"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


SYSTEM = platform.system()  # 'Windows' | 'Darwin' | 'Linux'


def is_mac() -> bool:
    return SYSTEM == "Darwin"


def use_ui_emoji() -> bool:
    """macOS 彩色 Emoji 与桌面风格冲突；界面装饰符号仅 Windows 保留。"""
    return not is_mac()


def ui_decorative_icon(icon: str) -> str:
    """卡片标题前缀：Mac 返回空，靠色条区分模块。"""
    if not icon or is_mac():
        return ""
    return icon.strip()


def ui_pause_label(*, paused: bool, compact: bool = False) -> str:
    if is_mac():
        return "继续" if paused else "暂停"
    if compact:
        return "▶" if paused else "⏸"
    return "▶  继续" if paused else "⏸  暂停"


def ui_start_batch_label() -> str:
    if is_mac():
        return "开始批处理（当前方案）"
    return "▶  开始批处理（当前方案）"


def ui_stop_label(*, compact: bool = False) -> str:
    if is_mac():
        return "停" if compact else "停止"
    return "⏹" if compact else "⏹  停止"


def ui_settings_label() -> str:
    if is_mac():
        return "设置"
    return "⚙️  设置"


def ui_collapse_chevron(*, expanded: bool) -> str:
    if is_mac():
        return "v" if expanded else ">"
    return "▼" if expanded else "▶"


def ui_queue_expand_hint() -> str:
    if is_mac():
        return "按顺序串行执行；失败自动重试。点 > 展开任务明细。"
    return "按顺序串行执行；失败自动重试。点 ▶ 展开任务明细。"


def ui_rules_expand_label() -> str:
    return "展开文件名微调（规则方块 · 含旧版清理 · 默认收起）"


def ui_hint_prefix() -> str:
    return "" if is_mac() else "💡 "


def ui_warning_prefix() -> str:
    return "注意 " if is_mac() else "⚠ "


def ui_ok_prefix() -> str:
    return "" if is_mac() else "✅ "


def ui_list_item(icon: str, text: str) -> str:
    deco = ui_decorative_icon(icon)
    if deco:
        return f"  {deco} {text}"
    return f"  {text}"


def ui_gear_hint() -> str:
    return "设置" if is_mac() else "⚙"


def ui_gear_glyph() -> str:
    return "···" if is_mac() else "⚙"


def silent_subprocess_kwargs() -> dict:
    """
    跨平台 GUI 子进程默认参数：
    - 全平台：stdin=DEVNULL，避免 macOS .app 继承 stdin 导致 FFmpeg 挂起
    - macOS/Linux：close_fds 降低 fd 继承
    - Windows：CREATE_NO_WINDOW + 隐藏 STARTUPINFO，避免 CMD 黑框
    """
    kw: dict = {
        "stdin": subprocess.DEVNULL,
    }
    if SYSTEM != "Windows":
        kw["close_fds"] = True
    else:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        kw["startupinfo"] = si
    return kw


def hidden_subprocess_kwargs() -> dict:
    """兼容旧名；请优先使用 silent_subprocess_kwargs / merge_subprocess_kwargs。"""
    return silent_subprocess_kwargs()


def resolve_subprocess_cwd(explicit: str | Path | None = None) -> str | None:
    """
    解析子进程工作目录。
    macOS 双击 .app 时 cwd 常为 /，相对路径会失效，回退到程序目录。
    """
    if explicit:
        p = Path(explicit)
        return str(p if p.is_dir() else p.parent)
    if SYSTEM == "Darwin":
        try:
            cwd = os.getcwd()
            if cwd and cwd not in ("", "/"):
                return None
        except OSError:
            pass
        ad = app_dir()
        if ad.is_dir():
            return str(ad)
    return None


def merge_subprocess_kwargs(user_kwargs: dict | None = None) -> dict:
    """合并 silent 默认项；不覆盖调用方已显式传入的参数。"""
    merged = dict(user_kwargs or {})
    for key, val in silent_subprocess_kwargs().items():
        if key == "creationflags":
            merged[key] = int(merged.get(key, 0)) | int(val)
        else:
            merged.setdefault(key, val)
    if SYSTEM == "Darwin":
        merged.setdefault("stdout", subprocess.PIPE)
        merged.setdefault("stderr", subprocess.PIPE)
    if merged.get("cwd") is None:
        cwd = resolve_subprocess_cwd()
        if cwd:
            merged["cwd"] = cwd
    return merged


def run_subprocess(
    cmd,
    *,
    cwd: str | Path | None = None,
    check: bool = False,
    **kwargs,
):
    """跨平台静默 subprocess.run（批处理 / FFmpeg / ffprobe 统一入口）。"""
    kw = merge_subprocess_kwargs(kwargs)
    if cwd is not None:
        kw["cwd"] = str(cwd)
    return subprocess.run(cmd, check=check, **kw)


_SUBPROCESS_HIDE_PATCHED = False


def install_silent_subprocess() -> None:
    """GUI 应用：全局 patch subprocess，避免遗漏调用点（Windows 黑框 / macOS stdin 挂起等）。"""
    global _SUBPROCESS_HIDE_PATCHED
    if _SUBPROCESS_HIDE_PATCHED:
        return
    _SUBPROCESS_HIDE_PATCHED = True

    _orig_run = subprocess.run
    _orig_popen = subprocess.Popen

    def run(*args, **kwargs):
        return _orig_run(*args, **merge_subprocess_kwargs(kwargs))

    def popen(*args, **kwargs):
        return _orig_popen(*args, **merge_subprocess_kwargs(kwargs))

    subprocess.run = run  # type: ignore[method-assign]
    subprocess.Popen = popen  # type: ignore[method-assign]


def install_windows_subprocess_hide() -> None:
    """兼容旧名。"""
    install_silent_subprocess()


def resolve_console_free_python(python_exe: str) -> str:
    """Windows: 同目录有 pythonw.exe 时优先使用，减少 Whisper 等子进程黑框。"""
    if SYSTEM != "Windows":
        return python_exe
    p = Path(python_exe)
    if p.name.lower() == "python.exe":
        pw = p.with_name("pythonw.exe")
        if pw.is_file():
            return str(pw)
    return python_exe


def subprocess_flags() -> int:
    return int(hidden_subprocess_kwargs().get("creationflags") or 0)


def ffmpeg_names() -> tuple[str, str]:
    if SYSTEM == "Windows":
        return "ffmpeg.exe", "ffprobe.exe"
    return "ffmpeg", "ffprobe"


def check_ffmpeg_available(ffmpeg: str, ffprobe: str) -> tuple[bool, str]:
    try:
        r = run_subprocess(
            [ffmpeg, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
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
    """用户配置路径。macOS 打包版写入 Application Support，避免 .app 内只读目录导致异常。"""
    if getattr(sys, "frozen", False) and SYSTEM == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "HabiVideoTool"
        base.mkdir(parents=True, exist_ok=True)
        return base / filename
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


def _first_existing(*candidates: Path) -> Path | None:
    for p in candidates:
        if p.is_file():
            return p
    return None


def resolve_naming_tool_launcher(project_root: Path | None = None) -> Path | None:
    """
    定位规范命名工具可执行路径。
    Windows: 同目录 飞跃命名工具.exe（兼容旧名 HabiNamingTool.exe）
    macOS .app: 与主程序同级的 HabiNamingTool.app / 飞跃命名工具.app
    开发环境: project_root/naming_tool.py
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if SYSTEM == "Windows":
            return _first_existing(
                exe.parent / "飞跃命名工具.exe",
                exe.parent / "HabiNamingTool.exe",
            )
        if SYSTEM == "Darwin":
            # .../HabiVideoTool.app/Contents/MacOS/HabiVideoTool
            macos_dir = exe.parent
            bundle = macos_dir.parent.parent  # .app
            release_dir = bundle.parent
            found = _first_existing(
                release_dir / "飞跃命名工具.app" / "Contents" / "MacOS" / "飞跃命名工具",
                release_dir / "HabiNamingTool.app" / "Contents" / "MacOS" / "HabiNamingTool",
                macos_dir / "飞跃命名工具",
                macos_dir / "HabiNamingTool",
                release_dir / "飞跃命名工具",
                release_dir / "HabiNamingTool",
            )
            if found:
                return found
            for app_name in ("飞跃命名工具.app", "HabiNamingTool.app"):
                naming_app = release_dir / app_name
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
    Windows: 同目录 飞跃视频工具.exe（兼容旧名 HabiVideoTool.exe）
    macOS: 与主程序同级的 HabiVideoTool.app / 飞跃视频工具.app
    开发环境: project_root/video_batch_tool_v22.py（或更早入口）
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if SYSTEM == "Windows":
            return _first_existing(
                exe.parent / "飞跃视频工具.exe",
                exe.parent / "HabiVideoTool.exe",
            )
        if SYSTEM == "Darwin":
            macos_dir = exe.parent
            bundle = macos_dir.parent.parent
            release_dir = bundle.parent
            found = _first_existing(
                release_dir / "飞跃视频工具.app" / "Contents" / "MacOS" / "飞跃视频工具",
                release_dir / "HabiVideoTool.app" / "Contents" / "MacOS" / "HabiVideoTool",
                macos_dir / "飞跃视频工具",
                macos_dir / "HabiVideoTool",
                release_dir / "飞跃视频工具",
                release_dir / "HabiVideoTool",
            )
            if found:
                return found
            for app_name in ("飞跃视频工具.app", "HabiVideoTool.app"):
                video_app = release_dir / app_name
                if video_app.is_dir():
                    return video_app
            return None
        return None
    root = project_root or Path(__file__).resolve().parent.parent
    for name in (
        "video_batch_tool_v23.py",
        "video_batch_tool_v22.py",
        "video_batch_tool_v21.py",
        "video_batch_tool_higo.py",
    ):
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
