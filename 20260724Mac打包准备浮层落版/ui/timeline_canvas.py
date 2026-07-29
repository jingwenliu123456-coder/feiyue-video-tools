#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双轨道时间轴预览（主视频 + 浮层落版）
用于可视化拖动「结尾前X秒」。
"""

from __future__ import annotations

import tkinter as tk


class TimelineCanvas(tk.Canvas):
  LEAD_MIN = 0.1
  LEAD_MAX = 10.0
  SNAP = 0.1

  def __init__(self, parent, *, width: int = 620, height: int = 130, **kwargs):
    super().__init__(
      parent, width=width, height=height, bg="#f6f7f9",
      highlightthickness=1, highlightbackground="#ddd", **kwargs,
    )
    self.main_duration = 30.0
    self.overlay_duration = 3.0
    self.lead_time = 1.0

    self._pad_l = 50
    self._pad_r = 20
    self._y_main = 34
    self._y_ov = 72
    self._h = 18

    self._dragging = False
    self._drag_start_x = 0.0
    self._drag_start_time = 0.0

    self.on_lead_changed = None  # callable(lead_time: float)

    self.bind("<Configure>", lambda _e: self.redraw())
    self.bind("<Button-1>", self._on_down)
    self.bind("<B1-Motion>", self._on_move)
    self.bind("<ButtonRelease-1>", self._on_up)

    self.redraw()

  def _timeline_duration(self) -> float:
    start = self._overlay_start_time()
    return max(self.main_duration, start + self.overlay_duration, 0.1)

  def set_durations(self, main_duration: float, overlay_duration: float):
    self.main_duration = max(0.1, float(main_duration or 0.1))
    self.overlay_duration = max(0.0, float(overlay_duration or 0.0))
    self.lead_time = self._clamp_lead(self.lead_time)
    self.redraw()

  def set_lead_time(self, lead_time: float):
    self.lead_time = self._clamp_lead(lead_time)
    self.redraw()

  def _clamp_lead(self, lead: float) -> float:
    v = round(float(lead or 0) / self.SNAP) * self.SNAP
    return max(self.LEAD_MIN, min(self.LEAD_MAX, v))

  def _overlay_start_time(self) -> float:
    return max(0.0, self.main_duration - self.lead_time)

  def _usable_w(self) -> int:
    w = int(self.winfo_width() or int(self["width"]))
    return max(10, w - self._pad_l - self._pad_r)

  def _t_to_x(self, t: float) -> float:
    span = self._timeline_duration()
    return self._pad_l + (float(t) / span) * self._usable_w()

  def _x_to_t(self, x: float) -> float:
    span = self._timeline_duration()
    r = (float(x) - self._pad_l) / max(1.0, float(self._usable_w()))
    return max(0.0, min(span, r * span))

  def redraw(self):
    self.delete("all")
    span = self._timeline_duration()
    u = self._usable_w()
    main_end_x = self._t_to_x(self.main_duration)

    # 时间刻度
    step = 5.0 if span >= 20 else (1.0 if span >= 8 else 0.5)
    t = 0.0
    while t <= span + 1e-6:
      x = self._t_to_x(t)
      is_major = abs((t / step) - round(t / step)) < 1e-6
      self.create_line(
        x, 16, x, 108,
        fill="#e5e7eb" if not is_major else "#d1d5db",
        dash=(2, 3) if not is_major else None,
      )
      if is_major:
        label = f"{t:.0f}s" if span >= 30 else f"{t:.1f}s"
        self.create_text(x, 118, text=label, fill="#6b7280", font=("", 8))
      t += step / 5 if step >= 5 else step

    # 主视频轨道（仅到主视频时长）
    x1 = self._pad_l
    self.create_rectangle(x1, self._y_main, main_end_x, self._y_main + self._h, fill="#e5e7eb", outline="#d1d5db")
    self.create_text((x1 + main_end_x) / 2, self._y_main + self._h / 2,
                     text=f"主视频 {self.main_duration:.1f}s", fill="#666", font=("", 9))

    # 落版轨道：全长 = 落版素材时长，可超出主视频
    start_t = self._overlay_start_time()
    end_t = start_t + self.overlay_duration
    start_x = self._t_to_x(start_t)
    end_x = self._t_to_x(end_t)
    main_clip_x = self._t_to_x(min(end_t, self.main_duration))

    if self.overlay_duration > 0:
      # 轨道内（覆盖主视频）
      inside_end = min(end_x, main_end_x)
      if inside_end > start_x:
        self.create_rectangle(
          start_x, self._y_ov, inside_end, self._y_ov + self._h,
          fill="#4a90d9", outline="#357abd", width=2, tags=("ov",),
        )
      # 轨道外（拼接继续播放）
      if end_x > main_end_x:
        self.create_rectangle(
          max(start_x, main_end_x), self._y_ov, end_x, self._y_ov + self._h,
          fill="#9ec5ef", outline="#357abd", width=2, dash=(4, 3), tags=("ov",),
        )
      mid_x = (start_x + end_x) / 2
      self.create_text(
        mid_x, self._y_ov + self._h / 2,
        text=f"落版 {self.overlay_duration:.1f}s", fill="white", font=("", 9), tags=("ov",),
      )
      self.create_line(start_x, self._y_ov - 4, start_x, self._y_ov + self._h + 4, fill="white", width=3, tags=("ov",))
      if end_t > self.main_duration:
        self.create_text(main_end_x, self._y_ov - 8, text="↑主视频结尾", fill="#6b7280", font=("", 7), anchor="s")

    self.create_text(
      self._pad_l, 10, anchor="w",
      text=f"结尾前 {self.lead_time:.1f}s 开始叠加（第 {start_t:.1f}s）",
      fill="#333", font=("", 9),
    )
    self.create_text(
      self._pad_l + u, 10, anchor="e",
      text=f"总时长 {max(self.main_duration, end_t):.1f}s",
      fill="#6b7280", font=("", 8),
    )

  def _hit_overlay(self, x: float, y: float) -> bool:
    return bool(self.find_withtag("ov")) and (self._y_ov - 8 <= y <= self._y_ov + self._h + 8)

  def _on_down(self, event):
    if not self._hit_overlay(event.x, event.y):
      return
    self._dragging = True
    self._drag_start_x = event.x
    self._drag_start_time = self._overlay_start_time()

  def _on_move(self, event):
    if not self._dragging:
      return
    delta_t = (event.x - self._drag_start_x) / max(1.0, float(self._usable_w())) * self._timeline_duration()
    new_start = self._drag_start_time + delta_t
    new_start = round(new_start / self.SNAP) * self.SNAP
    new_start = max(0.0, new_start)
    lead = self.main_duration - new_start
    self.lead_time = self._clamp_lead(lead)
    self.redraw()
    if self.on_lead_changed:
      self.on_lead_changed(self.lead_time)

  def _on_up(self, _event):
    self._dragging = False
