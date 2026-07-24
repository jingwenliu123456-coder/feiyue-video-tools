"""批量裂变独立页：列表 + 思维导图（天然展开 / 细节设置 / 引用模板）。"""

from __future__ import annotations

import copy
import os
import tkinter as tk
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, BooleanVar, StringVar, filedialog, messagebox, ttk
from typing import Any, Callable, Optional

from modules.fission_engine import (
    FissionBranch,
    FissionSourceGroup,
    MAX_SOURCE_GROUPS,
    bind_fission_io_paths,
    list_template_names,
    new_group_id,
    sanitize_branch_name,
    source_group_from_dict,
    source_group_to_dict,
)
from modules.ui_skin import make_button

# ---------- 四套主题（方案色偏柔和，少荧光） ----------
_THEMES: dict[str, dict[str, Any]] = {
    "cream": {
        "label": "奶油可爱",
        "bg": "#FFF9F5", "card": "#FFFFFF", "border": "#F0D9CC",
        "text": "#5C4B51", "muted": "#9B8B8F", "center": "#E8A0AE", "check": "#7BAE7F",
        "line": "#E8D0C4", "scheme_fill": True,
        "scheme": ["#B8D4C8", "#B4C9DC", "#C9B8D0", "#E8CDB0", "#E0B4B4", "#C5D4E0", "#DCC4CE"],
        "folder": ["#E0B4B4", "#E8CDB0", "#B8D4C8", "#B4C9DC", "#C9B8D0", "#DCC4CE"],
    },
    "blue": {
        "label": "经典蓝白",
        "bg": "#F0F4F8", "card": "#FFFFFF", "border": "#D0DCEC",
        "text": "#1E3A5F", "muted": "#64748B", "center": "#5B8FC7", "check": "#5A9A6A",
        "line": "#B8CCE0", "scheme_fill": True,
        "scheme": ["#7BA3C9", "#8B9BC7", "#9B8FBF", "#C99BB0", "#C9A07A", "#7BB0C4", "#7BAE8A"],
        "folder": ["#7BA3C9", "#8B9BC7", "#C99BB0", "#C9A07A", "#7BAE8A", "#9B8FBF"],
    },
    "dark": {
        "label": "黑紫赛博",
        "bg": "#0A0A0F", "card": "#12121A", "border": "#2D2D44",
        "text": "#E8E8F0", "muted": "#9CA3AF", "center": "#8B6BB5", "check": "#5A9A6A",
        "line": "#4A4A60", "scheme_fill": False,
        "scheme": ["#8B6BB5", "#6B7AB5", "#B56B8F", "#7A6BB5", "#5B9AAA", "#B59A5B", "#5BAAA0"],
        "folder": ["#B58A5B", "#B56B6B", "#5BAAA0", "#B5A55B", "#6B8AB5", "#8B6BB5"],
    },
    "green": {
        "label": "绿黄养眼",
        "bg": "#F5F7F0", "card": "#FFFFFF", "border": "#D2DEC4",
        "text": "#3A4A32", "muted": "#6E7A62", "center": "#7FA86A", "check": "#6B9A5A",
        "line": "#C5D4B0", "scheme_fill": True,
        "scheme": ["#9CB88A", "#C4B67A", "#8AAD7E", "#C9B06A", "#7AAD8E", "#A8C090", "#B8A86A"],
        "folder": ["#9CB88A", "#C4B67A", "#8AAD7E", "#C9B06A", "#7AAD8E", "#A8C090"],
    },
}


def _basename(p: Any) -> str:
    s = str(p or "").strip()
    return Path(s).name if s else ""


def _detail_cut(cfg: dict) -> str:
    mode = cfg.get("cut_range_mode") or "固定时段"
    if mode == "末尾N秒":
        return f"末尾{cfg.get('cut_tail_sec', '5')}秒 · {cfg.get('cut_mode', '保留')}"
    return f"{cfg.get('cut_mode', '保留')} {cfg.get('cut_start', '')}-{cfg.get('cut_end', '')}"


def _detail_ratio(cfg: dict) -> str:
    return f"比例:{cfg.get('ratio_target', '9:16')}"


def _detail_enhance(cfg: dict) -> str:
    return str(cfg.get("enhance_mode") or "锐化降噪")


def _detail_png(cfg: dict) -> str:
    pos = cfg.get("png_wm_position") or cfg.get("png_wm_mode") or ""
    name = _basename(cfg.get("png_wm_path"))
    return " · ".join(x for x in (name, str(pos)) if x) or "未设水印"


def _detail_mov(cfg: dict) -> str:
    mode = "全屏" if cfg.get("mov_watermark_mode") == "fullscreen" else "自定义"
    return " · ".join(x for x in (_basename(cfg.get("mov_watermark_path")), mode) if x) or "未设MOV"


def _detail_logo(cfg: dict) -> str:
    return " · ".join(
        x for x in (_basename(cfg.get("logo_path")), str(cfg.get("logo_position") or "")) if x
    ) or "未设落版"


def _detail_ending(cfg: dict) -> str:
    name = _basename(cfg.get("ending_file")) or "未选落版视频"
    bits = [name]
    if cfg.get("ending_keep_audio"):
        bits.append("保留落版音频")
    trim = str(cfg.get("ending_concat_trim") or "0").strip()
    if trim and trim not in ("0", "0.0"):
        bits.append(f"截取前{trim}s")
    return " · ".join(bits)


def _detail_overlay(cfg: dict) -> str:
    st = cfg.get("overlay_state")
    return "已配置叠加" if isinstance(st, dict) and st else "未配置"


# 与批处理流水线一致（无「替换音频」）；顺序默认 = 批处理默认
# (enable_key, label, feature_jump_key, detail_fn)
_FUNC_DEFS: list[tuple[str, str, str, Callable[[dict], str]]] = [
    ("cut_enable", "视频裁切", "cut", _detail_cut),
    ("enhance_enable", "画质增强", "enhance", _detail_enhance),
    ("ratio_enable", "比例适配", "ratio", _detail_ratio),
    ("enable_mov_watermark", "动态水印", "mov_wm", _detail_mov),
    ("png_wm_enable", "静态水印", "png_wm", _detail_png),
    ("logo_enable", "浮层落版", "layer", _detail_logo),
    ("ending_enable", "拼接落版", "ending", _detail_ending),
    ("overlay_enable", "可视化叠加", "overlay", _detail_overlay),
]
_FUNC_BY_KEY = {k: (k, lab, jump, df) for k, lab, jump, df in _FUNC_DEFS}
_ORDER_KEY = "_fission_func_order"


