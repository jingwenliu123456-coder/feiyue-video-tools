import difflib
import os
import py_compile
import sys

ORIG = r"D:\其他软件\我的\video_batch_processor_v17.py"
PATCHED = r"D:\其他软件\我的\_video_batch_processor_v17_patched.py"

with open(ORIG, "r", encoding="utf-8") as f:
    content = f.read()

# ---------- 1. 替换文字水印UI区域 ----------
old_txt_ui = '''        txt_frame = ttk.LabelFrame(param_frame, text="文字水印", padding=8)
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
'''

new_txt_ui = '''        # === 动态文字水印（独立区域，v9丰富效果移植）===
        txt_wm_frame = ttk.LabelFrame(scrollable_frame, text="动态文字水印", padding=10)
        txt_wm_frame.pack(fill=tk.X, padx=10, pady=5)
        txt_wm_frame.columnconfigure(1, weight=1)

        self.txt_wm_enable = tk.BooleanVar(value=False)
        self.txt_wm_text = tk.StringVar(value="Nov")
        self.txt_wm_dir = tk.StringVar(value="从左往右")
        self.txt_wm_speed = tk.IntVar(value=100)
        self.txt_wm_size = tk.IntVar(value=36)
        self.txt_wm_color = tk.StringVar(value="white")
        self.txt_wm_border = tk.StringVar(value="none")
        self.txt_wm_bg_color = tk.StringVar(value="none")
        self.txt_wm_bg_opacity = tk.IntVar(value=50)
        self.txt_wm_font = tk.StringVar(value=self.find_font())

        ttk.Checkbutton(txt_wm_frame, text="启用", variable=self.txt_wm_enable).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(txt_wm_frame, text="水印文字:").grid(row=0, column=1, sticky=tk.W, padx=(20,0))
        ttk.Entry(txt_wm_frame, textvariable=self.txt_wm_text, width=20).grid(row=0, column=2, sticky=tk.W, padx=5)

        ttk.Label(txt_wm_frame, text="运动方向:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Combobox(txt_wm_frame, textvariable=self.txt_wm_dir,
                     values=["从左往右", "从右往左", "从上往下", "从下往上",
                             "左上到右下", "右下到左上", "右上到左下", "左下到右上", "波浪", "全场随机", "静止"],
                     width=12, state="readonly").grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Label(txt_wm_frame, text="滚动速度:").grid(row=1, column=2, sticky=tk.W, padx=(20,0))
        ttk.Spinbox(txt_wm_frame, from_=50, to=500, increment=10, textvariable=self.txt_wm_speed, width=8).grid(row=1, column=3, sticky=tk.W, padx=5)
        ttk.Label(txt_wm_frame, text="px/s").grid(row=1, column=4, sticky=tk.W)

        ttk.Label(txt_wm_frame, text="字体大小:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(txt_wm_frame, from_=12, to=120, increment=2, textvariable=self.txt_wm_size, width=8).grid(row=2, column=1, sticky=tk.W, padx=5)
        ttk.Label(txt_wm_frame, text="px").grid(row=2, column=2, sticky=tk.W)
        ttk.Label(txt_wm_frame, text="字体颜色:").grid(row=2, column=3, sticky=tk.W, padx=(20,0))
        ttk.Combobox(txt_wm_frame, textvariable=self.txt_wm_color, values=["white", "black", "red", "yellow", "green", "blue"], width=10, state="readonly").grid(row=2, column=4, sticky=tk.W, padx=5)

        ttk.Label(txt_wm_frame, text="描边颜色:").grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Combobox(txt_wm_frame, textvariable=self.txt_wm_border, values=["none", "black", "white", "red", "blue", "green"], width=10, state="readonly").grid(row=3, column=1, sticky=tk.W, padx=5)
        ttk.Label(txt_wm_frame, text="背景颜色:").grid(row=3, column=2, sticky=tk.W, padx=(20,0))
        ttk.Combobox(txt_wm_frame, textvariable=self.txt_wm_bg_color, values=["none", "black", "white", "red", "blue", "green"], width=10, state="readonly").grid(row=3, column=3, sticky=tk.W, padx=5)

        ttk.Label(txt_wm_frame, text="背景透明度:").grid(row=4, column=0, sticky=tk.W, pady=5)
        ttk.Scale(txt_wm_frame, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.txt_wm_bg_opacity, length=120).grid(row=4, column=1, sticky=tk.W, padx=5)
        ttk.Label(txt_wm_frame, textvariable=self.txt_wm_bg_opacity).grid(row=4, column=2, sticky=tk.W)
        ttk.Label(txt_wm_frame, text="%").grid(row=4, column=3, sticky=tk.W)

        ttk.Label(txt_wm_frame, text="字体文件:").grid(row=5, column=0, sticky=tk.W, pady=5)
        ttk.Entry(txt_wm_frame, textvariable=self.txt_wm_font, width=50).grid(row=5, column=1, columnspan=3, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(txt_wm_frame, text="选择", command=self.select_font).grid(row=5, column=4, padx=5)

        if not self.txt_wm_font.get():
            ttk.Label(txt_wm_frame, text="[!] 未检测到系统字体，请手动选择", foreground="red").grid(row=6, column=0, columnspan=5, sticky=tk.W)
'''

