import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import platform
import shutil
import tempfile
import json

CONFIG_FILE = "video_batch_config.json"

class VideoBatchProcessor:
    def __init__(self, root):
        self.root = root
        self.root.title("视频批量处理工具 v16.0")
        self.root.geometry("1400x950")
        self.root.minsize(1300, 850)
        self.setup_ui()
        self.load_config()
        self.check_ffmpeg()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=1350)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        ttk.Label(scrollable_frame, text="视频批量处理工具 v16.0", font=("Microsoft YaHei", 18, "bold")).pack(pady=(0,5))
        ttk.Button(scrollable_frame, text="使用说明", command=self.show_help).pack(anchor=tk.W, padx=10, pady=5)

        top_btn_frame = ttk.Frame(scrollable_frame)
        top_btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(top_btn_frame, text="一键批量处理", command=self.start_process, style="Accent.TButton").pack(side=tk.LEFT, padx=10)
        ttk.Button(top_btn_frame, text="保存配置", command=self.save_config).pack(side=tk.LEFT, padx=10)
        ttk.Button(top_btn_frame, text="打开输出文件夹", command=self.open_output_folder).pack(side=tk.LEFT, padx=10)
        top_btn_frame.pack(anchor=tk.CENTER)

        io_frame = ttk.LabelFrame(scrollable_frame, text="输入 / 输出文件夹", padding=10)
        io_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(io_frame, text="输入文件夹:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.input_var = tk.StringVar()
        ttk.Entry(io_frame, textvariable=self.input_var, width=55).grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Button(io_frame, text="选择", command=self.select_input_folder, width=6).grid(row=0, column=2, padx=5)

        ttk.Label(io_frame, text="输出文件夹:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.output_var = tk.StringVar()
        ttk.Entry(io_frame, textvariable=self.output_var, width=55).grid(row=1, column=1, sticky=tk.EW, padx=5)
        ttk.Button(io_frame, text="选择", command=self.select_output_folder, width=6).grid(row=1, column=2, padx=5)

        io_frame.columnconfigure(1, weight=1)

        param_frame = ttk.Frame(scrollable_frame)
        param_frame.pack(fill=tk.X, padx=10, pady=10)

        cut_frame = ttk.LabelFrame(param_frame, text="裁切设置", padding=8)
        cut_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        self.cut_enable = tk.BooleanVar(value=False)
        ttk.Checkbutton(cut_frame, text="启用裁切", variable=self.cut_enable).pack(anchor=tk.W)
        ttk.Label(cut_frame, text="模式:").pack(anchor=tk.W)
        self.cut_mode = tk.StringVar(value="保留")
        ttk.Combobox(cut_frame, textvariable=self.cut_mode, values=["保留", "删除"], width=10, state="readonly").pack()
        ttk.Label(cut_frame, text="开始(秒或分:秒):").pack(anchor=tk.W, pady=(5,0))
        self.cut_start = tk.StringVar(value="00:00")
        ttk.Entry(cut_frame, textvariable=self.cut_start, width=12).pack()
        ttk.Label(cut_frame, text="结束:").pack(anchor=tk.W, pady=(5,0))
        self.cut_end = tk.StringVar(value="00:15")
        ttk.Entry(cut_frame, textvariable=self.cut_end, width=12).pack()

        audio_frame = ttk.LabelFrame(param_frame, text="音频替换", padding=8)
        audio_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        self.audio_enable = tk.BooleanVar(value=False)
        ttk.Checkbutton(audio_frame, text="启用", variable=self.audio_enable).pack(anchor=tk.W)
        ttk.Label(audio_frame, text="音频文件:").pack(anchor=tk.W)
        self.audio_path = tk.StringVar()
        ttk.Entry(audio_frame, textvariable=self.audio_path, width=30).pack()
        ttk.Button(audio_frame, text="选择", command=self.select_audio).pack(anchor=tk.W, pady=2)

        cta_frame = ttk.LabelFrame(param_frame, text="结尾落版", padding=8)
        cta_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        self.cta_enable = tk.BooleanVar(value=False)
        ttk.Checkbutton(cta_frame, text="启用", variable=self.cta_enable).pack(anchor=tk.W)
        ttk.Label(cta_frame, text="落版视频:").pack(anchor=tk.W)
        self.cta_path = tk.StringVar()
        ttk.Entry(cta_frame, textvariable=self.cta_path, width=30).pack()
        ttk.Button(cta_frame, text="选择", command=self.select_cta).pack(anchor=tk.W, pady=2)
        self.cta_keep_audio = tk.BooleanVar(value=False)
        ttk.Checkbutton(cta_frame, text="落版保留原音频", variable=self.cta_keep_audio).pack(anchor=tk.W)
        ttk.Label(cta_frame, text="落版截取秒数(0=完整):").pack(anchor=tk.W, pady=(5,0))
        self.cta_trim = tk.StringVar(value="0")
        ttk.Entry(cta_frame, textvariable=self.cta_trim, width=12).pack()

        mov_frame = ttk.LabelFrame(param_frame, text="AE透明MOV循环水印", padding=8)
        mov_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        self.mov_wm_enable = tk.BooleanVar(value=False)
        ttk.Checkbutton(mov_frame, text="启用MOV水印", variable=self.mov_wm_enable).pack(anchor=tk.W)
        ttk.Label(mov_frame, text="水印MOV:").pack(anchor=tk.W)
        self.mov_wm_path = tk.StringVar()
        ttk.Entry(mov_frame, textvariable=self.mov_wm_path, width=30).pack()
        ttk.Button(mov_frame, text="选择", command=self.select_mov_wm).pack(anchor=tk.W, pady=2)
        ttk.Label(mov_frame, text="位置X:").pack(anchor=tk.W)
        self.mov_wm_x = tk.StringVar(value="10")
        ttk.Entry(mov_frame, textvariable=self.mov_wm_x, width=12).pack()
        ttk.Label(mov_frame, text="位置Y:").pack(anchor=tk.W)
        self.mov_wm_y = tk.StringVar(value="10")
        ttk.Entry(mov_frame, textvariable=self.mov_wm_y, width=12).pack()
        self.mov_wm_rb = tk.BooleanVar(value=False)
        ttk.Checkbutton(mov_frame, text="右下角对齐", variable=self.mov_wm_rb).pack(anchor=tk.W)
        ttk.Label(mov_frame, text="水印持续秒数(0=全程):").pack(anchor=tk.W, pady=(5,0))
        self.mov_wm_duration = tk.StringVar(value="0")
        ttk.Entry(mov_frame, textvariable=self.mov_wm_duration, width=12).pack()

        txt_frame = ttk.LabelFrame(param_frame, text="文字水印", padding=8)
        txt_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        self.txt_wm_enable = tk.BooleanVar(value=False)
        ttk.Checkbutton(txt_frame, text="启用", variable=self.txt_wm_enable).pack(anchor=tk.W)
        ttk.Label(txt_frame, text="文字:").pack(anchor=tk.W)
        self.txt_wm_text = tk.StringVar(value="Nov")
        ttk.Entry(txt_frame, textvariable=self.txt_wm_text, width=15).pack()
        ttk.Label(txt_frame, text="方向:").pack(anchor=tk.W)
        self.txt_wm_dir = tk.StringVar(value="静止")
        ttk.Combobox(txt_frame, textvariable=self.txt_wm_dir, values=["静止", "从左往右", "从右往左", "从上往下", "从下往上"], width=10, state="readonly").pack()
        ttk.Label(txt_frame, text="大小:").pack(anchor=tk.W)
        self.txt_wm_size = tk.StringVar(value="24")
        ttk.Entry(txt_frame, textvariable=self.txt_wm_size, width=10).pack()
        ttk.Label(txt_frame, text="颜色:").pack(anchor=tk.W)
        self.txt_wm_color = tk.StringVar(value="white")
        ttk.Entry(txt_frame, textvariable=self.txt_wm_color, width=10).pack()

        log_frame = ttk.LabelFrame(scrollable_frame, text="处理日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_area = scrolledtext.ScrolledText(log_frame, height=12, wrap=tk.WORD)
        self.log_area.pack(fill=tk.BOTH, expand=True)

        self.progress = ttk.Progressbar(scrollable_frame, orient=tk.HORIZONTAL, length=600, mode='determinate')
        self.progress.pack(fill=tk.X, padx=10, pady=5)

        rename_frame = ttk.LabelFrame(scrollable_frame, text="批量重命名（源→目标，可选）", padding=10)
        rename_frame.pack(fill=tk.X, padx=10, pady=10)

        left_frame = ttk.Frame(rename_frame)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=5)
        ttk.Label(left_frame, text="源文件夹（点击复制）").pack(anchor=tk.W)
        src_path_frame = ttk.Frame(left_frame)
        src_path_frame.pack(fill=tk.X)
        self.src_dir_var = tk.StringVar()
        ttk.Entry(src_path_frame, textvariable=self.src_dir_var, width=45).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(src_path_frame, text="选择", command=self.select_src_dir, width=6).pack(side=tk.LEFT, padx=5)
        ttk.Label(left_frame, text="文件名").pack(anchor=tk.W, pady=(5,0))
        self.src_listbox = tk.Listbox(left_frame, height=5, width=55, exportselection=False)
        self.src_listbox.pack(fill=tk.BOTH, expand=True)
        self.src_listbox.bind("<<ListboxSelect>>", self.on_src_select)

        mid_frame = ttk.Frame(rename_frame)
        mid_frame.grid(row=0, column=1, sticky="ns", padx=10)
        ttk.Label(mid_frame, text="→", font=("Arial", 20)).pack(pady=(20,5))
        ttk.Label(mid_frame, text="剪贴板:").pack(anchor=tk.W)
        self.clipboard_var = tk.StringVar(value="")
        ttk.Entry(mid_frame, textvariable=self.clipboard_var, width=20, state="readonly").pack(pady=2)
        ttk.Button(mid_frame, text="复制选中", command=self.copy_selected, width=12).pack(pady=3)
        ttk.Button(mid_frame, text="粘贴到选中", command=self.paste_to_target, width=12).pack(pady=3)
        ttk.Button(mid_frame, text="刷新两列", command=self.refresh_both, width=12).pack(pady=3)

        right_frame = ttk.Frame(rename_frame)
        right_frame.grid(row=0, column=2, sticky="nsew", padx=5)
        ttk.Label(right_frame, text="目标文件夹（点击粘贴重命名）").pack(anchor=tk.W)
        dst_path_frame = ttk.Frame(right_frame)
        dst_path_frame.pack(fill=tk.X)
        self.dst_dir_var = tk.StringVar()
        ttk.Entry(dst_path_frame, textvariable=self.dst_dir_var, width=45).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(dst_path_frame, text="选择", command=self.select_dst_dir, width=6).pack(side=tk.LEFT, padx=5)
        ttk.Label(right_frame, text="文件名").pack(anchor=tk.W, pady=(5,0))
        self.dst_listbox = tk.Listbox(right_frame, height=5, width=55, exportselection=False)
        self.dst_listbox.pack(fill=tk.BOTH, expand=True)

        rename_frame.columnconfigure(0, weight=1)
        rename_frame.columnconfigure(2, weight=1)

        style = ttk.Style()
        style.configure("Accent.TButton", font=("Microsoft YaHei", 12, "bold"))

    def select_input_folder(self):
        p = filedialog.askdirectory()
        if p:
            self.input_var.set(p)
            self.log(f"输入文件夹: {p}")

    def select_output_folder(self):
        p = filedialog.askdirectory()
        if p:
            self.output_var.set(p)
            self.log(f"输出文件夹: {p}")

    def select_src_dir(self):
        p = filedialog.askdirectory()
        if p:
            self.src_dir_var.set(p)
            self.refresh_both()

    def select_dst_dir(self):
        p = filedialog.askdirectory()
        if p:
            self.dst_dir_var.set(p)
            self.refresh_both()

    def refresh_both(self):
        src = self.src_dir_var.get()
        dst = self.dst_dir_var.get()
        self.src_listbox.delete(0, tk.END)
        self.dst_listbox.delete(0, tk.END)
        if not src or not os.path.isdir(src):
            return
        exts = ('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v')
        files = [f for f in os.listdir(src) if f.lower().endswith(exts)]
        files.sort()
        for f in files:
            self.src_listbox.insert(tk.END, f)
            self.dst_listbox.insert(tk.END, f)
        self.log(f"重命名区已加载 {len(files)} 个文件")

    def on_src_select(self, event):
        sel = self.src_listbox.curselection()
        if sel:
            self.dst_listbox.selection_clear(0, tk.END)
            self.dst_listbox.selection_set(sel[0])
            self.dst_listbox.see(sel[0])

    def copy_selected(self):
        sel = self.src_listbox.curselection()
        if not sel:
            messagebox.showwarning("提示", "请先在左列选中一个文件")
            return
        name = self.src_listbox.get(sel[0])
        self.root.clipboard_clear()
        self.root.clipboard_append(name)
        self.clipboard_var.set(name)
        self.log(f"已复制: {name}")

    def paste_to_target(self):
        sel = self.dst_listbox.curselection()
        if not sel:
            messagebox.showwarning("提示", "请先在右列选中要替换的行")
            return
        try:
            cb = self.root.clipboard_get()
            idx = sel[0]
            self.dst_listbox.delete(idx)
            self.dst_listbox.insert(idx, cb)
            self.dst_listbox.selection_set(idx)
            self.log(f"已粘贴到第{idx+1}行: {cb}")
        except tk.TclError:
            messagebox.showwarning("提示", "剪贴板为空")

    def open_output_folder(self):
        d = self.output_var.get() or self.dst_dir_var.get()
        if d and os.path.isdir(d):
            os.startfile(d)
        else:
            messagebox.showwarning("提示", "输出文件夹不存在")

    def select_audio(self):
        p = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.aac *.m4a *.flac")])
        if p:
            self.audio_path.set(p)

    def select_cta(self):
        p = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv")])
        if p:
            self.cta_path.set(p)

    def select_mov_wm(self):
        p = filedialog.askopenfilename(filetypes=[("MOV with Alpha", "*.mov"), ("Video", "*.mp4 *.webm")])
        if p:
            self.mov_wm_path.set(p)

    def show_help(self):
        messagebox.showinfo("使用说明",
            "【基础用法】\n"
            "1. 选择输入文件夹和输出文件夹（上方）\n"
            "2. 勾选需要的功能，设置参数\n"
            "3. 点击顶部【一键批量处理】\n"
            "4. 输出文件自动保留原文件名\n\n"
            "【高级用法：批量重命名】\n"
            "1. 在底部重命名区选择源文件夹和目标文件夹\n"
            "2. 左列选中文件 → 点击复制 → 剪贴板显示\n"
            "3. 右列选中对应行 → 点击粘贴到选中 → 修改目标文件名\n"
            "4. 点击一键批量处理，按重命名映射输出\n\n"
            "落版截取秒数：填0=落版完整保留，填2=只取落版前2秒拼接\n"
            "水印持续秒数：填0=全程显示，填10=只显示前10秒后自动消失\n"
            "处理顺序：裁切 → 音频替换 → 落版拼接 → MOV水印 → 文字水印")

    def check_ffmpeg(self):
        try:
            r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
            self.log(f"FFmpeg 已就绪: {r.stdout.split(chr(10))[0]}")
        except Exception as e:
            self.log(f"FFmpeg 未安装: {e}")
            messagebox.showwarning("FFmpeg", "请先安装FFmpeg并添加到环境变量！")

    def log(self, msg):
        self.log_area.insert(tk.END, msg + "\n")
        self.log_area.see(tk.END)
        self.root.update_idletasks()

    def time_to_sec(self, s):
        s = s.strip()
        if ':' in s:
            p = s.split(':')
            if len(p) == 2:
                return int(p[0])*60 + int(p[1])
            elif len(p) == 3:
                return int(p[0])*3600 + int(p[1])*60 + int(p[2])
        return int(s)

    def get_duration(self, path):
        try:
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=noprint_wrappers=1:nokey=1", path],
                             capture_output=True, text=True, check=True)
            return float(r.stdout.strip())
        except:
            return 0

    def get_temp(self, final_path, suffix):
        d = os.path.dirname(final_path)
        b = os.path.splitext(os.path.basename(final_path))[0]
        return os.path.join(d, f".temp_{b}_{suffix}_{os.getpid()}.mp4")

    def run_ffmpeg(self, cmd):
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return r

    def _has_audio(self, path):
        try:
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                              "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
                             capture_output=True, text=True)
            return "audio" in r.stdout
        except:
            return False

    def cut(self, inp, out, start, end, mode):
        if mode == "保留":
            self.run_ffmpeg(["ffmpeg", "-i", inp, "-ss", str(start), "-to", str(end),
                           "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                           "-c:a", "aac", "-y", out])
        else:
            dur = self.get_duration(inp)
            if start <= 0:
                self.run_ffmpeg(["ffmpeg", "-i", inp, "-ss", str(end), "-c:v", "libx264",
                               "-preset", "fast", "-crf", "23", "-c:a", "aac", "-y", out])
            elif end >= dur:
                self.run_ffmpeg(["ffmpeg", "-i", inp, "-to", str(start), "-c:v", "libx264",
                               "-preset", "fast", "-crf", "23", "-c:a", "aac", "-y", out])
            else:
                f = (f"[0:v]trim=start=0:end={start},setpts=PTS-STARTPTS[v1];"
                     f"[0:a]atrim=start=0:end={start},asetpts=PTS-STARTPTS[a1];"
                     f"[0:v]trim=start={end}:end={dur},setpts=PTS-STARTPTS[v2];"
                     f"[0:a]atrim=start={end}:end={dur},asetpts=PTS-STARTPTS[a2];"
                     f"[v1][a1][v2][a2]concat=n=2:v=1:a=1[outv][outa]")
                self.run_ffmpeg(["ffmpeg", "-i", inp, "-filter_complex", f,
                               "-map", "[outv]", "-map", "[outa]",
                               "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                               "-c:a", "aac", "-y", out])

    def replace_audio(self, inp, audio, out):
        self.run_ffmpeg(["ffmpeg", "-i", inp, "-i", audio,
                        "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0",
                        "-shortest", "-y", out])

    def add_cta(self, inp, cta, out, keep_audio, trim_sec=0):
        """v16修复：改用TS中间格式拼接，彻底解决裁切后+落版时长异常问题"""
        # 处理落版截取
        if trim_sec > 0:
            cta_trimmed = self.get_temp(out, "cta_trim")
            if keep_audio:
                self.run_ffmpeg(["ffmpeg", "-i", cta, "-t", str(trim_sec),
                               "-c:v", "libx264", "-c:a", "aac", "-y", cta_trimmed])
            else:
                self.run_ffmpeg(["ffmpeg", "-i", cta, "-t", str(trim_sec), "-an",
                               "-c:v", "libx264", "-y", cta_trimmed])
            cta = cta_trimmed
        else:
            cta_trimmed = None

        # 检查音频情况
        main_has_audio = self._has_audio(inp)
        cta_has_audio = self._has_audio(cta) if keep_audio else False

        # 生成TS中间文件（MPEG-TS格式天生适合拼接，不受MP4的moov元数据影响）
        ts1 = self.get_temp(out, "ts1")
        ts2 = self.get_temp(out, "ts2")

        # 主视频转TS：确保有音频流（无音频则补静音）
        if main_has_audio:
            self.run_ffmpeg(["ffmpeg", "-i", inp, "-c", "copy",
                           "-bsf:v", "h264_mp4toannexb", "-f", "mpegts", "-y", ts1])
        else:
            self.run_ffmpeg(["ffmpeg", "-i", inp, "-f", "lavfi",
                           "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
                           "-c:v", "copy", "-c:a", "aac",
                           "-bsf:v", "h264_mp4toannexb", "-f", "mpegts", "-y", ts1])

        # 落版转TS：确保有音频流（无音频则补静音）
        if cta_has_audio:
            self.run_ffmpeg(["ffmpeg", "-i", cta, "-c", "copy",
                           "-bsf:v", "h264_mp4toannexb", "-f", "mpegts", "-y", ts2])
        else:
            self.run_ffmpeg(["ffmpeg", "-i", cta, "-f", "lavfi",
                           "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
                           "-c:v", "copy", "-c:a", "aac",
                           "-bsf:v", "h264_mp4toannexb", "-f", "mpegts", "-y", ts2])

        # concat TS（流式复制，速度极快，时长完全准确）
        list_file = tempfile.mktemp(suffix=".txt")
        with open(list_file, "w", encoding="utf-8") as f:
            f.write(f"file '{os.path.abspath(ts1).replace(os.sep, '/')}'\n")
            f.write(f"file '{os.path.abspath(ts2).replace(os.sep, '/')}'\n")

        self.run_ffmpeg(["ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file,
                       "-c", "copy", "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", "-y", out])

        # 清理临时文件
        for f in [ts1, ts2, list_file]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except:
                    pass
        if cta_trimmed and os.path.exists(cta_trimmed):
            try:
                os.remove(cta_trimmed)
            except:
                pass

    def add_mov_wm(self, inp, wm, out, x, y, duration_sec):
        overlay_params = f"{x}:{y}:shortest=1"
        if duration_sec > 0:
            overlay_params += f":enable='lte(t,{duration_sec})'"
        cmd = [
            "ffmpeg",
            "-i", inp,
            "-stream_loop", "-1",
            "-i", wm,
            "-filter_complex", f"[0:v][1:v]overlay={overlay_params}[outv]",
            "-map", "[outv]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "copy",
            "-shortest",
            "-y", out
        ]
        self.run_ffmpeg(cmd)

    def add_txt_wm(self, inp, out, text, direction, size, color):
        font = self.find_font()
        if not font:
            raise Exception("未找到系统字体")
        safe = text.replace(chr(92), chr(92)+chr(92)).replace("'", chr(92)+"'")
        if color.startswith("#"):
            color = color.replace("#", "0x")
        if direction == "从左往右":
            x, y = "mod(t*100,W-tw)", "10"
        elif direction == "从右往左":
            x, y = "W-mod(t*100,W+tw)", "10"
        elif direction == "从上往下":
            x, y = "10", "mod(t*100,H-th)"
        elif direction == "从下往上":
            x, y = "10", "H-mod(t*100,H+th)"
        else:
            x, y = "10", "10"
        vf = f"drawtext=fontfile='{font}':text='{safe}':fontsize={size}:fontcolor={color}:x={x}:y={y}"
        self.run_ffmpeg(["ffmpeg", "-i", inp, "-vf", vf,
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-c:a", "copy", "-y", out])

    def find_font(self):
        s = platform.system()
        cands = []
        if s == "Windows":
            cands = ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]
        elif s == "Darwin":
            cands = ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/PingFang.ttc"]
        else:
            cands = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        for f in cands:
            if os.path.exists(f):
                return f
        return ""

    def save_config(self):
        cfg = {
            "input_dir": self.input_var.get(),
            "output_dir": self.output_var.get(),
            "src_dir": self.src_dir_var.get(),
            "dst_dir": self.dst_dir_var.get(),
            "cut_enable": self.cut_enable.get(),
            "cut_mode": self.cut_mode.get(),
            "cut_start": self.cut_start.get(),
            "cut_end": self.cut_end.get(),
            "audio_enable": self.audio_enable.get(),
            "audio_path": self.audio_path.get(),
            "cta_enable": self.cta_enable.get(),
            "cta_path": self.cta_path.get(),
            "cta_keep_audio": self.cta_keep_audio.get(),
            "cta_trim": self.cta_trim.get(),
            "mov_wm_enable": self.mov_wm_enable.get(),
            "mov_wm_path": self.mov_wm_path.get(),
            "mov_wm_x": self.mov_wm_x.get(),
            "mov_wm_y": self.mov_wm_y.get(),
            "mov_wm_rb": self.mov_wm_rb.get(),
            "mov_wm_duration": self.mov_wm_duration.get(),
            "txt_wm_enable": self.txt_wm_enable.get(),
            "txt_wm_text": self.txt_wm_text.get(),
            "txt_wm_dir": self.txt_wm_dir.get(),
            "txt_wm_size": self.txt_wm_size.get(),
            "txt_wm_color": self.txt_wm_color.get(),
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self.log("配置已保存")
            messagebox.showinfo("保存配置", f"配置已保存到 {CONFIG_FILE}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.input_var.set(cfg.get("input_dir", ""))
            self.output_var.set(cfg.get("output_dir", ""))
            self.src_dir_var.set(cfg.get("src_dir", ""))
            self.dst_dir_var.set(cfg.get("dst_dir", ""))
            self.cut_enable.set(cfg.get("cut_enable", False))
            self.cut_mode.set(cfg.get("cut_mode", "保留"))
            self.cut_start.set(cfg.get("cut_start", "00:00"))
            self.cut_end.set(cfg.get("cut_end", "00:15"))
            self.audio_enable.set(cfg.get("audio_enable", False))
            self.audio_path.set(cfg.get("audio_path", ""))
            self.cta_enable.set(cfg.get("cta_enable", False))
            self.cta_path.set(cfg.get("cta_path", ""))
            self.cta_keep_audio.set(cfg.get("cta_keep_audio", False))
            self.cta_trim.set(cfg.get("cta_trim", "0"))
            self.mov_wm_enable.set(cfg.get("mov_wm_enable", False))
            self.mov_wm_path.set(cfg.get("mov_wm_path", ""))
            self.mov_wm_x.set(cfg.get("mov_wm_x", "10"))
            self.mov_wm_y.set(cfg.get("mov_wm_y", "10"))
            self.mov_wm_rb.set(cfg.get("mov_wm_rb", False))
            self.mov_wm_duration.set(cfg.get("mov_wm_duration", "0"))
            self.txt_wm_enable.set(cfg.get("txt_wm_enable", False))
            self.txt_wm_text.set(cfg.get("txt_wm_text", "Nov"))
            self.txt_wm_dir.set(cfg.get("txt_wm_dir", "静止"))
            self.txt_wm_size.set(cfg.get("txt_wm_size", "24"))
            self.txt_wm_color.set(cfg.get("txt_wm_color", "white"))
            if self.src_dir_var.get() and os.path.isdir(self.src_dir_var.get()):
                self.refresh_both()
            self.log("配置已加载")
        except Exception as e:
            self.log(f"加载配置失败: {e}")

    def start_process(self):
        t = threading.Thread(target=self.process_all)
        t.daemon = True
        t.start()

    def process_all(self):
        src_files = list(self.src_listbox.get(0, tk.END))
        dst_files = list(self.dst_listbox.get(0, tk.END))

        if src_files and dst_files and len(src_files) == len(dst_files):
            src_dir = self.src_dir_var.get()
            dst_dir = self.dst_dir_var.get()
            use_rename = True
        else:
            src_dir = self.input_var.get()
            dst_dir = self.output_var.get()
            use_rename = False

        if not src_dir or not dst_dir:
            messagebox.showerror("错误", "请选择输入/输出文件夹（或重命名区的源/目标文件夹）")
            return
        if not os.path.isdir(src_dir):
            messagebox.showerror("错误", "源文件夹不存在")
            return
        os.makedirs(dst_dir, exist_ok=True)

        if use_rename:
            file_map = list(zip(src_files, dst_files))
        else:
            exts = ('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v')
            files = [f for f in os.listdir(src_dir) if f.lower().endswith(exts)]
            files.sort()
            file_map = [(f, f) for f in files]

        if not file_map:
            self.log("没有文件需要处理")
            return

        total = len(file_map)
        self.progress["maximum"] = total
        self.progress["value"] = 0

        for idx, (src_name, dst_name) in enumerate(file_map, 1):
            inp = os.path.join(src_dir, src_name)
            out = os.path.join(dst_dir, dst_name)
            self.log(f"\n[{idx}/{total}] {src_name} -> {dst_name}")

            temps = []
            current = inp
            try:
                if self.cut_enable.get():
                    start = self.time_to_sec(self.cut_start.get())
                    end = self.time_to_sec(self.cut_end.get())
                    tmp = self.get_temp(out, "cut")
                    self.cut(current, tmp, start, end, self.cut_mode.get())
                    if current != inp:
                        temps.append(current)
                    current = tmp
                    self.log(f"  裁切 {self.cut_mode.get()} {start}s-{end}s")

                if self.audio_enable.get():
                    ap = self.audio_path.get()
                    if not ap or not os.path.exists(ap):
                        raise Exception("音频文件不存在")
                    tmp = self.get_temp(out, "audio")
                    self.replace_audio(current, ap, tmp)
                    if current != inp:
                        temps.append(current)
                    current = tmp
                    self.log("  音频替换完成")

                if self.cta_enable.get():
                    cp = self.cta_path.get()
                    if not cp or not os.path.exists(cp):
                        raise Exception("落版视频不存在")
                    trim_sec = int(self.cta_trim.get() or "0")
                    tmp = self.get_temp(out, "cta")
                    self.add_cta(current, cp, tmp, self.cta_keep_audio.get(), trim_sec)
                    if current != inp:
                        temps.append(current)
                    current = tmp
                    if trim_sec > 0:
                        self.log(f"  落版拼接完成（截取前{trim_sec}秒）")
                    else:
                        self.log("  落版拼接完成")

                if self.mov_wm_enable.get():
                    wp = self.mov_wm_path.get()
                    if not wp or not os.path.exists(wp):
                        raise Exception("水印MOV不存在")
                    if self.mov_wm_rb.get():
                        x, y = "W-w-10", "H-h-10"
                    else:
                        x, y = self.mov_wm_x.get(), self.mov_wm_y.get()
                    duration_sec = int(self.mov_wm_duration.get() or "0")
                    tmp = self.get_temp(out, "movwm")
                    self.add_mov_wm(current, wp, tmp, x, y, duration_sec)
                    if current != inp:
                        temps.append(current)
                    current = tmp
                    if duration_sec > 0:
                        self.log(f"  MOV水印叠加完成 ({x}:{y}) 显示{duration_sec}秒")
                    else:
                        self.log(f"  MOV水印叠加完成 ({x}:{y}) 全程显示")

                if self.txt_wm_enable.get():
                    tmp = self.get_temp(out, "txtwm")
                    self.add_txt_wm(current, tmp, self.txt_wm_text.get(),
                                   self.txt_wm_dir.get(), self.txt_wm_size.get(),
                                   self.txt_wm_color.get())
                    if current != inp:
                        temps.append(current)
                    current = tmp
                    self.log("  文字水印完成")

                if current != inp:
                    shutil.move(current, out)
                else:
                    shutil.copy2(inp, out)
                self.log(f"  完成: {dst_name}")

            except Exception as e:
                self.log(f"  失败: {str(e)}")
            finally:
                for t in temps:
                    try:
                        if os.path.exists(t):
                            os.remove(t)
                    except:
                        pass
                if current != inp and os.path.exists(current):
                    try:
                        os.remove(current)
                    except:
                        pass

            self.progress["value"] = idx
            self.root.update_idletasks()

        self.log(f"\n全部完成！共 {total} 个文件")
        messagebox.showinfo("完成", f"批量处理完成！共 {total} 个文件")

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoBatchProcessor(root)
    root.mainloop()