class FissionMindmapPanel:
    """嵌入 Notebook 的裂变页。"""

    def __init__(self, parent: tk.Misc, app: Any) -> None:
        self.app = app
        self.root = app.root
        self._selected_idx: Optional[int] = None
        self._hover_idx: Optional[int] = None
        self._progress: dict[str, tuple[float, str]] = {}
        self._view = StringVar(value="mindmap")
        self._theme_key = StringVar(value=_THEMES["cream"]["label"])
        self._layout_mode = StringVar(value="思维导图")  # 思维导图 | 地铁线路
        self._io_mode = StringVar(value="单源")  # 单源 | 多源 —— 两套界面分开
        self._folders: list[str] = []
        self._hit_regions: list[tuple[Any, ...]] = []
        self._add_popup: Optional[tk.Toplevel] = None
        self._drag: Optional[dict[str, Any]] = None
        self.th = _THEMES["cream"]

        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=BOTH, expand=True)

        top = ttk.Frame(self.frame)
        top.pack(fill=X, padx=12, pady=8)
        self._title_lbl = ttk.Label(top, text="批量裂变 · 单源多分支", font=("Microsoft YaHei", 12, "bold"))
        self._title_lbl.pack(side=LEFT)

        # 模式切换：单源 / 多源（核心交互，置顶显眼）
        mode_bar = ttk.Frame(top)
        mode_bar.pack(side=LEFT, padx=(16, 0))
        ttk.Radiobutton(
            mode_bar, text="单源", value="单源", variable=self._io_mode,
            command=self._on_io_mode_change,
        ).pack(side=LEFT, padx=2)
        ttk.Radiobutton(
            mode_bar, text="多源", value="多源", variable=self._io_mode,
            command=self._on_io_mode_change,
        ).pack(side=LEFT, padx=2)

        make_button(top, "思维导图", lambda: self._switch("mindmap"), kind="info", width=8).pack(side=RIGHT, padx=2)
        make_button(top, "列表", lambda: self._switch("list"), kind="outline", width=6).pack(side=RIGHT, padx=2)

        ttk.Label(top, text="布局").pack(side=RIGHT, padx=(8, 2))
        layout = ttk.Combobox(
            top, textvariable=self._layout_mode, width=10, state="readonly",
            values=["思维导图", "地铁线路"],
        )
        layout.pack(side=RIGHT)
        layout.bind("<<ComboboxSelected>>", lambda _e: self._on_layout_change())

        ttk.Label(top, text="皮肤").pack(side=RIGHT, padx=(8, 2))
        skin = ttk.Combobox(
            top, textvariable=self._theme_key, width=12, state="readonly",
            values=[_THEMES[k]["label"] for k in _THEMES],
        )
        skin.pack(side=RIGHT)
        skin.bind("<<ComboboxSelected>>", lambda _e: self._on_skin_selected())

        self._tip = ttk.Label(
            self.frame,
            text="单源：左边选文件夹 → 画布加方案 → 右边选输出根 → 开始",
            foreground="gray",
        )
        self._tip.pack(anchor="w", padx=12)

        # 单源：可选预处理条（旧交互）
        self._pp_host = ttk.Frame(self.frame)
        self._pp_host.pack(fill=X, padx=8, pady=(4, 0))
        self._build_single_preprocess_strip(self._pp_host)

        # 多源：源素材组列表（与单源分开，默认隐藏）
        self._sg_host = ttk.Frame(self.frame)
        self._sg_cards: list[dict] = []
        self._sg_expanded: dict[str, bool] = {}
        self._build_source_groups_panel(self._sg_host)

        self._body = ttk.Frame(self.frame)
        self._body.pack(fill=BOTH, expand=True, padx=8, pady=8)
        self._list_frame = ttk.Frame(self._body)
        self._map_frame = ttk.Frame(self._body)

        self._build_list_view(self._list_frame)
        self._build_map_view(self._map_frame)
        self._sync_folders_from_app()
        self._rebuild_folder_list()
        self._apply_theme()
        self._switch("mindmap")
        self._apply_io_mode_ui()

        self.root.bind("<Control-n>", self._on_ctrl_n, add="+")
        self.root.bind("<Control-N>", self._on_ctrl_n, add="+")

    def apply_memory_prefs(self, pref: dict) -> None:
        """应用全局记忆：主题 / 视图 / 布局。"""
        if not isinstance(pref, dict):
            return
        theme_label = str(pref.get("default_theme") or "").strip()
        if theme_label:
            labels = [_THEMES[k]["label"] for k in _THEMES]
            if theme_label in labels:
                self._theme_key.set(theme_label)
                self._apply_theme()
        view = str(pref.get("default_view") or "").strip()
        io = str(pref.get("fission_io_mode") or "").strip()
        if io in ("单源", "多源"):
            self._io_mode.set(io)
            self._apply_io_mode_ui()
        # 单源预处理条
        if hasattr(self, "_pp_enable"):
            try:
                self._pp_enable.set(bool(pref.get("fission_preprocess_enable")))
                tpl = str(pref.get("fission_preprocess_template") or "").strip()
                if tpl:
                    self._pp_template.set(tpl)
                mode = str(pref.get("fission_preprocess_temp_mode") or "自动清理").strip()
                if mode:
                    self._pp_temp_mode.set(mode)
                self._pp_temp_path.set(str(pref.get("fission_preprocess_temp_path") or ""))
                self._refresh_pp_templates()
                self._on_pp_toggle()
            except Exception:
                pass
        if view == "列表":
            self._switch("list")
            return
        if view in ("思维导图", "地铁线路"):
            self._layout_mode.set(view)
            self._switch("mindmap")
            self._on_layout_change()
        elif view:
            self._switch("mindmap")
        try:
            if self._io_mode.get() == "多源" and hasattr(self, "_rebuild_source_group_cards"):
                self._rebuild_source_group_cards()
        except Exception:
            pass

    def _on_skin_selected(self) -> None:
        self._apply_theme()
        try:
            from modules import habi_memory
            habi_memory.update_prefs(default_theme=self._theme_key.get())
        except Exception:
            pass

    def ensure_scheme_from_template(self, template_name: str) -> bool:
        """快速启动：若画布尚无该模板方案，则挂上一条（不重复添加）。"""
        name = (template_name or "").strip()
        if not name:
            return False
        plan = getattr(self.app, "_fission_plan", None)
        if plan is None:
            return False
        for i, b in enumerate(plan.branches):
            if (b.template_name or "").strip() == name or (b.branch_name or "").strip() == sanitize_branch_name(name):
                self._select_branch(i)
                self.redraw()
                return True
        self._quick_add_from_template(name)
        return True

    def _apply_theme(self) -> None:
        label = self._theme_key.get()
        key = next((k for k, v in _THEMES.items() if v["label"] == label), "cream")
        self.th = _THEMES[key]
        th = self.th
        if hasattr(self, "canvas"):
            self.canvas.configure(bg=th["bg"])
        if hasattr(self, "_drop_lbl"):
            self._drop_lbl.configure(bg=th["card"], fg=th["muted"])
        for attr, kw in (
            ("_right_outer", {"bg": th["bg"]}),
            ("_right_title", {"bg": th["bg"], "fg": th["text"]}),
            ("_right_sub", {"bg": th["bg"], "fg": th["muted"]}),
            ("_out_box", {"bg": th["bg"]}),
            ("_out_hint", {"bg": th["bg"], "fg": th["muted"]}),
            ("_out_sec_title", {"bg": th["bg"], "fg": th["text"]}),
            ("_out_host", {"bg": th["bg"]}),
            ("_out_entry", {"bg": th["card"], "fg": th["text"], "insertbackground": th["text"]}),
        ):
            w = getattr(self, attr, None)
            if w is not None:
                try:
                    w.configure(**kw)
                except Exception:
                    pass
        self._rebuild_folder_list()
        if self._view.get() == "mindmap":
            if self._layout_mode.get() == "地铁线路":
                self._rebuild_func_lib()
            self.redraw()

    def _switch(self, mode: str) -> None:
        self._view.set(mode)
        self._list_frame.pack_forget()
        self._map_frame.pack_forget()
        if mode == "list":
            self._list_frame.pack(fill=BOTH, expand=True)
            self.app._fission_refresh_tree()
        else:
            self._map_frame.pack(fill=BOTH, expand=True)
            self.redraw()

    def _build_list_view(self, parent: ttk.Frame) -> None:
        host = ttk.Frame(parent)
        host.pack(fill=BOTH, expand=True)
        old = self.app.main_frame
        try:
            self.app.main_frame = host
            self.app.build_fission_section(0)
        finally:
            self.app.main_frame = old

    def _build_map_view(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        paned = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew")

        left = ttk.Frame(paned, width=220)
        self._left_pane = left
        self._map_paned = paned
        mid = ttk.Frame(paned)
        self._right_outer = tk.Frame(paned, width=220, bg=self.th["bg"])
        paned.add(left, weight=1)
        paned.add(mid, weight=4)
        paned.add(self._right_outer, weight=1)
        try:
            # 防止中间区（尤其地铁双栏）把右栏挤没
            self.root.after(120, lambda: paned.sashpos(1, max(paned.winfo_width() - 230, 400)))
        except Exception:
            pass

        ttk.Label(left, text="输入文件夹", font=("Microsoft YaHei", 10, "bold")).pack(anchor="w", padx=8, pady=(8, 4))
        ttk.Label(left, text="主文件夹排最上 · ▲▼ 排序", foreground="gray", font=("", 8)).pack(anchor="w", padx=8)
        self._folder_host = ttk.Frame(left)
        self._folder_host.pack(fill=BOTH, expand=True, padx=6, pady=6)
        make_button(left, "＋ 添加文件夹", self._add_folder, kind="outline").pack(fill=X, padx=8, pady=(0, 4))
        drop = tk.Label(left, text="或拖入文件夹 / 点击添加", bg=self.th["card"], fg=self.th["muted"], relief="groove", bd=1, pady=10)
        drop.pack(fill=X, padx=8, pady=(0, 8))
        drop.bind("<Button-1>", lambda _e: self._add_folder())
        self._drop_lbl = drop
        self._hook_folder_drop(drop)
        self._hook_folder_drop(self._folder_host)

        # 中间：地铁模式时 = 功能库 | 线路画布
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)
        self._mid_split = ttk.Panedwindow(mid, orient=tk.HORIZONTAL)
        self._mid_split.pack(fill=BOTH, expand=True)

        self._func_lib_shell = tk.Frame(self._mid_split, width=145, bg=self.th["card"])
        try:
            self._func_lib_shell.pack_propagate(False)
        except Exception:
            pass
        self._func_lib_title = tk.Label(
            self._func_lib_shell, text="功能库", bg=self.th["card"], fg=self.th["muted"],
            font=("Microsoft YaHei", 10, "bold"),
        )
        self._func_lib_title.pack(anchor="w", padx=10, pady=(10, 2))
        self._func_lib_scheme = tk.Label(
            self._func_lib_shell, text="（选中方案后显示）", bg=self.th["card"], fg=self.th["muted"], font=("", 8),
        )
        self._func_lib_scheme.pack(anchor="w", padx=10)
        self._func_lib_host = tk.Frame(self._func_lib_shell, bg=self.th["card"])
        self._func_lib_host.pack(fill=BOTH, expand=True, padx=6, pady=6)

        canvas_wrap = ttk.Frame(self._mid_split)
        self.canvas = tk.Canvas(canvas_wrap, bg=self.th["bg"], highlightthickness=0)
        ysb = ttk.Scrollbar(canvas_wrap, orient="vertical", command=self.canvas.yview)
        xsb = ttk.Scrollbar(canvas_wrap, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        canvas_wrap.rowconfigure(0, weight=1)
        canvas_wrap.columnconfigure(0, weight=1)
        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self._on_canvas_dbl)
        self.canvas.bind("<Button-3>", self._on_canvas_right)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Leave>", lambda _e: self._hide_tooltip())
        self.canvas.bind("<MouseWheel>", self._on_wheel)

        self._mid_split.add(canvas_wrap, weight=3)
        self._canvas_wrap = canvas_wrap
        self._tooltip: Optional[tk.Toplevel] = None
        self._tooltip_text = ""
        # 注意：此时右栏尚未创建，勿在这里 redraw（会打断后续输出栏构建）

        right = self._right_outer
        # 右栏用 tk 控件，深色皮肤时不割裂
        self._right_title = tk.Label(
            right, text="输出（全局根）", bg=self.th["bg"], fg=self.th["text"],
            font=("Microsoft YaHei", 10, "bold"),
        )
        self._right_title.pack(anchor="w", padx=8, pady=(8, 2))
        self._right_sub = tk.Label(
            right, text="选一个总文件夹；每个方案自动建子目录",
            bg=self.th["bg"], fg=self.th["muted"], font=("", 8), wraplength=180, justify="left",
        )
        self._right_sub.pack(anchor="w", padx=8)

        out_box = tk.Frame(right, bg=self.th["bg"])
        out_box.pack(fill=X, padx=8, pady=4)
        self._out_box = out_box
        self._out_root_var = self.app.global_output_folder
        self._out_entry = tk.Entry(
            out_box, textvariable=self._out_root_var, bg=self.th["card"], fg=self.th["text"],
            insertbackground=self.th["text"], relief="solid", bd=1,
        )
        self._out_entry.pack(fill=X, pady=(0, 4))
        row = tk.Frame(out_box, bg=self.th["bg"])
        row.pack(fill=X)
        make_button(row, "选择…", self._pick_output_root, kind="outline", width=7).pack(side=LEFT)
        make_button(row, "打开", self.app.open_global_output, kind="outline", width=5).pack(side=LEFT, padx=4)
        self._out_hint = tk.Label(out_box, text="", bg=self.th["bg"], fg=self.th["muted"], font=("", 8), wraplength=180, justify="left")
        self._out_hint.pack(anchor="w", pady=(4, 0))
        self._refresh_out_root_hint()

        self._out_sec_title = tk.Label(
            right, text="各方案输出", bg=self.th["bg"], fg=self.th["text"],
            font=("Microsoft YaHei", 9, "bold"),
        )
        self._out_sec_title.pack(anchor="w", padx=8, pady=(10, 2))
        self._out_host = tk.Frame(right, bg=self.th["bg"])
        self._out_host.pack(fill=BOTH, expand=True, padx=6)

        # 右栏就绪后再切布局 / 首次绘制
        self._on_layout_change()

        bar = ttk.Frame(parent)
        bar.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        make_button(bar, "应用方案", self._apply_selected, kind="info").pack(side=LEFT, padx=4)
        make_button(bar, "新建方案", self._create_new_scheme, kind="outline").pack(side=LEFT, padx=4)
        make_button(bar, "编辑方案", self._edit_selected, kind="outline").pack(side=LEFT, padx=4)
        # 右下角：开始处理在「打开规范命名」左边（pack RIGHT 先放的在最右）
        make_button(bar, "打开规范命名", self._open_naming_for_output, kind="outline").pack(side=RIGHT, padx=4)
        make_button(bar, "开始处理", self.app.start_fission, kind="success").pack(side=RIGHT, padx=4)

    # ----- 单源 / 多源 模式 -----

    def _on_io_mode_change(self) -> None:
        self._apply_io_mode_ui()
        try:
            from modules import habi_memory
            habi_memory.update_prefs(fission_io_mode=self._io_mode.get())
        except Exception:
            pass

    def _apply_io_mode_ui(self) -> None:
        multi = self._io_mode.get() == "多源"
        if hasattr(self, "_title_lbl"):
            self._title_lbl.config(
                text="批量裂变 · 多源多分支" if multi else "批量裂变 · 单源多分支",
            )
        if hasattr(self, "_tip"):
            self._tip.config(
                text=(
                    "多源：上方每组各自选输入/预处理/方案；中间画布只当方案库"
                    if multi else
                    "单源：左文件夹 →（可选预处理成品）→ 画布多方案 → 右输出根"
                ),
            )
        # 单源预处理条 / 多源组列表互斥显示
        try:
            self._pp_host.pack_forget()
        except Exception:
            pass
        try:
            self._sg_host.pack_forget()
        except Exception:
            pass
        if multi:
            self._sg_host.pack(fill=X, padx=8, pady=(4, 0), before=self._body)
            try:
                self._rebuild_source_group_cards()
            except Exception:
                pass
        else:
            self._pp_host.pack(fill=X, padx=8, pady=(4, 0), before=self._body)

        # 多源时隐藏左侧「输入文件夹」（避免和源组重复）
        paned = getattr(self, "_map_paned", None)
        left = getattr(self, "_left_pane", None)
        if paned is not None and left is not None:
            try:
                panes = list(paned.panes())
            except Exception:
                panes = []
            if multi:
                if str(left) in [str(p) for p in panes]:
                    try:
                        paned.forget(left)
                    except Exception:
                        pass
            else:
                if str(left) not in [str(p) for p in panes]:
                    try:
                        # 插回最左侧
                        paned.insert(0, left, weight=1)
                    except Exception:
                        try:
                            paned.add(left, weight=1)
                        except Exception:
                            pass

    def _build_single_preprocess_strip(self, parent: ttk.Frame) -> None:
        """单源：可选「素材 → 预处理成品目录 → 再裂变到各方案」。"""
        wrap = ttk.LabelFrame(parent, text="单源 · 可选预处理（勾选后 = 单源→预处理→多方案）", padding=6)
        wrap.pack(fill=X)
        self._pp_enable = tk.BooleanVar(value=False)
        self._pp_template = StringVar(value="")
        # 默认「保留」：预处理成品目录可见，方便检查
        self._pp_temp_mode = StringVar(value="保留")
        self._pp_temp_path = StringVar(value="")
        self._pp_path_hint = StringVar(value="")

        row = ttk.Frame(wrap)
        row.pack(fill=X)
        ttk.Checkbutton(
            row, text="启用预处理",
            variable=self._pp_enable, command=self._on_pp_toggle,
        ).pack(side=LEFT)
        ttk.Label(row, text="模板").pack(side=LEFT, padx=(8, 2))
        self._pp_tpl_cb = ttk.Combobox(row, textvariable=self._pp_template, width=22, state="disabled")
        self._pp_tpl_cb.pack(side=LEFT, padx=2)
        self._pp_tpl_cb.bind("<<ComboboxSelected>>", lambda _e: self._on_pp_toggle())
        ttk.Label(row, text="成品目录").pack(side=LEFT, padx=(8, 2))
        self._pp_mode_cb = ttk.Combobox(
            row, textvariable=self._pp_temp_mode, width=10, state="disabled",
            values=["保留", "指定路径", "自动清理"],
        )
        self._pp_mode_cb.pack(side=LEFT, padx=2)
        self._pp_mode_cb.bind("<<ComboboxSelected>>", lambda _e: self._on_pp_toggle())
        self._pp_path_ent = ttk.Entry(row, textvariable=self._pp_temp_path, width=22, state="disabled")
        self._pp_path_ent.pack(side=LEFT, padx=2)
        self._pp_browse_btn = make_button(row, "浏览", self._browse_pp_temp, kind="outline", width=5)
        self._pp_browse_btn.pack(side=LEFT, padx=2)

        ttk.Label(
            wrap, textvariable=self._pp_path_hint,
            foreground="gray", font=("", 8),
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            wrap,
            text="流程：左栏输入夹 → 预处理写出成品 → 画布各方案再读这些成品 → 输出到右栏「输出根/方案名/」。"
                 "不勾选则跳过预处理，素材直接进各方案。",
            foreground="gray", font=("", 8), wraplength=900,
        ).pack(anchor="w", pady=(2, 0))
        self._refresh_pp_templates()
        self._on_pp_toggle()

    def _refresh_pp_templates(self) -> None:
        names = self._tpl_names()
        try:
            self._pp_tpl_cb["values"] = names
            if self._pp_template.get() and self._pp_template.get() not in names and names:
                pass
            elif not self._pp_template.get() and names:
                self._pp_template.set(names[0])
        except Exception:
            pass

    def _pp_default_product_dir(self) -> str:
        out = (self.app.global_output_folder.get() or "").strip()
        tpl = sanitize_branch_name((self._pp_template.get() or "").strip()) or "预处理模板"
        if not out:
            return f"（先在右侧选输出根，成品 → 输出根/_预处理_{tpl}）"
        return str(Path(out) / f"_预处理_{tpl}")

    def _on_pp_toggle(self) -> None:
        on = bool(self._pp_enable.get())
        st = "readonly" if on else "disabled"
        try:
            self._pp_tpl_cb.configure(state=st)
            self._pp_mode_cb.configure(state=st)
            path_on = on and self._pp_temp_mode.get() == "指定路径"
            self._pp_path_ent.configure(state="normal" if path_on else "disabled")
        except Exception:
            pass
        mode = (self._pp_temp_mode.get() or "保留").strip()
        if not on:
            self._pp_path_hint.set("未启用预处理：素材直接进入画布上的各方案。")
        elif mode == "指定路径":
            p = (self._pp_temp_path.get() or "").strip() or "（请点浏览选择成品文件夹）"
            self._pp_path_hint.set(f"预处理成品目录：{p}  →  各方案将以此为输入")
        elif mode == "自动清理":
            self._pp_path_hint.set(
                f"预处理成品目录：{self._pp_default_product_dir()}  （跑完各方案后自动删除）"
            )
        else:
            self._pp_path_hint.set(
                f"预处理成品目录：{self._pp_default_product_dir()}  （保留，方便你检查）"
            )

    def _browse_pp_temp(self) -> None:
        p = filedialog.askdirectory(parent=self.root, title="选择预处理成品文件夹")
        if p:
            self._pp_temp_path.set(p)
            self._pp_temp_mode.set("指定路径")
            self._on_pp_toggle()

    def _build_source_groups_panel(self, parent: ttk.Frame) -> None:
        """多源专用：可滚动 + 每组可折叠的一列列表。"""
        wrap = ttk.LabelFrame(
            parent,
            text="多源素材组（点 ▶ 展开设置 · 设完可收起）",
            padding=6,
        )
        wrap.pack(fill=X)
        self._sg_wrap = wrap
        self._sg_expanded: dict[str, bool] = getattr(self, "_sg_expanded", {}) or {}

        head = ttk.Frame(wrap)
        head.pack(fill=X)
        ttk.Label(
            head,
            text="一列列表 · 滚轮可滚动 · 箭头收起/展开",
            foreground="gray", font=("", 8),
        ).pack(side=LEFT)
        make_button(head, "全部收起", self._collapse_all_source_groups, kind="outline", width=8).pack(side=RIGHT, padx=2)
        make_button(head, "＋ 添加源组", self._add_source_group, kind="outline", width=10).pack(side=RIGHT)

        # 固定可视高度 + 滚动条（之前滚不动是没绑滚轮）
        list_shell = ttk.Frame(wrap)
        list_shell.pack(fill=X, pady=(6, 0))
        canvas = tk.Canvas(list_shell, height=150, highlightthickness=0)
        vsb = ttk.Scrollbar(list_shell, orient="vertical", command=canvas.yview)
        self._sg_inner = ttk.Frame(canvas)
        self._sg_canvas = canvas
        self._sg_canvas_win = canvas.create_window((0, 0), window=self._sg_inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side=LEFT, fill=X, expand=True)
        vsb.pack(side=RIGHT, fill=Y)

        def _sync_scroll(_e=None):
            canvas.update_idletasks()
            bbox = canvas.bbox("all")
            if bbox:
                canvas.configure(scrollregion=bbox)
            try:
                canvas.itemconfig(self._sg_canvas_win, width=max(canvas.winfo_width(), 1))
            except Exception:
                pass

        self._sg_inner.bind("<Configure>", _sync_scroll)
        canvas.bind("<Configure>", _sync_scroll)

        def _on_mousewheel(event):
            # Windows: event.delta 通常是 ±120
            try:
                if event.delta:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                elif getattr(event, "num", None) == 4:
                    canvas.yview_scroll(-1, "units")
                elif getattr(event, "num", None) == 5:
                    canvas.yview_scroll(1, "units")
            except Exception:
                pass
            return "break"

        def _bind_wheel(_e=None):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", _on_mousewheel)
            canvas.bind_all("<Button-5>", _on_mousewheel)

        def _unbind_wheel(_e=None):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)
        self._sg_inner.bind("<Enter>", _bind_wheel)
        self._sg_sync_scroll = _sync_scroll

        self._sg_cards = []
        self._ensure_default_source_groups()
        self._rebuild_source_group_cards()

    def _collapse_all_source_groups(self) -> None:
        self.sync_groups_to_plan()
        plan = getattr(self.app, "_fission_plan", None)
        if plan is None:
            return
        for g in plan.source_groups:
            gid = g.group_id or ""
            if gid:
                self._sg_expanded[gid] = False
        self._rebuild_source_group_cards()

    def _toggle_source_group_expand(self, group_id: str) -> None:
        self.sync_groups_to_plan()
        gid = group_id or ""
        cur = bool(self._sg_expanded.get(gid, False))
        self._sg_expanded[gid] = not cur
        self._rebuild_source_group_cards()

    def _tpl_names(self) -> list[str]:
        try:
            import video_batch_tool_v20 as v20
            return list_template_names(v20._templates_dir())
        except Exception:
            return []

    def _ensure_default_source_groups(self) -> None:
        plan = getattr(self.app, "_fission_plan", None)
        if plan is None:
            return
        if plan.source_groups:
            return
        from modules import habi_memory
        pref = habi_memory.prefs()
        in_dir = (self.app.global_input_folder.get() or "").strip()
        out_dir = (self.app.global_output_folder.get() or "").strip()
        if self._folders:
            in_dir = self._folders[0] or in_dir
        g = FissionSourceGroup(
            group_id=new_group_id(),
            enabled=True,
            title="源组1",
            input_folder=in_dir,
            output_folder=out_dir,
            preprocess_enable=bool(pref.get("fission_preprocess_enable")),
            preprocess_template=str(pref.get("fission_preprocess_template") or ""),
            preprocess_temp_mode=str(pref.get("fission_preprocess_temp_mode") or "自动清理"),
            preprocess_temp_path=str(pref.get("fission_preprocess_temp_path") or ""),
            selected_branch_names=[],
        )
        plan.source_groups = [g]
        self._sg_expanded[g.group_id] = True

    def _rebuild_source_group_cards(self) -> None:
        inner = getattr(self, "_sg_inner", None)
        if inner is None:
            return
        for child in list(inner.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self._sg_cards = []
        plan = getattr(self.app, "_fission_plan", None)
        groups = list(plan.source_groups) if plan is not None else []
        if not groups:
            ttk.Label(inner, text="还没有源组，点右上角「添加源组」。", foreground="gray").pack(anchor="w")
            return
        branch_names = [b.branch_name for b in self._branch_list()]
        tpls = self._tpl_names()
        # 若都没展开过，默认展开第一组
        if not any(self._sg_expanded.get(g.group_id, False) for g in groups if g.group_id):
            if groups[0].group_id:
                self._sg_expanded[groups[0].group_id] = True
        for i, g in enumerate(groups):
            self._sg_cards.append(self._make_source_group_card(i, g, branch_names, tpls))
        try:
            self.root.after_idle(getattr(self, "_sg_sync_scroll", lambda: None))
        except Exception:
            pass
        try:
            self._sg_canvas.configure(scrollregion=self._sg_canvas.bbox("all"))
        except Exception:
            pass

    def _sg_summary_text(
        self,
        *,
        in_path: str,
        pp_on: bool,
        pp_tpl: str,
        branch_vars: dict,
    ) -> str:
        folder = Path(in_path).name if in_path else "未选输入"
        if pp_on and pp_tpl:
            pp = f"预处理:{pp_tpl}"
        elif pp_on:
            pp = "预处理:未选模板"
        else:
            pp = "无预处理"
        if not branch_vars:
            sch = "方案:全部"
        else:
            n = sum(1 for v in branch_vars.values() if bool(v.get()))
            sch = f"方案:{n}/{len(branch_vars)}"
        return f"{folder}  ·  {pp}  ·  {sch}"

    def _make_source_group_card(
        self, idx: int, g: FissionSourceGroup, branch_names: list[str], tpls: list[str],
    ) -> dict:
        gid = g.group_id or new_group_id()
        expanded = bool(self._sg_expanded.get(gid, False))

        card = ttk.Frame(self._sg_inner, padding=2)
        card.pack(fill=X, pady=3)

        title_var = StringVar(value=g.title or f"源组{idx + 1}")
        in_var = StringVar(value=g.input_folder or "")
        out_var = StringVar(value=g.output_folder or "")
        en_var = tk.BooleanVar(value=bool(g.enabled))
        pp_en = tk.BooleanVar(value=bool(g.preprocess_enable))
        pp_tpl = StringVar(value=g.preprocess_template or "")
        pp_mode = StringVar(value=g.preprocess_temp_mode or "自动清理")
        pp_path = StringVar(value=g.preprocess_temp_path or "")

        # ---- 折叠标题行（始终可见）----
        head = ttk.Frame(card)
        head.pack(fill=X)
        arrow = "▼" if expanded else "▶"
        make_button(
            head, arrow, lambda i=gid: self._toggle_source_group_expand(i),
            kind="outline", width=3,
        ).pack(side=LEFT, padx=(0, 4))
        ttk.Checkbutton(head, text=f"组{idx + 1}", variable=en_var).pack(side=LEFT)
        ttk.Entry(head, textvariable=title_var, width=12).pack(side=LEFT, padx=4)
        summary_var = StringVar(value="")
        summary_lbl = ttk.Label(head, textvariable=summary_var, foreground="gray", font=("", 8))
        summary_lbl.pack(side=LEFT, fill=X, expand=True, padx=6)
        make_button(head, "上移", lambda i=idx: self._move_source_group(i, -1), kind="outline", width=4).pack(side=RIGHT, padx=1)
        make_button(head, "下移", lambda i=idx: self._move_source_group(i, 1), kind="outline", width=4).pack(side=RIGHT, padx=1)
        make_button(head, "删除", lambda i=idx: self._remove_source_group(i), kind="danger", width=4).pack(side=RIGHT, padx=1)

        body = ttk.Frame(card, padding=(28, 4, 4, 4))
        if expanded:
            body.pack(fill=X)

        r1 = ttk.Frame(body)
        r1.pack(fill=X, pady=2)
        ttk.Label(r1, text="输入").pack(side=LEFT)
        ttk.Entry(r1, textvariable=in_var).pack(side=LEFT, fill=X, expand=True, padx=4)

        def browse_in(v=in_var):
            p = filedialog.askdirectory(parent=self.root, title="选择输入文件夹")
            if p:
                v.set(p)
                _refresh_summary()

        make_button(r1, "浏览", browse_in, kind="outline", width=5).pack(side=LEFT)

        r2 = ttk.Frame(body)
        r2.pack(fill=X, pady=2)
        ttk.Label(r2, text="输出").pack(side=LEFT)
        ttk.Entry(r2, textvariable=out_var).pack(side=LEFT, fill=X, expand=True, padx=4)

        def browse_out(v=out_var):
            p = filedialog.askdirectory(parent=self.root, title="本组输出根（各方案建子文件夹）")
            if p:
                v.set(p)

        make_button(r2, "浏览", browse_out, kind="outline", width=5).pack(side=LEFT)
        ttk.Label(r2, text="空=用全局输出根", foreground="gray", font=("", 8)).pack(side=LEFT, padx=4)

        r3 = ttk.Frame(body)
        r3.pack(fill=X, pady=2)
        ttk.Checkbutton(r3, text="预处理", variable=pp_en, command=lambda: _refresh_summary()).pack(side=LEFT)
        ttk.Combobox(r3, textvariable=pp_tpl, values=tpls, width=22, state="readonly").pack(side=LEFT, padx=4)
        ttk.Label(r3, text="成品", foreground="gray", font=("", 8)).pack(side=LEFT)
        ttk.Combobox(
            r3, textvariable=pp_mode, width=10, state="readonly",
            values=["保留", "指定路径", "自动清理"],
        ).pack(side=LEFT, padx=4)
        ttk.Entry(r3, textvariable=pp_path, width=18).pack(side=LEFT, padx=2)

        def browse_pp(v=pp_path, m=pp_mode):
            p = filedialog.askdirectory(parent=self.root, title="预处理成品目录")
            if p:
                v.set(p)
                m.set("指定路径")

        make_button(r3, "…", browse_pp, kind="outline", width=3).pack(side=LEFT)

        r4 = ttk.Frame(body)
        r4.pack(fill=X, pady=(4, 0))
        ttk.Label(r4, text="裂变方案").pack(side=LEFT)
        ttk.Label(r4, text="（不勾=全部已启用方案）", foreground="gray", font=("", 8)).pack(side=LEFT, padx=4)
        cb_host = ttk.Frame(body)
        cb_host.pack(fill=X)
        selected = set(g.selected_branch_names or [])
        branch_vars: dict[str, tk.BooleanVar] = {}
        if not branch_names:
            ttk.Label(cb_host, text="方案库为空：请先在画布添加方案", foreground="gray").pack(anchor="w")
        else:
            for bn in branch_names:
                bv = tk.BooleanVar(value=(bn in selected) if selected else True)
                branch_vars[bn] = bv
                ttk.Checkbutton(cb_host, text=bn, variable=bv, command=lambda: _refresh_summary()).pack(
                    side=LEFT, padx=4, pady=1,
                )

        def _refresh_summary(*_a):
            summary_var.set(self._sg_summary_text(
                in_path=(in_var.get() or "").strip(),
                pp_on=bool(pp_en.get()),
                pp_tpl=(pp_tpl.get() or "").strip(),
                branch_vars=branch_vars,
            ))

        try:
            in_var.trace_add("write", lambda *_: _refresh_summary())
            pp_tpl.trace_add("write", lambda *_: _refresh_summary())
        except Exception:
            pass
        _refresh_summary()

        # 收起时标题行右侧提示「点箭头展开」
        if not expanded:
            ttk.Label(card, text="点左侧 ▶ 展开详细设置", foreground="gray", font=("", 8)).pack(
                anchor="w", padx=28,
            )

        return {
            "group_id": gid,
            "enabled": en_var,
            "title": title_var,
            "input": in_var,
            "output": out_var,
            "pp_en": pp_en,
            "pp_tpl": pp_tpl,
            "pp_mode": pp_mode,
            "pp_path": pp_path,
            "branch_vars": branch_vars,
        }

    def _collect_source_groups_from_ui(self) -> list[FissionSourceGroup]:
        out: list[FissionSourceGroup] = []
        for card in self._sg_cards:
            bvars = card.get("branch_vars") or {}
            selected = [n for n, v in bvars.items() if bool(v.get())]
            # 若全勾选，存空列表表示「全部」
            if bvars and len(selected) == len(bvars):
                selected = []
            out.append(FissionSourceGroup(
                group_id=str(card.get("group_id") or new_group_id()),
                enabled=bool(card["enabled"].get()),
                title=(card["title"].get() or "").strip(),
                input_folder=(card["input"].get() or "").strip(),
                output_folder=(card["output"].get() or "").strip(),
                preprocess_enable=bool(card["pp_en"].get()),
                preprocess_template=(card["pp_tpl"].get() or "").strip(),
                preprocess_temp_mode=(card["pp_mode"].get() or "自动清理").strip(),
                preprocess_temp_path=(card["pp_path"].get() or "").strip(),
                selected_branch_names=selected,
            ))
        return out

    def sync_groups_to_plan(self) -> None:
        plan = getattr(self.app, "_fission_plan", None)
        if plan is None:
            return
        if self._io_mode.get() == "多源":
            plan.source_groups = self._collect_source_groups_from_ui()
        else:
            plan.source_groups = [self._single_source_group_from_ui()]
        try:
            from modules import habi_memory
            if plan.source_groups:
                g0 = plan.source_groups[0]
                habi_memory.update_prefs(
                    fission_io_mode=self._io_mode.get(),
                    fission_preprocess_enable=bool(g0.preprocess_enable),
                    fission_preprocess_template=g0.preprocess_template,
                    fission_preprocess_temp_mode=g0.preprocess_temp_mode,
                    fission_preprocess_temp_path=g0.preprocess_temp_path,
                )
        except Exception:
            pass

    def _single_source_group_from_ui(self) -> FissionSourceGroup:
        """单源模式：左栏主文件夹 + 预处理条 → 一组；方案=画布上全部已启用。"""
        in_dir = ""
        if self._folders:
            in_dir = (self._folders[0] or "").strip()
        if not in_dir:
            in_dir = (self.app.global_input_folder.get() or "").strip()
        out_dir = (self.app.global_output_folder.get() or "").strip()
        pp_en = bool(getattr(self, "_pp_enable", tk.BooleanVar(value=False)).get())
        return FissionSourceGroup(
            group_id=new_group_id(),
            enabled=True,
            title="单源",
            input_folder=in_dir,
            output_folder=out_dir,
            preprocess_enable=pp_en,
            preprocess_template=(self._pp_template.get() or "").strip() if pp_en else "",
            preprocess_temp_mode=(self._pp_temp_mode.get() or "保留").strip(),
            preprocess_temp_path=(self._pp_temp_path.get() or "").strip(),
            selected_branch_names=[],  # 空=用方案库全部已启用方案
        )

    def get_preprocess_options(self) -> dict[str, Any]:
        """兼容旧接口。"""
        try:
            self.sync_groups_to_plan()
            for g in self.app._fission_plan.enabled_groups():
                return {
                    "enable": bool(g.preprocess_enable),
                    "template": g.preprocess_template,
                    "temp_mode": g.preprocess_temp_mode,
                    "temp_path": g.preprocess_temp_path,
                }
        except Exception:
            pass
        return {"enable": False, "template": "", "temp_mode": "保留", "temp_path": ""}

    def _add_source_group(self) -> None:
        plan = getattr(self.app, "_fission_plan", None)
        if plan is None:
            return
        self.sync_groups_to_plan()
        if len(plan.source_groups) >= MAX_SOURCE_GROUPS:
            messagebox.showinfo("提示", f"最多 {MAX_SOURCE_GROUPS} 个源素材组。", parent=self.root)
            return
        n = len(plan.source_groups) + 1
        out = (self.app.global_output_folder.get() or "").strip()
        g = FissionSourceGroup(
            group_id=new_group_id(),
            title=f"源组{n}",
            output_folder=out,
            selected_branch_names=[],
        )
        # 新组展开，其它收起，方便看见刚加的那一行
        for old in plan.source_groups:
            if old.group_id:
                self._sg_expanded[old.group_id] = False
        self._sg_expanded[g.group_id] = True
        plan.source_groups.append(g)
        self._rebuild_source_group_cards()
        try:
            self.root.after(50, lambda: self._sg_canvas.yview_moveto(1.0))
        except Exception:
            pass

    def _remove_source_group(self, idx: int) -> None:
        plan = getattr(self.app, "_fission_plan", None)
        if plan is None:
            return
        self.sync_groups_to_plan()
        if not (0 <= idx < len(plan.source_groups)):
            return
        if len(plan.source_groups) <= 1:
            messagebox.showinfo("提示", "至少保留一个源素材组。", parent=self.root)
            return
        plan.source_groups.pop(idx)
        self._rebuild_source_group_cards()

    def _move_source_group(self, idx: int, delta: int) -> None:
        plan = getattr(self.app, "_fission_plan", None)
        if plan is None:
            return
        self.sync_groups_to_plan()
        j = idx + delta
        if not (0 <= idx < len(plan.source_groups) and 0 <= j < len(plan.source_groups)):
            return
        plan.source_groups[idx], plan.source_groups[j] = plan.source_groups[j], plan.source_groups[idx]
        self._rebuild_source_group_cards()

    # ----- 左栏文件夹 -----

    def _sync_folders_from_app(self) -> None:
        path = (self.app.global_input_folder.get() or "").strip()
        if not path or not os.path.isdir(path):
            return
        if path not in self._folders:
            if self._folders:
                self._folders.insert(0, path)
            else:
                self._folders = [path]

    def _push_primary_folder(self) -> None:
        if self._folders:
            self.app.global_input_folder.set(self._folders[0])
            # 同步到第一源组输入（单源场景最常见）
            try:
                if hasattr(self, "_sg_cards") and self._sg_cards:
                    self._sg_cards[0]["input"].set(self._folders[0])
                    self.sync_groups_to_plan()
                else:
                    plan = getattr(self.app, "_fission_plan", None)
                    if plan is not None and plan.source_groups:
                        plan.source_groups[0].input_folder = self._folders[0]
            except Exception:
                pass
        self._rebuild_folder_list()
        self.redraw()

    def _pick_output_root(self) -> None:
        """选择全局输出总文件夹；不存在时可自动创建。"""
        path = filedialog.askdirectory(parent=self.root, title="选择裂变输出总文件夹")
        if not path:
            return
        self.app.global_output_folder.set(path)
        if not os.path.isdir(path):
            try:
                Path(path).mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                messagebox.showerror("错误", f"无法创建文件夹：{exc}", parent=self.root)
                return
        self._refresh_out_root_hint()
        try:
            if hasattr(self, "_on_pp_toggle"):
                self._on_pp_toggle()
        except Exception:
            pass
        self.redraw()

    def _refresh_out_root_hint(self) -> None:
        lbl = getattr(self, "_out_hint", None)
        if lbl is None:
            return
        root = (self.app.global_output_folder.get() or "").strip()
        if not root:
            lbl.config(text="未设置 → 处理前请先选总文件夹")
            return
        name = os.path.basename(root.rstrip("\\/")) or root
        branches = self._branch_list()
        if branches:
            sample = branches[0].branch_name or "方案名"
            lbl.config(text=f"…/{name}/\n  └ {sample}/\n  └ …（每方案一个）")
        else:
            lbl.config(text=f"…/{name}/{{方案名}}/")

    def _add_folder(self) -> None:
        self.app._pick_folder(self.app.global_input_folder)
        path = (self.app.global_input_folder.get() or "").strip()
        if path and os.path.isdir(path) and path not in self._folders:
            self._folders.append(path)
        self._push_primary_folder()

    def _hook_folder_drop(self, widget) -> None:
        try:
            from modules.folder_drop import hook_folder_drop

            ok = hook_folder_drop(widget, self._on_folders_dropped)
            if not ok and widget is getattr(self, "_drop_lbl", None):
                self._drop_lbl.config(text="点击添加文件夹（本机暂不支持拖入）")
        except Exception:
            pass

    def _on_folders_dropped(self, dirs: list[str]) -> None:
        added = 0
        for path in dirs:
            path = os.path.normpath(path)
            if not os.path.isdir(path):
                continue
            if path not in self._folders:
                self._folders.append(path)
                added += 1
        if not self._folders:
            return
        self._push_primary_folder()
        if added:
            self._toast(f"已加入 {added} 个文件夹")

    def _open_naming_for_output(self) -> None:
        """打开规范命名并指向裂变输出根（含子文件夹扫描）。"""
        last = (getattr(self.app, "_last_fission_out_root", "") or "").strip()
        out = (self.app.global_output_folder.get() or "").strip()
        target = last if last and os.path.isdir(last) else out
        opener = getattr(self.app, "open_naming_for_folder", None)
        if callable(opener) and target:
            opener(target, scan_subfolders=True)
            return
        if hasattr(self.app, "open_naming_tool"):
            self.app.open_naming_tool()

    def _remove_folder(self, index: int) -> None:
        if 0 <= index < len(self._folders):
            self._folders.pop(index)
            self.app.global_input_folder.set(self._folders[0] if self._folders else "")
            self._push_primary_folder()

    def _move_folder(self, index: int, delta: int) -> None:
        j = index + delta
        if j < 0 or j >= len(self._folders):
            return
        self._folders[index], self._folders[j] = self._folders[j], self._folders[index]
        self._push_primary_folder()

    def _rebuild_folder_list(self) -> None:
        host = getattr(self, "_folder_host", None)
        if host is None:
            return
        for w in host.winfo_children():
            w.destroy()
        if not self._folders:
            ttk.Label(host, text="还没有文件夹", foreground="gray").pack(anchor="w", pady=8)
            return
        for i, path in enumerate(self._folders):
            color = self.th["folder"][i % len(self.th["folder"])]
            name = os.path.basename(path.rstrip("\\/")) or path
            try:
                n = len(self.app._list_videos(path))
            except Exception:
                n = 0
            card_bg = self.th["card"]
            muted = self.th["muted"]
            row = tk.Frame(host, bg=card_bg, highlightthickness=1, highlightbackground=self.th["border"])
            row.pack(fill=X, pady=4)
            # 左侧彩色贴纸
            sticker = tk.Frame(row, bg=color, width=10)
            sticker.pack(side=LEFT, fill=Y, padx=(0, 4))
            sticker.pack_propagate(False)
            body = tk.Frame(row, bg=card_bg)
            body.pack(side=LEFT, fill=BOTH, expand=True, padx=2, pady=4)
            tk.Label(body, text=name, bg=card_bg, fg=self.th["text"], font=("Microsoft YaHei", 9, "bold")).pack(anchor="w", padx=4)
            tk.Label(body, text=f"{n} 个视频", bg=card_bg, fg=muted, font=("", 8)).pack(anchor="w", padx=4, pady=(0, 2))
            tk.Button(
                row, text="×", bg="#FF8FA3", fg="white", bd=0, width=2, font=("", 9, "bold"), cursor="hand2",
                command=lambda idx=i: self._remove_folder(idx),
            ).place(relx=1.0, x=-22, y=2, width=18, height=18)
            arrows = tk.Frame(row, bg=card_bg)
            arrows.pack(side=RIGHT, padx=(2, 4), pady=4)
            tk.Button(
                arrows, text="▲", width=2, font=("", 7), bg=card_bg, fg=muted, bd=1,
                relief="solid", highlightbackground=self.th["border"], cursor="hand2",
                command=lambda idx=i: self._move_folder(idx, -1),
                state=tk.DISABLED if i == 0 else tk.NORMAL,
            ).pack()
            tk.Button(
                arrows, text="▼", width=2, font=("", 7), bg=card_bg, fg=muted, bd=1,
                relief="solid", cursor="hand2",
                command=lambda idx=i: self._move_folder(idx, 1),
                state=tk.DISABLED if i == len(self._folders) - 1 else tk.NORMAL,
            ).pack()

    # ----- 分支数据 -----

    def _branch_list(self) -> list:
        plan = getattr(self.app, "_fission_plan", None)
        return list(plan.branches) if plan is not None else []

    def _select_branch(self, idx: int) -> None:
        self._selected_idx = idx
        try:
            self.app.fission_tree.selection_set(str(idx))
        except Exception:
            pass
        if self._layout_mode.get() == "地铁线路":
            self._rebuild_func_lib()

    def _on_layout_change(self) -> None:
        """思维导图隐藏功能库；地铁线路显示功能库（约原宽度的 2/3）。"""
        if not hasattr(self, "_mid_split"):
            return
        subway = self._layout_mode.get() == "地铁线路"
        panes = list(self._mid_split.panes())
        # 先清掉再按模式添加，避免重复
        for p in panes:
            try:
                self._mid_split.forget(p)
            except Exception:
                pass
        if subway:
            # weight 1:5 ≈ 功能库更窄；再强制 sash ≈ 145px（相对原先 220 缩约 1/3）
            self._mid_split.add(self._func_lib_shell, weight=1)
            self._mid_split.add(self._canvas_wrap, weight=5)
            if self._selected_idx is None and self._branch_list():
                self._selected_idx = 0
            self._rebuild_func_lib()
            try:
                self.root.after(80, self._shrink_func_lib_sash)
            except Exception:
                pass
        else:
            self._mid_split.add(self._canvas_wrap, weight=1)
        if getattr(self, "_out_host", None) is not None:
            self.redraw()

    def _shrink_func_lib_sash(self) -> None:
        if self._layout_mode.get() != "地铁线路":
            return
        try:
            self._mid_split.sashpos(0, 145)
        except Exception:
            pass

    def _rebuild_func_lib(self) -> None:
        host = getattr(self, "_func_lib_host", None)
        if host is None:
            return
        for w in host.winfo_children():
            w.destroy()
        th = self.th
        host.configure(bg=th["card"])
        self._func_lib_shell.configure(bg=th["card"])
        self._func_lib_title.configure(bg=th["card"], fg=th["muted"])
        self._func_lib_scheme.configure(bg=th["card"], fg=th["muted"])

        branches = self._branch_list()
        idx = self._selected_idx
        if idx is None or not (0 <= idx < len(branches)):
            self._func_lib_scheme.config(text="点击线路上的方案站口以编辑功能")
            tk.Label(host, text="请先选中一个方案", bg=th["card"], fg=th["muted"]).pack(anchor="w", pady=8)
            return

        b = branches[idx]
        color = th["scheme"][idx % len(th["scheme"])]
        self._func_lib_scheme.config(text=f"当前：{b.branch_name or f'方案{idx+1}'}")
        funcs = self._func_states(b)
        # 顺序号：仅已启用
        order_map: dict[int, int] = {}
        n = 0
        for j, (_k, _lab, checked, _d) in enumerate(funcs):
            if checked:
                n += 1
                order_map[j] = n

        for j, (key, label, checked, detail) in enumerate(funcs):
            row_bg = th["card"]
            if checked:
                # 浅色底
                row_bg = th["bg"]
            row = tk.Frame(host, bg=row_bg, cursor="hand2")
            row.pack(fill=X, pady=2, ipady=4)
            if checked:
                tk.Frame(row, bg=color, width=4).pack(side=LEFT, fill=Y)

            # 勾选圆
            circ = tk.Canvas(row, width=22, height=22, bg=row_bg, highlightthickness=0)
            circ.pack(side=LEFT, padx=6)
            if checked:
                circ.create_oval(2, 2, 20, 20, fill=th["check"], outline=th["check"])
                circ.create_text(11, 11, text="✓", fill="white", font=("", 9, "bold"))
            else:
                circ.create_oval(2, 2, 20, 20, fill="", outline=th["border"], width=2)

            def _toggle(si=idx, fi=j):
                self._toggle_func(si, fi)

            circ.bind("<Button-1>", lambda _e, fn=_toggle: fn())
            text_fr = tk.Frame(row, bg=row_bg)
            text_fr.pack(side=LEFT, fill=X, expand=True)
            tk.Label(text_fr, text=label, bg=row_bg, fg=th["text"], font=("Microsoft YaHei", 10), anchor="w").pack(fill=X)
            det = detail if checked else "点击圆圈加入线路"
            tk.Label(text_fr, text=det[:28], bg=row_bg, fg=th["muted"], font=("", 8), anchor="w").pack(fill=X)

            def _cfg(si=idx, fi=j, widget=row):
                try:
                    ax = widget.winfo_rootx()
                    ay = widget.winfo_rooty() + widget.winfo_height() + 4
                except Exception:
                    ax = ay = None
                self._open_func_config(si, fi, anchor_root=(ax, ay) if ax is not None else None)

            text_fr.bind("<Button-1>", lambda _e, fn=_cfg: fn())
            for child in text_fr.winfo_children():
                child.bind("<Button-1>", lambda _e, fn=_cfg: fn())

            if checked:
                tk.Label(row, text=str(order_map.get(j, "")), bg=row_bg, fg=color, font=("Microsoft YaHei", 11, "bold"), width=2).pack(side=RIGHT, padx=6)

    def _resolve_cfg_copy(self, branch: FissionBranch) -> dict:
        if isinstance(branch.embedded_config, dict):
            return copy.deepcopy(branch.embedded_config)
        try:
            import video_batch_tool_v20 as v20
            from modules.fission_engine import resolve_branch_config

            return copy.deepcopy(resolve_branch_config(branch, templates_dir=v20._templates_dir()))
        except Exception:
            return {}

    def _ensure_mutable_config(self, branch: FissionBranch) -> dict:
        if isinstance(branch.embedded_config, dict):
            return branch.embedded_config
        cfg = self._resolve_cfg_copy(branch)
        branch.embedded_config = cfg
        branch.template_name = ""
        if not branch.note:
            branch.note = "自建快照"
        return branch.embedded_config

    def _ordered_func_defs(self, cfg: dict) -> list[tuple[str, str, str, Callable[[dict], str]]]:
        raw = cfg.get(_ORDER_KEY)
        keys = [k for k, *_ in _FUNC_DEFS]
        if isinstance(raw, list) and raw:
            ordered = [k for k in raw if k in _FUNC_BY_KEY]
            for k in keys:
                if k not in ordered:
                    ordered.append(k)
        else:
            ordered = keys
        return [_FUNC_BY_KEY[k] for k in ordered]

    def _func_states(self, branch: FissionBranch) -> list[tuple[str, str, bool, str]]:
        cfg = self._resolve_cfg_copy(branch)
        out: list[tuple[str, str, bool, str]] = []
        for key, label, _jump, detail_fn in self._ordered_func_defs(cfg):
            checked = bool(cfg.get(key))
            out.append((key, label, checked, detail_fn(cfg) if checked else ""))
        return out

    def _move_func_order(self, scheme_idx: int, func_idx: int, delta: int) -> None:
        branches = self._branch_list()
        if not (0 <= scheme_idx < len(branches)):
            return
        b = branches[scheme_idx]
        cfg = self._ensure_mutable_config(b)
        defs = self._ordered_func_defs(cfg)
        j = func_idx + delta
        if j < 0 or j >= len(defs):
            return
        keys = [d[0] for d in defs]
        keys[func_idx], keys[j] = keys[j], keys[func_idx]
        cfg[_ORDER_KEY] = keys
        self._after_plan_change()

    def _after_plan_change(self, select_last: bool = False) -> None:
        try:
            self.app._fission_refresh_tree()
        except Exception:
            pass
        if select_last:
            n = len(self._branch_list())
            if n:
                self._selected_idx = n - 1
                try:
                    self.app.fission_tree.selection_set(str(self._selected_idx))
                except Exception:
                    pass
        if self._layout_mode.get() == "地铁线路":
            self._rebuild_func_lib()
        # 方案库变更后，多源模式下刷新各组勾选列表
        try:
            if self._io_mode.get() == "多源":
                if hasattr(self, "_sg_cards") and self._sg_cards:
                    self.sync_groups_to_plan()
                if hasattr(self, "_rebuild_source_group_cards"):
                    self._rebuild_source_group_cards()
        except Exception:
            pass
        self.redraw()

    # ----- 绘制 -----

    def redraw(self, *, refresh_out: bool = True) -> None:
        if not hasattr(self, "canvas"):
            return
        if self._layout_mode.get() == "地铁线路":
            self._redraw_subway(refresh_out=refresh_out)
        else:
            self._redraw_mindmap(refresh_out=refresh_out)

    def _short_label(self, label: str) -> str:
        mapping = {
            "视频裁切": "裁切", "替换音频": "音频", "比例适配": "比例",
            "PNG水印": "水印", "MOV水印": "MOV", "浮层落版": "浮层",
            "拼接落版": "落版", "可视化叠加": "叠加",
        }
        return mapping.get(label, label[:4])

    def _ellipsis(self, text: str, max_chars: int) -> str:
        t = text or ""
        return (t[: max_chars - 1] + "…") if len(t) > max_chars else t

    def _redraw_subway(self, *, refresh_out: bool = True) -> None:
        """地铁线路：固定节点间距 120px；只画已勾选功能。"""
        c = self.canvas
        th = self.th
        c.delete("all")
        self._hit_regions.clear()
        self._tip_regions: list[tuple[float, float, float, float, str]] = []
        self._subway_slots: dict[int, list[tuple[int, float]]] = {}
        view_w = max(c.winfo_width(), 400)
        view_h = max(c.winfo_height(), 320)
        branches = self._branch_list()
        n = len(branches)
        row_h = 120  # 方案垂直间距固定
        node_gap = 120  # 功能节点水平间距固定
        content_h = max(view_h, 40 + max(n, 1) * row_h + 40)

        if not branches:
            c.configure(scrollregion=(0, 0, view_w, content_h), bg=th["bg"])
            c.create_text(
                view_w // 2, content_h // 2,
                text="还没有方案\n双击空白添加 · 左功能库勾选功能",
                fill=th["muted"], font=("Microsoft YaHei", 11), justify=tk.CENTER,
            )
            if refresh_out:
                self._refresh_out_panel([])
                self._refresh_out_root_hint()
            return

        max_content_w = view_w
        for i, b in enumerate(branches):
            color = th["scheme"][i % len(th["scheme"])]
            y = 50 + i * row_h + row_h // 2
            title = b.branch_name or f"方案{chr(65 + i) if i < 26 else i + 1}"
            selected = self._selected_idx == i
            hx1, hy1, hx2, hy2 = 16, y - 28, 150, y + 28
            fill = color if th.get("scheme_fill") else th["card"]
            outline_w = 3 if selected else 2
            self._round_rect(c, hx1, hy1, hx2, hy2, fill=fill, outline=color, width=outline_w)
            tfg = "white" if th.get("scheme_fill") else th["text"]
            c.create_text(hx1 + 12, y - 8, text=title[:10], fill=tfg, font=("Microsoft YaHei", 11, "bold"), anchor="w")
            c.create_text(
                hx1 + 12, y + 10, text=b.display_source()[:12],
                fill=th["muted"] if not th.get("scheme_fill") else "#F1F5F9", font=("", 8), anchor="w",
            )
            self._hit_regions.append(("scheme", i, -1, hx1, hy1, hx2, hy2))

            funcs = self._func_states(b)
            enabled = [(j, lab, det) for j, (_k, lab, checked, det) in enumerate(funcs) if checked]
            track_x0 = hx2 + 40
            # 线长随节点数变：首站到末站 = (n-1)*120，再加左右留白
            n_en = len(enabled)
            if n_en:
                last_sx = track_x0 + (n_en - 1) * node_gap
                track_x1 = last_sx + 40
            else:
                track_x1 = track_x0 + 80
            # 半透明轨道（用浅色模拟）
            c.create_line(track_x0 - 8, y, track_x1, y, fill=color, width=4, stipple="gray50")
            c.create_polygon(track_x1 + 12, y, track_x1 - 2, y - 7, track_x1 - 2, y + 7, fill=color, outline="")

            slots: list[tuple[int, float]] = []
            for k, (j, lab, det) in enumerate(enabled):
                sx = track_x0 + k * node_gap
                slots.append((j, sx))
                short = self._short_label(lab)
                c.create_text(sx, y - 32, text=short, fill=th["text"], font=("Microsoft YaHei", 10, "bold"))
                r = 10
                c.create_oval(sx - r - 2, y - r - 2, sx + r + 2, y + r + 2, fill="white", outline="")
                c.create_oval(sx - r, y - r, sx + r, y + r, fill=color, outline="white", width=2)
                c.create_text(sx, y, text="✓", fill="white", font=("", 9, "bold"))

                full_det = det or "已启用"
                show = self._ellipsis(full_det, 12)
                cw = max(80, min(120, 7 * len(show) + 20))
                card_y0, card_y1 = y + 18, y + 42
                self._round_rect(c, sx - cw / 2, card_y0, sx + cw / 2, card_y1, fill=th["card"], outline=color, width=1)
                c.create_text(sx, (card_y0 + card_y1) / 2, text=show, fill=th["muted"], font=("Microsoft YaHei", 8))
                tip = f"{lab}\n{full_det}" if full_det else lab
                self._tip_regions.append((sx - cw / 2, y - 40, sx + cw / 2, card_y1, tip))
                self._hit_regions.append(("func", i, j, sx - cw / 2, y - 40, sx + cw / 2, card_y1))
                self._hit_regions.append(("station", i, j, sx - r - 4, y - r - 4, sx + r + 4, y + r + 4))

            self._subway_slots[i] = slots
            if not enabled:
                c.create_text(
                    track_x0 + 10, y - 22,
                    text="← 在左侧功能库勾选功能", fill=th["muted"], font=("", 9), anchor="w",
                )

            ox1 = track_x1 + 28
            ox2 = ox1 + 110
            oy1, oy2 = y - 22, y + 22
            self._round_rect(c, ox1, oy1, ox2, oy2, fill=fill, outline=color, width=2)
            c.create_text((ox1 + ox2) / 2, y - 6, text=f"{title[:6]}输出", fill=tfg, font=("Microsoft YaHei", 9, "bold"))
            c.create_text(
                (ox1 + ox2) / 2, y + 10, text="自动建文件夹",
                fill=th["muted"] if not th.get("scheme_fill") else "#F1F5F9", font=("", 8),
            )
            max_content_w = max(max_content_w, ox2 + 40)

            if self._drag and self._drag.get("scheme") == i and self._drag.get("ghost_x") is not None:
                gx = self._drag["ghost_x"]
                c.create_oval(gx - 12, y - 12, gx + 12, y + 12, fill=color, outline="white", width=2, stipple="gray25")

        c.configure(scrollregion=(0, 0, max_content_w, content_h), bg=th["bg"])
        if refresh_out:
            self._refresh_out_panel(branches)
            self._refresh_out_root_hint()

    def _redraw_mindmap(self, *, refresh_out: bool = True) -> None:
        c = self.canvas
        th = self.th
        c.delete("all")
        self._hit_regions.clear()
        self._tip_regions = []
        w = max(c.winfo_width(), 520)
        view_h = max(c.winfo_height(), 320)
        branches = self._branch_list()
        n = len(branches)

        # 按功能数量分配垂直空间，避免方案之间子功能重叠
        row_h_func = 28
        scheme_gap = 48
        block_hs: list[float] = []
        for b in branches:
            nf = max(1, len(self._func_states(b)))
            block_hs.append(max(120, nf * row_h_func + 36))
        if n:
            content_h = max(view_h, 60 + sum(block_hs) + (n - 1) * scheme_gap + 60)
        else:
            content_h = view_h
        c.configure(scrollregion=(0, 0, max(w, 720), content_h), bg=th["bg"])

        n_vid = 0
        for p in self._folders:
            try:
                n_vid += len(self.app._list_videos(p))
            except Exception:
                pass

        cx, cy = 120, content_h // 2
        self._round_rect(c, cx - 68, cy - 34, cx + 68, cy + 34, fill=th["center"], outline="")
        c.create_text(cx, cy - 8, text="当前项目", fill="white", font=("Microsoft YaHei", 11, "bold"))
        folder_txt = f"{len(self._folders)} 个文件夹 · {n_vid} 视频" if self._folders else "未选择输入"
        c.create_text(cx, cy + 14, text=folder_txt, fill="#FFF5F5", font=("Microsoft YaHei", 8))

        if not branches:
            c.create_text(
                w // 2, content_h // 2,
                text="还没有方案\n双击空白处 → 在落点直接选模板/方案",
                fill=th["muted"], font=("Microsoft YaHei", 11), justify=tk.CENTER,
            )
            if refresh_out:
                self._refresh_out_panel([])
                self._refresh_out_root_hint()
            return

        scheme_x, sub_x = 290, 455
        y_cursor = 50
        for i, b in enumerate(branches):
            color = th["scheme"][i % len(th["scheme"])]
            block_h = block_hs[i]
            y = y_cursor + block_h / 2
            y_cursor += block_h + scheme_gap

            c.create_line(cx + 68, cy, scheme_x - 88, y, fill=th["line"], width=2, dash=(4, 3), smooth=True)
            funcs = self._func_states(b)
            x1, y1 = scheme_x - 90, y - 24
            x2, y2 = scheme_x + 90, y + 24
            active = self._selected_idx == i
            fill = color if th.get("scheme_fill") else th["card"]
            title_fg = "white" if th.get("scheme_fill") else color
            self._round_rect(
                c, x1, y1, x2, y2, fill=fill,
                outline="#4ADE80" if active else color,
                width=2 if active else 1,
                dash=(4, 3) if active else (),
            )
            title = b.branch_name or f"方案{chr(65 + i) if i < 26 else i + 1}"
            c.create_text(
                x1 + 12, y - 6, text=f"{'●' if b.enabled else '○'} {title}",
                fill=title_fg, font=("Microsoft YaHei", 10, "bold"), anchor="w",
            )
            c.create_text(
                x1 + 12, y + 10, text=b.display_source()[:16],
                fill=th["muted"] if not th.get("scheme_fill") else "#F8FAFC",
                font=("Microsoft YaHei", 8), anchor="w",
            )
            self._hit_regions.append(("scheme", i, -1, x1, y1, x2, y2))

            total_h = max(1, len(funcs)) * row_h_func
            for j, (_key, label, checked, detail) in enumerate(funcs):
                sy = y - total_h / 2 + j * row_h_func + row_h_func / 2
                c.create_line(x2, y, sub_x - 6, sy, fill=th["line"], width=1, dash=(3, 3))
                r = 7
                check = th["check"]
                if checked:
                    c.create_oval(sub_x - r, sy - r, sub_x + r, sy + r, fill=check, outline=check)
                    c.create_text(sub_x, sy, text="✓", fill="white", font=("", 8, "bold"))
                    chip_fill, chip_outline, chip_fg = th["card"], check, th["text"]
                else:
                    c.create_oval(sub_x - r, sy - r, sub_x + r, sy + r, fill="", outline=th["muted"], width=1.5)
                    chip_fill, chip_outline, chip_fg = th["card"], th["border"], th["muted"]
                self._hit_regions.append(("toggle", i, j, sub_x - r - 2, sy - r - 2, sub_x + r + 2, sy + r + 2))

                detail_show = self._ellipsis(detail or "", 20) if detail else ""
                chip_h = 24 if detail_show else 16
                tw = max(110, 9 * max(len(label), len(detail_show or "")) + 32)
                tx1, ty1 = sub_x + 12, sy - chip_h / 2
                tx2, ty2 = tx1 + tw, sy + chip_h / 2
                self._round_rect(c, tx1, ty1, tx2, ty2, fill=chip_fill, outline=chip_outline, width=1)
                if detail_show:
                    c.create_text(tx1 + 6, sy - 5, text=label, fill=chip_fg, font=("Microsoft YaHei", 9), anchor="w")
                    c.create_text(tx1 + 6, sy + 7, text=detail_show, fill=th["muted"], font=("Microsoft YaHei", 8), anchor="w")
                else:
                    c.create_text(tx1 + 6, sy, text=label, fill=chip_fg, font=("Microsoft YaHei", 9), anchor="w")
                c.create_text(tx2 - 10, sy, text="⚙", fill=th["muted"], font=("", 8))
                tip = f"{label}\n{detail}" if detail else label
                self._tip_regions.append((tx1, ty1, tx2, ty2, tip))
                self._hit_regions.append(("func", i, j, tx1, ty1, tx2, ty2))

            c.create_line(sub_x + 140, y, max(w, 720) - 24, y, fill=th["line"], width=1, dash=(3, 3))

        if refresh_out:
            self._refresh_out_panel(branches)
            self._refresh_out_root_hint()

    def _refresh_out_panel(self, branches: list) -> None:
        host = getattr(self, "_out_host", None)
        if host is None:
            return
        for w in host.winfo_children():
            w.destroy()
        out_root = (self.app.global_output_folder.get() or "").strip()
        th = self.th

        # 预处理成品（保留时显示在方案输出上方，可打开）
        pp_outs = list(getattr(self.app, "_fission_preprocess_outputs", []) or [])
        # 也扫输出根下 _预处理_* 目录，方便重开软件后仍能打开
        if out_root and os.path.isdir(out_root):
            try:
                known = {str(x.get("path") or "") for x in pp_outs}
                for name in sorted(os.listdir(out_root)):
                    if not name.startswith("_预处理"):
                        continue
                    full = os.path.join(out_root, name)
                    if not os.path.isdir(full) or full in known:
                        continue
                    pp_outs.append({"name": name, "path": full})
            except OSError:
                pass
        for item in pp_outs:
            path = str(item.get("path") or "")
            name = str(item.get("name") or Path(path).name or "预处理")
            if not path or not os.path.isdir(path):
                continue
            row = tk.Frame(host, bg=th["card"], highlightthickness=1, highlightbackground=th["border"])
            row.pack(fill=X, pady=4)
            tk.Frame(row, bg="#7BAE7F", height=4).pack(fill=X)
            tk.Label(
                row, text=f"预处理成品 · {name}", bg=th["card"], fg=th["text"],
                font=("Microsoft YaHei", 9, "bold"),
            ).pack(anchor="w", padx=8, pady=(6, 2))
            pct, label = self._progress.get(name, (0.0, "就绪"))
            ttk.Progressbar(row, orient="horizontal", mode="determinate", maximum=100, value=pct).pack(fill=X, padx=8)
            tk.Label(row, text=label, bg=th["card"], fg=th["muted"], font=("", 8)).pack(anchor="w", padx=8, pady=(2, 2))
            tk.Label(
                row, text=path, bg=th["card"], fg=th["muted"], font=("", 7), wraplength=180, justify="left",
            ).pack(anchor="w", padx=8, pady=(0, 4))

            def _open_pp(p=path):
                from modules.platform_utils import open_folder
                open_folder(p)

            make_button(row, "打开", _open_pp, kind="tool", width=5).pack(anchor="e", padx=6, pady=(0, 6))

        for i, b in enumerate(branches):
            color = th["scheme"][i % len(th["scheme"])]
            name = b.branch_name or f"方案{i + 1}"
            row = tk.Frame(host, bg=th["card"], highlightthickness=1, highlightbackground=th["border"])
            row.pack(fill=X, pady=4)
            tk.Frame(row, bg=color, height=4).pack(fill=X)
            tk.Label(row, text=f"{name}输出", bg=th["card"], fg=th["text"], font=("Microsoft YaHei", 9, "bold")).pack(
                anchor="w", padx=8, pady=(6, 2),
            )
            pct, label = self._progress.get(name, (0.0, "等待中"))
            ttk.Progressbar(row, orient="horizontal", mode="determinate", maximum=100, value=pct).pack(fill=X, padx=8)
            tk.Label(row, text=label, bg=th["card"], fg=th["muted"], font=("", 8)).pack(anchor="w", padx=8, pady=(2, 6))

            def _open(bn=name):
                if out_root and os.path.isdir(os.path.join(out_root, bn)):
                    from modules.platform_utils import open_folder
                    open_folder(os.path.join(out_root, bn))

            make_button(row, "打开", _open, kind="tool", width=5).pack(anchor="e", padx=6, pady=(0, 6))
        if not branches and not pp_outs:
            ttk.Label(host, text="添加方案后这里显示输出", foreground="gray").pack(anchor="w")

    def _round_rect(self, c, x1, y1, x2, y2, **kw):
        r = 8
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return c.create_polygon(points, smooth=True, **kw)

    # ----- 命中 -----

    def _canvas_xy(self, event) -> tuple[float, float]:
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def _hide_tooltip(self) -> None:
        tip = getattr(self, "_tooltip", None)
        if tip is not None:
            try:
                tip.destroy()
            except Exception:
                pass
        self._tooltip = None
        self._tooltip_text = ""

    def _show_tooltip(self, x_root: int, y_root: int, text: str) -> None:
        if not text:
            self._hide_tooltip()
            return
        if text == getattr(self, "_tooltip_text", None) and self._tooltip is not None:
            return
        self._hide_tooltip()
        self._tooltip_text = text
        tip = tk.Toplevel(self.root)
        tip.wm_overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except Exception:
            pass
        tk.Label(
            tip, text=text, bg="#1E293B", fg="white", font=("Microsoft YaHei", 9),
            padx=8, pady=4, justify="left",
        ).pack()
        tip.geometry(f"+{int(x_root) + 12}+{int(y_root) + 12}")
        self._tooltip = tip

    def _tip_at(self, x: float, y: float) -> Optional[str]:
        for x1, y1, x2, y2, text in reversed(getattr(self, "_tip_regions", []) or []):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return text
        return None

    def _hit_test(self, x: float, y: float) -> Optional[tuple[str, int, int]]:
        for kind, si, fi, x1, y1, x2, y2 in reversed(self._hit_regions):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return kind, si, fi
        return None

    def _on_canvas_motion(self, event) -> None:
        if self._drag is not None:
            return
        x, y = self._canvas_xy(event)
        tip = self._tip_at(x, y)
        if tip:
            self._show_tooltip(event.x_root, event.y_root, tip)
        else:
            self._hide_tooltip()

    def _on_wheel(self, event) -> None:
        if event.state & 0x0001:  # Shift：横向滚动（地铁线路加长时）
            self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        else:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_canvas_press(self, event) -> None:
        x, y = self._canvas_xy(event)
        hit = self._hit_test(x, y)
        if not hit:
            self._drag = None
            return
        kind, idx, fi = hit
        # 地铁布局：站点可拖拽调序
        if self._layout_mode.get() == "地铁线路" and kind in ("station", "func") and fi >= 0:
            self._drag = {
                "scheme": idx, "func": fi, "x0": x, "y0": y,
                "ghost_x": x, "moved": False,
            }
            self._select_branch(idx)
            return
        self._drag = None
        self._handle_hit_click(kind, idx, fi)

    def _on_canvas_drag(self, event) -> None:
        if not self._drag:
            return
        x, y = self._canvas_xy(event)
        if abs(x - self._drag["x0"]) > 6 or abs(y - self._drag["y0"]) > 6:
            self._drag["moved"] = True
        self._drag["ghost_x"] = x
        self.redraw(refresh_out=False)

    def _on_canvas_release(self, event) -> None:
        drag = self._drag
        self._drag = None
        if not drag:
            return
        x, _y = self._canvas_xy(event)
        if not drag.get("moved"):
            self._open_func_config(drag["scheme"], drag["func"])
            self.redraw()
            return
        scheme = drag["scheme"]
        from_idx = drag["func"]
        slots = getattr(self, "_subway_slots", {}).get(scheme) or []
        if not slots:
            self.redraw()
            return
        target_pos = min(range(len(slots)), key=lambda k: abs(slots[k][1] - x))
        ordered_indices = [s[0] for s in slots]
        if from_idx not in ordered_indices:
            self.redraw()
            return
        from_pos = ordered_indices.index(from_idx)
        if from_pos == target_pos:
            self.redraw()
            return
        branches = self._branch_list()
        if not (0 <= scheme < len(branches)):
            return
        b = branches[scheme]
        cfg = self._ensure_mutable_config(b)
        keys = [d[0] for d in self._ordered_func_defs(cfg)]
        funcs = self._func_states(b)
        enabled_keys = [funcs[j][0] for j, _sx in slots]
        item = enabled_keys.pop(from_pos)
        enabled_keys.insert(target_pos, item)
        enabled_set = set(enabled_keys)
        new_keys = list(enabled_keys) + [k for k in keys if k not in enabled_set]
        cfg[_ORDER_KEY] = new_keys
        self._after_plan_change()
        self._toast("已调整站点顺序")

    def _handle_hit_click(self, kind: str, idx: int, fi: int) -> None:
        # 单击方案=选中高亮；点子功能=配置；右键方案=菜单
        if kind == "scheme":
            self._select_branch(idx)
            self.redraw(refresh_out=False)
        elif kind == "toggle":
            self._toggle_func(idx, fi)
        elif kind in ("func", "station"):
            self._select_branch(idx)
            self._open_func_config(idx, fi)

    def _on_canvas_right(self, event) -> None:
        x, y = self._canvas_xy(event)
        hit = self._hit_test(x, y)
        if not hit or hit[0] != "scheme":
            return
        idx = hit[1]
        self._select_branch(idx)
        self.redraw(refresh_out=False)
        self._show_scheme_context_menu(event.x_root, event.y_root, idx)

    def _show_scheme_context_menu(self, x_root: int, y_root: int, idx: int) -> None:
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="编辑方案", command=lambda: self._edit_selected())
        menu.add_command(label="复制方案", command=lambda: self._clone_branch_at(idx))
        menu.add_separator()
        menu.add_command(label="删除方案", command=lambda: self._delete_selected())
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def _on_canvas_click(self, event) -> None:
        # 兼容旧绑定
        self._on_canvas_press(event)
        if self._drag is None:
            return
        # 非拖拽布局时 press 已处理完
        if self._layout_mode.get() != "地铁线路":
            self._drag = None

    def _on_canvas_dbl(self, event) -> None:
        x, y = self._canvas_xy(event)
        hit = self._hit_test(x, y)
        if hit is None:
            self._show_add_popup_at(event.x_root, event.y_root)
        elif hit[0] == "scheme":
            self._select_branch(hit[1])
            self._edit_selected()

    def _on_ctrl_n(self, _event=None):
        if not self._is_active_tab() or self._view.get() != "mindmap":
            return
        # 窗口中心附近弹出
        try:
            x = self.canvas.winfo_rootx() + self.canvas.winfo_width() // 3
            y = self.canvas.winfo_rooty() + self.canvas.winfo_height() // 3
        except Exception:
            x, y = 200, 200
        self._show_add_popup_at(x, y)
        return "break"

    def _is_active_tab(self) -> bool:
        sheet = getattr(self.app, "_sheet", None)
        if sheet is None:
            return True
        try:
            return int(sheet.index(sheet.select())) == 2
        except Exception:
            return True

    def _toggle_func(self, scheme_idx: int, func_idx: int) -> None:
        branches = self._branch_list()
        if not (0 <= scheme_idx < len(branches)):
            return
        b = branches[scheme_idx]
        cfg = self._ensure_mutable_config(b)
        defs = self._ordered_func_defs(cfg)
        if not (0 <= func_idx < len(defs)):
            return
        key = defs[func_idx][0]
        cfg[key] = not bool(cfg.get(key))
        self._select_branch(scheme_idx)
        self._after_plan_change()

    # ----- 功能细节弹窗 -----

    def _func_anchor_root(self, scheme_idx: int, func_idx: int) -> tuple[int, int]:
        """子功能下方屏幕坐标（优先画布命中区）。"""
        for kind, si, fi, x1, y1, x2, y2 in reversed(self._hit_regions):
            if kind in ("func", "station") and si == scheme_idx and fi == func_idx:
                try:
                    rx = int(self.canvas.winfo_rootx() + (x1 - self.canvas.canvasx(0)))
                    ry = int(self.canvas.winfo_rooty() + (y2 - self.canvas.canvasy(0)) + 8)
                    return rx, ry
                except Exception:
                    break
        try:
            return self.canvas.winfo_rootx() + 48, self.canvas.winfo_rooty() + 48
        except Exception:
            return 120, 120

    def _place_win_below(self, win: tk.Toplevel, x: int, y: int, *, w: int = 500, h: int = 560) -> None:
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = max(8, min(int(x), sw - w - 8))
        y = max(8, min(int(y), sh - h - 8))
        win.geometry(f"{w}x{h}+{x}+{y}")

    def _open_func_config(
        self,
        scheme_idx: int,
        func_idx: int,
        *,
        anchor_root: Optional[tuple[int, int]] = None,
    ) -> None:
        """子功能设置：字段与视频批处理对齐；弹窗出现在子功能下方。"""
        from core.overlay_processor import POSITIONS
        import video_batch_tool_v20 as v20

        branches = self._branch_list()
        if not (0 <= scheme_idx < len(branches)):
            return
        b = branches[scheme_idx]
        cfg = self._ensure_mutable_config(b)
        defs = self._ordered_func_defs(cfg)
        if not (0 <= func_idx < len(defs)):
            return
        enable_key, label, jump_key, _df = defs[func_idx]
        self._select_branch(scheme_idx)

        ax, ay = anchor_root or self._func_anchor_root(scheme_idx, func_idx)

        win = tk.Toplevel(self.root)
        win.title(f"配置：{label} — {b.branch_name}")
        win.transient(self.root)
        win.grab_set()
        self._place_win_below(win, ax, ay)

        en = BooleanVar(value=bool(cfg.get(enable_key)))
        ttk.Checkbutton(win, text=f"启用「{label}」", variable=en).pack(anchor="w", padx=14, pady=(12, 6))
        ttk.Separator(win).pack(fill=X, padx=12, pady=4)

        # 可滚动表单，避免长字段被裁
        wrap = ttk.Frame(win)
        wrap.pack(fill=BOTH, expand=True, padx=8, pady=4)
        canvas = tk.Canvas(wrap, highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        form = ttk.Frame(canvas)
        form.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=form, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)
        form.columnconfigure(1, weight=1)

        fields: dict[str, StringVar] = {}
        bool_fields: dict[str, BooleanVar] = {}

        def add_entry(row: int, text: str, key: str, width: int = 28, default: str = ""):
            ttk.Label(form, text=text).grid(row=row, column=0, sticky="w", pady=4, padx=(6, 4))
            v = StringVar(value=str(cfg.get(key, default) if cfg.get(key) is not None else default))
            fields[key] = v
            ttk.Entry(form, textvariable=v, width=width).grid(row=row, column=1, sticky="ew", pady=4)
            return v

        def add_combo(row: int, text: str, key: str, values: list[str], default: str = ""):
            ttk.Label(form, text=text).grid(row=row, column=0, sticky="w", pady=4, padx=(6, 4))
            cur = str(cfg.get(key, default or (values[0] if values else "")) or (default or (values[0] if values else "")))
            if values and cur not in values:
                cur = values[0]
            v = StringVar(value=cur)
            fields[key] = v
            ttk.Combobox(form, textvariable=v, values=values, state="readonly", width=26).grid(
                row=row, column=1, sticky="w", pady=4,
            )

        def add_file(row: int, text: str, key: str, patterns):
            ttk.Label(form, text=text).grid(row=row, column=0, sticky="w", pady=4, padx=(6, 4))
            v = StringVar(value=str(cfg.get(key, "") or ""))
            fields[key] = v
            fr = ttk.Frame(form)
            fr.grid(row=row, column=1, sticky="ew", pady=4)
            ttk.Entry(fr, textvariable=v, width=22).pack(side=LEFT, fill=X, expand=True)

            def browse():
                p = filedialog.askopenfilename(parent=win, filetypes=patterns)
                if p:
                    v.set(p)

            ttk.Button(fr, text="浏览", command=browse, width=6).pack(side=LEFT, padx=4)

        def add_check(row: int, text: str, key: str):
            v = BooleanVar(value=bool(cfg.get(key)))
            bool_fields[key] = v
            ttk.Checkbutton(form, text=text, variable=v).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=4, padx=6,
            )

        ratio_values = list(getattr(v20, "RATIO_SIZES", {}).keys()) or ["9:16", "4:5", "1:1", "16:9"]
        pos_values = list(POSITIONS)

        if enable_key == "cut_enable":
            add_combo(0, "范围", "cut_range_mode", ["固定时段", "末尾N秒"], "固定时段")
            add_combo(1, "模式", "cut_mode", ["保留", "删除"], "保留")
            add_entry(2, "开始", "cut_start", default="00:00")
            add_entry(3, "结束", "cut_end", default="00:15")
            add_entry(4, "末尾秒数", "cut_tail_sec", default="5")
            ttk.Label(
                form, text="「末尾N秒」时用末尾秒数；固定时段用开始/结束",
                foreground="gray", font=("", 8), wraplength=420,
            ).grid(row=5, column=0, columnspan=2, sticky="w", padx=6)
        elif enable_key == "enhance_enable":
            add_combo(0, "模式", "enhance_mode", ["锐化降噪", "轻度放大"], "锐化降噪")
            ttk.Label(
                form, text="只能略改善观感，无法把糊片变真·高清",
                foreground="gray", font=("", 8), wraplength=420,
            ).grid(row=1, column=0, columnspan=2, sticky="w", padx=6)
        elif enable_key == "ratio_enable":
            add_combo(0, "目标比例", "ratio_target", ratio_values, "9:16")
            add_entry(1, "模糊强度", "ratio_blur_strength", default="20")
        elif enable_key == "png_wm_enable":
            add_file(0, "水印文件", "png_wm_path", [("图片", "*.png;*.jpg;*.jpeg;*.webp"), ("全部", "*.*")])
            add_combo(1, "模式", "png_wm_mode", ["fullscreen", "custom"], "fullscreen")
            add_combo(2, "位置", "png_wm_position", pos_values, "居中")
            add_entry(3, "自定义 X", "png_wm_x", default="0")
            add_entry(4, "自定义 Y", "png_wm_y", default="0")
            add_entry(5, "自定义 W", "png_wm_w", default="0")
            add_entry(6, "自定义 H", "png_wm_h", default="0")
            add_combo(7, "时间", "png_wm_time_mode", ["全程", "时段"], "全程")
            add_entry(8, "开始秒", "png_wm_time_start", default="0")
            add_entry(9, "结束秒", "png_wm_time_end", default="5")
        elif enable_key == "enable_mov_watermark":
            add_file(0, "MOV文件", "mov_watermark_path", [("视频", "*.mov;*.mp4;*.webm"), ("全部", "*.*")])
            add_combo(1, "模式", "mov_watermark_mode", ["fullscreen", "custom"], "fullscreen")
            add_entry(2, "时长(秒,0=全程)", "mov_watermark_duration", default="0")
            add_entry(3, "自定义 X", "mov_watermark_x", default="0")
            add_entry(4, "自定义 Y", "mov_watermark_y", default="0")
            add_entry(5, "自定义 W", "mov_watermark_w", default="0")
            add_entry(6, "自定义 H", "mov_watermark_h", default="0")
            add_check(7, "颜色保护（先缩放再去预乘）", "mov_color_protect")
            ttk.Label(
                form, text="自定义坐标也可在批处理页用「预览并定位」拖拽生成",
                foreground="gray", font=("", 8), wraplength=420,
            ).grid(row=8, column=0, columnspan=2, sticky="w", padx=6)
        elif enable_key == "logo_enable":
            add_file(0, "落版文件", "logo_path", [("媒体", "*.png;*.jpg;*.jpeg;*.mov;*.mp4"), ("全部", "*.*")])
            add_entry(1, "尺寸%", "logo_size_value", default="100")
            add_combo(2, "位置", "logo_position", pos_values, "居中")
            add_entry(3, "自定义 X", "overlay_custom_x", default="0")
            add_entry(4, "自定义 Y", "overlay_custom_y", default="0")
            add_entry(5, "结尾前N秒叠加", "ending_trim", default="1.0")
            add_check(6, "保留落版音频（重叠段混合）", "overlay_keep_audio")
            ttk.Label(
                form, text="模式固定为「结尾覆盖落版」（与批处理一致）",
                foreground="gray", font=("", 8), wraplength=420,
            ).grid(row=7, column=0, columnspan=2, sticky="w", padx=6)
        elif enable_key == "ending_enable":
            add_file(0, "落版视频", "ending_file", [("视频", "*.mp4;*.mov"), ("全部", "*.*")])
            add_check(1, "保留落版音频", "ending_keep_audio")
            add_entry(2, "截取落版前(秒)", "ending_concat_trim", default="0")
            ttk.Label(
                form, text="0=完整拼接；与「浮层落版」不同，此模式拼到主视频末尾",
                foreground="gray", font=("", 8), wraplength=420,
            ).grid(row=3, column=0, columnspan=2, sticky="w", padx=6)
        elif enable_key == "overlay_enable":
            ttk.Label(
                form,
                text="可视化叠加的图层树请在批处理页完整编辑。\n"
                     "点下方「在主页完整设置」载入本方案后编辑，\n"
                     "再回裂变页用「用主页刷新快照」。",
                foreground="gray", wraplength=440, justify="left",
            ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=8)

        def save():
            cfg[enable_key] = bool(en.get())
            if enable_key == "logo_enable":
                cfg["layer_enable"] = bool(en.get())
                cfg["logo_mode"] = "结尾覆盖落版"
            for k, v in fields.items():
                cfg[k] = v.get()
            for k, v in bool_fields.items():
                cfg[k] = bool(v.get())
            self._after_plan_change()
            win.destroy()
            self._toast(f"已保存「{label}」细节")

        def open_main():
            save()
            self._load_branch_to_main(scheme_idx, jump_key or None)

        bf = ttk.Frame(win)
        bf.pack(fill=X, padx=14, pady=12)
        ttk.Button(bf, text="在主页完整设置…", command=open_main).pack(side=LEFT)
        ttk.Button(bf, text="取消", command=win.destroy).pack(side=RIGHT, padx=4)
        ttk.Button(bf, text="保存", command=save).pack(side=RIGHT)

    def _load_branch_to_main(self, scheme_idx: int, jump_key: Optional[str] = None) -> None:
        branches = self._branch_list()
        if not (0 <= scheme_idx < len(branches)):
            return
        b = branches[scheme_idx]
        cfg = self._resolve_cfg_copy(b)
        # 载入主页时也用裂变页当前输入/输出，避免模板里旧路径捣乱
        in_dir = ""
        if self._folders:
            in_dir = (self._folders[0] or "").strip()
        if not in_dir:
            in_dir = (self.app.global_input_folder.get() or "").strip()
        out_dir = (self.app.global_output_folder.get() or "").strip()
        cfg = bind_fission_io_paths(cfg, in_path=in_dir, out_path=out_dir)
        try:
            self.app._apply_config_dict(cfg, io_mode="template")
        except Exception as exc:
            messagebox.showerror("错误", f"载入主页失败: {exc}", parent=self.root)
            return
        if getattr(self.app, "_sheet", None) is not None:
            try:
                self.app._sheet.select(0)
            except Exception:
                pass
        if jump_key and hasattr(self.app, "_jump_to_feature"):
            try:
                # 确保功能勾选
                fvar = self.app._feature_var(jump_key) if hasattr(self.app, "_feature_var") else None
                if fvar is not None:
                    fvar.set(True)
                self.app._jump_to_feature(jump_key)
            except Exception:
                pass
        messagebox.showinfo(
            "已载入主页",
            f"方案「{b.branch_name}」已载入视频批处理页。\n"
            f"输入/输出已对齐裂变页：\n输入：{in_dir or '（空）'}\n输出：{out_dir or '（空）'}\n\n"
            "在主页改完细节后，回到裂变页 → 选中该方案 ✎ →「用主页刷新快照」。",
            parent=self.root,
        )

    # ----- 新建 / 编辑 / 删除 -----

    def _dismiss_add_popup(self) -> None:
        pop = self._add_popup
        self._add_popup = None
        if pop is not None:
            try:
                pop.destroy()
            except Exception:
                pass

    def _show_add_popup_at(self, root_x: int, root_y: int) -> None:
        """双击落点：直接展示已有模板/方案 + 新建入口。"""
        self._dismiss_add_popup()
        th = self.th
        pop = tk.Toplevel(self.root)
        self._add_popup = pop
        pop.overrideredirect(True)
        pop.attributes("-topmost", True)
        pop.configure(bg=th["border"])

        outer = tk.Frame(pop, bg=th["card"], highlightthickness=1, highlightbackground=th["border"], padx=8, pady=8)
        outer.pack(padx=1, pady=1)

        tk.Label(outer, text="添加方案", bg=th["card"], fg=th["text"], font=("Microsoft YaHei", 11, "bold")).pack(anchor="w")
        tk.Label(outer, text="点一项即可 · Esc 关闭", bg=th["card"], fg=th["muted"], font=("", 8)).pack(anchor="w", pady=(0, 6))

        # 已有方案模板
        tk.Label(outer, text="— 已有方案模板 —", bg=th["card"], fg=th["muted"], font=("", 8)).pack(anchor="w")
        tpl_host = tk.Frame(outer, bg=th["card"])
        tpl_host.pack(fill=X)
        try:
            import video_batch_tool_v20 as v20
            names = list_template_names(v20._templates_dir())
        except Exception:
            names = []
        if not names:
            tk.Label(tpl_host, text="（暂无模板，请先在批处理页保存方案）", bg=th["card"], fg=th["muted"], font=("", 8)).pack(anchor="w")
        else:
            for name in names[:12]:
                def _add_tpl(tn=name):
                    self._dismiss_add_popup()
                    self._quick_add_from_template(tn)

                tk.Button(
                    tpl_host, text=f"  📋 {name}", anchor="w", bg=th["bg"], fg=th["text"],
                    relief="flat", cursor="hand2", command=_add_tpl,
                ).pack(fill=X, pady=1)

        # 本页已有方案
        branches = self._branch_list()
        tk.Label(outer, text="— 本页已有方案（克隆） —", bg=th["card"], fg=th["muted"], font=("", 8)).pack(anchor="w", pady=(8, 0))
        br_host = tk.Frame(outer, bg=th["card"])
        br_host.pack(fill=X)
        if not branches:
            tk.Label(br_host, text="（还没有方案）", bg=th["card"], fg=th["muted"], font=("", 8)).pack(anchor="w")
        else:
            for i, b in enumerate(branches[:10]):
                def _clone(idx=i):
                    self._dismiss_add_popup()
                    self._clone_branch_at(idx)

                tk.Button(
                    br_host, text=f"  📑 {b.branch_name}", anchor="w", bg=th["bg"], fg=th["text"],
                    relief="flat", cursor="hand2", command=_clone,
                ).pack(fill=X, pady=1)

        tk.Label(outer, text="— 新建 —", bg=th["card"], fg=th["muted"], font=("", 8)).pack(anchor="w", pady=(8, 0))
        new_host = tk.Frame(outer, bg=th["card"])
        new_host.pack(fill=X)

        def go_current():
            self._dismiss_add_popup()
            before = len(self._branch_list())
            self.app._fission_add_from_current()
            if len(self._branch_list()) > before:
                self._after_plan_change(select_last=True)
                self._toast("已从当前界面存为分支")

        def go_blank():
            self._dismiss_add_popup()
            self._create_blank_scheme()

        def go_more():
            self._dismiss_add_popup()
            self.app._fission_add_from_template()
            self._after_plan_change(select_last=True)

        tk.Button(new_host, text="  📄 从当前界面复制", anchor="w", bg=th["bg"], fg=th["text"], relief="flat", cursor="hand2", command=go_current).pack(fill=X, pady=1)
        tk.Button(new_host, text="  📝 新建空白方案", anchor="w", bg=th["bg"], fg=th["text"], relief="flat", cursor="hand2", command=go_blank).pack(fill=X, pady=1)
        tk.Button(new_host, text="  📂 更多模板…", anchor="w", bg=th["bg"], fg=th["text"], relief="flat", cursor="hand2", command=go_more).pack(fill=X, pady=1)

        pop.update_idletasks()
        pw, ph = pop.winfo_reqwidth(), pop.winfo_reqheight()
        sw, sh = pop.winfo_screenwidth(), pop.winfo_screenheight()
        x = min(max(8, root_x), sw - pw - 8)
        y = min(max(8, root_y), sh - ph - 8)
        pop.geometry(f"+{x}+{y}")
        pop.bind("<Escape>", lambda _e: self._dismiss_add_popup())
        pop.focus_force()
        # 点外面关闭
        pop.bind("<FocusOut>", lambda _e: self.root.after(150, self._maybe_close_popup))

    def _maybe_close_popup(self) -> None:
        pop = self._add_popup
        if pop is None:
            return
        try:
            if pop.focus_get() is None:
                self._dismiss_add_popup()
        except Exception:
            self._dismiss_add_popup()

    def _quick_add_from_template(self, template_name: str) -> None:
        plan = getattr(self.app, "_fission_plan", None)
        if plan is None:
            return
        bn = sanitize_branch_name(template_name)
        # 避免重名
        exist = {b.branch_name for b in plan.branches}
        base, n = bn, 2
        while bn in exist:
            bn = f"{base}-{n}"
            n += 1
        plan.branches.append(
            FissionBranch(enabled=True, branch_name=bn, template_name=template_name, note="引用模板"),
        )
        try:
            from modules import habi_memory
            habi_memory.remember_scheme(template_name)
        except Exception:
            pass
        self._after_plan_change(select_last=True)
        self._toast(f"已引用模板「{template_name}」")

    def _clone_branch_at(self, idx: int) -> None:
        branches = self._branch_list()
        if not (0 <= idx < len(branches)):
            return
        src = branches[idx]
        cfg = self._resolve_cfg_copy(src)
        cfg["global_input"] = ""
        cfg["global_output"] = ""
        name = sanitize_branch_name(f"{src.branch_name}-复制")
        self.app._fission_plan.branches.append(
            FissionBranch(enabled=True, branch_name=name, embedded_config=cfg, note="克隆"),
        )
        self._after_plan_change(select_last=True)
        self._toast(f"已克隆「{src.branch_name}」")

    def _create_new_scheme(self) -> None:
        try:
            x = self.canvas.winfo_rootx() + 80
            y = self.canvas.winfo_rooty() + 80
        except Exception:
            x, y = 200, 200
        self._show_add_popup_at(x, y)

    def _show_clone_picker(self) -> None:
        branches = self._branch_list()
        if not branches:
            messagebox.showinfo("提示", "本页还没有可克隆的方案，请先引用模板。", parent=self.root)
            return
        win = tk.Toplevel(self.root)
        win.title("克隆已有方案")
        win.transient(self.root)
        win.grab_set()
        win.geometry("360x320")
        ttk.Label(win, text="选择要复制的方案（含全部细节）").pack(anchor="w", padx=12, pady=10)
        lb = tk.Listbox(win, height=10)
        lb.pack(fill=BOTH, expand=True, padx=12)
        for b in branches:
            lb.insert(END, f"{b.branch_name}  ·  {b.display_source()}")

        def ok():
            sel = lb.curselection()
            if not sel:
                return
            src = branches[int(sel[0])]
            cfg = self._resolve_cfg_copy(src)
            cfg["global_input"] = ""
            cfg["global_output"] = ""
            name = sanitize_branch_name(f"{src.branch_name}-复制")
            self.app._fission_plan.branches.append(
                FissionBranch(enabled=True, branch_name=name, embedded_config=cfg, note="克隆"),
            )
            win.destroy()
            self._after_plan_change(select_last=True)
            self._toast(f"已克隆「{src.branch_name}」")

        bf = ttk.Frame(win)
        bf.pack(fill=X, padx=12, pady=10)
        ttk.Button(bf, text="取消", command=win.destroy).pack(side=RIGHT, padx=4)
        ttk.Button(bf, text="克隆", command=ok).pack(side=RIGHT)

    def _create_blank_scheme(self) -> None:
        plan = getattr(self.app, "_fission_plan", None)
        if plan is None:
            return
        n = len(plan.branches)
        letter = chr(65 + n) if n < 26 else str(n + 1)
        win = tk.Toplevel(self.root)
        win.title("新建空白方案")
        win.transient(self.root)
        win.grab_set()
        name_var = StringVar(value=f"方案{letter}")
        ttk.Label(win, text="方案名称（=输出文件夹）").pack(anchor="w", padx=12, pady=(12, 4))
        ttk.Entry(win, textvariable=name_var, width=36).pack(fill=X, padx=12)
        ttk.Label(win, text="创建后点子功能⚙配置比例/路径等细节", foreground="gray").pack(anchor="w", padx=12, pady=8)

        def ok():
            bn = sanitize_branch_name(name_var.get())
            if not bn:
                return
            try:
                cfg = dict(self.app._current_config_dict())
            except Exception:
                cfg = {}
            cfg["global_input"] = ""
            cfg["global_output"] = ""
            for key, *_rest in _FUNC_DEFS:
                cfg[key] = False
            plan.branches.append(
                FissionBranch(enabled=True, branch_name=bn, embedded_config=cfg, note="自建快照"),
            )
            win.destroy()
            self._after_plan_change(select_last=True)
            self._toast(f"已创建「{bn}」，请点子功能设置细节")

        bf = ttk.Frame(win)
        bf.pack(fill=X, padx=12, pady=12)
        ttk.Button(bf, text="取消", command=win.destroy).pack(side=RIGHT, padx=4)
        ttk.Button(bf, text="创建", command=ok).pack(side=RIGHT)

    def _edit_selected(self) -> None:
        idx = self._selected_idx
        if idx is None:
            try:
                idx = self.app._fission_selected_index()
            except Exception:
                idx = None
        if idx is None:
            messagebox.showinfo("提示", "请先选中一个方案", parent=self.root)
            return
        branches = self._branch_list()
        if not (0 <= idx < len(branches)):
            return
        self._select_branch(idx)
        b = branches[idx]
        cfg = self._ensure_mutable_config(b)

        win = tk.Toplevel(self.root)
        win.title(f"编辑方案：{b.branch_name}")
        win.transient(self.root)
        win.grab_set()
        win.geometry("420x520")

        name_var = StringVar(value=b.branch_name)
        en_var = BooleanVar(value=b.enabled)
        ttk.Checkbutton(win, text="启用此方案", variable=en_var).pack(anchor="w", padx=14, pady=(12, 4))
        ttk.Label(win, text="方案名称").pack(anchor="w", padx=14)
        ttk.Entry(win, textvariable=name_var, width=36).pack(fill=X, padx=14)
        ttk.Label(win, text=f"来源: {b.display_source()}", foreground="gray").pack(anchor="w", padx=14, pady=6)

        ttk.Label(win, text="功能（↑↓调整处理顺序，裂变时按此顺序剪辑）").pack(anchor="w", padx=14, pady=(4, 2))
        box = ttk.Frame(win)
        box.pack(fill=BOTH, expand=True, padx=14)
        vars_map: dict[str, BooleanVar] = {}
        ordered = self._ordered_func_defs(cfg)

        def rebuild_list():
            for w in box.winfo_children():
                w.destroy()
            nonlocal ordered
            ordered = self._ordered_func_defs(cfg)
            for fi, (key, label, _j, _d) in enumerate(ordered):
                row = ttk.Frame(box)
                row.pack(fill=X, pady=2)
                if key not in vars_map:
                    vars_map[key] = BooleanVar(value=bool(cfg.get(key)))
                ttk.Checkbutton(row, text=label, variable=vars_map[key]).pack(side=LEFT)
                ttk.Button(
                    row, text="设细节", width=6,
                    command=lambda i=fi, w=win: (w.destroy(), self._open_func_config(idx, i)),
                ).pack(side=RIGHT)
                ttk.Button(
                    row, text="↓", width=2,
                    command=lambda i=fi: _move(i, 1),
                ).pack(side=RIGHT, padx=1)
                ttk.Button(
                    row, text="↑", width=2,
                    command=lambda i=fi: _move(i, -1),
                ).pack(side=RIGHT, padx=1)

        def _move(fi: int, delta: int):
            keys = [d[0] for d in ordered]
            j = fi + delta
            if j < 0 or j >= len(keys):
                return
            keys[fi], keys[j] = keys[j], keys[fi]
            cfg[_ORDER_KEY] = keys
            rebuild_list()

        rebuild_list()

        def save():
            b.enabled = bool(en_var.get())
            b.branch_name = sanitize_branch_name(name_var.get())
            for key, v in vars_map.items():
                cfg[key] = bool(v.get())
            win.destroy()
            self._after_plan_change()
            self._toast("方案已保存")

        def refresh_from_main():
            if not messagebox.askyesno("确认", "用当前主页配置覆盖此方案快照？", parent=win):
                return
            try:
                new_cfg = dict(self.app._current_config_dict())
            except Exception as exc:
                messagebox.showerror("错误", str(exc), parent=win)
                return
            new_cfg["global_input"] = ""
            new_cfg["global_output"] = ""
            # 保留本方案已调好的处理顺序
            if isinstance(cfg.get(_ORDER_KEY), list):
                new_cfg[_ORDER_KEY] = list(cfg[_ORDER_KEY])
            b.embedded_config = new_cfg
            b.template_name = ""
            b.note = "自建快照"
            win.destroy()
            self._after_plan_change()
            self._toast("已用主页刷新快照")

        def to_main():
            win.destroy()
            self._load_branch_to_main(idx)

        bf = ttk.Frame(win)
        bf.pack(fill=X, padx=14, pady=10)
        ttk.Button(bf, text="载入主页编辑", command=to_main).pack(side=LEFT)
        ttk.Button(bf, text="用主页刷新快照", command=refresh_from_main).pack(side=LEFT, padx=6)
        ttk.Button(bf, text="取消", command=win.destroy).pack(side=RIGHT, padx=4)
        ttk.Button(bf, text="保存", command=save).pack(side=RIGHT)

    def _delete_selected(self) -> None:
        idx = self._selected_idx
        if idx is None:
            return
        branches = self._branch_list()
        if not (0 <= idx < len(branches)):
            return
        name = branches[idx].branch_name
        if not messagebox.askyesno("确认", f"删除方案「{name}」？", parent=self.root):
            return
        self.app._fission_plan.branches.pop(idx)
        self._selected_idx = None
        self._after_plan_change()

    def _toast(self, message: str) -> None:
        tip = tk.Toplevel(self.root)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        bg = self.th.get("check", "#84CC16")
        tk.Label(tip, text=message, bg=bg, fg="white", font=("Microsoft YaHei", 10), padx=16, pady=8).pack()
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + self.root.winfo_width() // 2 - 100
        y = self.root.winfo_rooty() + self.root.winfo_height() - 100
        tip.geometry(f"+{x}+{y}")
        tip.after(2000, tip.destroy)

    def _apply_selected(self) -> None:
        idx = self._selected_idx
        if idx is None:
            try:
                idx = self.app._fission_selected_index()
            except Exception:
                idx = None
        if idx is None:
            messagebox.showinfo("提示", "请先选中一个方案", parent=self.root)
            return
        branches = self._branch_list()
        if not (0 <= idx < len(branches)):
            return
        self._load_branch_to_main(idx)
        self.app.log(f"已应用裂变方案到主页: {branches[idx].branch_name}")

    def set_progress(self, branch_name: str, percent: float, label: str = "") -> None:
        self._progress[branch_name] = (max(0.0, min(100.0, percent)), label or f"{int(percent)}%")
        if self._view.get() == "mindmap":
            self.redraw()

    def refresh(self) -> None:
        self._sync_folders_from_app()
        self._rebuild_folder_list()
        if self._view.get() == "mindmap":
            self.redraw()
        else:
            self.app._fission_refresh_tree()