if old_txt_ui not in content:
    print("ERROR: old_txt_ui not found")
    sys.exit(1)
content = content.replace(old_txt_ui, new_txt_ui)

# ---------- 2. 添加 select_font ----------
old_select_mov = '''    def select_mov_wm(self):
        p = filedialog.askopenfilename(filetypes=[("MOV with Alpha", "*.mov"), ("Video", "*.mp4 *.webm")])
        if p:
            self.mov_wm_path.set(p)
'''
new_select_mov = '''    def select_mov_wm(self):
        p = filedialog.askopenfilename(filetypes=[("MOV with Alpha", "*.mov"), ("Video", "*.mp4 *.webm")])
        if p:
            self.mov_wm_path.set(p)

    def select_font(self):
        p = filedialog.askopenfilename(filetypes=[("字体文件", "*.ttf *.ttc *.otf"), ("所有文件", "*.*")])
        if p:
            self.txt_wm_font.set(p)
'''
if old_select_mov not in content:
    print("ERROR: old_select_mov not found")
    sys.exit(1)
content = content.replace(old_select_mov, new_select_mov)

# ---------- 3. 替换 add_txt_wm ----------
old_add_txt = '''    def add_txt_wm(self, inp, out, text, direction, size, color):
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
'''
new_add_txt = '''    def get_watermark_exprs(self, direction, speed):
        """返回 (x_expr, y_expr)"""
        if direction == "从左往右":
            return (f"mod(t*{speed},W+tw)-tw", f"mod(t*{speed}*0.3,H+th)-th")
        elif direction == "从右往左":
            return (f"W-tw-mod(t*{speed},W+tw)", f"mod(t*{speed}*0.3,H+th)-th")
        elif direction == "从上往下":
            return (f"mod(t*{speed}*0.3,W+tw)-tw", f"mod(t*{speed},H+th)-th")
        elif direction == "从下往上":
            return (f"mod(t*{speed}*0.3,W+tw)-tw", f"H-th-mod(t*{speed},H+th)")
        elif direction == "左上到右下":
            return (f"mod(t*{speed},W+tw)-tw", f"mod(t*{speed},H+th)-th")
        elif direction == "右下到左上":
            return (f"W-tw-mod(t*{speed},W+tw)", f"H-th-mod(t*{speed},H+th)")
        elif direction == "右上到左下":
            return (f"W-tw-mod(t*{speed},W+tw)", f"mod(t*{speed},H+th)-th")
        elif direction == "左下到右上":
            return (f"mod(t*{speed},W+tw)-tw", f"H-th-mod(t*{speed},H+th)")
        elif direction == "波浪":
            return (f"(W-tw)/2+(W/2-tw/2)*sin(t*{speed}/100)", f"(H-th)/2+(H/2-th/2)*cos(t*{speed}/150)")
        elif direction == "全场随机":
            return (f"mod(abs(sin(t*{speed}/200)*cos(t*{speed}/300))*W,W+tw)-tw",
                    f"mod(abs(cos(t*{speed}/250)*sin(t*{speed}/350))*H,H+th)-th")
        else:
            return ("(W-tw)/2", "(H-th)/2")

    def build_watermark_filter(self, text, direction, speed, font_size, color, border, font_file, bg_color, bg_opacity):
        x_expr, y_expr = self.get_watermark_exprs(direction, speed)
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

        # 描边
        if border != "none":
            filter_parts.append(f"borderw=1:bordercolor={border}")

        # 背景框
        if bg_color != "none":
            opacity_hex = hex(int(bg_opacity * 255 / 100))[2:].zfill(2)
            color_map = {"black": "0x000000", "white": "0xFFFFFF", "red": "0xFF0000", "blue": "0x0000FF", "green": "0x00FF00"}
            bg_hex = color_map.get(bg_color, "0x000000")
            filter_parts.append(f"box=1:boxcolor={bg_hex}{opacity_hex}:boxborderw=2")

        return ":".join(filter_parts)

    def add_txt_wm(self, inp, out, text, direction, speed, size, color, border, font_file, bg_color, bg_opacity):
        if not font_file or not os.path.exists(font_file):
            raise Exception("未找到字体文件")
        safe = text.replace(chr(92), chr(92)+chr(92)).replace("'", chr(92)+"'")
        if color.startswith("#"):
            color = color.replace("#", "0x")
        vf = f"drawtext={self.build_watermark_filter(safe, direction, speed, size, color, border, font_file, bg_color, bg_opacity)}"
        self.run_ffmpeg(["ffmpeg", "-i", inp, "-vf", vf,
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-c:a", "copy", "-y", out])
'''
if old_add_txt not in content:
    print("ERROR: old_add_txt not found")
    sys.exit(1)
