import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import json
import platform

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class VideoBatchProcessor:
    def __init__(self, root):
        self.root = root
        self.root.title("视频批量处理工具 v4.0")
        self.root.geometry("1000x950")
        self.root.minsize(900, 900)
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

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        row = 0

        title_label = ttk.Label(main_frame, text="视频批量处理工具 v4.0", font=("Microsoft YaHei", 16, "bold"))
        title_label.grid(row=row, column=0, columnspan=3, pady=(0, 15))
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

        # === 裁切设置（新增保留/删除模式）===
        cut_frame = ttk.LabelFrame(main_frame, text="裁切设置", padding="10")
        cut_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        cut_frame.columnconfigure(1, weight=1)

        ttk.Label(cut_frame, text="裁切模式:").grid(row=0, column=0, sticky=tk.W)
        self.cut_mode_var = tk.StringVar(value="保留")
        ttk.Combobox(cut_frame, textvariable=self.cut_mode_var, values=["保留", "删除"], width=10, state="readonly").grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Label(cut_frame, text="保留=只留这段 / 删除=去掉这段").grid(row=0, column=2, sticky=tk.W, padx=10)

        ttk.Label(cut_frame, text="开始时间:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.start_time_var = tk.StringVar(value="00:00")
        ttk.Entry(cut_frame, textvariable=self.start_time_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=5)

        ttk.Label(cut_frame, text="结束时间:").grid(row=1, column=2, sticky=tk.W, padx=(20, 0))
        self.end_time_var = tk.StringVar(value="00:15")
        ttk.Entry(cut_frame, textvariable=self.end_time_var, width=10).grid(row=1, column=3, sticky=tk.W, padx=5)

        ttk.Label(cut_frame, text="(格式: 秒 或 分:秒)").grid(row=1, column=4, sticky=tk.W, padx=10)
        row += 1

        # === 音频 & 结尾落版（音频改为选填）===
        media_frame = ttk.LabelFrame(main_frame, text="音频 & 结尾落版", padding="10")
        media_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        media_frame.columnconfigure(1, weight=1)

        ttk.Label(media_frame, text="音频文件:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.audio_var = tk.StringVar()
        ttk.Entry(media_frame, textvariable=self.audio_var, width=50).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(media_frame, text="选择", command=self.select_audio).grid(row=0, column=2, padx=5)
        ttk.Label(media_frame, text="(选填，不填保留原音频)").grid(row=0, column=3, sticky=tk.W, padx=5)

        ttk.Label(media_frame, text="结尾落版:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.cta_var = tk.StringVar()
        ttk.Entry(media_frame, textvariable=self.cta_var, width=50).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(media_frame, text="选择", command=self.select_cta).grid(row=1, column=2, padx=5)

        self.cta_audio_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(media_frame, text="结尾落版保留原音频", variable=self.cta_audio_var).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=5)
        row += 1

        wm_frame = ttk.LabelFrame(main_frame, text="动态文字水印设置", padding="10")
        wm_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        wm_frame.columnconfigure(1, weight=1)

        ttk.Label(wm_frame, text="水印文字:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.wm_text_var = tk.StringVar(value="Nov")
        ttk.Entry(wm_frame, textvariable=self.wm_text_var, width=30).grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(wm_frame, text="滚动方向:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.wm_dir_var = tk.StringVar(value="从左往右")
        ttk.Combobox(wm_frame, textvariable=self.wm_dir_var, values=["从左往右", "从右往左", "静止"], width=12, state="readonly").grid(row=1, column=1, sticky=tk.W, padx=5)

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
        ttk.Entry(wm_frame, textvariable=self.wm_font_var, width=50).grid(row=4, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(wm_frame, text="选择", command=self.select_font).grid(row=4, column=2, padx=5)

        if not self.system_font:
            ttk.Label(wm_frame, text="⚠️ 未检测到系统字体，请手动选择", foreground="red").grid(row=5, column=0, columnspan=3, sticky=tk.W)
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

    def select_cta(self):
        file = filedialog.askopenfilename(title="选择结尾落版视频", filetypes=[("视频文件", "*.mp4 *.mov *.avi"), ("所有文件", "*.*")])
        if file:
            self.cta_var.set(file)

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

    def get_watermark_y(self, pos_name, font_size):
        if pos_name == "顶部":
            return "20"
        elif pos_name == "中部":
            return "(h-th)/2"
        else:
            return "h-th-20"

    def get_watermark_x_expr(self, direction, speed):
        if direction == "静止":
            return "(W-tw)/2"
        elif direction == "从左往右":
            return f"mod(t*{speed},W+tw)-tw"
        else:
            return f"W-tw-mod(t*{speed},W+tw)"

    def build_watermark_filter(self, text, direction, speed, y_pos, font_size, color, border, font_file):
        x_expr = self.get_watermark_x_expr(direction, speed)
        y_expr = self.get_watermark_y(y_pos, font_size)

        # 字体路径处理：反斜杠转斜杠，空格路径加引号
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

    def get_video_duration(self, video_path):
        """获取视频总时长（秒）"""
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except:
            pass
        return 0

    def process_video(self, input_file, output_file, start_time, end_time, cut_mode, audio_file, cta_file, cta_has_audio, wm_text, wm_dir, wm_speed, wm_y, wm_size, wm_color, wm_border, wm_font):
        try:
            start_sec = self.time_to_seconds(start_time)
            end_sec = self.time_to_seconds(end_time)
            has_audio = bool(audio_file) and os.path.exists(audio_file)
            has_cta = bool(cta_file) and os.path.exists(cta_file)
            has_wm = bool(wm_text) and bool(wm_font) and os.path.exists(wm_font)

            self.log(f"  裁切模式: {cut_mode}, 时间段: {start_sec}-{end_sec}s")

            # === 步骤1: 裁切 ===
            if cut_mode == "保留":
                # 保留模式：只保留 start-end 这段
                temp_cut = output_file + ".temp_cut.mp4"
                duration = end_sec - start_sec
                cmd_cut = ["ffmpeg", "-y", "-i", input_file, "-ss", str(start_sec), "-t", str(duration), "-c", "copy", temp_cut]
                subprocess.run(cmd_cut, capture_output=True, text=True)
                temp_after_cut = temp_cut
            else:
                # 删除模式：去掉 start-end 这段，保留前后拼接
                total_duration = self.get_video_duration(input_file)
                if total_duration == 0:
                    total_duration = 999999  # 如果获取失败，假设很长

                temp_part1 = output_file + ".temp_part1.mp4"
                temp_part2 = output_file + ".temp_part2.mp4"
                temp_merged = output_file + ".temp_merged.mp4"

                # 提取前半段 (0 到 start)
                if start_sec > 0:
                    cmd_part1 = ["ffmpeg", "-y", "-i", input_file, "-ss", "0", "-t", str(start_sec), "-c", "copy", temp_part1]
                    subprocess.run(cmd_part1, capture_output=True, text=True)
                else:
                    temp_part1 = None

                # 提取后半段 (end 到结尾)
                if end_sec < total_duration:
                    cmd_part2 = ["ffmpeg", "-y", "-i", input_file, "-ss", str(end_sec), "-c", "copy", temp_part2]
                    subprocess.run(cmd_part2, capture_output=True, text=True)
                else:
                    temp_part2 = None

                # 拼接前后两段
                concat_parts = []
                if temp_part1 and os.path.exists(temp_part1):
                    concat_parts.append(temp_part1)
                if temp_part2 and os.path.exists(temp_part2):
                    concat_parts.append(temp_part2)

                if len(concat_parts) == 0:
                    return False, "删除后视频为空"
                elif len(concat_parts) == 1:
                    # 只有一段，直接复制
                    import shutil
                    shutil.copy(concat_parts[0], temp_merged)
                else:
                    # 两段拼接
                    concat_list = output_file + ".concat_cut.txt"
                    with open(concat_list, "w", encoding="utf-8") as f2:
                        for p in concat_parts:
                            f2.write(f"file '{p.replace(chr(92), '/')}'\n")
                    cmd_concat = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", temp_merged]
                    subprocess.run(cmd_concat, capture_output=True, text=True)
                    if os.path.exists(concat_list):
                        os.remove(concat_list)

                temp_after_cut = temp_merged

                # 清理临时文件
                for p in [temp_part1, temp_part2]:
                    if p and os.path.exists(p):
                        os.remove(p)

            # === 步骤2: 替换音频（选填）===
            if has_audio:
                temp_audio = output_file + ".temp_audio.mp4"
                cmd_audio = ["ffmpeg", "-y", "-i", temp_after_cut, "-i", audio_file, "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0", "-shortest", temp_audio]
                subprocess.run(cmd_audio, capture_output=True, text=True)
                if os.path.exists(temp_after_cut) and temp_after_cut != temp_merged:
                    os.remove(temp_after_cut)
                temp_after_audio = temp_audio
            else:
                self.log("  未选择音频，保留原音频")
                temp_after_audio = temp_after_cut

            # === 步骤3: 动态水印 ===
            if has_wm:
                temp_watermark = output_file + ".temp_wm.mp4"
                wm_filter = self.build_watermark_filter(wm_text, wm_dir, wm_speed, wm_y, wm_size, wm_color, wm_border, wm_font)
                self.log(f"  水印滤镜: {wm_filter[:60]}...")
                cmd_wm = ["ffmpeg", "-y", "-i", temp_after_audio, "-vf", wm_filter, "-c:a", "copy", temp_watermark]
                result_wm = subprocess.run(cmd_wm, capture_output=True, text=True)
                if result_wm.returncode != 0:
                    self.log(f"  水印失败: {result_wm.stderr[:100]}")
                    return False, "水印添加失败"
                if os.path.exists(temp_after_audio) and temp_after_audio != temp_after_cut:
                    os.remove(temp_after_audio)
                temp_after_wm = temp_watermark
            else:
                if wm_text and (not wm_font or not os.path.exists(wm_font)):
                    self.log("  警告: 未找到字体文件，跳过水印")
                temp_after_wm = temp_after_audio

            # === 步骤4: 拼接CTA结尾落版 ===
            if has_cta:
                concat_list = output_file + ".concat_final.txt"
                with open(concat_list, "w", encoding="utf-8") as f2:
                    f2.write(f"file '{temp_after_wm.replace(chr(92), '/')}'\n")
                    f2.write(f"file '{cta_file.replace(chr(92), '/')}'\n")

                if not cta_has_audio:
                    # CTA去掉音频
                    temp_cta_mute = output_file + ".temp_cta_mute.mp4"
                    cmd_cta_mute = ["ffmpeg", "-y", "-i", cta_file, "-c:v", "copy", "-an", temp_cta_mute]
                    subprocess.run(cmd_cta_mute, capture_output=True, text=True)
                    with open(concat_list, "w", encoding="utf-8") as f2:
                        f2.write(f"file '{temp_after_wm.replace(chr(92), '/')}'\n")
                        f2.write(f"file '{temp_cta_mute.replace(chr(92), '/')}'\n")

                cmd_concat = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", output_file]
                result = subprocess.run(cmd_concat, capture_output=True, text=True)

                # 清理
                for f in [concat_list, temp_after_wm]:
                    if f and os.path.exists(f) and f != output_file:
                        os.remove(f)
                if not cta_has_audio and os.path.exists(temp_cta_mute):
                    os.remove(temp_cta_mute)
            else:
                # 没有CTA，直接复制结果
                import shutil
                shutil.copy(temp_after_wm, output_file)
                if os.path.exists(temp_after_wm) and temp_after_wm != output_file:
                    os.remove(temp_after_wm)

            if os.path.exists(output_file):
                return True, "成功"
            else:
                return False, "输出文件未生成"

        except Exception as e:
            return False, str(e)

    def start_batch_process(self):
        input_folder = self.input_var.get()
        output_folder = self.output_var.get()
        cta_file = self.cta_var.get()

        if not input_folder or not output_folder:
            messagebox.showerror("错误", "请填写输入和输出文件夹！")
            return
        if not os.path.exists(input_folder):
            messagebox.showerror("错误", "输入文件夹不存在！")
            return

        os.makedirs(output_folder, exist_ok=True)

        start_time = self.start_time_var.get()
        end_time = self.end_time_var.get()
        cut_mode = self.cut_mode_var.get()
        audio_file = self.audio_var.get()
        cta_has_audio = self.cta_audio_var.get()

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
        self.log(f"裁切: {cut_mode} {start_time}-{end_time}")
        if audio_file:
            self.log(f"音频: {audio_file}")
        else:
            self.log("音频: 保留原音频")
        self.log(f"CTA: {cta_file if cta_file else "无"}")
        if wm_text:
            self.log(f"动态水印: {wm_text} ({wm_dir}, {wm_speed}px/s)")
        self.log("=" * 50)

        thread = threading.Thread(target=self.process_all, args=(input_folder, output_folder, start_time, end_time, cut_mode, audio_file, cta_file, cta_has_audio, wm_text, wm_dir, wm_speed, wm_y, wm_size, wm_color, wm_border, wm_font))
        thread.daemon = True
        thread.start()

    def process_all(self, input_folder, output_folder, start_time, end_time, cut_mode, audio_file, cta_file, cta_has_audio, wm_text, wm_dir, wm_speed, wm_y, wm_size, wm_color, wm_border, wm_font):
        video_extensions = [".mp4", ".mov", ".avi", ".mkv", ".m4v"]
        video_files = [f for f in os.listdir(input_folder) if os.path.splitext(f)[1].lower() in video_extensions]
        total = len(video_files)
        success_count = 0

        for i, filename in enumerate(video_files, 1):
            input_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder, filename)
            self.log(f"[{i}/{total}] 处理: {filename}")
            for item in self.tree.get_children():
                if self.tree.item(item, "values")[0] == filename:
                    self.tree.item(item, values=(filename, "处理中...", "复制 | 粘贴"))
                    break
            success, msg = self.process_video(input_path, output_path, start_time, end_time, cut_mode, audio_file, cta_file, cta_has_audio, wm_text, wm_dir, wm_speed, wm_y, wm_size, wm_color, wm_border, wm_font)
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
            self.log(f"  成功 {filename}")
        else:
            self.log(f"  失败 {filename}: {msg}")

    def save_config(self):
        config = {
            "input_folder": self.input_var.get(),
            "output_folder": self.output_var.get(),
            "audio_file": self.audio_var.get(),
            "cta_file": self.cta_var.get(),
            "start_time": self.start_time_var.get(),
            "end_time": self.end_time_var.get(),
            "cut_mode": self.cut_mode_var.get(),
            "cta_has_audio": self.cta_audio_var.get(),
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
