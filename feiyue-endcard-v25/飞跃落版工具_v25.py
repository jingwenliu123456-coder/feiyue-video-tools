#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞跃落版工具 v25 — 透明落版 · 背景模糊版

功能
----
- 批量处理素材视频，在最后 N 秒叠加「透明落版」（9:16、带 alpha 通道的动态 logo，
  支持 ProRes 4444 / qtrle .mov、VP9/AV1 alpha .webm 等）。
- 落版出现期间，底层素材继续播放但施加高斯模糊（剪映同款模糊特效观感）。
- 落版出现时长默认**自动识别**落版文件长度（也可用「手动指定 N 秒」覆盖）。
- 落版短于所需时长时自动循环铺满；时长一致时只播一遍，不重复循环。

命名规范
--------
    VNO编号-语言-尺寸
    编号：手动填写（批量时可勾选「编号自动递增」）
    语言：默认 EN
    尺寸：默认 P2
    示例：VNO105-EN-P2.mp4

依赖：ffmpeg / ffprobe 需在 PATH 中（或与本脚本同目录）。
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

APP_TITLE = "飞跃落版工具 v25 · 透明落版背景模糊"
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".ts"}
ENDCARD_EXTS = {".mov", ".webm", ".mp4", ".mkv"}

# ---------------------------------------------------------------------------
# 核心处理（与 GUI 解耦，可单独 import 使用）
# ---------------------------------------------------------------------------


def find_bin(name: str) -> str:
    """优先 PATH，其次脚本同目录。"""
    p = shutil.which(name)
    if p:
        return p
    local = Path(__file__).resolve().parent / (name + (".exe" if os.name == "nt" else ""))
    return str(local) if local.exists() else name


FFMPEG = find_bin("ffmpeg")
FFPROBE = find_bin("ffprobe")