content = content.replace(old_add_txt, new_add_txt)

# ---------- 4. save_config ----------
old_save = '''            "txt_wm_enable": self.txt_wm_enable.get(),
            "txt_wm_text": self.txt_wm_text.get(),
            "txt_wm_dir": self.txt_wm_dir.get(),
            "txt_wm_size": self.txt_wm_size.get(),
            "txt_wm_color": self.txt_wm_color.get(),
        }
'''
new_save = '''            "txt_wm_enable": self.txt_wm_enable.get(),
            "txt_wm_text": self.txt_wm_text.get(),
            "txt_wm_dir": self.txt_wm_dir.get(),
            "txt_wm_speed": self.txt_wm_speed.get(),
            "txt_wm_size": self.txt_wm_size.get(),
            "txt_wm_color": self.txt_wm_color.get(),
            "txt_wm_border": self.txt_wm_border.get(),
            "txt_wm_bg_color": self.txt_wm_bg_color.get(),
            "txt_wm_bg_opacity": self.txt_wm_bg_opacity.get(),
            "txt_wm_font": self.txt_wm_font.get(),
        }
'''
if old_save not in content:
    print("ERROR: old_save not found")
    sys.exit(1)
content = content.replace(old_save, new_save)

# ---------- 5. load_config ----------
old_load = '''            self.txt_wm_enable.set(cfg.get("txt_wm_enable", False))
            self.txt_wm_text.set(cfg.get("txt_wm_text", "Nov"))
            self.txt_wm_dir.set(cfg.get("txt_wm_dir", "静止"))
            self.txt_wm_size.set(cfg.get("txt_wm_size", "24"))
            self.txt_wm_color.set(cfg.get("txt_wm_color", "white"))
'''
new_load = '''            self.txt_wm_enable.set(cfg.get("txt_wm_enable", False))
            self.txt_wm_text.set(cfg.get("txt_wm_text", "Nov"))
            self.txt_wm_dir.set(cfg.get("txt_wm_dir", "从左往右"))
            self.txt_wm_speed.set(cfg.get("txt_wm_speed", 100))
            self.txt_wm_size.set(cfg.get("txt_wm_size", 36))
            self.txt_wm_color.set(cfg.get("txt_wm_color", "white"))
            self.txt_wm_border.set(cfg.get("txt_wm_border", "none"))
            self.txt_wm_bg_color.set(cfg.get("txt_wm_bg_color", "none"))
            self.txt_wm_bg_opacity.set(cfg.get("txt_wm_bg_opacity", 50))
            self.txt_wm_font.set(cfg.get("txt_wm_font", self.find_font()))
'''
if old_load not in content:
    print("ERROR: old_load not found")
    sys.exit(1)
