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


def resolve_whisper_python() -> str:
    """
    定位用于 Faster-Whisper 子进程的 Python。
    优先：HABIVIDEO_SUBTITLE_PYTHON → 项目 .venv_subtitle → 当前解释器。
    """
    override = (os.environ.get("HABIVIDEO_SUBTITLE_PYTHON") or "").strip().strip('"')
    if override and os.path.isfile(override):
        return override

    try:
        from modules.platform_utils import SYSTEM, app_dir

        root = app_dir()
    except Exception:
        import sys

        return sys.executable

    if SYSTEM == "Windows":
        candidates = (
            root / ".venv_subtitle" / "Scripts" / "python.exe",
            root / "venv_subtitle" / "Scripts" / "python.exe",
        )
    else:
        candidates = (
            root / ".venv_subtitle" / "bin" / "python",
            root / "venv_subtitle" / "bin" / "python",
        )
        if getattr(sys, "frozen", False):
            try:
                exe = Path(sys.executable).resolve()
                bundle = exe.parent.parent.parent  # *.app
                release = bundle.parent
                candidates = (
                    release / ".venv_subtitle" / "bin" / "python",
                    bundle / "Contents" / "Resources" / ".venv_subtitle" / "bin" / "python",
                    *candidates,
                )
            except Exception:
                pass
    for p in candidates:
        if p.is_file():
            return str(p)

    import sys

    return sys.executable


def resolve_whisper_worker_script() -> Optional[str]:
    try:
        from modules.platform_utils import app_dir

        script = app_dir() / "scripts" / "whisper_transcribe_worker.py"
        if script.is_file():
            return str(script)
    except Exception:
        pass
    return None


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


def check_whisper_available(*, timeout_sec: int = 90) -> tuple[bool, str]:
    """
    检测本机 Faster-Whisper 是否可用（子进程隔离，避免拖垮主程序）。
    返回 (可用, 说明)。
    """
    if SubtitleEngine._whisper_broken:
        return False, "本会话内 Faster-Whisper 曾失败，当前会走 Google 备用识别"
    backend = (os.environ.get("HABIVIDEO_SUBTITLE_BACKEND") or "auto").strip().lower()
    if backend in {"google", "sr", "speech"}:
        return False, f"已设置 HABIVIDEO_SUBTITLE_BACKEND={backend}，不会使用 Whisper"

    py = resolve_whisper_python()
    probe = (
        "from faster_whisper import WhisperModel; "
        "WhisperModel('tiny', device='cpu', compute_type='int8'); "
        "print('ok')"
    )
    try:
        proc = subprocess.run(
            [py, "-c", probe],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=max(20, int(timeout_sec)),
        )
        if proc.returncode == 0 and "ok" in (proc.stdout or ""):
            hint = py
            if ".venv_subtitle" in py.replace("\\", "/"):
                hint = "专用环境 .venv_subtitle"
            return True, f"Faster-Whisper 可用（{hint}）"
        err = (proc.stderr or proc.stdout or "").strip()
        if len(err) > 280:
            err = "…" + err[-280:]
        code = proc.returncode
        if code in (-1073741819, 3221225477, -1073740791):
            return False, (
                "Whisper 模型加载崩溃（多为 VC++ 运行库或 Python 版本问题）。"
                "请安装 Microsoft Visual C++ 2015-2022 x64 运行库后，"
                "重新运行 scripts\\setup_subtitle_env.bat（优先 Python 3.12）"
            )
        setup = "请运行 scripts\\setup_subtitle_env.bat（建议 py -3.12）"
        if "torch" in err.lower() or "c10.dll" in err.lower():
            return False, f"主 Python 与 Whisper 冲突；{setup}"
        if "onnxruntime" in err.lower() or "DLL" in err:
            return False, f"Whisper 依赖 DLL 加载失败；请安装 VC++ 运行库后重装字幕环境。{err[:120]}"
        return False, f"{err or f'Whisper 探测失败(code={code})'}；{setup}"
    except subprocess.TimeoutExpired:
        return False, "Faster-Whisper 检测超时（首次需下载 tiny 模型，请稍后重试）"
    except Exception as e:
        return False, f"{e}；请运行 scripts\\setup_subtitle_env.bat"


