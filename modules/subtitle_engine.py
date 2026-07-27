"""
subtitle_engine.py

给 HabiVideoTool / video_batch_tool_v24.py 提供字幕能力：
1) 提取音频 (FFmpeg -> 16kHz 单声道 wav)
2) Faster-Whisper 识别 (支持 ar/tr/zh，支持 auto)
3) 可选 Google 翻译 (googletrans)
4) 生成 SRT (含阿语 RTL 嵌入标记)
5) 可选 FFmpeg 烧录 SRT 到视频画面 (libass subtitles 滤镜)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


def _ensure_dep(dep: str, exc: Exception) -> RuntimeError:
    return RuntimeError(f"缺少依赖: {dep}。请先安装后重试。原始错误: {exc}")


def _contains_rtl(text: str) -> bool:
    # 阿拉伯语 Unicode 范围：\u0600-\u06FF, \u0750-\u077F, \u08A0-\u08FF
    for ch in text:
        if "\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F" or "\u08A0" <= ch <= "\u08FF":
            return True
    return False


def _format_srt_time(seconds: float) -> str:
    # HH:MM:SS,mmm
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _ffmpeg_subtitles_filter_escape(path: str) -> str:
    # FFmpeg subtitles 滤镜：建议用 posix 路径，并转义盘符冒号
    p = Path(path).resolve().as_posix()
    return p.replace(":", "\\:")


@dataclass(frozen=True)
class WhisperCfg:
    model_size: str
    device: str
    compute_type: str


class SubtitleEngine:
    """
    说明：
    - 模型缓存：同一 cfg 会复用 WhisperModel，避免每个文件都重复加载。
    - 翻译：默认使用 googletrans（若未安装会抛出清晰错误）。
    """

    _model_cache: dict[WhisperCfg, Any] = {}
    _whisper_broken: bool = False  # 本机 Faster-Whisper 崩过一次后，会话内直接走 Google 备用

    # Whisper 语言：ar / tr / zh（auto -> None）
    # googletrans 语言：zh -> zh-cn
    _GOOGLE_LANG_MAP = {
        "zh": "zh-cn",
        "tr": "tr",
        "ar": "ar",
        "en": "en",
    }

    def __init__(
        self,
        *,
        ffmpeg_path: str = "ffmpeg",
        whisper_model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        font_name: str = "Arial Unicode MS",
        rtl_embed: bool = True,
    ):
        self.ffmpeg_path = ffmpeg_path
        self.whisper_model_size = whisper_model_size
        self.device = device
        self.compute_type = compute_type
        self.font_name = font_name
        self.rtl_embed = rtl_embed
        self._WhisperModel = None

    def _get_model(self) -> Any:
        # 延迟导入：生成/烧录 SRT 不需要 Whisper；本机 torch/ctranslate2 也可能崩
        if self._WhisperModel is None:
            try:
                from faster_whisper import WhisperModel  # type: ignore
            except Exception as e:  # pragma: no cover
                raise _ensure_dep("faster-whisper", e)
            self._WhisperModel = WhisperModel

        cfg = WhisperCfg(self.whisper_model_size, self.device, self.compute_type)
        if cfg in SubtitleEngine._model_cache:
            return SubtitleEngine._model_cache[cfg]
        model = self._WhisperModel(
            self.whisper_model_size,
            device=self.device,
            compute_type=self.compute_type,
        )
        SubtitleEngine._model_cache[cfg] = model
        return model

    def extract_audio_to_wav(self, video_path: str) -> str:
        out_wav = tempfile.mktemp(suffix=".wav")
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i",
            video_path,
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            out_wav,
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg 提取音频失败: {proc.stderr[-800:] if proc.stderr else ''}")
        return out_wav

    def transcribe(
        self,
        video_path: str,
        *,
        language: Optional[str] = None,  # ar/tr/zh 或 None(auto)
        beam_size: int = 5,
    ) -> tuple[list[dict[str, Any]], str]:
        audio_path = self.extract_audio_to_wav(video_path)
        try:
            model = self._get_model()
            segments, info = model.transcribe(
                audio_path,
                beam_size=beam_size,
                language=language,
                task="transcribe",
            )
            detected_lang = getattr(info, "language", None) or ""
            out: list[dict[str, Any]] = []
            for seg in segments:
                text = (getattr(seg, "text", "") or "").strip()
                # Faster-Whisper 有时会产生空文本，保留也没意义；直接跳过
                if not text:
                    continue
                out.append({"start": float(seg.start), "end": float(seg.end), "text": text})
            return out, detected_lang
        finally:
            try:
                if os.path.exists(audio_path):
                    os.remove(audio_path)
            except OSError:
                pass

    def _translate_one(self, text: str, *, source_lang: Optional[str], target_lang: str) -> str:
        # 优先 deep_translator（更稳），失败再试 googletrans
        tgt = "zh-CN" if target_lang in {"zh", "zh-cn", "zh-CN"} else target_lang
        src = source_lang
        if src in {"zh", "zh-cn", "zh-CN"}:
            src = "zh-CN"
        try:
            from deep_translator import GoogleTranslator  # type: ignore

            return GoogleTranslator(source=src or "auto", target=tgt).translate(text) or text
        except Exception:
            pass
        try:
            from googletrans import Translator  # type: ignore

            kwargs: dict[str, Any] = {"dest": target_lang}
            if source_lang:
                kwargs["src"] = source_lang
            r = Translator().translate(text, **kwargs)
            return (getattr(r, "text", None) or "").strip() or text
        except Exception as e:
            raise _ensure_dep("deep-translator 或 googletrans==4.0.0-rc1", e)

    def translate_segments(
        self,
        segments: list[dict[str, Any]],
        *,
        source_lang: Optional[str],  # googletrans 语言（如 zh-cn）
        target_lang: str,  # googletrans 语言（如 zh-cn / ar / tr）
    ) -> list[dict[str, Any]]:
        if not target_lang or (source_lang and target_lang == source_lang):
            return segments

        out: list[dict[str, Any]] = []
        for seg in segments:
            text = str(seg.get("text", "") or "")
            if not text.strip():
                out.append(seg)
                continue
            try:
                translated_text = self._translate_one(text, source_lang=source_lang, target_lang=target_lang)
            except Exception:
                translated_text = text
            out.append({"start": seg["start"], "end": seg["end"], "text": translated_text})
        return out

    def transcribe_google_fallback(
        self,
        video_path: str,
        *,
        language: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], str]:
        """
        Faster-Whisper 不可用时的备用：Google 网页语音识别。
        注意：免费接口对长音频不稳定；短片（约 1 分钟内）更稳。
        时间轴会按整段音频时长生成（不保证逐句切分）。
        """
        try:
            import speech_recognition as sr  # type: ignore
        except Exception as e:  # pragma: no cover
            raise _ensure_dep("SpeechRecognition", e)

        import wave

        audio_path = self.extract_audio_to_wav(video_path)
        try:
            with wave.open(audio_path, "rb") as wf:
                duration = wf.getnframes() / float(wf.getframerate() or 1)

            recognizer = sr.Recognizer()
            with sr.AudioFile(audio_path) as source:
                audio = recognizer.record(source)

            # 指定语言优先；否则依次试 tr/ar/zh/en
            trials: list[tuple[str, str]] = []
            if language:
                mapping = {"tr": "tr-TR", "ar": "ar-SA", "zh": "zh-CN", "en": "en-US"}
                code = mapping.get(language, language)
                trials.append((code, language))
            trials.extend([("tr-TR", "tr"), ("ar-SA", "ar"), ("zh-CN", "zh"), ("en-US", "en")])

            best_text = ""
            best_lang = language or ""
            seen: set[str] = set()
            for code, short in trials:
                if code in seen:
                    continue
                seen.add(code)
                try:
                    text = recognizer.recognize_google(audio, language=code)
                except Exception:
                    continue
                if text and len(text) > len(best_text):
                    best_text = text
                    best_lang = short

            if not best_text.strip():
                raise RuntimeError("Google 语音识别失败（无结果）。可检查网络，或安装可用的 Faster-Whisper。")

            return (
                [{"start": 0.0, "end": max(float(duration) - 0.05, 0.5), "text": best_text.strip()}],
                best_lang or "auto",
            )
        finally:
            try:
                if os.path.exists(audio_path):
                    os.remove(audio_path)
            except OSError:
                pass

    def generate_srt(self, segments: list[dict[str, Any]], output_srt: str) -> str:
        rtl_any = False
        for seg in segments:
            if self.rtl_embed and _contains_rtl(str(seg.get("text", ""))):
                rtl_any = True
                break

        with open(output_srt, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, start=1):
                start_t = _format_srt_time(seg["start"])
                end_t = _format_srt_time(seg["end"])
                text = str(seg.get("text", "") or "")
                if self.rtl_embed and _contains_rtl(text):
                    text = "\u202B" + text  # RTL embedding
                f.write(f"{i}\n")
                f.write(f"{start_t} --> {end_t}\n")
                f.write(f"{text}\n\n")

        return output_srt

    def burn_subtitles(self, video_path: str, srt_path: str, output_path: str) -> str:
        # 用 libass subtitles 滤镜烧录（FFmpeg 编译需包含 libass）
        style = (
            f"Fontname={self.font_name},"
            "Fontsize=24,"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "Outline=2,"
            "Shadow=1,"
            "Alignment=2,"  # 底部居中
            "MarginV=30"
        )

        # 阿语更稳妥：加大字号 + MarginV
        try:
            with open(srt_path, "r", encoding="utf-8") as f:
                head = f.read(800)
            if _contains_rtl(head):
                style = (
                    f"Fontname={self.font_name},"
                    "Fontsize=26,"
                    "PrimaryColour=&H00FFFFFF,"
                    "OutlineColour=&H00000000,"
                    "Outline=2,"
                    "Shadow=1,"
                    "Alignment=2,"
                    "MarginV=40"
                )
        except Exception:
            pass

        srt_esc = _ffmpeg_subtitles_filter_escape(srt_path)
        vf = f"subtitles='{srt_esc}':force_style='{style}'"

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i",
            video_path,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-crf",
            "23",
            "-preset",
            "fast",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            output_path,
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg 烧录失败: {proc.stderr[-800:] if proc.stderr else ''}")
        return output_path

    def _transcribe_whisper_subprocess(
        self,
        video_path: str,
        *,
        language: Optional[str] = None,
        beam_size: int = 5,
        timeout_sec: int = 1800,
    ) -> tuple[list[dict[str, Any]], str]:
        """
        在独立子进程里跑 Faster-Whisper。
        某些 Windows 环境加载 ctranslate2/torch 会 Access Violation，
        子进程崩溃不会拖垮主程序，可回退到 Google 识别。
        """
        import json
        import sys

        out_json = tempfile.mktemp(suffix=".json")
        py = sys.executable
        code = f"""