content = content.replace(old_load, new_load)

# ---------- 6. process_all ----------
old_process_txt = '''                if self.txt_wm_enable.get():
                    tmp = self.get_temp(out, "txtwm")
                    self.add_txt_wm(current, tmp, self.txt_wm_text.get(),
                                   self.txt_wm_dir.get(), self.txt_wm_size.get(),
                                   self.txt_wm_color.get())
                    if current != inp:
                        temps.append(current)
                    current = tmp
                    self.log("  文字水印完成")
'''
new_process_txt = '''                if self.txt_wm_enable.get():
                    fp = self.txt_wm_font.get()
                    if not fp or not os.path.exists(fp):
                        raise Exception("字体文件不存在")
                    tmp = self.get_temp(out, "txtwm")
                    self.add_txt_wm(current, tmp, self.txt_wm_text.get(),
                                   self.txt_wm_dir.get(), self.txt_wm_speed.get(),
                                   self.txt_wm_size.get(), self.txt_wm_color.get(),
                                   self.txt_wm_border.get(), fp,
                                   self.txt_wm_bg_color.get(), self.txt_wm_bg_opacity.get())
                    if current != inp:
                        temps.append(current)
                    current = tmp
                    self.log("  文字水印完成")
'''
if old_process_txt not in content:
    print("ERROR: old_process_txt not found")
    sys.exit(1)
content = content.replace(old_process_txt, new_process_txt)

# 写入临时补丁文件
with open(PATCHED, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Patched file written: {PATCHED}")
print(f"Patched file size: {os.path.getsize(PATCHED)} bytes")

# 语法检查
try:
    py_compile.compile(PATCHED, doraise=True)
    print("PY_COMPILE: OK")
except py_compile.PyCompileError as e:
    print(f"PY_COMPILE ERROR: {e}")
    sys.exit(1)

# 检查关键函数是否存在
with open(PATCHED, "r", encoding="utf-8") as f:
    patched_src = f.read()

checks = [
    "def get_watermark_exprs",
    "def build_watermark_filter",
    "def add_txt_wm",
    "def select_font",
    "def add_mov_wm",
    "def add_cta",
    "txt_wm_speed",
    "txt_wm_border",
    "txt_wm_bg_opacity",
    "txt_wm_font",
]
for c in checks:
    if c in patched_src:
        print(f"CHECK PASS: {c}")
    else:
        print(f"CHECK FAIL: {c}")
        sys.exit(1)

# 检查没有误删的关键函数
must_have = [
    "def cut",
    "def replace_audio",
    "def add_cta",
    "def add_mov_wm",
    "def start_process",
    "def process_all",
]
for c in must_have:
    if c in patched_src:
        print(f"PRESERVED: {c}")
    else:
        print(f"MISSING: {c}")
        sys.exit(1)

print("\nAll checks passed.")
