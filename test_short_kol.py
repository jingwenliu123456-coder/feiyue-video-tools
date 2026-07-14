"""短格式 KOL 文件名解析测试"""
from modules.naming_convention import (
    parse_legacy_filename,
    merge_legacy_with_fields,
    NamingFields,
    DEFAULT_TAG_LIBRARY,
    DEFAULT_TEMPLATE,
)

fields = NamingFields(
    brand="sami",
    lang="ar",
    type_="chat",
    tags=["", "", ""],
    size="9x16",
    date="20260707",
    designer="ljw",
    template=DEFAULT_TEMPLATE,
)
lib = set(DEFAULT_TAG_LIBRARY)

cases = [
    (
        "AR-KOL-3ssfoora.mp4",
        195,
        "195-sami-video-ar-KOL-3ssfoora-9x16-20260707-ljw.mp4",
        "短格式KOL文件，KOL名字「3ssfoora」已提取并保留",
    ),
    (
        "AR-KOL-basmalla.mp4",
        196,
        "196-sami-video-ar-KOL-basmalla-9x16-20260707-ljw.mp4",
        "短格式KOL文件，KOL名字「basmalla」已提取并保留",
    ),
    (
        "ar-kol-hamo.mp4",
        197,
        "197-sami-video-ar-KOL-hamo-9x16-20260707-ljw.mp4",
        "短格式KOL文件，KOL名字「hamo」已提取并保留",
    ),
]

for fname, idx, expected_name, expected_note in cases:
    p = parse_legacy_filename(fname, lib)
    name, warns, _ = merge_legacy_with_fields(
        p, fields, idx, lib, index_width=3, date_format="8"
    )
    assert p.parse_ok, f"{fname}: parse_ok should be True"
    assert p.short_kol, f"{fname}: short_kol should be True"
    assert name == expected_name, f"{fname}: got {name}"
    assert expected_note in warns[0], f"{fname}: warns={warns}"
    print(f"OK: {fname} -> {name}")

# 长格式不受影响
long_name = "03-habi-video-ar-chat-PK-9x16-0702-ljw.mp4"
p = parse_legacy_filename(long_name, lib)
name, warns, _ = merge_legacy_with_fields(
    p, fields, 198, lib, index_width=3, date_format="8"
)
assert p.parse_ok and not p.short_kol
assert "PK" in name or "chat" in name
print(f"OK long format: {long_name} -> {name}")

# 无法解析走兜底
p = parse_legacy_filename("final_export.mp4", lib)
name, warns, _ = merge_legacy_with_fields(
    p, fields, 199, lib, index_width=3, date_format="8"
)
assert not p.parse_ok
assert name.startswith("199-sami-video")
print(f"OK fallback: final_export.mp4 -> {name}")

# 短格式 KOL：界面标签不覆盖 KOL 名字
fields_with_tag = NamingFields(
    brand="sami",
    lang="ar",
    type_="chat",
    tags=["原版换音频", "", ""],
    size="9x16",
    date="20260707",
    designer="ljw",
    template=DEFAULT_TEMPLATE,
)
for fname, kol in [
    ("AR-KOL-hamo.mp4", "hamo"),
    ("AR-KOL-basmalla.nasserr.mp4", "basmalla.nasserr"),
    ("AR-KOL-nonosh 18.mp4", "nonosh 18"),
]:
    p = parse_legacy_filename(fname, lib)
    name, warns, _ = merge_legacy_with_fields(
        p, fields_with_tag, 195, lib, index_width=3, date_format="8"
    )
    assert kol in name, f"{fname}: expected {kol} in {name}"
    assert "原版换音频" not in name, f"{fname}: UI tag should not override"
    assert "已提取并保留" in warns[0]
    print(f"OK: short KOL keeps name: {fname} -> {name}")

print("ALL PASSED")