import json, sys
from faster_whisper import WhisperModel
video_path = sys.argv[1]
out_json = sys.argv[2]
lang = sys.argv[3]
language = None if lang == "" else lang
model = WhisperModel({self.whisper_model_size!r}, device={self.device!r}, compute_type={self.compute_type!r})
segments, info = model.transcribe(video_path, beam_size={beam_size}, language=language, task="transcribe")
out = []
for seg in segments:
    t = (seg.text or "").strip()
    if not t:
        continue
    out.append({{"start": float(seg.start), "end": float(seg.end), "text": t}})
payload = {{"language": getattr(info, "language", "") or "", "segments": out}}
with open(out_json, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)
"""
        try:
            proc = subprocess.run(
                [py, "-c", code, video_path, out_json, language or ""],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=timeout_sec,
            )
            if proc.returncode != 0 or not os.path.isfile(out_json):
                err = (proc.stderr or proc.stdout or "")[-800:]
                raise RuntimeError(f"Faster-Whisper 子进程失败(code={proc.returncode}): {err}")
            with open(out_json, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return list(payload.get("segments") or []), str(payload.get("language") or "")
        finally:
            try:
                if os.path.exists(out_json):
                    os.remove(out_json)
            except OSError:
                pass

    def process_video_to_srt(
        self,
        video_path: str,
        output_srt: str,
        *,
        source_lang: Optional[str],  # Whisper language: ar/tr/zh 或 None(auto)
        target_lang: Optional[str],  # googletrans language code: ar/tr/zh-cn
    ) -> tuple[list[dict[str, Any]], str]:
        backend = (os.environ.get("HABIVIDEO_SUBTITLE_BACKEND") or "auto").strip().lower()
        segments: list[dict[str, Any]] = []
        detected = ""

        if backend in {"google", "sr", "speech"} or SubtitleEngine._whisper_broken:
            segments, detected = self.transcribe_google_fallback(video_path, language=source_lang)
        else:
            try:
                # 子进程隔离，避免 Access Violation 拖垮主程序
                segments, detected = self._transcribe_whisper_subprocess(
                    video_path, language=source_lang,
                )
            except Exception:
                SubtitleEngine._whisper_broken = True
                segments, detected = self.transcribe_google_fallback(video_path, language=source_lang)

        if target_lang and target_lang.strip():
            src_google = None
            if detected:
                src_google = self._GOOGLE_LANG_MAP.get(detected, detected)
            segments = self.translate_segments(
                segments,
                source_lang=src_google,
                target_lang=target_lang,
            )

        self.generate_srt(segments, output_srt)
        return segments, detected


def process_video_subtitles(
    *,
    ffmpeg_path: str,
    video_path: str,
    output_srt: str,
    whisper_model_size: str = "small",
    device: str = "cpu",
    compute_type: str = "int8",
    source_lang: Optional[str] = None,  # ar/tr/zh 或 None(auto)
    target_lang: Optional[str] = None,  # ar/tr/zh-cn 或 None(不翻译)
    font_name: str = "Arial Unicode MS",
    burn_in: bool = True,
    output_burned_video: Optional[str] = None,
) -> tuple[str | None, str]:
    """
    一次性把 video -> srt -> (可选 burned video)
    返回：(burned_video_path_or_none, output_srt_path)
    """
    engine = SubtitleEngine(
        ffmpeg_path=ffmpeg_path,
        whisper_model_size=whisper_model_size,
        device=device,
        compute_type=compute_type,
        font_name=font_name,
    )
    engine.process_video_to_srt(
        video_path,
        output_srt,
        source_lang=source_lang,
        target_lang=target_lang,
    )

    if not burn_in:
        return None, output_srt

    if not output_burned_video:
        raise ValueError("burn_in=True 时必须提供 output_burned_video")
    engine.burn_subtitles(video_path, output_srt, output_burned_video)
    return output_burned_video, output_srt

