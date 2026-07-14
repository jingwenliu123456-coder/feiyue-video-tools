"""旧版清理：勾选 + 局部字段更新测试"""
from modules.naming_convention import (
    DEFAULT_TAG_LIBRARY,
    DEFAULT_TEMPLATE,
    NamingFields,
    merge_legacy_with_fields,
    parse_legacy_filename,
)

lib = set(DEFAULT_TAG_LIBRARY)
fields = NamingFields(
    brand="sami",
    lang="AR",
    type_="chat",
    tags=["美女诱导", "", ""],
    size="9x16",
    date="20260707",
    designer="ljw",
    template=DEFAULT_TEMPLATE,
)
kw = {"index_width": 3, "date_format": "8"}

files = [
    "AR-KOL-3ssfoora.mp4",
    "AR-KOL-basmalla.mp4",
    "EN-KOL-hamo.mp4",
    "03-habi-video-ar-chat-PK-9x16-0702-ljw.mp4",
]


def merge_file(fname: str, idx: int, *, overrides=None, legacy_priority=False):
    parsed = parse_legacy_filename(fname, lib)
    return merge_legacy_with_fields(
        parsed, fields, idx, lib,
        overrides=overrides, legacy_priority=legacy_priority, **kw,
    )


# 测试步骤 1：勾选 1/2/3，语言 -> EN
for i, fname in enumerate(files[:3]):
    name, warns, _ = merge_file(
        fname, 195 + i,
        overrides={"lang": "EN"},
        legacy_priority=True,
    )
    assert "EN" in name and "KOL" in name
    assert fname.split("-")[2].split(".")[0] in name
    assert "局部更新：语言=EN" in warns[0]
    print(f"step1 OK: {fname} -> {name}")

# 文件 4 未勾选：界面标签覆盖 PK
name4, warns4, _ = merge_file(files[3], 198)
assert "美女诱导" in name4
assert "habi" in name4
assert "按旧名解析合并" in warns4[0] or "非标准" in warns4[0]
print(f"step1 file4 OK: {files[3]} -> {name4}")

# 测试步骤 2：文件 4 标签1 -> KOL
name4b, warns4b, _ = merge_file(
    files[3], 198,
    overrides={"tag1": "KOL"},
    legacy_priority=True,
)
assert "KOL" in name4b
assert "局部更新：标签1=KOL" in warns4b[0]
print(f"step2 OK: {files[3]} -> {name4b}")

# 测试步骤 3：文件 1 品牌 -> habi
name1b, warns1b, _ = merge_file(
    files[0], 195,
    overrides={"brand": "habi"},
    legacy_priority=True,
)
assert name1b.startswith("195-habi-video")
assert "3ssfoora" in name1b
assert "局部更新：品牌=habi" in warns1b[0]
print(f"step3 OK: {files[0]} -> {name1b}")

print("ALL PASSED")