def probe_video(path: str | Path) -> dict:
    """返回 {width, height, duration, fps}，失败抛异常。"""
    cmd = [
        FFPROBE, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration,nb_frames",
        "-show_entries", "format=duration",
        "-of", "json", str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {path}\n{r.stderr.strip()}")
    info = json.loads(r.stdout or "{}")
    st = (info.get("streams") or [{}])[0]
    fmt_dur = float((info.get("format") or {}).get("duration") or 0)
    st_dur = 0.0
    if st.get("duration") is not None:
        try:
            st_dur = float(st["duration"])
        except (TypeError, ValueError):
            st_dur = 0.0
    dur = max(fmt_dur, st_dur)
    fps_s = st.get("r_frame_rate", "30/1")
    try:
        num, den = fps_s.split("/")
        fps = float(num) / max(float(den), 1)
    except Exception:
        fps = 30.0
    if dur <= 0 and st.get("nb_frames"):
        try:
            dur = int(st["nb_frames"]) / max(fps, 1.0)
        except (TypeError, ValueError):
            pass
    return {
        "width": int(st.get("width") or 0),
        "height": int(st.get("height") or 0),
        "duration": dur,
        "fps": fps,
    }


def resolve_last_seconds(
    src_duration: float,
    endcard: str | Path,
    last_seconds: float | None = None,
    *,
    auto_from_endcard: bool = True,
) -> tuple[float, float]:
    """
    计算落版段时长 N 与落版文件自身时长。
    auto_from_endcard=True 时 N = 落版文件时长（自动识别）。
    """
    ec_meta = probe_video(endcard)
    ec_dur = float(ec_meta["duration"] or 0)
    if ec_dur <= 0:
        raise RuntimeError(f"无法读取落版时长: {Path(endcard).name}")
    if auto_from_endcard or last_seconds is None:
        target = ec_dur
    else:
        target = float(last_seconds)
    n = min(max(target, 0.5), max(src_duration, 0.5))
    return n, ec_dur


ENDCARD_LEAD_SKIP_DEFAULT = 1.0  # smash尾板.mov 等 qtrle 片头约 1s 全黑，需跳过


def probe_endcard_lead(path: str | Path, *, default: float = ENDCARD_LEAD_SKIP_DEFAULT) -> float:
    """跳过落版片头黑场/空透明段（避免叠上去「看不见」）。"""
    path = Path(path)
    try:
        tmp = Path(tempfile.gettempdir()) / f"habi_lead_{path.stem}.png"
        subprocess.run(
            [FFMPEG, "-y", "-i", str(path), "-vframes", "1", str(tmp)],
            capture_output=True, timeout=30,
        )
        if tmp.is_file() and tmp.stat().st_size < 80_000:
            return max(default, 0.5)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return 0.0


def build_filter(
    w: int,
    h: int,
    duration: float,
    last_seconds: float,
    sigma: float,
    *,
    ec_dur: float = 0.0,
    loop_endcard: bool = False,
    endcard_skip: float = 0.0,
    fit_endcard: bool = True,
    fade_sec: float = 1.0,
    radial_div: float = 2.0,
    sharpen: bool = True,
) -> str:
    """
    单时间轴（避免 trim+xfade 后 overlay 失效）：
      · t < t0：原画清晰
      · t >= t0：径向景深虚化 + 透明落版（qtrle/argb 用 format=auto）
    """
    t0 = max(duration - last_seconds, 0.0)
    skip = max(0.0, float(endcard_skip))
    trim_end = skip + last_seconds
    if ec_dur > skip:
        trim_end = min(trim_end, ec_dur)

    geq_lum = (
        "255*pow(max(0,1-min(1,sqrt(pow(X-W/2,2)+pow(Y-H/2,2))/"
        f"(min(W\\,H)/{radial_div:.2f}))),0.7)"
    )

    if loop_endcard:
        card_in = (
            f"[1:v]trim=start={skip:.3f}:end={trim_end:.3f},setpts=PTS-STARTPTS,"
            "loop=loop=-1:size=32767:start=0,"
            f"trim=duration={last_seconds:.3f},setpts=PTS-STARTPTS"
        )
    else:
        card_in = f"[1:v]trim=start={skip:.3f}:end={trim_end:.3f},setpts=PTS-STARTPTS"

    if fit_endcard:
        card_in += f",scale={w}:{h}:force_original_aspect_ratio=decrease"
    else:
        card_in += f",scale={w}:{h}"

    if sharpen:
        card_in += ",format=rgba,unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=1.5[card];"
    else:
        card_in += ",format=rgba[card];"

    return (
        "[0:v]split=3[clean][gbin][msk_src];"
        f"[gbin]gblur=sigma={sigma:.1f}[gb];"
        f"[msk_src]format=gray,geq=lum='{geq_lum}'[mask];"
        "[clean][gb][mask]maskedmerge[dof];"
        f"[dof][clean]overlay=0:0:enable='lt(t,{t0:.3f})'[bg];"
        f"{card_in}"
        "[bg][card]overlay=(W-w)/2:(H-h)/2:format=auto:eof_action=pass,format=yuv420p[v]"
    )


def _run_ffmpeg_with_progress(
    cmd: list,
    dur: float,
    log,
    progress,
    cancel_event: threading.Event | None,
) -> None:
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        if cancel_event is not None and cancel_event.is_set():
            proc.kill()
            raise RuntimeError("已取消")
        line = line.strip()
        if line.startswith("out_time_us=") and progress and dur > 0:
            try:
                us = int(line.split("=", 1)[1])
                progress(min(us / 1e6 / dur * 100, 99.0))
            except ValueError:
                pass
    proc.wait()
    if proc.returncode != 0:
        err = (proc.stderr.read() if proc.stderr else "")[-2500:]
        raise RuntimeError(f"ffmpeg 失败（退出码 {proc.returncode}）\n{err}")


def process_one(
    src: str | Path,
    endcard: str | Path,
    out_path: str | Path,
    last_seconds: float | None = 5.0,
    sigma: float = 8.0,
    crf: int = 18,
    preset: str = "slow",
    log=print,
    progress=None,  # callable(percent: float)
    cancel_event: threading.Event | None = None,
    *,
    auto_from_endcard: bool = True,
) -> Path:
    """处理单个视频：前段原画 + 后段（模糊+透明落版）concat，叠层最稳。"""
    src, endcard, out_path = Path(src), Path(endcard), Path(out_path)
    meta = probe_video(src)
    w, h, dur = meta["width"], meta["height"], meta["duration"]
    if not w or not h or dur <= 0:
        raise RuntimeError(f"无法读取视频信息: {src.name}")

    n, ec_dur = resolve_last_seconds(
        dur, endcard, last_seconds, auto_from_endcard=auto_from_endcard,
    )
    if auto_from_endcard or last_seconds is None:
        log(f"  落版时长自动识别: {ec_dur:.2f}s → 最后 {n:.2f}s 出现落版")
    elif n < float(last_seconds) - 0.05:
        log(f"  ⚠ {src.name} 片长 {dur:.1f}s 不足 {float(last_seconds):.1f}s，落版将覆盖全片")

    loop_endcard = ec_dur < n - 0.05
    lead_skip = probe_endcard_lead(endcard)
    t0 = max(dur - n, 0.0)
    card_take = min(n, max(ec_dur - lead_skip, 0.1))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="habi_v25_"))
    tail_path = tmp / "tail.mp4"
    head_path = tmp / "head.mp4"

    loop_note = "循环铺满" if loop_endcard else "播一遍"
    log(
        f"  ffmpeg: 落版段 {n:.2f}s / 文件 {ec_dur:.2f}s ({loop_note}) / "
        f"跳过片头 {lead_skip:.2f}s / 径向模糊 sigma={sigma:.0f} / {w}x{h}"
    )

    tail_fc = (
        f"[0:v]gblur=sigma={sigma:.1f}[bg];"
        f"[1:v]scale={w}:{h}:force_original_aspect_ratio=decrease,format=rgba[card];"
        "[bg][card]overlay=(W-w)/2:(H-h)/2:format=auto[v]"
    )
    tail_cmd = [FFMPEG, "-y", "-threads", "4", "-ss", f"{t0:.3f}", "-t", f"{n:.3f}", "-i", str(src)]
    if loop_endcard:
        tail_cmd.extend(["-stream_loop", "-1", "-ss", f"{lead_skip:.3f}", "-t", f"{n:.3f}", "-i", str(endcard)])
    else:
        tail_cmd.extend(["-ss", f"{lead_skip:.3f}", "-t", f"{card_take:.3f}", "-i", str(endcard)])
    tail_cmd.extend([
        "-filter_complex", tail_fc,
        "-map", "[v]",
        "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-progress", "pipe:1", "-nostats",
        str(tail_path),
    ])
    _run_ffmpeg_with_progress(tail_cmd, n, log, progress, cancel_event)

    if t0 > 0.05:
        head_cmd = [
            FFMPEG, "-y", "-i", str(src), "-t", f"{t0:.3f}",
            "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            str(head_path),
        ]
        subprocess.run(head_cmd, capture_output=True, check=False)

        merge_fc = "[0:v][1:v]concat=n=2:v=1:a=0[vout]"
        merge_cmd = [
            FFMPEG, "-y", "-i", str(head_path), "-i", str(tail_path), "-i", str(src),
            "-filter_complex", merge_fc,
            "-map", "[vout]", "-map", "2:a?",
            "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            "-progress", "pipe:1", "-nostats",
            str(out_path),
        ]
    else:
        merge_cmd = [
            FFMPEG, "-y", "-i", str(tail_path), "-i", str(src),
            "-map", "0:v", "-map", "1:a?",
            "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            "-progress", "pipe:1", "-nostats",
            str(out_path),
        ]

    _run_ffmpeg_with_progress(merge_cmd, dur, log, progress, cancel_event)

    try:
        shutil.rmtree(tmp, ignore_errors=True)
    except OSError:
        pass

    if not out_path.exists():
        raise RuntimeError(f"输出文件未生成: {out_path}")
    if progress:
        progress(100.0)
    return out_path


