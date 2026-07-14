import difflib

ORIG = r"D:\其他软件\我的\video_batch_processor_v17.py"
PATCHED = r"D:\其他软件\我的\_video_batch_processor_v17_patched.py"
OUT = r"D:\其他软件\我的\_diff_v17_watermark_final.patch"

with open(ORIG, "r", encoding="utf-8") as f:
    orig_lines = f.readlines()
with open(PATCHED, "r", encoding="utf-8") as f:
    patched_lines = f.readlines()

diff = difflib.unified_diff(
    orig_lines,
    patched_lines,
    fromfile="video_batch_processor_v17.py",
    tofile="video_batch_processor_v17.py",
    lineterm="\n",
    n=5
)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("".join(diff))

print(f"Diff written: {OUT}")
print(f"Lines: {sum(1 for _ in open(OUT, encoding='utf-8'))}")
