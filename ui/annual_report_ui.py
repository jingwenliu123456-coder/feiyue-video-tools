#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""年度工具年报：翻页弹窗"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Callable, Optional

from modules.tool_stats import (
    OP_LABELS,
    dismiss_report,
    generate_annual_report_data,
    list_years_with_data,
    mark_report_seen,
    pick_manual_report_year,
    _in_auto_window,
)
from ui.annual_report_html import export_annual_report_html


class AnnualReportWindow:
    def __init__(
        self,
        parent: tk.Misc,
        year: int,
        *,
        is_auto_popup: bool = False,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        self.year = year
        self.is_auto_popup = is_auto_popup
        self._on_close = on_close
        self.data = generate_annual_report_data(year)
        self._page = 0

        self.top = tk.Toplevel(parent)
        self.top.title(f"{year} 年度工具报告")
        self.top.geometry("520x460")
        self.top.minsize(480, 400)
        self.top.transient(parent)
        self.top.configure(bg="#1a1a2e")
        self.top.protocol("WM_DELETE_WINDOW", self._on_close_window)

        self.container = tk.Frame(self.top, bg="#1a1a2e")
        self.container.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 4))

        nav = tk.Frame(self.top, bg="#1a1a2e")
        nav.pack(fill=tk.X, padx=16, pady=(0, 12))
        self.btn_prev = ttk.Button(nav, text="← 上一页", command=self._prev)
        self.btn_prev.pack(side=tk.LEFT)
        self.page_label = ttk.Label(nav, text="")
        self.page_label.pack(side=tk.LEFT, padx=12)
        self.btn_next = ttk.Button(nav, text="下一页 →", command=self._next)
        self.btn_next.pack(side=tk.RIGHT)

        self.pages: list[tk.Frame] = []
        self._build_pages()
        self._show_page(0)

        self.top.bind("<Left>", lambda _e: self._prev())
        self.top.bind("<Right>", lambda _e: self._next())
        self.top.bind("<Return>", lambda _e: self._next())

    def _on_close_window(self) -> None:
        if self.is_auto_popup and self._page == 0:
            dismiss_report(self.year, never_again=False)
        self.top.destroy()
        if self._on_close:
            self._on_close()

    def _frame(self) -> tk.Frame:
        f = tk.Frame(self.container, bg="#1a1a2e")
        self.pages.append(f)
        return f

    def _title(self, parent: tk.Frame, text: str, *, size: int = 20) -> None:
        tk.Label(
            parent, text=text, bg="#1a1a2e", fg="#eaeaea",
            font=("Microsoft YaHei", size, "bold"), justify=tk.CENTER,
        ).pack(pady=(24, 8))

    def _body(self, parent: tk.Frame, text: str, *, size: int = 12, color: str = "#cccccc") -> None:
        tk.Label(
            parent, text=text, bg="#1a1a2e", fg=color,
            font=("Microsoft YaHei", size), justify=tk.CENTER, wraplength=440,
        ).pack(pady=6)

    def _big_num(self, parent: tk.Frame, target: int) -> None:
        lbl = tk.Label(parent, text="0", bg="#1a1a2e", fg="#e94560", font=("Microsoft YaHei", 48, "bold"))
        lbl.pack(pady=8)
        self._animate_number(lbl, target)

    def _animate_number(self, label: tk.Label, target: int) -> None:
        if target <= 0:
            label.config(text="0")
            return
        step = max(1, target // 40)

        def tick(cur: int = 0) -> None:
            cur = min(target, cur + step)
            label.config(text=f"{cur:,}")
            if cur < target:
                label.after(30, lambda: tick(cur))

        tick()

    def _is_makeup(self) -> bool:
        return not _in_auto_window(datetime.now())

    def _build_pages(self) -> None:
        d = self.data

        # 1/7 封面
        p0 = self._frame()
        self._title(p0, f"🎬 {self.year} 年度工具报告")
        if self.is_auto_popup:
            if self._is_makeup():
                sub = (
                    f"你错过了 {self.year} 年底的自动提醒\n"
                    "但数据替你记着——剪过的视频、命过的名、熬过的夜"
                )
            else:
                sub = f"你的 {self.year} 年处理数据已生成\n点击查看回顾，或选择跳过"
        else:
            sub = "今年，工具陪你度过了\n无数个剪辑的日夜"
        self._body(p0, sub)
        if self.is_auto_popup:
            opt = tk.Frame(p0, bg="#1a1a2e")
            opt.pack(pady=10)
            self.never_var = tk.BooleanVar(value=False)
            tk.Checkbutton(
                opt, text="不再自动提醒（仍可在工具栏手动查看）",
                variable=self.never_var, bg="#1a1a2e", fg="#888888",
                selectcolor="#1a1a2e", activebackground="#1a1a2e",
                font=("Microsoft YaHei", 9),
            ).pack()
            btns = tk.Frame(p0, bg="#1a1a2e")
            btns.pack(pady=8)
            tk.Button(
                btns, text="开始回顾 →", bg="#e94560", fg="white", bd=0, padx=16, pady=6,
                font=("Microsoft YaHei", 11), command=self._start_from_cover,
            ).pack(side=tk.LEFT, padx=6)
            tk.Button(
                btns, text="跳过", bg="#333333", fg="#aaaaaa", bd=0, padx=16, pady=6,
                font=("Microsoft YaHei", 11), command=self._skip,
            ).pack(side=tk.LEFT, padx=6)
        else:
            ttk.Button(p0, text="开始回顾 →", command=lambda: self._show_page(1)).pack(pady=12)

        # 2/7 总量
        p1 = self._frame()
        self._title(p1, "今年，你一共处理了")
        self._big_num(p1, d.total_count)
        self._body(p1, "个文件 / 次操作")

        # 3/7 功能偏好
        p2 = self._frame()
        self._title(p2, "你最常用的功能")
        if d.by_type:
            top = sorted(d.by_type.items(), key=lambda x: -x[1])[:3]
            lines = []
            for i, (k, v) in enumerate(top):
                name = OP_LABELS.get(k, k)
                prefix = "最爱" if i == 0 else "其次"
                lines.append(f"{prefix}：{name}（{v} 次）")
            self._body(p2, "\n".join(lines))
        else:
            self._body(p2, "暂无记录，明年见！")

        # 4/7 时间印记
        p3 = self._frame()
        self._title(p3, "时间印记")
        parts = []
        if d.busiest_day[0]:
            parts.append(f"高峰日：{d.busiest_day[0]}\n一天处理了 {d.busiest_day[1]} 次")
        if d.busiest_month[0]:
            parts.append(f"高产月：{d.busiest_month[0]} 月（{d.busiest_month[1]} 次）")
        if d.streak_days > 1:
            parts.append(f"最长连续使用：{d.streak_days} 天")
        if d.first_use:
            parts.append(f"首次记录：{d.first_use}")
        self._body(p3, "\n\n".join(parts) if parts else "平稳的一年，也是一种节奏。")

        # 5/7 深夜
        p4 = self._frame()
        self._title(p4, "深夜的屏幕光")
        if d.night_ops > 0:
            t = d.latest_night[11:16] if len(d.latest_night) >= 16 else ""
            self._body(
                p4,
                f"有 {d.night_ops} 次操作发生在 23:00 之后或凌晨\n"
                + (f"最晚一次：{d.latest_night[:10]} {t}" if d.latest_night else ""),
            )
        else:
            self._body(p4, "你很注重作息，今年没有深夜加班记录。")

        # 6/7 称号
        p5 = self._frame()
        self._title(p5, "你的年度称号")
        self._body(p5, " · ".join(d.titles), size=16, color="#e94560")

        # 7/7 结尾
        p6 = self._frame()
        self._title(p6, f"{self.year}，感谢陪伴")
        self._body(p6, f"{self.year + 1} 年，我们继续一起\n把混乱的视频世界理得井井有条。")
        end_btns = tk.Frame(p6, bg="#1a1a2e")
        end_btns.pack(pady=12)
        ttk.Button(end_btns, text="生成 HTML 版（浏览器打开）", command=self._export_html).pack(side=tk.LEFT, padx=6)
        ttk.Button(end_btns, text="完成", command=self._finish).pack(side=tk.LEFT, padx=6)

        for i, p in enumerate(self.pages):
            p.place(relx=0, rely=0, relwidth=1, relheight=1)
            if i > 0:
                p.place_forget()

    def _show_page(self, idx: int) -> None:
        idx = max(0, min(len(self.pages) - 1, idx))
        self.pages[self._page].place_forget()
        self._page = idx
        self.pages[idx].place(relx=0, rely=0, relwidth=1, relheight=1)
        total = len(self.pages)
        self.page_label.config(text=f"第 {idx + 1} / {total} 页")
        self.btn_prev.config(state=tk.NORMAL if idx > 0 else tk.DISABLED)
        if idx >= total - 1:
            self.btn_next.config(text="完成", state=tk.NORMAL)
        else:
            self.btn_next.config(text="下一页 →", state=tk.NORMAL)

    def _prev(self) -> None:
        if self._page > 0:
            self._show_page(self._page - 1)

    def _next(self) -> None:
        if self._page >= len(self.pages) - 1:
            self._finish()
        else:
            self._show_page(self._page + 1)

    def _start_from_cover(self) -> None:
        if getattr(self, "never_var", None) and self.never_var.get():
            dismiss_report(self.year, never_again=True)
        mark_report_seen(self.year)
        self.is_auto_popup = False
        self._show_page(1)

    def _skip(self) -> None:
        never = bool(getattr(self, "never_var", None) and self.never_var.get())
        dismiss_report(self.year, never_again=never)
        self.top.destroy()
        if self._on_close:
            self._on_close()

    def _export_html(self) -> None:
        try:
            path = export_annual_report_html(self.year, open_browser=True)
            messagebox.showinfo(
                "HTML 年报",
                f"已在浏览器中打开。\n文件位置：\n{path}",
                parent=self.top,
            )
        except Exception as e:
            messagebox.showerror("HTML 年报", f"生成失败：{e}", parent=self.top)

    def _finish(self) -> None:
        mark_report_seen(self.year)
        self.top.destroy()
        if self._on_close:
            self._on_close()


def show_annual_report(
    parent: tk.Misc,
    year: int | None = None,
    *,
    is_auto_popup: bool = False,
) -> None:
    y = year or pick_manual_report_year()
    if y is None:
        messagebox.showinfo("年度工具年报", "暂无使用记录，先用工具处理一些视频吧！", parent=parent)
        return
    data = generate_annual_report_data(y)
    if data.total_count <= 0:
        messagebox.showinfo("年度工具年报", f"{y} 年暂无数据。", parent=parent)
        return
    AnnualReportWindow(parent, y, is_auto_popup=is_auto_popup)


def show_annual_report_year_picker(parent: tk.Misc) -> None:
    years = list_years_with_data()
    if not years:
        messagebox.showinfo("年度工具年报", "暂无使用记录。", parent=parent)
        return
    win = tk.Toplevel(parent)
    win.title("选择年份")
    win.transient(parent)
    ttk.Label(win, text="查看哪一年的报告？", padding=12).pack()
    var = tk.StringVar(value=str(years[0]))
    ttk.Combobox(win, textvariable=var, values=[str(y) for y in years], state="readonly", width=12).pack(
        padx=12, pady=4,
    )

    def _open() -> None:
        try:
            y = int(var.get())
        except ValueError:
            return
        win.destroy()
        show_annual_report(parent, y, is_auto_popup=False)

    ttk.Button(win, text="打开", command=_open).pack(pady=12)
