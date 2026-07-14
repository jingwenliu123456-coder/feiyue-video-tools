import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import json
import platform
import shutil

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class VideoBatchProcessor:
    def __init__(self, root):
        self.root = root
        self.root.title("视频批量处理工具 v7.0")
        self.root.geometry("1000x1020")
        self.root.minsize(900, 970)
        self.clipboard_filename = ""
        self.video_files = []
        self.system_font = self.detect_system_font()
        self.setup_ui()
        self.check_ffmpeg()

    def detect_system_font(self):
        system = platform.system()
        font_paths = []
        if system == "Windows":
            font_paths = [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/segoeui.ttf"
            ]
        elif system == "Darwin":
            font_paths = [
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/PingFang.ttc",
                "/Library/Fonts/Arial.ttf"
            ]
        else:
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
            ]
        for fp in font_paths:
            if os.path.exists(fp):
                return fp
        return ""

    def check_ffmpeg(self):
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.split("\n")[0]
                self.log(f"FFmpeg已安装: {version}")
            else:
                self.log("FFmpeg未安装")
        except FileNotFoundError:
            self.log("FFmpeg未找到！请安装并添加到环境变量")
            messagebox.showwarning("FFmpeg未安装", "请先安装FFmpeg！\nWindows: https://ffmpeg.org/download.html\nMac: brew install ffmpeg")

    def get_video_info(self, video_path):
        """获取视频分辨率、帧率、时长"""
        try:
            cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate", "-of", "csv=p=0", video_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                if len(parts) >= 3:
                    w, h = int(parts[0]), int(parts[1])
                    fps = parts[2]
                    # 计算fps数值
                    if "/" in fps:
                        num, den = fps.split("/")
                        fps_val = int(num) / int(den)
                    else:
                        fps_val = float(fps)
                    return w, h, fps_val
        except Exception as e:
            self.log(f"  获取视频信息失败: {e}")
        return 1920, 1080, 30.0

    def get_video_duration(self, video_path):
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except:
            pass
        return 0

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        row = 0

        title_label = ttk.Label(main_frame, text="视频批量处理工具 v7.0", font=("Microsoft YaHei", 16, "bold"))
        title_label.grid(row=row, column=0, columnspan=3, pady=(0, 10))
        row += 1

        # 使用说明按钮
        ttk.Button(main_frame, text="📖 使用说明", command=self.show_help).grid(row=row, column=0, sticky=tk.W, pady=5)
        row += 1

        ttk.Label(main_frame, text="输入文件夹:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.input_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.input_var, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="选择", command=self.select_input_folder).grid(row=row, column=2, padx=5)
        row += 1

        ttk.Label(main_frame, text="输出文件夹:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.output_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.output_var, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="选择", command=self.select_output_folder).grid(row=row, column=2, padx=5)
        row += 1

        # === 裁切设置 ===
        cut_frame = ttk.LabelFrame(main_frame, text="裁切设置", padding="10")
        cut_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        cut_frame.columnconfigure(1, weight=1)

        self.cut_enable_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(cut_frame, text="启用裁切", variable=self.cut_enable_var).grid(row=0, column=0, sticky=tk.W)

        ttk.Label(cut_frame, text="模式:").grid(row=0, column=1, sticky=tk.W, padx=(20,0))
        self.cut_mode_var = tk.StringVar(value="保留")
        ttk.Combobox(cut_frame, textvariable=self.cut_mode_var, values=["保留", "删除"], width=10, state="readonly").grid(row=0, column=2, sticky=tk.W, padx=5)
        ttk.Label(cut_frame, text="保留=只留这段 / 删除=去掉这段").grid(row=0, column=3, sticky=tk.W, padx=10)

        ttk.Label(cut_frame, text="开始时间:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.start_time_var = tk.StringVar(value="00:00")
        ttk.Entry(cut_frame, textvariable=self.start_time_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=5)

        ttk.Label(cut_frame, text="结束时间:").grid(row=1, column=2, sticky=tk.W, padx=(20, 0))
        self.end_time_var = tk.StringVar(value="00:15")
        ttk.Entry(cut_frame, textvariable=self.end_time_var, width=10).grid(row=1, column=3, sticky=tk.W, padx=5)

        ttk.Label(cut_frame, text="(格式: 秒 或 分:秒)").grid(row=1, column=4, sticky=tk.W, padx=10)
        row += 1

        # === 音频替换 ===
        audio_frame = ttk.LabelFrame(main_frame, text="音频替换", padding="10")
        audio_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        audio_frame.columnconfigure(1, weight=1)

        self.audio_enable_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(audio_frame, text="启用音频替换", variable=self.audio_enable_var).grid(row=0, column=0, sticky=tk.W)

        ttk.Label(audio_frame, text="音频文件:").grid(row=0, column=1, sticky=tk.W, padx=(20,0))
        self.audio_var = tk.StringVar()
        ttk.Entry(audio_frame, textvariable=self.audio_var, width=40).grid(row=0, column=2, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(audio_frame, text="选择", command=self.select_audio).grid(row=0, column=3, padx=5)
        row += 1

        # === 结尾落版 ===
        cta_frame = ttk.LabelFrame(main_frame, text="结尾落版 (拼接模式)", padding="10")
        cta_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        cta_frame.columnconfigure(1, weight=1)

        self.cta_enable_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(cta_frame, text="启用结尾落版", variable=self.cta_enable_var).grid(row=0, column=0, sticky=tk.W)

        ttk.Label(cta_frame, text="落版视频:").grid(row=0, column=1, sticky=tk.W, padx=(20,0))
        self.cta_var = tk.StringVar()
        ttk.Entry(cta_frame, textvariable=self.cta_var, width=40).grid(row=0, column=2, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(cta_frame, text="选择", command=self.select_cta).grid(row=0, column=3, padx=5)

        self.cta_audio_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(cta_frame, text="落版保留原音频", variable=self.cta_audio_var).grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=5)
        row += 1

        # === 动态水印 ===
        wm_frame = ttk.LabelFrame(main_frame, text="动态文字水印", padding="10")
        wm_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        wm_frame.columnconfigure(1, weight=1)

        self.wm_enable_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(wm_frame, text="启用水印", variable=self.wm_enable_var).grid(row=0, column=0, sticky=tk.W)

        ttk.Label(wm_frame, text="水印文字:").grid(row=0, column=1, sticky=tk.W, padx=(20,0))
        self.wm_text_var = tk.StringVar(value="Nov")
        ttk.Entry(wm_frame, textvariable=self.wm_text_var, width=20).grid(row=0, column=2, sticky=tk.W, padx=5)

        ttk.Label(wm_frame, text="运动方向:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.wm_dir_var = tk.StringVar(value="从左往右")
        ttk.Combobox(wm_frame, textvariable=self.wm_dir_var, 
                     values=["从左往右", "从右往左", "从上往下", "从下往上", 
                             "左上到右下", "右下到左上", "右上到左下", "左下到右上", "波浪", "随机"], 
                     width=12, state="readonly").grid(row=1, column=1, sticky=tk.W, padx=5)

        ttk.Label(wm_frame, text="滚动速度:").grid(row=1, column=2, sticky=tk.W, padx=(20, 0))
        self.wm_speed_var = tk.IntVar(value=100)
        ttk.Spinbox(wm_frame, from_=50, to=500, increment=10, textvariable=self.wm_speed_var, width=8).grid(row=1, column=3, sticky=tk.W, padx=5)
        ttk.Label(wm_frame, text="px/s").grid(row=1, column=4, sticky=tk.W)

        ttk.Label(wm_frame, text="垂直位置:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.wm_y_var = tk.StringVar(value="底部")
        ttk.Combobox(wm_frame, textvariable=self.wm_y_var, values=["顶部", "中部", "底部"], width=10, state="readonly").grid(row=2, column=1, sticky=tk.W, padx=5)

        ttk.Label(wm_frame, text="字体大小:").grid(row=2, column=2, sticky=tk.W, padx=(20, 0))
        self.wm_size_var = tk.IntVar(value=36)
        ttk.Spinbox(wm_frame, from_=12, to=120, increment=2, textvariable=self.wm_size_var, width=8).grid(row=2, column=3, sticky=tk.W, padx=5)
        ttk.Label(wm_frame, text="px").grid(row=2, column=4, sticky=tk.W)

        ttk.Label(wm_frame, text="字体颜色:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.wm_color_var = tk.StringVar(value="white")
        ttk.Combobox(wm_frame, textvariable=self.wm_color_var, values=["white", "black", "red", "yellow", "green", "blue"], width=10, state="readonly").grid(row=3, column=1, sticky=tk.W, padx=5)

        ttk.Label(wm_frame, text="描边颜色:").grid(row=3, column=2, sticky=tk.W, padx=(20, 0))
        self.wm_border_var = tk.StringVar(value="black")
        ttk.Combobox(wm_frame, textvariable=self.wm_border_var, values=["none", "black", "white", "red"], width=10, state="readonly").grid(row=3, column=3, sticky=tk.W, padx=5)

        ttk.Label(wm_frame, text="字体文件:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.wm_font_var = tk.StringVar(value=self.system_font)
        ttk.Entry(wm_frame, textvariable=self.wm_font_var, width=50).grid(row=4, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(wm_frame, text="选择", command=self.select_font).grid(row=4, column=3, padx=5)

        if not self.system_font:
            ttk.Label(wm_frame, text="⚠️ 未检测到系统字体，请手动选择", foreground="red").grid(row=5, column=0, columnspan=4, sticky=tk.W)
        row += 1

        list_frame = ttk.LabelFrame(main_frame, text="文件列表 (点击复制文件名 | 点击粘贴重命名)", padding="10")
        list_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        columns = ("filename", "status", "actions")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=8)
        self.tree.heading("filename", text="文件名")
        self.tree.heading("status", text="状态")
        self.tree.heading("actions", text="操作")
        self.tree.column("filename", width=400)
        self.tree.column("status", width=100)
        self.tree.column("actions", width=150)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        self.tree.bind("<Double-1>", self.on_tree_double_click)
        row += 1

        clipboard_frame = ttk.Frame(main_frame)
        clipboard_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(clipboard_frame, text="剪贴板:").pack(side=tk.LEFT)
        self.clipboard_label = ttk.Label(clipboard_frame, text="(空)", foreground="gray")
        self.clipboard_label.pack(side=tk.LEFT, padx=5)

        ttk.Button(clipboard_frame, text="粘贴到选中文件", command=self.paste_to_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(clipboard_frame, text="刷新列表", command=self.refresh_file_list).pack(side=tk.RIGHT, padx=5)
        row += 1

        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=15)

        ttk.Button(btn_frame, text="一键批量处理", command=self.start_batch_process, width=20).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="保存配置", command=self.save_config).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="打开输出文件夹", command=self.open_output_folder).pack(side=tk.LEFT, padx=10)
        row += 1

        log_frame = ttk.LabelFrame(main_frame, text="处理日志", padding="5")
        log_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        row += 1

        main_frame.rowconfigure(row-2, weight=1)
        main_frame.rowconfigure(row-1, weight=1)

    def log(self, message):
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)

    def show_help(self):
        help_text = """
使用说明：

1. 选择输入文件夹（含原始视频）和输出文件夹

2. 勾选需要的功能（可任意组合）：
   [裁切] 勾选"启用裁切" → 选保留/删除 → 填时间
   [音频] 勾选"启用音频替换" → 选音频文件
   [水印] 勾选"启用水印" → 填文字 → 选方向
   [落版] 勾选"启用结尾落版" → 选CTA视频

3. 点击"一键批量处理"

处理顺序：裁切 → 音频 → 水印 → 落版拼接

常见问题：
• 落版没加上：检查是否勾选了"启用结尾落版"
• 水印没显示：检查字体文件是否存在
• 处理失败：看日志里的红色报错信息
"""
        messagebox.showinfo("使用说明", help_text)

    def select_input_folder(self):
        folder = filedialog.askdirectory(title="选择输入文件夹")
        if folder:
            self.input_var.set(folder)
            self.refresh_file_list()

    def select_output_folder(self):
        folder = filedialog.askdirectory(title="选择输出文件夹")
        if folder:
            self.output_var.set(folder)

    def select_audio(self):
        file = filedialog.askopenfilename(title="选择音频文件", filetypes=[("音频文件", "*.mp3 *.wav *.aac *.m4a"), ("所有文件", "*.*")])
        if file:
            self.audio_var.set(file)
            self.audio_enable_var.set(True)

    def select_cta(self):
        file = filedialog.askopenfilename(title="选择结尾落版视频", filetypes=[("视频文件", "*.mp4 *.mov *.avi"), ("所有文件", "*.*")])
        if file:
            self.cta_var.set(file)
            self.cta_enable_var.set(True)

    def select_font(self):
        file = filedialog.askopenfilename(title="选择字体文件", filetypes=[("字体文件", "*.ttf *.ttc *.otf"), ("所有文件", "*.*")])
        if file:
            self.wm_font_var.set(file)

    def refresh_file_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        input_folder = self.input_var.get()
        if not input_folder or not os.path.exists(input_folder):
            return
        video_extensions = [".mp4", ".mov", ".avi", ".mkv", ".m4v"]
        self.video_files = []
        for f in sorted(os.listdir(input_folder)):
            ext = os.path.splitext(f)[1].lower()
            if ext in video_extensions:
                self.video_files.append(f)
                self.tree.insert("", tk.END, values=(f, "待处理", "复制 | 粘贴"))
        self.log(f"找到 {len(self.video_files)} 个视频文件")

    def on_tree_double_click(self, event):
        item = self.tree.selection()[0]
        col = self.tree.identify_column(event.x)
        filename = self.tree.item(item, "values")[0]
        if col == "#3":
            if not self.clipboard_filename:
                self.copy_filename(filename)
            else:
                self.paste_to_item(item)
        else:
            self.copy_filename(filename)

    def copy_filename(self, filename):
        self.clipboard_filename = filename
        self.clipboard_label.config(text=filename, foreground="green")
        self.log(f"已复制: {filename}")

    def paste_to_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择一个文件")
            return
        if not self.clipboard_filename:
            messagebox.showwarning("提示", "剪贴板为空")
            return
        for item in selected:
            self.paste_to_item(item)

    def paste_to_item(self, item):
        if not self.clipboard_filename:
            return
        old_name = self.tree.item(item, "values")[0]
        new_name = self.clipboard_filename
        input_folder = self.input_var.get()
        old_path = os.path.join(input_folder, old_name)
        new_path = os.path.join(input_folder, new_name)
        if old_name != new_name and os.path.exists(old_path) and not os.path.exists(new_path):
            try:
                os.rename(old_path, new_path)
                self.tree.item(item, values=(new_name, "已重命名", "复制 | 粘贴"))
                self.log(f"重命名: {old_name} -> {new_name}")
            except Exception as e:
                self.log(f"重命名失败: {e}")
        else:
            self.log(f"无法重命名: {old_name} -> {new_name}")

    def time_to_seconds(self, time_str):
        try:
            if ":" in time_str:
                parts = time_str.split(":")
                if len(parts) == 2:
                    return int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            else:
                return int(time_str)
        except:
            return 0

    def get_watermark_exprs(self, direction, speed, y_pos):
        base_y = "20" if y_pos == "顶部" else "(h-th)/2" if y_pos == "中部" else "h-th-20"
        if direction == "从左往右":
            return (f"mod(t*{speed},W+tw)-tw", base_y)
        elif direction == "从右往左":
            return (f"W-tw-mod(t*{speed},W+tw)", base_y)
        elif direction == "从上往下":
            return ("(W-tw)/2", f"mod(t*{speed},H+th)-th")
        elif direction == "从下往上":
            return ("(W-tw)/2", f"H-th-mod(t*{speed},H+th)")
        elif direction == "左上到右下":
            return (f"mod(t*{speed},W+tw)-tw", f"mod(t*{speed},H+th)-th")
        elif direction == "右下到左上":
            return (f"W-tw-mod(t*{speed},W+tw)", f"H-th-mod(t*{speed},H+th)")
        elif direction == "右上到左下":
            return (f"W-tw-mod(t*{speed},W+tw)", f"mod(t*{speed},H+th)-th")
        elif direction == "左下到右上":
            return (f"mod(t*{speed},W+tw)-tw", f"H-th-mod(t*{speed},H+th)")
        elif direction == "波浪":
            return (f"(W-tw)/2+(W/2-tw/2)*sin(t*{speed}/100)", f"{base_y}+(th)*cos(t*{speed}/150)")
        elif direction == "随机":
            return (f"mod(abs(sin(t*{speed}/200)*cos(t*{speed}/300))*W,W+tw)-tw",
                    f"mod(abs(cos(t*{speed}/250)*sin(t*{speed}/350))*H,H+th)-th")
        else:
            return ("(W-tw)/2", base_y)

    def build_watermark_filter(self, text, direction, speed, y_pos, font_size, color, border, font_file):
        x_expr, y_expr = self.get_watermark_exprs(direction, speed, y_pos)
        # 字体路径：反斜杠转斜杠，空格路径加引号
        font_path = font_file.replace(chr(92), "/")
        if " " in font_path:
            font_path = f"'{font_path}'"
        filter_parts = [
            f"fontfile={font_path}",
            f"text='{text}'",
            f"x={x_expr}",
            f"y={y_expr}",
            f"fontsize={font_size}",
            f"fontcolor={color}"
        ]
        if border != "none":
            filter_parts.append(f"borderw=2:bordercolor={border}")
        return ":".join(filter_parts)

    def concat_cta(self, main_video, cta_video, output_file, cta_keep_audio):
        """使用filter_complex concat拼接CTA，统一编码确保100%成功"""
        try:
            self.log("  [CTA] 获取视频参数...")
            w, h, fps = self.get_video_info(main_video)
            self.log(f"  [CTA] 主视频参数: {w}x{h} @ {fps}fps")

            # 构建filter_complex：统一分辨率、帧率、SAR，然后concat
            scale_filter = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"

            if cta_keep_audio:
                # CTA保留音频
                filter_complex = (
                    f"[0:v]{scale_filter}[v0];[1:v]{scale_filter}[v1];"
                    f"[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[outv][outa]"
                )
                cmd = [
                    "ffmpeg", "-y", "-i", main_video, "-i", cta_video,
                    "-filter_complex", filter_complex,
                    "-map", "[outv]", "-map", "[outa]",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                    output_file
                ]
            else:
                # CTA静音，使用anullsrc
                filter_complex = (
                    f"[0:v]{scale_filter}[v0];[1:v]{scale_filter}[v1];"
                    f"[v0][0:a][v1][2:a]concat=n=2:v=1:a=1[outv][outa]"
                )
                cmd = [
                    "ffmpeg", "-y", "-i", main_video, "-i", cta_video,
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-filter_complex", filter_complex,
                    "-map", "[outv]", "-map", "[outa]",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
                    output_file
                ]

            self.log("  [CTA] 开始拼接...")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0 and os.path.exists(output_file):
                self.log("  [CTA] ✓ 拼接成功")
                return True
            else:
                self.log(f"  [CTA] ✗ 失败: {result.stderr[:200]}")
                return False

        except Exception as e:
            self.log(f"  [CTA] ✗ 异常: {e}")
            return False

    def process_video(self, input_file, output_file, cut_enable, start_time, end_time, cut_mode,
                     audio_enable, audio_file, cta_enable, cta_file, cta_has_audio,
                     wm_enable, wm_text, wm_dir, wm_speed, wm_y, wm_size, wm_color, wm_border, wm_font):
        try:
            current_file = input_file
            temp_files = []

            # === 步骤1: 裁切 ===
            if cut_enable:
                start_sec = self.time_to_seconds(start_time)
                end_sec = self.time_to_seconds(end_time)
                self.log(f"  [裁切] {cut_mode} {start_sec}-{end_sec}s")

                if cut_mode == "保留":
                    temp_cut = output_file + ".temp_cut.mp4"
                    duration = end_sec - start_sec
                    cmd = ["ffmpeg", "-y", "-i", current_file, "-ss", str(start_sec), "-t", str(duration), "-c", "copy", temp_cut]
                    subprocess.run(cmd, capture_output=True, text=True)
                    current_file = temp_cut
                    temp_files.append(temp_cut)
                else:
                    total_duration = self.get_video_duration(input_file)
                    if total_duration == 0:
                        total_duration = 999999

                    temp_part1 = output_file + ".temp_p1.mp4"
                    temp_part2 = output_file + ".temp_p2.mp4"
                    temp_merged = output_file + ".temp_merged.mp4"

                    if start_sec > 0:
                        subprocess.run(["ffmpeg", "-y", "-i", current_file, "-ss", "0", "-t", str(start_sec), "-c", "copy", temp_part1], capture_output=True, text=True)
                    else:
                        temp_part1 = None

                    if end_sec < total_duration:
                        subprocess.run(["ffmpeg", "-y", "-i", current_file, "-ss", str(end_sec), "-c", "copy", temp_part2], capture_output=True, text=True)
                    else:
                        temp_part2 = None

                    parts = []
                    if temp_part1 and os.path.exists(temp_part1):
                        parts.append(temp_part1)
                    if temp_part2 and os.path.exists(temp_part2):
                        parts.append(temp_part2)

                    if len(parts) == 0:
                        return False, "删除后为空"
                    elif len(parts) == 1:
                        shutil.copy(parts[0], temp_merged)
                    else:
                        cl = output_file + ".concat_cut.txt"
                        with open(cl, "w", encoding="utf-8") as f2:
                            for p in parts:
                                line = "file '" + p.replace(chr(92), "/") + "'\n"
                                f2.write(line)
                        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", cl, "-c", "copy", temp_merged], capture_output=True, text=True)
                        if os.path.exists(cl):
                            os.remove(cl)

                    current_file = temp_merged
                    temp_files.extend([temp_part1, temp_part2, temp_merged])
            else:
                self.log("  [裁切] 跳过")

            # === 步骤2: 音频替换 ===
            if audio_enable and audio_file and os.path.exists(audio_file):
                self.log("  [音频] 替换...")
                temp_audio = output_file + ".temp_audio.mp4"
                cmd = ["ffmpeg", "-y", "-i", current_file, "-i", audio_file, "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0", "-shortest", temp_audio]
                subprocess.run(cmd, capture_output=True, text=True)
                current_file = temp_audio
                temp_files.append(temp_audio)
            else:
                self.log("  [音频] 跳过")

            # === 步骤3: 水印 ===
            if wm_enable and wm_text and wm_font and os.path.exists(wm_font):
                self.log(f"  [水印] 添加 {wm_dir}...")
                temp_wm = output_file + ".temp_wm.mp4"
                wm_filter = self.build_watermark_filter(wm_text, wm_dir, wm_speed, wm_y, wm_size, wm_color, wm_border, wm_font)
                cmd = ["ffmpeg", "-y", "-i", current_file, "-vf", wm_filter, "-c:a", "copy", temp_wm]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    self.log(f"  [水印] ✗ 失败: {result.stderr[:100]}")
                    return False, "水印失败"
                current_file = temp_wm
                temp_files.append(temp_wm)
                self.log("  [水印] ✓ 成功")
            else:
                if wm_enable:
                    self.log("  [水印] ⚠ 字体未找到，跳过")
                else:
                    self.log("  [水印] 跳过")

            # === 步骤4: CTA拼接 ===
            if cta_enable and cta_file and os.path.exists(cta_file):
                self.log("  [CTA] 开始拼接落版...")
                success = self.concat_cta(current_file, cta_file, output_file, cta_has_audio)
                if not success:
                    return False, "CTA拼接失败"
            else:
                self.log("  [CTA] 跳过")
                shutil.copy(current_file, output_file)

            # 清理临时文件
            for f in temp_files:
                if f and os.path.exists(f) and f != output_file and f != input_file:
                    try:
                        os.remove(f)
                    except:
                        pass

            if os.path.exists(output_file):
                return True, "成功"
            else:
                return False, "输出文件未生成"

        except Exception as e:
            return False, str(e)

    def start_batch_process(self):
        input_folder = self.input_var.get()
        output_folder = self.output_var.get()

        if not input_folder or not output_folder:
            messagebox.showerror("错误", "请填写输入和输出文件夹！")
            return
        if not os.path.exists(input_folder):
            messagebox.showerror("错误", "输入文件夹不存在！")
            return

        os.makedirs(output_folder, exist_ok=True)

        cut_enable = self.cut_enable_var.get()
        start_time = self.start_time_var.get()
        end_time = self.end_time_var.get()
        cut_mode = self.cut_mode_var.get()

        audio_enable = self.audio_enable_var.get()
        audio_file = self.audio_var.get()

        cta_enable = self.cta_enable_var.get()
        cta_file = self.cta_var.get()
        cta_has_audio = self.cta_audio_var.get()

        wm_enable = self.wm_enable_var.get()
        wm_text = self.wm_text_var.get()
        wm_dir = self.wm_dir_var.get()
        wm_speed = self.wm_speed_var.get()
        wm_y = self.wm_y_var.get()
        wm_size = self.wm_size_var.get()
        wm_color = self.wm_color_var.get()
        wm_border = self.wm_border_var.get()
        wm_font = self.wm_font_var.get()

        self.log("=" * 50)
        self.log("开始批量处理")
        self.log(f"输入: {input_folder}")
        self.log(f"输出: {output_folder}")
        self.log(f"功能: 裁切={cut_enable} 音频={audio_enable} 水印={wm_enable} CTA={cta_enable}")
        self.log("=" * 50)

        thread = threading.Thread(target=self.process_all, args=(
            input_folder, output_folder,
            cut_enable, start_time, end_time, cut_mode,
            audio_enable, audio_file,
            cta_enable, cta_file, cta_has_audio,
            wm_enable, wm_text, wm_dir, wm_speed, wm_y, wm_size, wm_color, wm_border, wm_font
        ))
        thread.daemon = True
        thread.start()

    def process_all(self, input_folder, output_folder,
                    cut_enable, start_time, end_time, cut_mode,
                    audio_enable, audio_file,
                    cta_enable, cta_file, cta_has_audio,
                    wm_enable, wm_text, wm_dir, wm_speed, wm_y, wm_size, wm_color, wm_border, wm_font):
        video_extensions = [".mp4", ".mov", ".avi", ".mkv", ".m4v"]
        video_files = [f for f in os.listdir(input_folder) if os.path.splitext(f)[1].lower() in video_extensions]
        total = len(video_files)
        success_count = 0

        for i, filename in enumerate(video_files, 1):
            input_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder, filename)
            self.log(f"[{i}/{total}] {filename}")
            for item in self.tree.get_children():
                if self.tree.item(item, "values")[0] == filename:
                    self.tree.item(item, values=(filename, "处理中...", "复制 | 粘贴"))
                    break
            success, msg = self.process_video(input_path, output_path,
                cut_enable, start_time, end_time, cut_mode,
                audio_enable, audio_file,
                cta_enable, cta_file, cta_has_audio,
                wm_enable, wm_text, wm_dir, wm_speed, wm_y, wm_size, wm_color, wm_border, wm_font)
            self.root.after(0, self.update_status, filename, success, msg)
            if success:
                success_count += 1
        self.root.after(0, self.log, f"\n完成！成功: {success_count}/{total}")

    def update_status(self, filename, success, msg):
        for item in self.tree.get_children():
            if self.tree.item(item, "values")[0] == filename:
                status = "成功" if success else "失败"
                self.tree.item(item, values=(filename, status, "复制 | 粘贴"))
                break
        if success:
            self.log(f"  ✓ {filename}")
        else:
            self.log(f"  ✗ {filename}: {msg}")

    def save_config(self):
        config = {
            "input_folder": self.input_var.get(),
            "output_folder": self.output_var.get(),
            "cut_enable": self.cut_enable_var.get(),
            "start_time": self.start_time_var.get(),
            "end_time": self.end_time_var.get(),
            "cut_mode": self.cut_mode_var.get(),
            "audio_enable": self.audio_enable_var.get(),
            "audio_file": self.audio_var.get(),
            "cta_enable": self.cta_enable_var.get(),
            "cta_file": self.cta_var.get(),
            "cta_has_audio": self.cta_audio_var.get(),
            "wm_enable": self.wm_enable_var.get(),
            "wm_text": self.wm_text_var.get(),
            "wm_dir": self.wm_dir_var.get(),
            "wm_speed": self.wm_speed_var.get(),
            "wm_y": self.wm_y_var.get(),
            "wm_size": self.wm_size_var.get(),
            "wm_color": self.wm_color_var.get(),
            "wm_border": self.wm_border_var.get(),
            "wm_font": self.wm_font_var.get()
        }
        with open("video_processor_config.json", "w", encoding="utf-8") as f2:
            json.dump(config, f2, ensure_ascii=False, indent=2)
        self.log("配置已保存")
        messagebox.showinfo("成功", "配置已保存")

    def open_output_folder(self):
        output_folder = self.output_var.get()
        if output_folder and os.path.exists(output_folder):
            os.startfile(output_folder)
        else:
            messagebox.showwarning("提示", "输出文件夹不存在")

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoBatchProcessor(root)
    root.mainloop()