# ---------------------------------------------------------------------------
# 命名：VNO编号-语言-尺寸
# ---------------------------------------------------------------------------


def make_out_name(code: str, lang: str, size: str, ext: str = ".mp4") -> str:
    """VNO编号-语言-尺寸，如 VNO105-EN-P2.mp4"""
    code = (code or "").strip() or "000"
    lang = (lang or "").strip().upper() or "EN"
    size = (size or "").strip().upper() or "P2"
    return f"VNO{code}-{lang}-{size}{ext}"


def bump_code(code: str, step: int) -> str:
    """编号自动递增：取尾部数字 +step，保留前导零与非数字前缀。无数字则追加。"""
    m = re.search(r"^(.*?)(\d+)$", code.strip())
    if not m:
        return f"{code.strip()}{step:03d}" if step else code.strip()
    head, digits = m.group(1), m.group(2)
    return f"{head}{int(digits) + step:0{len(digits)}d}"


def unique_path(out_dir: Path, name: str) -> Path:
    """重名时加 _1/_2 后缀，避免覆盖。"""
    p = out_dir / name
    if not p.exists():
        return p
    stem, ext = p.stem, p.suffix
    i = 1
    while (out_dir / f"{stem}_{i}{ext}").exists():
        i += 1
    return out_dir / f"{stem}_{i}{ext}"


