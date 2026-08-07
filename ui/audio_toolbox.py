"""音频工具箱：提取 / 替换 / 静音 / 音量"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import END, BOTH, LEFT, RIGHT, X, Y, BooleanVar, StringVar, Text, Toplevel, filedialog, messagebox, ttk
from typing import Callable, Optional

try:
    from modules.ui_skin import make_button
except Exception:
    def make_button(parent, text, command=None, *, kind="default", width=None, **kw):  # type: ignore
        return ttk.Button(parent, text=text, command=command, **kw)

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".m4v", ".webm"}
AUDIO_EXTS = {".mp3", ".wav", ".aac", ".m4a", ".flac"}


def _hidden_kw() -> dict:
    from modules.platform_utils import hidden_subprocess_kwargs
    return hidden_subprocess_kwargs()


def list_media(folder: str, *, videos_only: bool = True) -> list[str]:
    if not folder or not os.path.isdir(folder):
        return []
    exts = VIDEO_EXTS if videos_only else VIDEO_EXTS | AUDIO_EXTS
    return sorted(
        f for f in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, f)) and Path(f).suffix.lower() in exts
    )


class AudioToolboxWindow(Toplevel):
    def __init__(
        self,
        parent,
        *,
        ffmpeg: str,
        ffprobe: str,
        log_fn: Optional[Callable[[str], None]] = None,
        initial_folder: str = "",
    ):
        super().__init__(parent)
        self.title("音频工具箱")
        self.geometry("720x520")
        self.minsize(640, 460)
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.log_fn = log_fn

        self.folder_var = StringVar(value=initial_folder)
        self.func_var = StringVar(value="提取音频")
        self.out_dir_var = StringVar(value=initial_folder)
        self.bitrate_var = StringVar(value="192k")
        self.sample_var = StringVar(value="44100")
        self.format_var = StringVar(value="mp3")
        self.audio_replace_var = StringVar()
        self.gain_var = StringVar(value="0")
        self.keep_name_var = BooleanVar(value=True)
        self._func_buttons: dict[str, ttk.Button] = {}

        try:
            from modules.ui_skin import FONTS, PAD, card_colors, make_button, setup_log_tags
            self._ui = {"FONTS": FONTS, "PAD": PAD, "colors": card_colors()}
        except Exception:
            self._ui = {"FONTS": {"subtitle": ("Microsoft YaHei", 11, "bold")}, "PAD": {"sm": 8}, "colors": {}}

        hdr = tk.Frame(self, bg=self._ui["colors"].get("toolbar", "#252A33"), height=44)
        hdr.pack(fill=X)
        hdr.pack_propagate(False)
        tk.Label(
            hdr, text="🎵  音频工具箱", bg=hdr["bg"], fg="white",
            font=self._ui["FONTS"]["subtitle"],
        ).pack(side=LEFT, padx=self._ui["PAD"]["sm"])

        top = ttk.Frame(self, padding=8)
        top.pack(fill=X)
        ttk.Label(top, text="📁 素材文件夹:").pack(side=LEFT)
        ttk.Entry(top, textvariable=self.folder_var, width=48).pack(side=LEFT, padx=4, fill=X, expand=True)
        make_button(top, "浏览", self._pick_folder, kind="outline").pack(side=LEFT)
        make_button(top, "刷新", self._refresh_files, kind="outline").pack(side=LEFT, padx=4)

        tab_row = ttk.Frame(self, padding=(8, 0))
        tab_row.pack(fill=X)
        for name, icon in (
            ("提取音频", "📤"), ("替换音频", "🔁"), ("静音处理", "🔇"),
            ("音量调整", "🔊"), ("音频拼接", "🔗"),
        ):
            btn = make_button(
                tab_row, f"{icon} {name}",
                lambda n=name: self._select_func(n),
                kind="outline",
            )
            btn.pack(side=LEFT, padx=2, pady=4)
            self._func_buttons[name] = btn

        body = ttk.Frame(self, padding=8)
        body.pack(fill=BOTH, expand=True)

        fl_wrap = ttk.Frame(body)
        fl_wrap.pack(fill=BOTH, expand=True)
        fl_wrap.columnconfigure(0, weight=1)
        fl_wrap.rowconfigure(0, weight=1)
        self.file_list = tk.Listbox(fl_wrap, height=10, selectmode="extended", exportselection=False)
        self.file_list.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(fl_wrap, orient="vertical", command=self.file_list.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.file_list.configure(yscrollcommand=sb.set)

        self.panel = ttk.Frame(body, padding=8)
        self.panel.pack(fill=X, pady=8)
        self._panels: dict[str, ttk.Frame] = {}
        self._build_panels()

        out_row = ttk.Frame(body)
        out_row.pack(fill=X, pady=4)
        ttk.Label(out_row, text="输出目录:").pack(side=LEFT)
        ttk.Entry(out_row, textvariable=self.out_dir_var, width=40).pack(side=LEFT, padx=4, fill=X, expand=True)
        make_button(out_row, "浏览", self._pick_out_dir, kind="outline").pack(side=LEFT)

        make_button(body, "▶ 开始处理", self._run, kind="success").pack(anchor="e", pady=8)

        self.log_text = Text(body, height=6, font=("Consolas", 9))
        self.log_text.pack(fill=X)
        try:
            setup_log_tags(self.log_text)
        except Exception:
            pass

        self._select_func("提取音频")
        self._refresh_files()

    def _select_func(self, name: str) -> None:
        self.func_var.set(name)
        for n, btn in self._func_buttons.items():
            try:
                btn.configure(bootstyle="info" if n == name else "outline-secondary")
            except tk.TclError:
                pass
        self._show_panel()

    def _log(self, msg: str) -> None:
        self.log_text.insert(END, msg + "\n")
        self.log_text.see(END)
        if self.log_fn:
            self.log_fn(msg)

    def _pick_folder(self) -> None:
        p = filedialog.askdirectory()
        if p:
            self.folder_var.set(p)
            if not self.out_dir_var.get().strip():
                self.out_dir_var.set(p)
            self._refresh_files()

    def _pick_out_dir(self) -> None:
        p = filedialog.askdirectory()
        if p:
            self.out_dir_var.set(p)

    def _refresh_files(self) -> None:
        self.file_list.delete(0, END)
        folder = self.folder_var.get().strip()
        mode = self.func_var.get()
        if mode == "音频拼接":
            for f in sorted(
                x for x in os.listdir(folder) if os.path.isfile(os.path.join(folder, x)) and Path(x).suffix.lower() in AUDIO_EXTS
            ):
                self.file_list.insert(END, f)
        else:
            for f in list_media(folder):
                self.file_list.insert(END, f)

    def _build_panels(self) -> None:
        p1 = ttk.Frame(self.panel)
        ttk.Label(p1, text="输出格式:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(p1, textvariable=self.format_var, values=["mp3", "wav", "aac"], width=8, state="readonly").grid(row=0, column=1, sticky="w")
        ttk.Label(p1, text="码率:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(p1, textvariable=self.bitrate_var, values=["128k", "192k", "320k"], width=8, state="readonly").grid(row=1, column=1, sticky="w")
        ttk.Label(p1, text="采样率:").grid(row=2, column=0, sticky="w")
        ttk.Combobox(p1, textvariable=self.sample_var, values=["44100", "48000"], width=8, state="readonly").grid(row=2, column=1, sticky="w")
        ttk.Checkbutton(p1, text="保留原文件名（仅改扩展名）", variable=self.keep_name_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        self._panels["提取音频"] = p1

        p2 = ttk.Frame(self.panel)
        ttk.Label(p2, text="替换用音频文件:").grid(row=0, column=0, sticky="w")
        ttk.Entry(p2, textvariable=self.audio_replace_var, width=42).grid(row=0, column=1, padx=4)
        try:
            from modules.ui_skin import make_button
            make_button(p2, "选择", self._pick_replace_audio, kind="outline").grid(row=0, column=2)
        except Exception:
            ttk.Button(p2, text="选择", command=self._pick_replace_audio).grid(row=0, column=2)
        ttk.Label(p2, text="保留视频画面，用新音频替换原声", foreground="gray").grid(row=1, column=0, columnspan=3, sticky="w")
        self._panels["替换音频"] = p2

        p3 = ttk.Frame(self.panel)
        ttk.Label(p3, text="去除选中视频的全部音轨", foreground="gray").pack(anchor="w")
        self._panels["静音处理"] = p3

        p4 = ttk.Frame(self.panel)
        ttk.Label(p4, text="增益 (dB):").grid(row=0, column=0, sticky="w")
        ttk.Entry(p4, textvariable=self.gain_var, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(p4, text="-20 ~ +20", foreground="gray").grid(row=0, column=2, sticky="w", padx=8)
        self._panels["音量调整"] = p4

        p5 = ttk.Frame(self.panel)
        ttk.Label(p5, text="选择 ≥2 个音频文件（左侧列表可多选）", foreground="gray").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(p5, text="输出文件:").grid(row=1, column=0, sticky="w", pady=4)
        self.concat_out_var = StringVar()
        ttk.Entry(p5, textvariable=self.concat_out_var, width=42).grid(row=1, column=1, padx=4, sticky="w")
        try:
            from modules.ui_skin import make_button
            make_button(p5, "选择", self._pick_concat_out, kind="outline").grid(row=1, column=2, sticky="w")
        except Exception:
            ttk.Button(p5, text="选择", command=self._pick_concat_out).grid(row=1, column=2, sticky="w")
        ttk.Label(p5, text="说明：用 concat copy，要求输入编码一致；不一致可先转码为 mp3", foreground="gray").grid(
            row=2, column=0, columnspan=3, sticky="w"
        )
        self._panels["音频拼接"] = p5

    def _show_panel(self) -> None:
        for w in self.panel.winfo_children():
            if isinstance(w, ttk.Frame) and w not in self._panels.values():
                w.destroy()
        for p in self._panels.values():
            p.pack_forget()
        name = self.func_var.get()
        self._panels.get(name, self._panels["提取音频"]).pack(fill=X)
        self._refresh_files()

    def _pick_replace_audio(self) -> None:
        p = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.aac *.m4a")])
        if p:
            self.audio_replace_var.set(p)

    def _selected_files(self) -> list[str]:
        idxs = self.file_list.curselection()
        if idxs:
            return [self.file_list.get(i) for i in idxs]
        return [self.file_list.get(i) for i in range(self.file_list.size())]

    def _run(self) -> None:
        folder = self.folder_var.get().strip()
        out_dir = self.out_dir_var.get().strip() or folder
        files = self._selected_files()
        if not folder or not files:
            messagebox.showwarning("提示", "请选择文件夹并确保列表中有文件")
            return
        os.makedirs(out_dir, exist_ok=True)
        threading.Thread(target=self._work, args=(folder, out_dir, files), daemon=True).start()

    def _work(self, folder: str, out_dir: str, files: list[str]) -> None:
        mode = self.func_var.get()
        ok = fail = 0
        if mode == "音频拼接":
            try:
                self._concat(folder, out_dir, files)
                ok = 1
            except Exception as e:
                fail = 1
                self.after(0, lambda err=e: self._log(f"✗ 音频拼接: {err}"))
            try:
                from modules.tool_stats import OpType, log_operation
                if ok > 0:
                    log_operation(OpType.AUDIO_TOOLBOX, ok, mode)
            except Exception:
                pass
            self.after(0, lambda: messagebox.showinfo("完成", f"成功 {ok} 个，失败 {fail} 个", parent=self))
            return
        for fname in files:
            src = os.path.join(folder, fname)
            try:
                if mode == "提取音频":
                    self._extract(src, out_dir, fname)
                elif mode == "替换音频":
                    self._replace(src, out_dir, fname)
                elif mode == "静音处理":
                    self._mute(src, out_dir, fname)
                elif mode == "音量调整":
                    self._volume(src, out_dir, fname)
                ok += 1
                self.after(0, lambda f=fname: self._log(f"✓ {f}"))
            except Exception as e:
                fail += 1
                self.after(0, lambda f=fname, err=e: self._log(f"✗ {f}: {err}"))
        try:
            from modules.tool_stats import OpType, log_operation
            if ok > 0:
                log_operation(OpType.AUDIO_TOOLBOX, ok, mode)
        except Exception:
            pass
        self.after(0, lambda: messagebox.showinfo("完成", f"成功 {ok} 个，失败 {fail} 个", parent=self))

    def _out_path(self, fname: str, out_dir: str, ext: str) -> str:
        stem = Path(fname).stem if self.keep_name_var.get() else Path(fname).stem + "_out"
        return os.path.join(out_dir, stem + ext)

    def _run_ffmpeg(self, cmd: list[str]) -> None:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore",
                           **_hidden_kw())
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout or "FFmpeg 失败")[:300])

    def _pick_concat_out(self) -> None:
        p = filedialog.asksaveasfilename(defaultextension=".mp3", filetypes=[("音频", "*.mp3 *.wav *.aac")])
        if p:
            self.concat_out_var.set(p)

    def _concat(self, folder: str, out_dir: str, files: list[str]) -> None:
        if len(files) < 2:
            raise RuntimeError("请至少选择 2 个音频文件")
        out = self.concat_out_var.get().strip()
        if not out:
            raise RuntimeError("请选择输出文件")
        # concat demuxer list
        list_file = os.path.join(os.path.dirname(out), "_concat_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for fname in files:
                p = os.path.join(folder, fname)
                safe = p.replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe}'\n")
        try:
            self._run_ffmpeg([self.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", out])
        finally:
            try:
                os.remove(list_file)
            except OSError:
                pass

    def _extract(self, src: str, out_dir: str, fname: str) -> None:
        fmt = self.format_var.get().lower()
        ext = f".{fmt}"
        out = self._out_path(fname, out_dir, ext)
        cmd = [self.ffmpeg, "-y", "-i", src, "-vn", "-ar", self.sample_var.get()]
        if fmt in ("mp3", "aac"):
            cmd.extend(["-b:a", self.bitrate_var.get()])
        cmd.append(out)
        self._run_ffmpeg(cmd)

    def _replace(self, src: str, out_dir: str, fname: str) -> None:
        audio = self.audio_replace_var.get().strip()
        if not audio or not os.path.isfile(audio):
            raise RuntimeError("请选择替换用音频文件")
        out = self._out_path(fname, out_dir, Path(fname).suffix or ".mp4")
        cmd = [
            self.ffmpeg, "-y", "-i", src, "-i", audio,
            "-map", "0:v:0", "-map", "1:a:0", "-shortest",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", out,
        ]
        self._run_ffmpeg(cmd)

    def _mute(self, src: str, out_dir: str, fname: str) -> None:
        out = self._out_path(fname, out_dir, Path(fname).suffix or ".mp4")
        cmd = [self.ffmpeg, "-y", "-i", src, "-an", "-c:v", "copy", out]
        self._run_ffmpeg(cmd)

    def _volume(self, src: str, out_dir: str, fname: str) -> None:
        gain = float(self.gain_var.get() or 0)
        out = self._out_path(fname, out_dir, Path(fname).suffix or ".mp4")
        cmd = [
            self.ffmpeg, "-y", "-i", src,
            "-af", f"volume={gain}dB",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", out,
        ]
        self._run_ffmpeg(cmd)


def open_audio_toolbox(parent, *, ffmpeg: str, ffprobe: str, log_fn=None, initial_folder: str = "") -> AudioToolboxWindow:
    win = AudioToolboxWindow(parent, ffmpeg=ffmpeg, ffprobe=ffprobe, log_fn=log_fn, initial_folder=initial_folder)
    win.transient(parent)
    return win
