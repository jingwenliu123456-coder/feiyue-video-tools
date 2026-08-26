#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V24 全功能自测：使用 /Users/jingwen/Documents/TR.mp4"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path("/Users/jingwen/Documents/HabiVideoTool_V24_Build")
VIDEO = Path("/Users/jingwen/Documents/TR.mp4")
OUT_ROOT = Path("/Users/jingwen/Documents/HabiVideoTool_V24_TestOut")
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

RESULTS: list[tuple[str, str, str]] = []  # name, status, detail


def record(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    RESULTS.append((name, status, detail[:500]))
    mark = "✅" if ok else "❌"
    print(f"{mark} [{status}] {name}" + (f" — {detail[:200]}" if detail else ""))


def section(title: str) -> None:
    print(f"\n===== {title} =====")


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    if not VIDEO.is_file():
        print(f"缺少测试视频: {VIDEO}")
        return 2

    # ── 0. 环境 ──
    section("0. 环境 / 依赖")
    try:
        from modules.platform_utils import resolve_ffmpeg, check_ffmpeg_available, path_for_ffmpeg

        ff, fp = resolve_ffmpeg()
        ok, msg = check_ffmpeg_available(ff, fp)
        record("FFmpeg/ffprobe 可用", ok, f"{ff} | {fp} | {msg}")
    except Exception as e:
        record("FFmpeg/ffprobe 可用", False, str(e))
        return 1

    try:
        import tkinter as tk

        record("Tkinter", True, f"Tk {tk.TkVersion}")
    except Exception as e:
        record("Tkinter", False, str(e))
        return 1

    try:
        from modules.scroll_compat import has_touchpad_scroll, scroll_sequences, precise_deltas

        class E:
            delta = (3 << 16) | (0xFFEC & 0xFFFF)  # dx=3, dy=-20

        dx, dy = precise_deltas(E())
        seqs = scroll_sequences()
        record(
            "触控板滚动兼容 (scroll_compat)",
            has_touchpad_scroll() and "<TouchpadScroll>" in seqs and dy != 0,
            f"touchpad={has_touchpad_scroll()} seq={seqs} dy={dy}",
        )
    except Exception as e:
        record("触控板滚动兼容 (scroll_compat)", False, str(e))

    try:
        from modules.folder_drop import normalize_drop_paths, only_existing_dirs

        paths = normalize_drop_paths([str(VIDEO.parent), f'"{VIDEO}"', b"/tmp"])
        dirs = only_existing_dirs(paths)
        record("拖放路径规范化 (folder_drop)", bool(dirs), f"dirs={dirs[:3]}")
    except Exception as e:
        record("拖放路径规范化 (folder_drop)", False, str(e))

    try:
        from modules.ui_skin import ensure_bootstrap_themes, enable_tk_dnd, UI_THEME_NONE, create_window

        ensure_bootstrap_themes()
        root0 = create_window(title="skin-test", themename="flatly", use_bootstrap=True)
        root0.withdraw()
        dnd = enable_tk_dnd(root0)
        record("主题/拖放注入 (ui_skin)", True, f"dnd={dnd} none={UI_THEME_NONE}")
        root0.destroy()
    except Exception as e:
        record("主题/拖放注入 (ui_skin)", False, traceback.format_exc()[-300:])

    # ── 1. 探测视频 ──
    section("1. 视频探测")
    try:
        import subprocess

        r = subprocess.run(
            [fp, "-v", "error", "-show_entries", "format=duration:stream=codec_name,width,height",
             "-of", "json", str(VIDEO)],
            capture_output=True, text=True, timeout=30,
        )
        meta = json.loads(r.stdout or "{}")
        dur = float((meta.get("format") or {}).get("duration") or 0)
        record("ffprobe 读 TR.mp4", r.returncode == 0 and dur > 0, f"duration={dur:.2f}s")
    except Exception as e:
        record("ffprobe 读 TR.mp4", False, str(e))
        dur = 14.0

    # ── 2. 批处理单步 ──
    section("2. 批处理管线（Tk withdraw）")
    work = Path(tempfile.mkdtemp(prefix="habi_test_", dir=str(OUT_ROOT)))
    in_dir = work / "in"
    out_dir = work / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    src = in_dir / "TR.mp4"
    shutil.copy2(VIDEO, src)

    root = tk.Tk()
    root.withdraw()
    try:
        from video_batch_tool_v24 import VideoBatchToolV24

        app = VideoBatchToolV24(root)
        record("V24 工作台实例化", True, "VideoBatchToolV24 OK")
    except Exception as e:
        record("V24 工作台实例化", False, traceback.format_exc()[-400:])
        root.destroy()
        return 1

    # cut：保留前 3 秒
    try:
        cut_out = work / "cut.mp4"
        app.cut(str(src), str(cut_out), "0", "3", "保留")
        record("裁剪 cut（保留 0-3s）", cut_out.is_file() and cut_out.stat().st_size > 1000, f"{cut_out.stat().st_size} bytes")
    except Exception as e:
        record("裁剪 cut（保留 0-3s）", False, traceback.format_exc()[-300:])

    # ratio：转 1:1（源是 9:16，测模糊背景）
    try:
        ratio_out = work / "ratio_1x1.mp4"
        app.convert_ratio_with_blur_bg(str(src), str(ratio_out), target_ratio="1:1", blur_strength=15)
        record("比例转换 ratio（→1:1）", ratio_out.is_file() and ratio_out.stat().st_size > 1000, f"{ratio_out.stat().st_size} bytes")
    except Exception as e:
        record("比例转换 ratio（→1:1）", False, traceback.format_exc()[-300:])

    # png 贴图水印（用 app icon）
    try:
        png = ROOT / "app_icon.png"
        png_out = work / "png_wm.mp4"
        app.add_logo(str(src), str(png), str(png_out), "1:1", "右下角", "固定像素", 120)
        record("PNG 贴图水印 add_logo", png_out.is_file() and png_out.stat().st_size > 1000, f"{png_out.stat().st_size} bytes")
    except Exception as e:
        record("PNG 贴图水印 add_logo", False, traceback.format_exc()[-350:])

    # process_batch：仅 ratio
    try:
        batch_in = work / "batch_in"
        batch_out = work / "batch_out"
        batch_in.mkdir()
        batch_out.mkdir()
        shutil.copy2(VIDEO, batch_in / "TR.mp4")
        app.global_input_folder.set(str(batch_in))
        app.global_output_folder.set(str(batch_out))
        # disable all then enable ratio
        for name in (
            "cut_enable", "ratio_enable", "enable_mov_watermark", "png_wm_enable",
            "layer_enable", "ending_enable", "overlay_enable", "subtitle_enable",
        ):
            var = getattr(app, name, None)
            if var is not None:
                try:
                    var.set(False)
                except Exception:
                    pass
        app.ratio_enable.set(True)
        app.ratio_target.set("9:16")  # already 9:16 — still should remux/encode
        t0 = time.time()
        app.process_batch(silent=True)
        elapsed = time.time() - t0
        outs = list(batch_out.rglob("*.mp4"))
        record(
            "批处理 process_batch（ratio 9:16）",
            len(outs) >= 1,
            f"outs={len(outs)} elapsed={elapsed:.1f}s {[p.name for p in outs[:3]]}",
        )
    except Exception as e:
        record("批处理 process_batch（ratio 9:16）", False, traceback.format_exc()[-400:])

    # ── 3. 规范命名 ──
    section("3. 规范命名")
    try:
        from modules.naming_convention import (
            NamingFields, list_media_files, build_filename, load_naming_config,
        )

        name_dir = work / "naming"
        name_dir.mkdir()
        shutil.copy2(VIDEO, name_dir / "TR.mp4")
        files = list_media_files(str(name_dir), recursive=False)
        fields = NamingFields(
            brand="habi", lang="ar", type_="chat", size="9x16",
            designer="test", date="20260807", tags=["smoke"],
            template="{序号}-{品牌}-{语言}-{类型}-{标签}-{尺寸}-{日期}-{设计师}",
        )
        new_name, _ = build_filename(fields, 1, source_ext=".mp4", index_width=3)
        ok_idx = "{序号}" not in new_name and "001" in new_name
        # also test 序号任意位置
        fields2 = NamingFields(
            brand="habi", lang="zh", type_="vlog", size="9x16",
            designer="ljw", date="20260807", tags=[],
            template="habi-{品牌}-{序号}-final",
        )
        new2, _ = build_filename(fields2, 7, source_ext=".mp4", index_width=2)
        record(
            "规范命名预览 build_filename",
            ok_idx and "07" in new2 and files == ["TR.mp4"],
            f"files={files} → {new_name} | alt={new2}",
        )
    except Exception as e:
        record("规范命名预览 build_filename", False, traceback.format_exc()[-300:])

    try:
        from modules.rename_rules import RenameRuleChain, batch_apply_chain

        chain = RenameRuleChain(
            add={"mode": "direct", "text": "_v2", "position": "suffix"},
            replace={"mode": "keep"},
        )
        pairs = batch_apply_chain(["TR.mp4"], chain, start_index=0)
        record("规则链更名 rename_rules", pairs and pairs[0][1].endswith("_v2.mp4") or "TR_v2" in pairs[0][1], str(pairs))
    except Exception as e:
        record("规则链更名 rename_rules", False, traceback.format_exc()[-300:])

    try:
        from naming_tool import NamingToolApp

        host = tk.Frame(root)
        naming = NamingToolApp(root, initial_folder=str(work / "naming"), embed_parent=host, skip_chrome=True)
        record("内嵌规范命名 NamingToolApp", naming is not None, "embed OK")
    except Exception as e:
        record("内嵌规范命名 NamingToolApp", False, traceback.format_exc()[-350:])

    # ── 4. 裂变 ──
    section("4. 裂变引擎")
    try:
        from modules.fission_engine import (
            FissionBranch, resolve_branch_config, bind_fission_io_paths, list_template_names,
        )
        from video_batch_tool_v20 import _templates_dir

        tdir = _templates_dir()
        names = list_template_names(tdir)
        record("裂变模板列表", len(names) > 0, f"n={len(names)} sample={names[:5]} dir={tdir}")
        pick = names[0] if names else ""
        if pick:
            b = FissionBranch(enabled=True, branch_name="smoke", template_name=pick)
            cfg = resolve_branch_config(b, templates_dir=tdir)
            cfg = bind_fission_io_paths(cfg, in_path=str(in_dir), out_path=str(work / "fission_out"))
            record("裂变 resolve_branch_config", isinstance(cfg, dict) and bool(cfg), f"template={pick} keys={list(cfg)[:8]}")
        else:
            record("裂变 resolve_branch_config", False, "无模板")
    except Exception as e:
        record("裂变 resolve_branch_config", False, traceback.format_exc()[-350:])

    # 单分支裂变批处理（若有模板）
    try:
        from modules.fission_engine import FissionBranch, resolve_branch_config, bind_fission_io_paths, list_template_names
        from video_batch_tool_v20 import _templates_dir

        tdir = _templates_dir()
        names = list_template_names(tdir)
        # pick a light template if possible
        pick = next((n for n in names if "habi169" in n.lower() or "habi11" in n.lower()), names[0] if names else "")
        if pick:
            fis_in = work / "fis_in"
            fis_out = work / "fis_out"
            fis_in.mkdir(exist_ok=True)
            fis_out.mkdir(exist_ok=True)
            shutil.copy2(VIDEO, fis_in / "TR.mp4")
            b = FissionBranch(enabled=True, branch_name="smoke", template_name=pick)
            cfg = resolve_branch_config(b, templates_dir=tdir)
            cfg = bind_fission_io_paths(cfg, in_path=str(fis_in), out_path=str(fis_out))
            # apply config into app then process
            if hasattr(app, "_apply_config_dict"):
                app._apply_config_dict(cfg, io_mode="template")
            app.global_input_folder.set(str(fis_in))
            app.global_output_folder.set(str(fis_out))
            # turn off heavy steps that need missing assets；至少保留 ratio 以便有产出
            for name in ("enable_mov_watermark", "png_wm_enable", "layer_enable", "ending_enable", "overlay_enable", "subtitle_enable"):
                var = getattr(app, name, None)
                if var is not None:
                    try:
                        var.set(False)
                    except Exception:
                        pass
            if hasattr(app, "ratio_enable"):
                app.ratio_enable.set(True)
                if hasattr(app, "ratio_target"):
                    app.ratio_target.set("9:16")
            t0 = time.time()
            app.process_batch(silent=True)
            outs = list(fis_out.rglob("*.mp4"))
            record(
                "裂变单分支批处理（模板→process_batch）",
                len(outs) >= 1,
                f"template={pick} outs={len(outs)} {time.time()-t0:.1f}s",
            )
        else:
            record("裂变单分支批处理（模板→process_batch）", False, "无模板可跑")
    except Exception as e:
        record("裂变单分支批处理（模板→process_batch）", False, traceback.format_exc()[-400:])

    # ── 5. 字幕 ──
    section("5. 字幕 SRT")
    try:
        from modules.subtitle_engine import check_whisper_available, SubtitleEngine

        ok_w, msg_w = check_whisper_available(timeout_sec=45)
        record("Whisper 环境检测", True, f"available={ok_w} | {msg_w}")  # 检测本身成功即记信息

        eng = SubtitleEngine(ffmpeg_path=ff, ffprobe_path=fp, whisper_model_size="tiny")
        srt_path = work / "manual.srt"
        eng.write_srt(
            [
                {"start": 0.0, "end": 2.0, "text": "测试字幕一行"},
                {"start": 2.0, "end": 4.0, "text": "第二行 subtitle"},
            ],
            str(srt_path),
        )
        record("写 SRT write_srt", srt_path.is_file() and srt_path.stat().st_size > 20, srt_path.read_text(encoding="utf-8")[:120])

        burn_out = work / "burned.mp4"
        eng.burn_subtitles(str(src), str(srt_path), str(burn_out))
        record("烧录字幕 burn_subtitles", burn_out.is_file() and burn_out.stat().st_size > 1000, f"{burn_out.stat().st_size} bytes")

        if ok_w:
            auto_srt = work / "auto.srt"
            try:
                eng.process_video_to_srt(str(src), str(auto_srt), source_lang="zh", target_lang=None)
                record("Whisper 识别→SRT", auto_srt.is_file() and auto_srt.stat().st_size > 10, auto_srt.read_text(encoding="utf-8")[:160] if auto_srt.is_file() else "")
            except Exception as e:
                record("Whisper 识别→SRT", False, str(e)[:300])
        else:
            # 未装字幕环境不算功能回归：检测与 burn/write 已覆盖主路径
            RESULTS.append(("Whisper 识别→SRT", "SKIP", f"未安装 faster_whisper：{msg_w}"[:500]))
            print(f"⏭️  [SKIP] Whisper 识别→SRT — 未安装字幕环境（可运行 setup_subtitle_env_mac.sh）")
    except Exception as e:
        record("字幕模块", False, traceback.format_exc()[-350:])

    # ── 6. 打包 App 启动 ──
    section("6. 打包 App 启动")
    try:
        import subprocess

        app_bin = Path("/Users/jingwen/Documents/HabiVideoTool_macOS/HabiVideoTool.app/Contents/MacOS/HabiVideoTool")
        log = work / "app_launch.log"
        proc = subprocess.Popen([str(app_bin)], stdout=open(log, "w"), stderr=subprocess.STDOUT)
        time.sleep(5)
        alive = proc.poll() is None
        if not alive:
            detail = log.read_text(encoding="utf-8", errors="replace")[-400:]
            record("HabiVideoTool.app 启动", False, detail)
        else:
            record("HabiVideoTool.app 启动", True, f"pid={proc.pid}")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
    except Exception as e:
        record("HabiVideoTool.app 启动", False, str(e))

    # cleanup tk
    try:
        root.destroy()
    except Exception:
        pass

    # ── 汇总 ──
    section("汇总")
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    skipped = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    report = OUT_ROOT / "test_report.json"
    report.write_text(json.dumps(
        [{"name": n, "status": s, "detail": d} for n, s, d in RESULTS],
        ensure_ascii=False, indent=2,
    ), encoding="utf-8")
    print(f"\nPASS={passed} FAIL={failed} SKIP={skipped} TOTAL={len(RESULTS)}")
    print(f"产物目录: {work}")
    print(f"报告: {report}")
    if failed:
        print("\n失败项:")
        for n, s, d in RESULTS:
            if s == "FAIL":
                print(f"  - {n}: {d[:200]}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