CONFIG_FILE = Path(__file__).resolve().parent / "飞跃落版工具_v25_config.json"


def load_config() -> dict:
    try:
        if CONFIG_FILE.is_file():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return {}


def save_config(data: dict) -> None:
    try:
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------


def run_gui() -> None:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("860x720")
    root.minsize(760, 640)

    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass

    PAD = {"padx": 10, "pady": 5}

    # ---- 状态变量 ----
    src_files: list[Path] = []
    endcard_var = tk.StringVar()
    outdir_var = tk.StringVar()
    n_var = tk.DoubleVar(value=5.0)
    sigma_var = tk.IntVar(value=8)
    code_var = tk.StringVar(value="001")
    lang_var = tk.StringVar(value="EN")
    size_var = tk.StringVar(value="P2")
    auto_inc_var = tk.BooleanVar(value=True)
    auto_n_var = tk.BooleanVar(value=True)
    endcard_info_var = tk.StringVar(value="落版: 未选择")
    progress_var = tk.DoubleVar(value=0.0)
    status_var = tk.StringVar(value="就绪")
    cancel_event = threading.Event()
    worker: list[threading.Thread | None] = [None]
    ui_q: queue.Queue = queue.Queue()

    cfg = load_config()
    if cfg.get("endcard"):
        endcard_var.set(str(cfg["endcard"]))
    if cfg.get("outdir"):
        outdir_var.set(str(cfg["outdir"]))
    if cfg.get("last_seconds") is not None:
        n_var.set(float(cfg["last_seconds"]))
    if cfg.get("sigma") is not None:
        sigma_var.set(int(cfg["sigma"]))
    if cfg.get("code"):
        code_var.set(str(cfg["code"]))
    if cfg.get("lang"):
        lang_var.set(str(cfg["lang"]))
    if cfg.get("size"):
        size_var.set(str(cfg["size"]))
    if "auto_inc" in cfg:
        auto_inc_var.set(bool(cfg["auto_inc"]))
    if "auto_n" in cfg:
        auto_n_var.set(bool(cfg["auto_n"]))

    def persist_settings() -> None:
        save_config({
            "endcard": endcard_var.get().strip(),
            "outdir": outdir_var.get().strip(),
            "last_seconds": float(n_var.get()),
            "sigma": int(sigma_var.get()),
            "code": code_var.get().strip(),
            "lang": lang_var.get().strip(),
            "size": size_var.get().strip(),
            "auto_inc": bool(auto_inc_var.get()),
            "auto_n": bool(auto_n_var.get()),
        })

    n_spin: ttk.Spinbox | None = None

    def refresh_endcard_info(*_):
        p = endcard_var.get().strip()
        if not p or not Path(p).is_file():
            endcard_info_var.set("落版: 未选择")
            return
        try:
            meta = probe_video(p)
            d = float(meta["duration"] or 0)
            if d <= 0:
                endcard_info_var.set("落版: 无法读取时长（请检查文件）")
                return
            if auto_n_var.get():
                n_var.set(round(d, 2))
            endcard_info_var.set(
                f"落版: {d:.2f}s · {meta['width']}×{meta['height']} · "
                + ("已自动设为最后 N 秒" if auto_n_var.get() else "手动指定 N 秒")
            )
        except Exception as exc:
            endcard_info_var.set(f"落版读取失败: {exc}")

    def on_auto_n_toggle(*_):
        if n_spin is not None:
            n_spin.configure(state="disabled" if auto_n_var.get() else "normal")
        refresh_endcard_info()

    # ---- 布局 ----
    top = ttk.Frame(root)
    top.pack(fill="both", expand=True, **PAD)

    # 素材列表
    f_src = ttk.LabelFrame(top, text=" ① 素材视频（批量） ")
    f_src.pack(fill="both", expand=True, **PAD)
    listbox = tk.Listbox(f_src, height=7, activestyle="none")
    sb = ttk.Scrollbar(f_src, orient="vertical", command=listbox.yview)
    listbox.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    listbox.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=6)

    btns = ttk.Frame(f_src)
    btns.pack(fill="x", padx=8, pady=(0, 6))

    def add_files():
        fs = filedialog.askopenfilenames(
            title="选择素材视频",
            filetypes=[("视频", " ".join(f"*{e}" for e in sorted(VIDEO_EXTS)))],
        )
        for f in fs:
            p = Path(f)
            if p not in src_files:
                src_files.append(p)
                listbox.insert("end", p.name)

    def add_folder():
        d = filedialog.askdirectory(title="选择素材文件夹")
        if not d:
            return
        for p in sorted(Path(d).iterdir()):
            if p.suffix.lower() in VIDEO_EXTS and p not in src_files:
                src_files.append(p)
                listbox.insert("end", p.name)

    def clear_files():
        src_files.clear()
        listbox.delete(0, "end")

    ttk.Button(btns, text="＋ 添加视频", command=add_files).pack(side="left", padx=3)
    ttk.Button(btns, text="📁 添加文件夹", command=add_folder).pack(side="left", padx=3)
    ttk.Button(btns, text="清空", command=clear_files).pack(side="left", padx=3)

    # 落版 + 参数
    f_cfg = ttk.LabelFrame(top, text=" ② 落版与效果 ")
    f_cfg.pack(fill="x", **PAD)

    ttk.Label(f_cfg, text="透明落版（9:16 动态 logo，.mov/.webm 带 alpha）:").grid(
        row=0, column=0, sticky="w", padx=8, pady=(8, 2))
    ttk.Entry(f_cfg, textvariable=endcard_var, width=62).grid(row=0, column=1, sticky="we", padx=4, pady=(8, 2))

    def pick_endcard():
        f = filedialog.askopenfilename(
            title="选择透明落版文件",
            filetypes=[("落版视频", "*.mov *.webm *.mp4 *.mkv")],
        )
        if f:
            endcard_var.set(f)
            refresh_endcard_info()

    ttk.Button(f_cfg, text="浏览…", command=pick_endcard).grid(row=0, column=2, padx=8, pady=(8, 2))
    ttk.Label(f_cfg, textvariable=endcard_info_var, foreground="#0a6").grid(
        row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))

    ttk.Checkbutton(
        f_cfg, text="自动识别落版时长（推荐）", variable=auto_n_var, command=on_auto_n_toggle,
    ).grid(row=2, column=0, columnspan=3, sticky="w", padx=8)

    ttk.Label(f_cfg, text="落版出现时间（最后 N 秒）:").grid(row=3, column=0, sticky="w", padx=8)
    n_spin = ttk.Spinbox(f_cfg, from_=0.5, to=120, increment=0.1, textvariable=n_var, width=8)
    n_spin.grid(row=3, column=1, sticky="w", padx=4)

    ttk.Label(f_cfg, text="背景模糊强度（径向景深，建议 6~10）:").grid(row=4, column=0, sticky="w", padx=8)
    sigma_row = ttk.Frame(f_cfg)
    sigma_row.grid(row=4, column=1, sticky="w", padx=4)
    sigma_lab = ttk.Label(sigma_row, text="8", width=4)
    ttk.Scale(
        sigma_row, from_=4, to=20, orient="horizontal", length=220, variable=sigma_var,
        command=lambda v: sigma_lab.config(text=str(int(float(v)))),
    ).pack(side="left")
    sigma_lab.pack(side="left")
    ttk.Label(f_cfg, text="值越大越模糊", foreground="#888").grid(row=4, column=2, sticky="w")
    ttk.Label(
        f_cfg,
        text="效果：最后 N 秒径向景深虚化 + 透明 9:16 动态 logo 居中叠层（非全程死糊）",
        foreground="#666",
    ).grid(row=5, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 8))

    endcard_var.trace_add("write", refresh_endcard_info)
    on_auto_n_toggle()

    f_cfg.columnconfigure(1, weight=1)

    # 命名
    f_name = ttk.LabelFrame(top, text=" ③ 输出命名（VNO编号-语言-尺寸） ")
    f_name.pack(fill="x", **PAD)
    ttk.Label(f_name, text="VNO", font=("", 11, "bold")).grid(row=0, column=0, padx=(10, 2), pady=8)
    ttk.Entry(f_name, textvariable=code_var, width=10).grid(row=0, column=1)
    ttk.Label(f_name, text=" - ", font=("", 11, "bold")).grid(row=0, column=2)
    ttk.Entry(f_name, textvariable=lang_var, width=6).grid(row=0, column=3)
    ttk.Label(f_name, text=" - ", font=("", 11, "bold")).grid(row=0, column=4)
    ttk.Entry(f_name, textvariable=size_var, width=6).grid(row=0, column=5)
    ttk.Label(f_name, text="编号", foreground="#888").grid(row=1, column=1, sticky="n")
    ttk.Label(f_name, text="语言", foreground="#888").grid(row=1, column=3, sticky="n")
    ttk.Label(f_name, text="尺寸", foreground="#888").grid(row=1, column=5, sticky="n")
    ttk.Checkbutton(
        f_name, text="批量时编号自动 +1（如 VNO105 → VNO106 …）", variable=auto_inc_var,
    ).grid(row=0, column=6, padx=16, sticky="w")

    preview_var = tk.StringVar()
    ttk.Label(f_name, textvariable=preview_var, foreground="#0a6").grid(
        row=2, column=0, columnspan=7, sticky="w", padx=10, pady=(4, 8))

    def refresh_preview(*_):
        preview_var.set("示例:  " + make_out_name(code_var.get(), lang_var.get(), size_var.get()))

    for v in (code_var, lang_var, size_var):
        v.trace_add("write", refresh_preview)
    refresh_preview()

    # 输出目录
    f_out = ttk.Frame(top)
    f_out.pack(fill="x", **PAD)
    ttk.Label(f_out, text="输出文件夹:").pack(side="left")
    ttk.Entry(f_out, textvariable=outdir_var, width=58).pack(side="left", padx=6, fill="x", expand=True)

    def pick_outdir():
        d = filedialog.askdirectory(title="选择输出文件夹")
        if d:
            outdir_var.set(d)

    ttk.Button(f_out, text="浏览…", command=pick_outdir).pack(side="left")

    # 日志 + 进度
    f_log = ttk.LabelFrame(root, text=" 日志 ")
    f_log.pack(fill="both", expand=True, **PAD)
    log_text = tk.Text(f_log, height=10, wrap="word", state="disabled")
    log_text.pack(fill="both", expand=True, padx=6, pady=6)

    def log(msg: str):
        ui_q.put(("log", msg))

    bar_row = ttk.Frame(root)
    bar_row.pack(fill="x", **PAD)
    ttk.Progressbar(bar_row, variable=progress_var, maximum=100).pack(
        side="left", fill="x", expand=True, padx=(0, 8))
    ttk.Label(bar_row, textvariable=status_var, width=22).pack(side="left")

    def pump_queue():
        try:
            while True:
                kind, payload = ui_q.get_nowait()
                if kind == "log":
                    log_text.configure(state="normal")
                    log_text.insert("end", str(payload) + "\n")
                    log_text.see("end")
                    log_text.configure(state="disabled")
                elif kind == "progress":
                    progress_var.set(payload)
                elif kind == "status":
                    status_var.set(str(payload))
                elif kind == "done":
                    start_btn.configure(state="normal")
                    cancel_btn.configure(state="disabled")
        except queue.Empty:
            pass
        root.after(80, pump_queue)

    # ---- 批量执行 ----
    def run_batch():
        if not src_files:
            messagebox.showwarning("提示", "请先添加素材视频")
            return
        ec = endcard_var.get().strip()
        if not ec or not Path(ec).exists():
            messagebox.showwarning("提示", "请选择透明落版文件（.mov / .webm 带 alpha）")
            return
        out_dir = outdir_var.get().strip()
        if not out_dir:
            messagebox.showwarning("提示", "请选择输出文件夹")
            return
        n_manual = None if auto_n_var.get() else float(n_var.get())
        sigma = float(sigma_var.get())
        code0 = code_var.get().strip() or "001"
        lang = lang_var.get().strip() or "EN"
        size = size_var.get().strip() or "P2"
        use_auto_n = bool(auto_n_var.get())

        cancel_event.clear()
        start_btn.configure(state="disabled")
        cancel_btn.configure(state="normal")

        def work():
            ok, fail = 0, 0
            total = len(src_files)
            for i, src in enumerate(list(src_files)):
                if cancel_event.is_set():
                    log("⛔ 已手动取消")
                    break
                code = bump_code(code0, i) if auto_inc_var.get() else code0
                out_path = unique_path(Path(out_dir), make_out_name(code, lang, size))
                ui_q.put(("status", f"[{i + 1}/{total}] {src.name}"))
                log(f"▶ [{i + 1}/{total}] {src.name}  →  {out_path.name}")
                try:
                    process_one(
                        src, ec, out_path,
                        last_seconds=n_manual, sigma=sigma,
                        auto_from_endcard=use_auto_n,
                        log=log,
                        progress=lambda p: ui_q.put(("progress", p)),
                        cancel_event=cancel_event,
                    )
                    ok += 1
                    log(f"  ✔ 完成: {out_path}")
                except Exception as exc:  # noqa: BLE001
                    fail += 1
                    log(f"  ✘ 失败: {exc}")
            ui_q.put(("progress", 0.0))
            ui_q.put(("status", f"完成 {ok} 个，失败 {fail} 个"))
            log(f"—— 批处理结束：成功 {ok}，失败 {fail} ——")
            persist_settings()
            ui_q.put(("done", None))

        worker[0] = threading.Thread(target=work, daemon=True)
        worker[0].start()

    btn_row = ttk.Frame(root)
    btn_row.pack(fill="x", padx=10, pady=(0, 10))
    start_btn = ttk.Button(btn_row, text="▶ 开始处理", command=run_batch)
    start_btn.pack(side="right", padx=4)
    cancel_btn = ttk.Button(btn_row, text="⏹ 取消", command=cancel_event.set, state="disabled")
    cancel_btn.pack(side="right", padx=4)

    pump_queue()
    root.protocol("WM_DELETE_WINDOW", lambda: (persist_settings(), root.destroy()))
    root.mainloop()


