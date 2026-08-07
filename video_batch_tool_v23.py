#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频批处理工具 V23 — 批量裂变（重分支）

每一行分支 = 一套完整方案模板工作流（可引用现成模板，或把当前界面另存为自建快照）。
按表顺序执行：加载配置 → 自动创建 {输出根}/{分支名}/ → 从序号 1 批处理。
跑完后再用「重编号」接到共享盘序号。
"""

from __future__ import annotations

import json
import copy
import os
import threading
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, BooleanVar, StringVar, Toplevel, messagebox, simpledialog, ttk
from typing import Any, Optional

from video_batch_tool_v22 import VideoBatchToolV22 as _V22
import video_batch_tool_v20 as v20
from modules.fission_engine import (
    FissionBranch,
    FissionPlan,
    FissionSourceGroup,
    MAX_SOURCE_GROUPS,
    bind_fission_io_paths,
    branch_to_dict,
    list_template_names,
    load_fission_plan,
    new_group_id,
    plan_from_dict,
    plan_to_dict,
    renumber_files_in_folder,
    resolve_branch_config,
    resolve_group_branches,
    sanitize_branch_name,
    save_fission_plan,
    source_group_from_dict,
    source_group_to_dict,
)

APP_TITLE = "视频批处理工具 V23"


class VideoBatchToolV23(_V22):
    def __init__(self, root):
        self._fission_plan = FissionPlan(name="默认裂变")
        self._fission_running = False
        self.fission_plan_name_var = StringVar(value="默认裂变")
        super().__init__(root)
        if not getattr(root, "_habi_workbench_v24", False):
            try:
                self.root.title(APP_TITLE)
            except Exception:
                pass

    def _on_templates_catalog_changed(self) -> None:
        panel = getattr(self, "_fission_panel", None)
        if panel is not None and hasattr(panel, "refresh_template_catalog"):
            try:
                panel.refresh_template_catalog()
            except Exception:
                pass

    def build_ui(self):
        self.main_frame.columnconfigure(0, weight=1, uniform="main_col")
        self.main_frame.columnconfigure(1, weight=1, uniform="main_col")
        self.main_frame.columnconfigure(2, weight=1, uniform="main_col")

        row = 0
        row = self.build_global_io(row)
        row = self.build_global_actions(row)

        mod_row = row
        layout = self._get_v22_layout()
        max_rel_row = max((int(item.get("r", 0)) for item in layout), default=0)
        for r in range(mod_row, mod_row + max_rel_row + 1):
            self.main_frame.rowconfigure(r, weight=0, uniform="module_row")

        placed: set[str] = set()
        for item in layout:
            key = str(item.get("key", ""))
            if not key or key in placed:
                continue
            placed.add(key)
            abs_row = mod_row + int(item.get("r", 0))
            col = int(item.get("c", 0))
            rowspan = int(item.get("rowspan", 1))
            self._build_v22_module(key, abs_row, col, rowspan=rowspan)

        if "preview_canvas" not in placed:
            self._build_v22_module("preview_canvas", mod_row, 1, rowspan=1)

        row = mod_row + max_rel_row + 1
        row = self.build_fission_section(row)
        self.build_log_section(row)

    def build_fission_section(self, row: int) -> int:
        from modules.ui_skin import make_button

        card, _hdr, frame = self._module_card(
            self.main_frame, "批量裂变（V23）", "🌿", "fission",
        )
        self._grid_card(card, row, 0, colspan=3)

        tip = ttk.Label(
            frame,
            text="每一行 = 一套完整方案模板。按顺序跑：自动建「输出根/分支名」文件夹，序号从 1 开始；跑完再用重编号接共享盘。",
            wraplength=900,
            foreground="gray",
        )
        tip.pack(anchor="w", padx=6, pady=(4, 2))

        top = ttk.Frame(frame)
        top.pack(fill=X, padx=6, pady=2)
        ttk.Label(top, text="裂变方案名:").pack(side=LEFT)
        ttk.Entry(top, textvariable=self.fission_plan_name_var, width=24).pack(side=LEFT, padx=4)

        cols = ("en", "name", "src", "note")
        tree_wrap = ttk.Frame(frame)
        tree_wrap.pack(fill=BOTH, expand=True, padx=6, pady=4)
        self.fission_tree = ttk.Treeview(
            tree_wrap, columns=cols, show="headings", height=5, selectmode="browse",
        )
        self.fission_tree.heading("en", text="启用")
        self.fission_tree.heading("name", text="分支名(=输出文件夹)")
        self.fission_tree.heading("src", text="工作流来源")
        self.fission_tree.heading("note", text="备注")
        self.fission_tree.column("en", width=50, stretch=False, anchor="center")
        self.fission_tree.column("name", width=160, stretch=True)
        self.fission_tree.column("src", width=200, stretch=True)
        self.fission_tree.column("note", width=160, stretch=True)
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.fission_tree.yview)
        self.fission_tree.configure(yscrollcommand=vsb.set)
        self.fission_tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill="y")
        self.fission_tree.bind("<Double-1>", lambda _e: self._fission_edit_selected())

        btns = ttk.Frame(frame)
        btns.pack(fill=X, padx=6, pady=(2, 8))
        make_button(btns, "+ 引用模板", self._fission_add_from_template, kind="outline").pack(side=LEFT, padx=2)
        make_button(btns, "+ 当前界面存为分支", self._fission_add_from_current, kind="outline").pack(side=LEFT, padx=2)
        make_button(btns, "编辑", self._fission_edit_selected, kind="outline").pack(side=LEFT, padx=2)
        make_button(btns, "删除", self._fission_delete_selected, kind="danger").pack(side=LEFT, padx=2)
        make_button(btns, "↑", lambda: self._fission_move(-1), kind="tool", width=3).pack(side=LEFT, padx=2)
        make_button(btns, "↓", lambda: self._fission_move(1), kind="tool", width=3).pack(side=LEFT, padx=2)
        make_button(btns, "启/停", self._fission_toggle_selected, kind="outline").pack(side=LEFT, padx=2)

        make_button(btns, "💾 保存裂变方案", self._fission_save_plan, kind="outline").pack(side=RIGHT, padx=2)
        make_button(btns, "📂 加载", self._fission_load_plan, kind="outline").pack(side=RIGHT, padx=2)
        make_button(btns, "🔢 重编号…", self._fission_renumber_dialog, kind="info").pack(side=RIGHT, padx=8)
        make_button(btns, "🚀 一键裂变", self.start_fission, kind="success").pack(side=RIGHT, padx=2)

        self._fission_refresh_tree()
        return row + 1

    # ---------- 分支表 CRUD ----------

    def _fission_sync_name(self) -> None:
        self._fission_plan.name = (self.fission_plan_name_var.get() or "").strip() or "默认裂变"

    def _fission_refresh_tree(self) -> None:
        tree = getattr(self, "fission_tree", None)
        if tree is None:
            return
        for iid in tree.get_children():
            tree.delete(iid)
        for i, b in enumerate(self._fission_plan.branches):
            tree.insert(
                "", END, iid=str(i),
                values=(
                    "☑" if b.enabled else "☐",
                    b.branch_name,
                    b.display_source(),
                    b.note,
                ),
            )

    def _fission_selected_index(self) -> Optional[int]:
        tree = getattr(self, "fission_tree", None)
        if tree is None:
            return None
        sel = tree.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except ValueError:
            return None

    def _fission_add_from_template(self) -> None:
        names = list_template_names(v20._templates_dir())
        if not names:
            messagebox.showwarning("提示", "还没有方案模板。请先在顶栏「方案模板」里保存一套。", parent=self.root)
            return
        win = Toplevel(self.root)
        win.title("引用方案模板为分支")
        win.transient(self.root)
        win.grab_set()
        ttk.Label(win, text="分支名（同时作为输出子文件夹名）:").pack(anchor="w", padx=10, pady=(10, 2))
        name_var = StringVar(value=names[0])
        ttk.Entry(win, textvariable=name_var, width=36).pack(fill=X, padx=10)
        ttk.Label(win, text="方案模板:").pack(anchor="w", padx=10, pady=(8, 2))
        tpl_var = StringVar(value=names[0])
        ttk.Combobox(win, textvariable=tpl_var, values=names, state="readonly", width=34).pack(fill=X, padx=10)
        note_var = StringVar()
        ttk.Label(win, text="备注:").pack(anchor="w", padx=10, pady=(8, 2))
        ttk.Entry(win, textvariable=note_var, width=36).pack(fill=X, padx=10)

        def ok():
            bn = sanitize_branch_name(name_var.get())
            tn = (tpl_var.get() or "").strip()
            if not bn or not tn:
                messagebox.showwarning("提示", "请填写分支名并选择模板", parent=win)
                return
            self._fission_plan.branches.append(
                FissionBranch(enabled=True, branch_name=bn, template_name=tn, note=note_var.get().strip()),
            )
            self._fission_refresh_tree()
            win.destroy()

        bf = ttk.Frame(win)
        bf.pack(fill=X, padx=10, pady=12)
        ttk.Button(bf, text="取消", command=win.destroy).pack(side=RIGHT, padx=4)
        ttk.Button(bf, text="添加", command=ok).pack(side=RIGHT)

    def _fission_add_from_current(self) -> None:
        bn = simpledialog.askstring("当前界面存为分支", "分支名（=输出文件夹名）:", parent=self.root)
        bn = sanitize_branch_name(bn or "")
        if not bn:
            return
        cfg = copy.deepcopy(self._current_config_dict())
        # 不把输入输出写死进分支快照（执行时强制覆盖）
        cfg["global_input"] = ""
        cfg["global_output"] = ""
        self._fission_plan.branches.append(
            FissionBranch(
                enabled=True,
                branch_name=bn,
                template_name="",
                embedded_config=cfg,
                note="自建快照",
            ),
        )
        self._fission_refresh_tree()
        self.log(f"已添加自建分支: {bn}")

    def _fission_edit_selected(self) -> None:
        idx = self._fission_selected_index()
        if idx is None or not (0 <= idx < len(self._fission_plan.branches)):
            messagebox.showinfo("提示", "请先选中一行分支", parent=self.root)
            return
        b = self._fission_plan.branches[idx]
        win = Toplevel(self.root)
        win.title("编辑分支")
        win.transient(self.root)
        win.grab_set()
        name_var = StringVar(value=b.branch_name)
        note_var = StringVar(value=b.note)
        en_var = BooleanVar(value=b.enabled)
        ttk.Checkbutton(win, text="启用", variable=en_var).pack(anchor="w", padx=10, pady=(10, 4))
        ttk.Label(win, text="分支名:").pack(anchor="w", padx=10)
        ttk.Entry(win, textvariable=name_var, width=36).pack(fill=X, padx=10)
        ttk.Label(win, text="备注:").pack(anchor="w", padx=10, pady=(8, 0))
        ttk.Entry(win, textvariable=note_var, width=36).pack(fill=X, padx=10)
        ttk.Label(win, text=f"来源: {b.display_source()}", foreground="gray").pack(anchor="w", padx=10, pady=8)

        names = list_template_names(v20._templates_dir())
        tpl_var = StringVar(value=b.template_name)
        if names and not b.embedded_config:
            ttk.Label(win, text="改绑模板:").pack(anchor="w", padx=10)
            ttk.Combobox(win, textvariable=tpl_var, values=names, state="readonly", width=34).pack(fill=X, padx=10)

        def ok():
            b.enabled = bool(en_var.get())
            b.branch_name = sanitize_branch_name(name_var.get())
            b.note = note_var.get().strip()
            if not b.embedded_config and tpl_var.get().strip():
                b.template_name = tpl_var.get().strip()
            self._fission_refresh_tree()
            win.destroy()

        bf = ttk.Frame(win)
        bf.pack(fill=X, padx=10, pady=12)
        ttk.Button(bf, text="取消", command=win.destroy).pack(side=RIGHT, padx=4)
        ttk.Button(bf, text="保存", command=ok).pack(side=RIGHT)

        def refresh_snapshot():
            if not messagebox.askyesno("确认", "用当前界面配置覆盖该分支的自建快照？", parent=win):
                return
            cfg = copy.deepcopy(self._current_config_dict())
            cfg["global_input"] = ""
            cfg["global_output"] = ""
            b.embedded_config = cfg
            b.template_name = ""
            b.note = (b.note or "自建快照").strip()
            self._fission_refresh_tree()
            messagebox.showinfo("完成", "已用当前界面更新该分支快照", parent=win)

        if b.embedded_config is not None:
            ttk.Button(win, text="用当前界面刷新快照", command=refresh_snapshot).pack(pady=(0, 8))

    def _fission_delete_selected(self) -> None:
        idx = self._fission_selected_index()
        if idx is None:
            return
        if not messagebox.askyesno("确认", "删除选中分支？", parent=self.root):
            return
        self._fission_plan.branches.pop(idx)
        self._fission_refresh_tree()

    def _fission_toggle_selected(self) -> None:
        idx = self._fission_selected_index()
        if idx is None:
            return
        b = self._fission_plan.branches[idx]
        b.enabled = not b.enabled
        self._fission_refresh_tree()

    def _fission_move(self, delta: int) -> None:
        idx = self._fission_selected_index()
        if idx is None:
            return
        j = idx + delta
        if j < 0 or j >= len(self._fission_plan.branches):
            return
        br = self._fission_plan.branches
        br[idx], br[j] = br[j], br[idx]
        self._fission_refresh_tree()
        self.fission_tree.selection_set(str(j))

    def _fission_plans_dir(self) -> Path:
        d = v20.config_path("fission_plans")
        d.mkdir(parents=True, exist_ok=True)
        return Path(d)

    def _fission_save_plan(self) -> None:
        from tkinter import filedialog

        self._fission_sync_name()
        panel = getattr(self, "_fission_panel", None)
        if panel is not None and hasattr(panel, "sync_groups_to_plan"):
            try:
                panel.sync_groups_to_plan()
            except Exception:
                pass
        default = self._fission_plans_dir() / f"{sanitize_branch_name(self._fission_plan.name)}.json"
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="保存裂变方案",
            defaultextension=".json",
            initialdir=str(self._fission_plans_dir()),
            initialfile=default.name,
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            save_fission_plan(path, self._fission_plan)
            self.log(f"裂变方案已保存: {path}")
            try:
                from modules import habi_memory
                habi_memory.remember_fission_plan(Path(path).stem)
            except Exception:
                pass
            messagebox.showinfo("完成", f"已保存：\n{path}", parent=self.root)
        except Exception as e:
            messagebox.showerror("错误", str(e), parent=self.root)

    def _fission_load_plan(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            parent=self.root,
            title="加载裂变方案",
            initialdir=str(self._fission_plans_dir()),
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            plan = load_fission_plan(path)
            self._fission_plan = plan
            self.fission_plan_name_var.set(plan.name)
            self._fission_refresh_tree()
            panel = getattr(self, "_fission_panel", None)
            if panel is not None:
                if hasattr(panel, "on_plan_loaded"):
                    try:
                        panel.on_plan_loaded()
                    except Exception:
                        pass
                elif hasattr(panel, "_rebuild_source_group_cards"):
                    try:
                        panel._rebuild_source_group_cards()
                    except Exception:
                        pass
            try:
                from modules import habi_memory
                habi_memory.remember_fission_plan(Path(path).stem)
            except Exception:
                pass
            self.log(f"已加载裂变方案: {path}")
        except Exception as e:
            messagebox.showerror("错误", str(e), parent=self.root)

    # ---------- P2 执行 ----------

    def _on_fission_finished(self, out_root: str, n_branches: int) -> None:
        messagebox.showinfo(
            "裂变完成",
            f"已处理 {n_branches} 个分支。\n输出根：{out_root}\n\n"
            "命名建议：每个方案文件夹里的成片，可到「规范命名」页统一改名。\n"
            "如需接共享盘序号，点「重编号」。",
            parent=self.root,
        )

    def start_fission(self) -> None:
        if self._processing or self._fission_running:
            messagebox.showwarning("提示", "已有任务在运行", parent=self.root)
            return

        panel = getattr(self, "_fission_panel", None)
        if panel is not None and hasattr(panel, "refresh_template_catalog"):
            try:
                panel.refresh_template_catalog()
            except Exception:
                pass
        if panel is not None and hasattr(panel, "sync_groups_to_plan"):
            try:
                panel.sync_groups_to_plan()
            except Exception:
                pass

        groups = list(self._fission_plan.enabled_groups())
        if not groups:
            in_dir = (self.global_input_folder.get() or "").strip()
            out_root = (self.global_output_folder.get() or "").strip()
            branches = self._fission_plan.enabled_branches()
            if not branches:
                messagebox.showwarning("提示", "请至少在画布上添加并启用一个裂变方案。", parent=self.root)
                return
            if not in_dir or not os.path.isdir(in_dir):
                messagebox.showwarning("提示", "请先设置有效的输入文件夹（或添加源素材组）。", parent=self.root)
                return
            if not out_root:
                messagebox.showwarning("提示", "请先设置全局输出根目录。", parent=self.root)
                return
            pp = self._fission_preprocess_options()
            groups = [
                FissionSourceGroup(
                    group_id=new_group_id(),
                    enabled=True,
                    title="默认组",
                    input_folder=in_dir,
                    output_folder=out_root,
                    preprocess_enable=bool(pp.get("enable")),
                    preprocess_template=str(pp.get("template") or ""),
                    preprocess_temp_mode=str(pp.get("temp_mode") or "自动清理"),
                    preprocess_temp_path=str(pp.get("temp_path") or ""),
                    selected_branch_names=[],
                )
            ]

        panel = getattr(self, "_fission_panel", None)
        io_mode = getattr(getattr(panel, "_io_mode", None), "get", lambda: "单源")()
        single_source = io_mode != "多源"

        problems: list[str] = []
        runnable: list[tuple[FissionSourceGroup, list[FissionBranch]]] = []
        for g in groups:
            title = g.display_title()
            in_dir = (g.input_folder or "").strip()
            if not in_dir or not os.path.isdir(in_dir):
                problems.append(f"「{title}」：输入文件夹无效")
                continue
            brs = resolve_group_branches(
                g, self._fission_plan.branches,
                empty_means_all=single_source,
            )
            if not brs:
                problems.append(f"「{title}」：未勾选任何裂变方案")
                continue
            if g.preprocess_enable:
                tpl = (g.preprocess_template or "").strip()
                if not tpl:
                    problems.append(f"「{title}」：已开预处理但未选模板")
                    continue
                if not (v20._templates_dir() / f"{tpl}.json").is_file():
                    problems.append(f"「{title}」：预处理模板不存在「{tpl}」")
                    continue
                if g.preprocess_temp_mode == "指定路径" and not (g.preprocess_temp_path or "").strip():
                    problems.append(f"「{title}」：预处理选了指定路径但未填写")
                    continue
            out = (g.output_folder or "").strip() or (self.global_output_folder.get() or "").strip()
            if not out:
                problems.append(f"「{title}」：未设置输出目录（组内或全局输出根）")
                continue
            if g.preprocess_enable:
                try:
                    pp_dir = self._resolve_preprocess_temp_dir(
                        out,
                        {
                            "temp_mode": g.preprocess_temp_mode,
                            "temp_path": g.preprocess_temp_path,
                            "template": g.preprocess_template,
                        },
                        group_key=title,
                    )
                    if os.path.normcase(os.path.abspath(pp_dir)) == os.path.normcase(os.path.abspath(in_dir)):
                        problems.append(
                            f"「{title}」：预处理成品目录不能与素材文件夹相同（会清空源视频）"
                        )
                        continue
                except Exception as e:
                    problems.append(f"「{title}」：预处理目录无效 — {e}")
                    continue
            runnable.append((g, brs))

        if problems:
            messagebox.showerror(
                "无法开始",
                "请先修正以下问题：\n\n" + "\n".join(f"· {p}" for p in problems[:15]),
                parent=self.root,
            )
            return
        if not runnable:
            messagebox.showwarning("提示", "没有可执行的源素材组。", parent=self.root)
            return

        lines = []
        for g, brs in runnable:
            pp = f"预处理「{g.preprocess_template}」→ " if g.preprocess_enable else ""
            names = "、".join(b.branch_name for b in brs)
            in_dir = (g.input_folder or "").strip()
            out = (g.output_folder or "").strip() or (self.global_output_folder.get() or "").strip()
            lines.append(f"· {g.display_title()}：{pp}{names}")
            lines.append(f"    输入: {in_dir}")
            lines.append(f"    输出根: {out}")
            if g.preprocess_enable:
                try:
                    pp_dir = self._resolve_preprocess_temp_dir(
                        out,
                        {
                            "temp_mode": g.preprocess_temp_mode,
                            "temp_path": g.preprocess_temp_path,
                            "template": g.preprocess_template,
                        },
                        group_key=g.display_title(),
                    )
                    lines.append(f"    预处理成品: {pp_dir}")
                except Exception:
                    pass
        if not messagebox.askyesno(
            "开始批量裂变",
            f"共 {len(runnable)} 个源素材组（组间串行）。\n\n"
            + "\n".join(lines)
            + "\n\n请确认路径无误后再开始。",
            parent=self.root,
        ):
            return

        snapshot = copy.deepcopy(self._current_config_dict())
        from modules.fission_engine import branch_to_dict, source_group_to_dict

        payload = [
            (source_group_to_dict(g), [branch_to_dict(b) for b in brs])
            for g, brs in runnable
        ]
        threading.Thread(
            target=self._fission_worker_groups,
            args=(payload, snapshot),
            daemon=True,
        ).start()

    def _fission_preprocess_options(self) -> dict:
        panel = getattr(self, "_fission_panel", None)
        if panel is not None and hasattr(panel, "get_preprocess_options"):
            try:
                return dict(panel.get_preprocess_options())
            except Exception:
                pass
        return {"enable": False, "template": "", "temp_mode": "自动清理", "temp_path": ""}

    def _resolve_preprocess_temp_dir(self, out_root: str, preprocess: dict, *, group_key: str = "") -> str:
        mode = str(preprocess.get("temp_mode") or "自动清理").strip()
        if mode == "指定路径":
            path = str(preprocess.get("temp_path") or "").strip()
            if not path:
                raise ValueError("未指定预处理临时目录")
            Path(path).mkdir(parents=True, exist_ok=True)
            return path
        # 成品目录用预处理模板名，便于辨认（前缀避免和方案子文件夹重名）
        tpl = sanitize_branch_name(str(preprocess.get("template") or "").strip()) or "预处理"
        gkey = sanitize_branch_name(str(group_key or "").strip())
        if gkey and gkey not in ("单源", "默认组"):
            sub = f"_预处理_{gkey}_{tpl}"
        else:
            sub = f"_预处理_{tpl}"
        path = os.path.join(out_root, sub)
        Path(path).mkdir(parents=True, exist_ok=True)
        return path

    def _fission_worker_groups(self, payload: list, snapshot: dict[str, Any]) -> None:
        """多源素材组串行：每组可选预处理 → 再跑本组勾选的裂变方案。"""
        from modules.fission_engine import branch_from_dict, source_group_from_dict

        self._fission_running = True
        self._processing = True
        self._ui_batch_quiet = True  # 整段裂变期间抑制侧栏/时间轴刷新
        self._fission_phase_label = ""
        self._fission_preprocess_outputs = []
        ctl = getattr(self, "_batch_ctl", None)
        if ctl is not None:
            ctl.begin()
        templates_dir = v20._templates_dir()
        last_out = (self.global_output_folder.get() or "").strip()
        n_branch_total = 0
        panel = getattr(self, "_fission_panel", None)

        def _ui_run_progress(**kw) -> None:
            if panel is not None and hasattr(panel, "set_run_progress"):
                self.root.after(0, lambda k=kw: panel.set_run_progress(**k))

        def _ui_clear_run_progress() -> None:
            if panel is not None and hasattr(panel, "clear_run_progress"):
                self.root.after(0, panel.clear_run_progress)

        try:
            _ui_clear_run_progress()
        except Exception:
            pass

        def _apply_on_ui(cfg: dict, *, in_path: str, out_path: str) -> None:
            done = threading.Event()
            err: list[BaseException] = []

            def _do():
                try:
                    # 强制用裂变输入/输出，覆盖模板里写死的路径（含叠加视频文件夹）
                    bound = bind_fission_io_paths(cfg, in_path=in_path, out_path=out_path)
                    self._apply_config_dict(bound, io_mode="template")
                    self.global_input_folder.set(in_path)
                    self.global_output_folder.set(out_path)
                except BaseException as e:
                    err.append(e)
                finally:
                    done.set()

            self.root.after(0, _do)
            if not done.wait(timeout=60):
                raise TimeoutError("应用配置超时")
            if err:
                raise err[0]

        def _clear_dir_files(folder: str) -> None:
            p = Path(folder)
            if not p.is_dir():
                return
            for old in p.iterdir():
                try:
                    if old.is_file():
                        old.unlink()
                except OSError:
                    pass

        def _list_out_videos(folder: str) -> list[str]:
            if hasattr(self, "_list_videos"):
                try:
                    return list(self._list_videos(folder) or [])
                except Exception:
                    pass
            return [
                x.name for x in Path(folder).iterdir()
                if x.is_file() and x.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}
            ]

        try:
            self.log(f"\n======== 批量裂变开始 | 源素材组={len(payload)}（串行）========")
            self.log("快捷键：空格=暂停/继续 · Esc=停止")
            fission_stopped = False
            for gi, (gdict, br_dicts) in enumerate(payload, 1):
                if ctl is not None and (ctl.should_stop or ctl.wait_if_paused()):
                    self.log("用户停止裂变")
                    fission_stopped = True
                    break
                g = source_group_from_dict(gdict)
                branches = [branch_from_dict(x) for x in br_dicts]
                title = g.display_title()
                in_dir = g.input_folder.strip()
                out_root = (g.output_folder or "").strip() or last_out
                Path(out_root).mkdir(parents=True, exist_ok=True)
                last_out = out_root
                self.log(f"\n######## [{gi}/{len(payload)}] 源组「{title}」########")
                self.log(f"输入: {in_dir}")
                self.log(f"输出根: {out_root}")
                _ui_run_progress(phase=f"源组 {gi}/{len(payload)} · {title}", file_name="", percent=0.0)

                work_in = in_dir
                temp_dir = None
                should_cleanup = False

                def _ui_progress(name: str, pct: float, label: str) -> None:
                    panel = getattr(self, "_fission_panel", None)
                    if panel is not None and hasattr(panel, "set_progress"):
                        self.root.after(0, lambda n=name, p=pct, l=label: panel.set_progress(n, p, l))

                def _ui_status(msg: str) -> None:
                    self.root.after(0, lambda m=msg: self.status_var.set(m))

                if g.preprocess_enable:
                    tpl_name = g.preprocess_template.strip()
                    pp = {
                        "temp_mode": g.preprocess_temp_mode,
                        "temp_path": g.preprocess_temp_path,
                        "template": tpl_name,
                    }
                    temp_dir = self._resolve_preprocess_temp_dir(out_root, pp, group_key=title)
                    should_cleanup = g.preprocess_temp_mode == "自动清理"
                    pp_label = f"_预处理_{sanitize_branch_name(tpl_name)}"
                    self._fission_phase_label = f"预处理·{tpl_name}"
                    _ui_status(f"预处理「{tpl_name}」…")
                    _ui_progress(pp_label, 5, "预处理开始")
                    _ui_run_progress(phase=f"预处理 · {tpl_name}", percent=5.0, label="准备中")
                    self.log(f"----- 第1级预处理「{tpl_name}」→ {temp_dir} -----")
                    try:
                        pp_cfg = resolve_branch_config(
                            FissionBranch(enabled=True, branch_name="_pp", template_name=tpl_name),
                            templates_dir=templates_dir,
                        )
                        # 清空成品目录旧视频，避免混入上次残留
                        _clear_dir_files(temp_dir)
                        # 预处理：输入=本组素材；输出=预处理成品目录
                        _apply_on_ui(pp_cfg, in_path=in_dir, out_path=temp_dir)
                        _ui_progress(pp_label, 20, "预处理编码中…")
                        self.process_batch(silent=True)
                        self._processing = True
                        outs = _list_out_videos(temp_dir)
                        if not outs:
                            raise RuntimeError("预处理没有产出视频（请检查预处理模板是否启用了功能）")
                        work_in = temp_dir
                        self.log(f"  预处理成品 {len(outs)} 个 → {temp_dir}")
                        self.log(f"  第2级裂变将以此成品目录为输入")
                        _ui_progress(pp_label, 100, f"预处理完成 · {len(outs)}个")
                        # 记住成品目录，裂变页右侧可打开
                        try:
                            outs_list = list(getattr(self, "_fission_preprocess_outputs", []) or [])
                            outs_list.append({"name": pp_label, "path": temp_dir, "template": tpl_name})
                            self._fission_preprocess_outputs = outs_list
                            panel = getattr(self, "_fission_panel", None)
                            if panel is not None:
                                self.root.after(0, panel.redraw)
                        except Exception:
                            pass
                    except Exception as e:
                        self.log(f"  预处理失败，跳过本组: {e}")
                        self._log_exception("fission_preprocess", e)
                        _ui_progress(pp_label, 0, f"预处理失败")
                        continue

                for bi, branch in enumerate(branches, 1):
                    if ctl is not None and (ctl.should_stop or ctl.wait_if_paused()):
                        self.log("用户停止裂变")
                        fission_stopped = True
                        break
                    bname = sanitize_branch_name(branch.branch_name)
                    out_dir = os.path.join(out_root, bname)
                    os.makedirs(out_dir, exist_ok=True)
                    self._fission_phase_label = f"方案·{bname}"
                    _ui_status(f"方案「{bname}」({bi}/{len(branches)})…")
                    _ui_progress(bname, 5, "开始")
                    n_files = len(_list_out_videos(work_in)) if work_in else 0
                    self._fission_batch_file_total = n_files
                    _ui_run_progress(
                        phase=f"方案 {bi}/{len(branches)} · {bname}",
                        file_name="",
                        file_idx=0,
                        file_total=max(n_files, 1),
                        percent=5.0,
                        label="开始",
                    )
                    self.log(f"----- [{bi}/{len(branches)}] 方案 {bname} ({branch.display_source()}) -----")
                    try:
                        cfg = resolve_branch_config(branch, templates_dir=templates_dir)
                        _apply_on_ui(cfg, in_path=work_in, out_path=out_dir)
                        _ui_progress(bname, 20, "编码中…")
                        self.process_batch(silent=True)
                        n_branch_total += 1
                        _ui_progress(bname, 100, "完成")
                    except Exception as e:
                        self.log(f"  方案失败: {e}")
                        self._log_exception("fission_branch", e)
                        _ui_progress(bname, 0, "失败")
                    self._processing = True
                    self.log(f"  完成 → {out_dir}")

                if fission_stopped:
                    break

                if should_cleanup and temp_dir and os.path.isdir(temp_dir):
                    try:
                        import shutil
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        self.log(f"已清理预处理临时目录: {temp_dir}")
                        # 清理后从可打开列表去掉
                        try:
                            kept = [
                                x for x in (getattr(self, "_fission_preprocess_outputs", []) or [])
                                if str(x.get("path") or "") != temp_dir
                            ]
                            self._fission_preprocess_outputs = kept
                        except Exception:
                            pass
                    except Exception as e:
                        self.log(f"清理临时目录失败: {e}")

            self._fission_phase_label = ""
            self.log("\n======== 批量裂变全部结束 ========")
            _ui_clear_run_progress()
            # 先记住输出根，避免 finally 还原快照后命名页找不到
            try:
                self._last_fission_out_root = (last_out or "").strip()
            except Exception:
                pass
            self.root.after(0, lambda r=last_out, n=n_branch_total: self._on_fission_finished(r, n))
        finally:
            try:
                done = threading.Event()
                remember_out = (last_out or "").strip()

                def _restore():
                    try:
                        self._pipeline_order_override = None
                        self._apply_config_dict(snapshot, io_mode="template")
                        self._pipeline_order_override = None
                        # 快照可能把输出指回旧值；裂变输出根必须保留给命名页
                        if remember_out:
                            self.global_output_folder.set(remember_out)
                            self._last_fission_out_root = remember_out
                    finally:
                        self._ui_batch_quiet = False
                        done.set()
                        try:
                            if hasattr(self, "_refresh_workspace_sidebars"):
                                self._refresh_workspace_sidebars()
                        except Exception:
                            pass

                self.root.after(0, _restore)
                done.wait(timeout=60)
            except Exception:
                self._pipeline_order_override = None
                self._ui_batch_quiet = False
            self._fission_phase_label = ""
            ctl = getattr(self, "_batch_ctl", None)
            if ctl is not None:
                ctl.end()
            self._fission_running = False
            self._processing = False
            try:
                _ui_clear_run_progress()
            except Exception:
                pass

    def _fission_worker(
        self,
        in_dir: str,
        out_root: str,
        branches: list[FissionBranch],
        snapshot: dict[str, Any],
        preprocess: dict | None = None,
    ) -> None:
        """兼容旧调用：转成单源组执行。"""
        from modules.fission_engine import branch_to_dict, source_group_to_dict

        preprocess = preprocess if isinstance(preprocess, dict) else {}
        g = FissionSourceGroup(
            group_id=new_group_id(),
            title="默认组",
            input_folder=in_dir,
            output_folder=out_root,
            preprocess_enable=bool(preprocess.get("enable")),
            preprocess_template=str(preprocess.get("template") or ""),
            preprocess_temp_mode=str(preprocess.get("temp_mode") or "自动清理"),
            preprocess_temp_path=str(preprocess.get("temp_path") or ""),
        )
        payload = [(source_group_to_dict(g), [branch_to_dict(b) for b in branches])]
        self._fission_worker_groups(payload, snapshot)

    # ---------- P3 重编号 ----------

    def _fission_renumber_dialog(self) -> None:
        from modules.ui_skin import make_button

        win = Toplevel(self.root)
        win.title("成品重编号")
        win.transient(self.root)
        win.grab_set()
        ttk.Label(
            win,
            text="选择裂变后的某个分支输出文件夹，按文件排序把开头序号改成从指定数字起。",
            wraplength=420,
        ).pack(anchor="w", padx=12, pady=(12, 6))

        folder_var = StringVar(value=(self.global_output_folder.get() or "").strip())
        start_var = StringVar(value="1")
        width_var = StringVar(value="3")

        row = ttk.Frame(win)
        row.pack(fill=X, padx=12, pady=4)
        ttk.Label(row, text="文件夹:").pack(side=LEFT)
        ttk.Entry(row, textvariable=folder_var, width=42).pack(side=LEFT, padx=4)

        def browse():
            from tkinter import filedialog
            p = filedialog.askdirectory(parent=win, initialdir=folder_var.get() or None)
            if p:
                folder_var.set(p)

        make_button(row, "浏览", browse, kind="outline", width=6).pack(side=LEFT)

        row2 = ttk.Frame(win)
        row2.pack(fill=X, padx=12, pady=4)
        ttk.Label(row2, text="起始序号:").pack(side=LEFT)
        ttk.Entry(row2, textvariable=start_var, width=8).pack(side=LEFT, padx=4)
        ttk.Label(row2, text="位数:").pack(side=LEFT, padx=(12, 0))
        ttk.Entry(row2, textvariable=width_var, width=4).pack(side=LEFT, padx=4)

        def preview():
            try:
                changes = renumber_files_in_folder(
                    folder_var.get().strip(),
                    start_index=int(start_var.get() or "1"),
                    index_width=int(width_var.get() or "3"),
                    dry_run=True,
                )
            except Exception as e:
                messagebox.showerror("错误", str(e), parent=win)
                return
            if not changes:
                messagebox.showinfo("预览", "无需改名（已是目标序号或没有媒体文件）", parent=win)
                return
            lines = "\n".join(f"{a}  →  {b}" for a, b in changes[:30])
            more = "" if len(changes) <= 30 else f"\n…共 {len(changes)} 个"
            messagebox.showinfo("预览", lines + more, parent=win)

        def apply():
            folder = folder_var.get().strip()
            try:
                start = int(start_var.get() or "1")
                width = int(width_var.get() or "3")
                changes = renumber_files_in_folder(folder, start_index=start, index_width=width, dry_run=True)
            except Exception as e:
                messagebox.showerror("错误", str(e), parent=win)
                return
            if not changes:
                messagebox.showinfo("完成", "没有需要改名的文件", parent=win)
                return
            if not messagebox.askyesno("确认", f"将对 {len(changes)} 个文件重命名，继续？", parent=win):
                return
            try:
                renumber_files_in_folder(folder, start_index=start, index_width=width, dry_run=False)
                self.log(f"重编号完成: {folder} 从 {start} 起，共 {len(changes)} 个")
                messagebox.showinfo("完成", f"已重命名 {len(changes)} 个文件", parent=win)
                win.destroy()
            except Exception as e:
                messagebox.showerror("错误", str(e), parent=win)

        bf = ttk.Frame(win)
        bf.pack(fill=X, padx=12, pady=12)
        make_button(bf, "预览", preview, kind="outline").pack(side=LEFT)
        make_button(bf, "取消", win.destroy, kind="outline").pack(side=RIGHT, padx=4)
        make_button(bf, "执行重编号", apply, kind="success").pack(side=RIGHT)


def main():
    from modules.ui_skin import UI_THEME_NONE, create_window
    from modules.platform_utils import config_path

    v21_cfg = config_path("video_batch_config_v21.json")
    ui_theme = "darkly"
    try:
        if os.path.isfile(v21_cfg):
            with open(v21_cfg, "r", encoding="utf-8") as f:
                ui_theme = str(json.load(f).get("ui_theme", "darkly"))
    except Exception:
        ui_theme = "darkly"

    try:
        if ui_theme == UI_THEME_NONE:
            root = create_window(title=APP_TITLE, use_bootstrap=False)
        else:
            root = create_window(title=APP_TITLE, themename=ui_theme)
    except Exception:
        from tkinter import Tk

        root = Tk()
        root._ui_theme = ui_theme  # noqa: SLF001

    VideoBatchToolV23(root)
    root.mainloop()


if __name__ == "__main__":
    main()