def probe_video_duration_sec(video_path: str, *, ffprobe_path: str = "ffprobe") -> float:
    """用 ffprobe 读取视频时长（秒），失败返回 0。"""
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="ignore", timeout=30,
        )
        if proc.returncode != 0:
            return 0.0
        return max(0.0, float((proc.stdout or "").strip()))
    except Exception:
        return 0.0


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

    @staticmethod
    def _normalize_lang_code(code: Optional[str]) -> Optional[str]:
        """统一 google/deep_translator 语言码，便于比较与传参。"""
        if not code:
            return None
        c = str(code).strip().lower().replace("_", "-")
        if not c or c == "none":
            return None
        if c.startswith("zh"):
            return "zh-cn"
        return c.split("-")[0]

    def _translate_one(self, text: str, *, source_lang: Optional[str], target_lang: str) -> str:
        # 优先 deep_translator（更稳），失败再试 googletrans
        tgt_norm = self._normalize_lang_code(target_lang) or target_lang
        tgt = "zh-CN" if tgt_norm == "zh-cn" else tgt_norm
        src_norm = self._normalize_lang_code(source_lang)
        src = "zh-CN" if src_norm == "zh-cn" else (src_norm or source_lang)
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
        stats: Optional[dict[str, int]] = None,
    ) -> list[dict[str, Any]]:
        tgt_norm = self._normalize_lang_code(target_lang)
        src_norm = self._normalize_lang_code(source_lang)
        if not tgt_norm or (src_norm and src_norm == tgt_norm):
            if stats is not None:
                stats.update({"changed": 0, "failed": 0, "skipped": len(segments), "total": len(segments)})
            return segments

        out: list[dict[str, Any]] = []
        changed = 0
        failed = 0
        for seg in segments:
            text = str(seg.get("text", "") or "")
            if not text.strip():
                out.append(seg)
                continue
            try:
                translated_text = self._translate_one(text, source_lang=source_lang, target_lang=target_lang)
            except Exception:
                translated_text = text
                failed += 1
            else:
                if translated_text.strip() == text.strip():
                    failed += 1
                else:
                    changed += 1
            out.append({"start": seg["start"], "end": seg["end"], "text": translated_text})
        if stats is not None:
            stats.update({"changed": changed, "failed": failed, "skipped": 0, "total": len(segments)})
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

    @staticmethod
    def _srt_has_dual_lines(srt_path: str) -> bool:
        """检测 SRT 是否含双行字幕（双语并存）。"""
        try:
            with open(srt_path, "r", encoding="utf-8") as f:
                head = f.read(4096)
            for block in head.split("\n\n"):
                lines = [ln for ln in block.strip().split("\n") if ln.strip()]
                if len(lines) >= 4:
                    return True
        except Exception:
            pass
        return False

    def burn_subtitles(self, video_path: str, srt_path: str, output_path: str) -> str:
        # 用 libass subtitles 滤镜烧录（FFmpeg 编译需包含 libass）
        dual_line = self._srt_has_dual_lines(srt_path)
        fontsize = 22 if dual_line else 24
        margin_v = 58 if dual_line else 30
        style = (
            f"Fontname={self.font_name},"
            f"Fontsize={fontsize},"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "Outline=2,"
            "Shadow=1,"
            "Alignment=2,"  # 底部居中
            f"MarginV={margin_v}"
        )

        # 阿语更稳妥：加大字号 + MarginV
        try:
            with open(srt_path, "r", encoding="utf-8") as f:
                head = f.read(800)
            if _contains_rtl(head):
                rtl_size = 24 if dual_line else 26
                rtl_margin = 62 if dual_line else 40
                style = (
                    f"Fontname={self.font_name},"
                    f"Fontsize={rtl_size},"
                    "PrimaryColour=&H00FFFFFF,"
                    "OutlineColour=&H00000000,"
                    "Outline=2,"
                    "Shadow=1,"
                    "Alignment=2,"
                    f"MarginV={rtl_margin}"
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

        out_json = tempfile.mktemp(suffix=".json")
        py = resolve_whisper_python()
        worker = resolve_whisper_worker_script()
        lang_arg = language or ""

        if worker:
            cmd = [
                py, worker, video_path, out_json, lang_arg,
                self.whisper_model_size, self.device, self.compute_type, str(beam_size),
            ]
        else:
            code = f"""
import json, sys
from faster_whisper import WhisperModel
video_path, out_json, lang = sys.argv[1], sys.argv[2], sys.argv[3]
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
            cmd = [py, "-c", code, video_path, out_json, lang_arg]

        try:
            proc = subprocess.run(
                cmd,
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

    def write_srt(self, segments: list[dict[str, Any]], output_srt: str) -> str:
        """写出 SRT（generate_srt 别名）。"""
        return self.generate_srt(segments, output_srt)

    @staticmethod
    def merge_bilingual(
        src_segments: list[dict[str, Any]],
        tgt_segments: list[dict[str, Any]],
        *,
        force_dual: bool = False,
        untranslated_hint: str = "（译文未变，请检查网络或目标语言）",
    ) -> list[dict[str, Any]]:
        """合并双语：每段两行。含阿语原文时译文在上、原文在下，减轻 RTL 排版问题。"""
        merged: list[dict[str, Any]] = []
        count = max(len(src_segments), len(tgt_segments))
        for i in range(count):
            s = src_segments[i] if i < len(src_segments) else src_segments[-1]
            t = tgt_segments[i] if i < len(tgt_segments) else tgt_segments[-1]
            src_text = str(s.get("text", "") or "").strip()
            tgt_text = str(t.get("text", "") or "").strip()
            if not src_text and not tgt_text:
                continue
            if not tgt_text or tgt_text == src_text:
                if force_dual and src_text:
                    if _contains_rtl(src_text):
                        combined = f"{untranslated_hint}\n{src_text}"
                    else:
                        combined = f"{src_text}\n{untranslated_hint}"
                else:
                    combined = src_text or tgt_text
            elif _contains_rtl(src_text):
                combined = f"{tgt_text}\n{src_text}"
            else:
                combined = f"{src_text}\n{tgt_text}"
            merged.append({
                "start": float(s.get("start", t.get("start", 0))),
                "end": float(s.get("end", t.get("end", 0))),
                "text": combined,
            })
        return merged

    def transcribe_video(
        self,
        video_path: str,
        *,
        source_lang: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], str, str]:
        """
        识别视频语音，返回 (segments, detected_lang, backend)。
        backend 为 whisper 或 google。
        """
        backend_env = (os.environ.get("HABIVIDEO_SUBTITLE_BACKEND") or "auto").strip().lower()
        segments: list[dict[str, Any]] = []
        detected = ""
        backend = "google"

        if backend_env in {"google", "sr", "speech"} or SubtitleEngine._whisper_broken:
            segments, detected = self.transcribe_google_fallback(video_path, language=source_lang)
        else:
            try:
                segments, detected = self._transcribe_whisper_subprocess(
                    video_path, language=source_lang,
                )
                backend = "whisper"
            except Exception:
                SubtitleEngine._whisper_broken = True
                segments, detected = self.transcribe_google_fallback(video_path, language=source_lang)
        return segments, detected, backend

    def process_video_to_srt(
        self,
        video_path: str,
        output_srt: str,
        *,
        source_lang: Optional[str],  # Whisper language: ar/tr/zh 或 None(auto)
        target_lang: Optional[str],  # googletrans language code: ar/tr/zh-cn
    ) -> tuple[list[dict[str, Any]], str, str]:
        """
        识别并写出 SRT（兼容旧接口：识别 → 可选翻译 → 写文件）。
        返回 (segments, detected_lang, backend)。
        """
        segments, detected, backend = self.transcribe_video(
            video_path, source_lang=source_lang,
        )

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
        return segments, detected, backend


def resolve_external_srt(video_path: str, *, srt_dir: Optional[str] = None) -> Optional[str]:
    """
    为视频匹配外部 SRT：优先 srt_dir/{stem}.srt，否则与视频同目录同名 .srt。
    """
    stem = Path(video_path).stem
    candidates: list[Path] = []
    if srt_dir:
        candidates.append(Path(srt_dir) / f"{stem}.srt")
    candidates.append(Path(video_path).with_suffix(".srt"))
    seen: set[str] = set()
    for p in candidates:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.is_file():
            return str(p)
    return None


def _subtitle_font_candidates() -> list[str]:
    """多语言烧录常用字体（置顶推荐，不要求本机已装）。"""
    return [
        "Arial Unicode MS",
        "Microsoft YaHei",
        "微软雅黑",
        "Noto Sans CJK SC",
        "Noto Sans Arabic",
        "SimHei",
        "SimSun",
        "Segoe UI",
        "Arial",
        "Tahoma",
        "PingFang SC",
        "Helvetica",
    ]


_FONT_LIST_CACHE: dict[int, list[str]] = {}


def _usable_burn_font(name: str) -> bool:
    """过滤竖排/装饰变体，libass 烧录一般不用。"""
    n = (name or "").strip()
    if not n:
        return False
    if n.startswith("@"):  # Windows 竖排字体
        return False
    return True


def clear_subtitle_font_cache() -> None:
    _FONT_LIST_CACHE.clear()


def list_subtitle_font_choices(root: Any = None, *, refresh: bool = False) -> list[str]:
    """返回本机全部可用字体；常用烧录字体排在最前。"""
    import tkinter.font as tkfont

    pinned = _subtitle_font_candidates()
    if root is None:
        return pinned

    try:
        top = root.winfo_toplevel()
        cache_key = id(top)
    except Exception:
        cache_key = id(root)

    if refresh:
        _FONT_LIST_CACHE.pop(cache_key, None)

    if cache_key in _FONT_LIST_CACHE:
        return _FONT_LIST_CACHE[cache_key]

    try:
        raw = sorted(
            {f for f in tkfont.families(root) if _usable_burn_font(f)},
            key=lambda s: s.lower(),
        )
    except Exception:
        return pinned

    if not raw:
        return pinned

    avail_set = set(raw)
    avail_lower = {f.lower(): f for f in raw}
    top_list: list[str] = []
    seen: set[str] = set()

    for name in pinned:
        if name in avail_set:
            top_list.append(name)
            seen.add(name)
            continue
        hit = avail_lower.get(name.lower())
        if hit and hit not in seen:
            top_list.append(hit)
            seen.add(hit)

    rest = [f for f in raw if f not in seen]
    result = top_list + rest
    _FONT_LIST_CACHE[cache_key] = result
    return result


def suggest_subtitle_font(
    *,
    src_code: Optional[str] = None,
    tgt_code: Optional[str] = None,
) -> str:
    """按源/目标语言推荐烧录字体名。"""
    codes = {c for c in (src_code, tgt_code) if c and c != "none"}
    if len(codes) >= 2 or ("ar" in codes) or ("tr" in codes and "zh" in codes):
        return "Arial Unicode MS"
    if "ar" in codes or "tr" in codes:
        return "Arial Unicode MS"
    if "zh" in codes:
        return "Microsoft YaHei"
    return "Microsoft YaHei"


def validate_subtitle_font(name: str, root: Any = None) -> tuple[bool, str]:
    """检查字体是否在本机 Tk 字体列表中（libass 名称需与系统安装名一致）。"""
    name = (name or "").strip()
    if not name:
        return False, "请填写或选择字体"
    import tkinter.font as tkfont

    try:
        if root is None:
            return True, "将交给 FFmpeg/libass 使用"
        families = set(tkfont.families(root))
        if name in families:
            return True, "本机已安装"
        for fam in families:
            if fam.lower() == name.lower():
                return True, f"匹配 {fam}"
        total = len(families)
        return False, f"未找到该字体（本机共 {total} 个可用字体）"
    except Exception:
        return True, "未校验"


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

