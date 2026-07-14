import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
import threading
import platform
import shutil
import tempfile

class VideoBatchProcessor:
    def __init__(self, root):
        self.root = root
        self.root.title("视频批量处理工具 v11.0 — 支持AE透明MOV循环水印")
        self.root.geometry("1250x1350")
        self.root.minsize(1100, 1250)
        self.input_dir = ""
        self.output_dir = ""
        self.video_files = []
        self.setup_ui()
        self.check_ffmpeg()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=1200)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        ttk.Label(scrollable_frame, text="视频批量处理工具 v11.0", 
                 font=("Microsoft YaHei", 18, "bold")).pack(pady=(0, 10))

        ttk.Button(scrollable_frame, text="使用说明", command=self.show_help).pack(anchor=tk.W, padx=10, pady=5)

        folder_frame = ttk.Frame(scrollable_frame)
        folder_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(folder_frame, text="输入文件夹:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.input_var = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.input_var, width=60).grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Button(folder_frame, text="选择", command=self.select_input).grid(row=0, column=2)

        ttk.Label(folder_frame, text="输出文件夹:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.output_var = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.output_var, width=60).grid(row=1, column=1, sticky=tk.EW, padx=5)
        ttk.Button(folder_frame, text="选择", command=self.select_output).grid(row=1, column=2)
        folder_frame.columnconfigure(1, weight=1)

        cut_frame = ttk.LabelFrame(scrollable_frame, text="裁切设置", padding=10)
        cut_frame.pack(fill=tk.X, padx=10, pady=10)

        self.cut_enable = tk.BooleanVar(value=False)
        ttk.Checkbutton(cut_frame, text="启用裁切", variable=self.cut_enable).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(cut_frame, text="模式:").grid(row=0, column=1, sticky=tk.W, padx=(20,0))
        self.cut_mode = tk.StringVar(value="保留")
        ttk.Combobox(cut_frame, textvariable=self.cut_mode, values=["保留", "删除"], width=10, state="readonly").grid(row=0, column=2, sticky=tk.W, padx=5)
        ttk.Label(cut_frame, text="保留=只留这段 / 删除=去掉这段").grid(row=0, column=3, sticky=tk.W, padx=10)

        ttk.Label(cut_frame, text="开始时间:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.cut_start = tk.StringVar(value="00:00")
        ttk.Entry(cut_frame, textvariable=self.cut_start, width=10).grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Label(cut_frame, text="结束时间:").grid(row=1, column=2, sticky=tk.W, padx=(20,0))
        self.cut_end = tk.StringVar(value="00:15")
        ttk.Entry(cut_frame, textvariable=self.cut_end, width=10).grid(row=1, column=3, sticky=tk.W, padx=5)
        ttk.Label(cut_frame, text="(格式: 秒 或 分:秒，如 90 或 1:30)").grid(row=1, column=4, sticky=tk.W, padx=10)

        audio_frame = ttk.LabelFrame(scrollable_frame, text="音频替换", padding=10)
        audio_frame.pack(fill=tk.X, padx=10, pady=10)

        self.audio_enable = tk.BooleanVar(value=False)
        ttk.Checkbutton(audio_frame, text="启用音频替换", variable=self.audio_enable).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(audio_frame, text="音频文件:").grid(row=0, column=1, sticky=tk.W, padx=(20,0))
        self.audio_path = tk.StringVar()
        ttk.Entry(audio_frame, textvariable=self.audio_path, width=50).grid(row=0, column=2, sticky=tk.EW, padx=5)
        ttk.Button(audio_frame, text="选择", command=self.select_audio).grid(row=0, column=3, padx=5)

        cta_frame = ttk.LabelFrame(scrollable_frame, text="结尾落版 (视频拼接)", padding=10)
        cta_frame.pack(fill=tk.X, padx=10, pady=10)

        self.cta_enable = tk.BooleanVar(value=False)
        ttk.Checkbutton(cta_frame, text="启用结尾落版", variable=self.cta_enable).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(cta_frame, text="落版视频:").grid(row=0, column=1, sticky=tk.W, padx=(20,0))
        self.cta_path = tk.StringVar()
        ttk.Entry(cta_frame, textvariable=self.cta_path, width=50).grid(row=0, column=2, sticky=tk.EW, padx=5)
        ttk.Button(cta_frame, text="选择", command=self.select_cta).grid(row=0, column=3, padx=5)

        self.cta_keep_audio = tk.BooleanVar(value=False)
        ttk.Checkbutton(cta_frame, text="落版保留原音频（不勾选则只取画面，音频沿用主视频）", 
                       variable=self.cta_keep_audio).grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=5)

        mov_frame = ttk.LabelFrame(scrollable_frame, text="AE透明MOV循环水印 (推荐)", padding=10)
        mov_frame.pack(fill=tk.X, padx=10, pady=10)

        self.mov_wm_enable = tk.BooleanVar(value=False)
        ttk.Checkbutton(mov_frame, text="启用MOV水印（AE导出带Alpha通道的MOV，自动循环匹配主视频长度）", 
                       variable=self.mov_wm_enable).grid(row=0, column=0, sticky=tk.W, columnspan=5)

        ttk.Label(mov_frame, text="水印MOV:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.mov_wm_path = tk.StringVar()
        ttk.Entry(mov_frame, textvariable=self.mov_wm_path, width=50).grid(row=1, column=1, sticky=tk.EW, padx=5)
        ttk.Button(mov_frame, text="选择", command=self.select_mov_wm).grid(row=1, column=2, padx=5)

        ttk.Label(mov_frame, text="位置X:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.mov_wm_x = tk.StringVar(value="10")
        ttk.Entry(mov_frame, textvariable=self.mov_wm_x, width=10).grid(row=2, column=1, sticky=tk.W, padx=5)
        ttk.Label(mov_frame, text="位置Y:").grid(row=2, column=2, sticky=tk.W, padx=(20,0))
        self.mov_wm_y = tk.StringVar(value="10")
        ttk.Entry(mov_frame, textvariable=self.mov_wm_y, width=10).grid(row=2, column=3, sticky=tk.W, padx=5)

        self.mov_wm_rb = tk.BooleanVar(value=False)
        ttk.Checkbutton(mov_frame, text="右下角对齐（自动覆盖X/Y，表达式: W-w-10:H-h-10）", 
                       variable=self.mov_wm_rb).grid(row=3, column=0, columnspan=5, sticky=tk.W, pady=5)

        ttk.Label(mov_frame, text="AE导出建议：格式MOV + 编码QuickTime Animation(RLE)或ProRes 4444，必须保留Alpha通道", 
                 foreground="gray").grid(row=4, column=0, columnspan=5, sticky=tk.W)
        ttk.Label(mov_frame, text="水印视频建议首尾无缝循环（最后一帧=第一帧），避免循环衔接处跳帧", 
                 foreground="gray").grid(row=5, column=0, columnspan=5, sticky=tk.W)

        txt_frame = ttk.LabelFrame(scrollable_frame, text="文字动态水印 (Python生成)", padding=10)
        txt_frame.pack(fill=tk.X, padx=10, pady=10)

        self.txt_wm_enable = tk.BooleanVar(value=False)
        ttk.Checkbutton(txt_frame, text="启用文字水印", variable=self.txt_wm_enable).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(txt_frame, text="文字:").grid(row=0, column=1, sticky=tk.W, padx=(20,0))
        self.txt_wm_text = tk.StringVar(value="Nov")
        ttk.Entry(txt_frame, textvariable=self.txt_wm_text, width=20).grid(row=0, column=2, sticky=tk.W, padx=5)

        ttk.Label(txt_frame, text="方向:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.txt_wm_dir = tk.StringVar(value="静止")
        ttk.Combobox(txt_frame, textvariable=self.txt_wm_dir, 
                    values=["静止", "从左往右", "从右往左", "从上往下", "从下往上"], 
                    width=12, state="readonly").grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Label(txt_frame, text="大小:").grid(row=1, column=2, sticky=tk.W, padx=(20,0))
        self.txt_wm_size = tk.StringVar(value="24")
        ttk.Entry(txt_frame, textvariable=self.txt_wm_size, width=8).grid(row=1, column=3, sticky=tk.W, padx=5)
        ttk.Label(txt_frame, text="颜色:").grid(row=1, column=4, sticky=tk.W, padx=(20,0))
        self.txt_wm_color = tk.StringVar(value="white")
        ttk.Entry(txt_frame, textvariable=self.txt_wm_color, width=10).grid(row=1, column=5, sticky=tk.W, padx=5)

        list_frame = ttk.LabelFrame(scrollable_frame, text="文件列表与重命名（双击目标名可编辑）", padding=10)
        list_frame.pack(fill=tk.X, padx=10, pady=10)

        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="刷新列表", command=self.refresh_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="复制选中源名", command=self.copy_source).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="粘贴到目标", command=self.paste_target).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="重置目标名", command=self.reset_targets).pack(side=tk.LEFT, padx=5)

        self.file_tree = ttk.Treeview(list_frame, columns=("source", "target"), show="headings", height=8)
        self.file_tree.heading("source", text="源文件名（原始）")
        self.file_tree.heading("target", text="目标文件名（点击复制/粘贴修改）")
        self.file_tree.column("source", width=450)
        self.file_tree.column("target", width=450)
        self.file_tree.pack(fill=tk.X)
        self.file_tree.bind("<Double-1>", self.edit_target)

        action_frame = ttk.Frame(scrollable_frame)
        action_frame.pack(fill=tk.X, pady=20)
        ttk.Button(action_frame, text="开始批量处理", command=self.start_process, 
                  style="Accent.TButton").pack(pady=10)

        self.progress = ttk.Progressbar(scrollable_frame, orient=tk.HORIZONTAL, length=400, mode='determinate')
        self.progress.pack(fill=tk.X, padx=10, pady=5)

        log_frame = ttk.LabelFrame(scrollable_frame, text="处理日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_area = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD)
        self.log_area.pack(fill=tk.BOTH, expand=True)

        style = ttk.Style()
        style.configure("Accent.TButton", font=("Microsoft YaHei", 12, "bold"))

    def show_help(self):
        messagebox.showinfo("使用说明", 
            "1. 选择输入/输出文件夹\n"
            "2. 勾选需要的功能模块（可同时多个）\n"
            "3. AE导出MOV水印：格式选MOV，编码选QuickTime Animation(RLE)或ProRes 4444，保留Alpha\n"
            "4. 文件列表中双击可修改目标文件名，或选中后点击复制/粘贴按钮\n"
            "5. 点击开始批量处理，自动保留你设定的目标文件名\n\n"
            "处理顺序：裁切 -> 音频替换 -> 落版拼接 -> MOV水印 -> 文字水印\n"
            "临时文件自动清理，处理完成后输出到目标文件夹。")

    def select_input(self):
        p = filedialog.askdirectory()
        if p:
            self.input_var.set(p)
            self.refresh_files()

    def select_output(self):
        p = filedialog.askdirectory()
        if p:
            self.output_var.set(p)

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

    def refresh_files(self):
        d = self.input_var.get()
        if not d or not os.path.isdir(d):
            return
        for i in self.file_tree.get_children():
            self.file_tree.delete(i)
        exts = ('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v')
        self.video_files = [f for f in os.listdir(d) if f.lower().endswith(exts)]
        self.video_files.sort()
        for f in self.video_files:
            self.file_tree.insert("", tk.END, values=(f, f))
        self.log(f"已加载 {len(self.video_files)} 个视频文件")

    def copy_source(self):
        sel = self.file_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选中一行")
            return
        v = self.file_tree.item(sel[0], "values")
        self.root.clipboard_clear()
        self.root.clipboard_append(v[0])
        self.log(f"已复制: {v[0]}")

    def paste_target(self):
        sel = self.file_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选中一行")
            return
        try:
            cb = self.root.clipboard_get()
            v = self.file_tree.item(sel[0], "values")
            self.file_tree.item(sel[0], values=(v[0], cb))
            self.log(f"已粘贴目标: {cb}")
        except tk.TclError:
            messagebox.showwarning("提示", "剪贴板为空")

    def reset_targets(self):
        for i in self.file_tree.get_children():
            v = self.file_tree.item(i, "values")
            self.file_tree.item(i, values=(v[0], v[0]))
        self.log("已重置所有目标文件名")

    def edit_target(self, event):
        sel = self.file_tree.selection()
        if not sel:
            return
        v = self.file_tree.item(sel[0], "values")
        new = simpledialog.askstring("修改文件名", "目标文件名:", initialvalue=v[1])
        if new:
            self.file_tree.item(sel[0], values=(v[0], new))

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

    def add_cta(self, inp, cta, out, keep_audio):
        list_file = tempfile.mktemp(suffix=".txt")
        try:
            if keep_audio:
                with open(list_file, "w", encoding="utf-8") as f:
                    f.write(f"file '{os.path.abspath(inp).replace(os.sep, '/')}'\n")
                    f.write(f"file '{os.path.abspath(cta).replace(os.sep, '/')}'\n")
                self.run_ffmpeg(["ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file,
                               "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                               "-c:a", "aac", "-y", out])
            else:
                silent = tempfile.mktemp(suffix=".mp4")
                try:
                    self.run_ffmpeg(["ffmpeg", "-i", cta, "-an", "-c:v", "libx264", "-y", silent])
                    with open(list_file, "w", encoding="utf-8") as f:
                        f.write(f"file '{os.path.abspath(inp).replace(os.sep, '/')}'\n")
                        f.write(f"file '{os.path.abspath(silent).replace(os.sep, '/')}'\n")
                    self.run_ffmpeg(["ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file,
                                   "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                                   "-c:a", "aac", "-y", out])
                finally:
                    if os.path.exists(silent):
                        os.remove(silent)
        finally:
            if os.path.exists(list_file):
                os.remove(list_file)

    def add_mov_wm(self, inp, wm, out, x, y):
        self.run_ffmpeg([
            "ffmpeg",
            "-i", inp,
            "-stream_loop", "-1",
            "-i", wm,
            "-filter_complex", f"[0:v][1:v]overlay={x}:{y}:shortest=1",
            "-c:a", "copy",
            "-y", out
        ])

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

    def start_process(self):
        t = threading.Thread(target=self.process_all)
        t.daemon = True
        t.start()

    def process_all(self):
        inp_dir = self.input_var.get()
        out_dir = self.output_var.get()
        if not inp_dir or not out_dir:
            messagebox.showerror("错误", "请选择输入和输出文件夹")
            return
        if not os.path.isdir(inp_dir):
            messagebox.showerror("错误", "输入文件夹不存在")
            return
        os.makedirs(out_dir, exist_ok=True)

        file_map = {}
        for i in self.file_tree.get_children():
            v = self.file_tree.item(i, "values")
            file_map[v[0]] = v[1]
        if not file_map:
            self.log("没有文件需要处理")
            return

        total = len(file_map)
        self.progress["maximum"] = total
        self.progress["value"] = 0

        for idx, (src, dst) in enumerate(file_map.items(), 1):
            inp = os.path.join(inp_dir, src)
            out = os.path.join(out_dir, dst)
            self.log(f"\n[{idx}/{total}] {src} -> {dst}")

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
                    tmp = self.get_temp(out, "cta")
                    self.add_cta(current, cp, tmp, self.cta_keep_audio.get())
                    if current != inp:
                        temps.append(current)
                    current = tmp
                    self.log(f"  落版拼接完成")

                if self.mov_wm_enable.get():
                    wp = self.mov_wm_path.get()
                    if not wp or not os.path.exists(wp):
                        raise Exception("水印MOV不存在")
                    if self.mov_wm_rb.get():
                        x, y = "W-w-10", "H-h-10"
                    else:
                        x, y = self.mov_wm_x.get(), self.mov_wm_y.get()
                    tmp = self.get_temp(out, "movwm")
                    self.add_mov_wm(current, wp, tmp, x, y)
                    if current != inp:
                        temps.append(current)
                    current = tmp
                    self.log(f"  MOV水印叠加完成 ({x}:{y})")

                if self.txt_wm_enable.get():
                    tmp = self.get_temp(out, "txtwm")
                    self.add_txt_wm(current, tmp, self.txt_wm_text.get(),
                                   self.txt_wm_dir.get(), self.txt_wm_size.get(),
                                   self.txt_wm_color.get())
                    if current != inp:
                        temps.append(current)
                    current = tmp
                    self.log(f"  文字水印完成")

                if current != inp:
                    shutil.move(current, out)
                else:
                    shutil.copy2(inp, out)
                self.log(f"  完成: {dst}")

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
