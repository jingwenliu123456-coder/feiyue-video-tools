#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Faster-Whisper 独立子进程：供主程序调用，避免 DLL 冲突拖垮 GUI。"""

from __future__ import annotations

import json
import sys


def main() -> int:
    if len(sys.argv) < 8:
        print("usage: whisper_transcribe_worker.py VIDEO OUT.json LANG MODEL DEVICE COMPUTE BEAM", file=sys.stderr)
        return 2

    video_path = sys.argv[1]
    out_json = sys.argv[2]
    lang = sys.argv[3]
    model_size = sys.argv[4]
    device = sys.argv[5]
    compute_type = sys.argv[6]
    beam_size = int(sys.argv[7] or "5")
    language = None if not lang.strip() else lang.strip()

    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        video_path,
        beam_size=beam_size,
        language=language,
        task="transcribe",
    )
    out: list[dict] = []
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        out.append({"start": float(seg.start), "end": float(seg.end), "text": text})
    payload = {"language": getattr(info, "language", "") or "", "segments": out}
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
