#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""年度工具年报 HTML 版（可截图分享）"""

from __future__ import annotations

import tempfile
import webbrowser
from pathlib import Path

from modules.tool_stats import OP_LABELS, AnnualReportData, generate_annual_report_data


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _top_features_html(data: AnnualReportData) -> str:
    if not data.by_type:
        return "<p>暂无记录</p>"
    top = sorted(data.by_type.items(), key=lambda x: -x[1])[:5]
    items = "".join(
        f"<li><strong>{_esc(OP_LABELS.get(k, k))}</strong> — {v} 次</li>"
        for k, v in top
    )
    return f"<ul class='feat'>{items}</ul>"


def _time_story_html(data: AnnualReportData) -> str:
    parts: list[str] = []
    if data.busiest_day[0]:
        parts.append(f"<p>高峰日 <strong>{_esc(data.busiest_day[0])}</strong>，一天处理了 {data.busiest_day[1]} 次</p>")
    if data.busiest_month[0]:
        parts.append(f"<p>高产月 <strong>{data.busiest_month[0]} 月</strong>（{data.busiest_month[1]} 次）</p>")
    if data.streak_days > 1:
        parts.append(f"<p>最长连续使用 <strong>{data.streak_days}</strong> 天</p>")
    if data.first_use:
        parts.append(f"<p>首次记录：{ _esc(data.first_use) }</p>")
    return "".join(parts) if parts else "<p>平稳的一年，也是一种节奏。</p>"


def _night_html(data: AnnualReportData) -> str:
    if data.night_ops <= 0:
        return "<p>你很注重作息，今年没有深夜加班记录。</p>"
    t = data.latest_night[11:16] if len(data.latest_night) >= 16 else ""
    extra = f"最晚一次：{data.latest_night[:10]} {t}" if data.latest_night else ""
    return f"<p>有 <strong>{data.night_ops}</strong> 次操作在 23:00 后或凌晨。</p><p>{_esc(extra)}</p>"


def build_annual_report_html(data: AnnualReportData) -> str:
    year = data.year
    titles = " · ".join(data.titles)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{year} 年度工具报告</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: "Microsoft YaHei", -apple-system, sans-serif;
    background: #0f0f1a; color: #eee;
  }}
  .page {{
    min-height: 100vh; display: flex; flex-direction: column;
    justify-content: center; align-items: center; padding: 48px 24px;
    border-bottom: 1px solid #222;
  }}
  h1 {{ font-size: 2rem; margin: 0 0 12px; }}
  h2 {{ font-size: 1.4rem; color: #aaa; font-weight: normal; }}
  .big {{
    font-size: 4.5rem; font-weight: bold; color: #e94560;
    margin: 16px 0; font-variant-numeric: tabular-nums;
  }}
  p {{ color: #ccc; line-height: 1.8; max-width: 520px; text-align: center; }}
  .titles {{ font-size: 1.5rem; color: #e94560; margin: 12px 0; }}
  ul.feat {{ list-style: none; padding: 0; text-align: center; }}
  ul.feat li {{ margin: 8px 0; font-size: 1.1rem; }}
  .fade {{ animation: fadeIn 0.8s ease-out; }}
  @keyframes fadeIn {{
    from {{ opacity: 0; transform: translateY(16px); }}
    to {{ opacity: 1; transform: none; }}
  }}
</style>
</head>
<body>
  <section class="page fade">
    <h1>🎬 {year} 年度工具报告</h1>
    <p>今年，工具陪你度过了无数个剪辑的日夜</p>
  </section>
  <section class="page fade">
    <h2>今年，你一共处理了</h2>
    <div class="big" id="total">{data.total_count}</div>
    <p>个文件 / 次操作</p>
  </section>
  <section class="page fade">
    <h2>你最常用的功能</h2>
    {_top_features_html(data)}
  </section>
  <section class="page fade">
    <h2>时间印记</h2>
    {_time_story_html(data)}
  </section>
  <section class="page fade">
    <h2>深夜的屏幕光</h2>
    {_night_html(data)}
  </section>
  <section class="page fade">
    <h2>你的年度称号</h2>
    <div class="titles">{_esc(titles)}</div>
  </section>
  <section class="page fade">
    <h1>{year}，感谢陪伴</h1>
    <p>{year + 1} 年，我们继续一起，把混乱的视频世界理得井井有条。</p>
  </section>
<script>
(function() {{
  const el = document.getElementById('total');
  if (!el) return;
  const target = {data.total_count};
  let cur = 0;
  const step = Math.max(1, Math.ceil(target / 50));
  const t = setInterval(() => {{
    cur = Math.min(target, cur + step);
    el.textContent = cur.toLocaleString();
    if (cur >= target) clearInterval(t);
  }}, 30);
}})();
</script>
</body>
</html>"""


def export_annual_report_html(year: int, *, open_browser: bool = True) -> Path:
    data = generate_annual_report_data(year)
    html = build_annual_report_html(data)
    out = Path(tempfile.gettempdir()) / f"habi_annual_report_{year}.html"
    out.write_text(html, encoding="utf-8")
    if open_browser:
        webbrowser.open(out.as_uri())
    return out