# ---------------------------------------------------------------------------
# CLI（无界面批处理）
# ---------------------------------------------------------------------------


def run_cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="飞跃落版工具 v25：最后N秒背景模糊 + 透明动态落版")
    ap.add_argument("src", nargs="+", help="素材视频（可多个）")
    ap.add_argument("--endcard", required=True, help="透明落版 .mov/.webm（9:16 带 alpha）")
    ap.add_argument("-n", "--last-seconds", type=float, default=None,
                    help="手动指定落版时长（秒）；默认自动读取落版文件长度")
    ap.add_argument("--no-auto-length", action="store_true",
                    help="不自动识别落版时长，须配合 -n")
    ap.add_argument("--sigma", type=float, default=8.0, help="径向模糊强度（gblur sigma，建议 6-10）")
    ap.add_argument("-o", "--outdir", required=True, help="输出文件夹")
    ap.add_argument("--code", default="001", help="VNO 编号（如 105）")
    ap.add_argument("--lang", default="EN", help="语言，默认 EN")
    ap.add_argument("--size", default="P2", help="尺寸，默认 P2")
    ap.add_argument("--no-inc", action="store_true", help="批量时编号不自动递增")
    args = ap.parse_args(argv)

    auto_n = not args.no_auto_length and args.last_seconds is None
    if not auto_n and args.last_seconds is None:
        ap.error("请指定 -n/--last-seconds，或去掉 --no-auto-length 以自动识别落版时长")

    out_dir = Path(args.outdir)
    fail = 0
    for i, s in enumerate(args.src):
        code = args.code if args.no_inc else bump_code(args.code, i)
        out_path = unique_path(out_dir, make_out_name(code, args.lang, args.size))
        print(f"▶ [{i + 1}/{len(args.src)}] {s} → {out_path.name}")
        try:
            process_one(
                s, args.endcard, out_path,
                last_seconds=args.last_seconds,
                sigma=args.sigma,
                auto_from_endcard=auto_n,
                progress=lambda p: print(f"\r  {p:5.1f}%", end="", flush=True),
            )
            print("\r  ✔ 100.0%")
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"\n  ✘ 失败: {exc}")
    return 1 if fail else 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(run_cli(sys.argv[1:]))
    run_gui()
