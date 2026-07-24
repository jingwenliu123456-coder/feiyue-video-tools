"""旧版清理：第 N 个「-」之后 + 无横线 KOL 名 + chat 类型保留"""
from modules.naming_convention import (
    DEFAULT_TAG_LIBRARY,
    DEFAULT_TEMPLATE,
    NamingFields,
    merge_legacy_with_fields,
    parse_legacy_filename,
)

lib = set(DEFAULT_TAG_LIBRARY)
fields = NamingFields(
    brand="habi",
    lang="ar",
    type_="chat",
    tags=["界面标签", "", ""],
    size="9x16",
    date="20260707",
    designer="ljw",
    template=DEFAULT_TEMPLATE,
)
kw = dict(index_width=3, date_format="8", dash_keep_after=2, legacy_priority=False)


def merge(fname: str, idx: int):
    return merge_legacy_with_fields(
        parse_legacy_filename(fname, lib), fields, idx, lib, **kw,
    )


def test_no_dash_kol_name():
    name, warns, _ = merge("3ssfoora.mp4", 42)
    assert "3ssfoora" in name, name
    assert any("无足够" in w or "整段" in w for w in warns)


def test_chat_as_type_not_tag():
    name, warns, _ = merge("agency-xx-chat-年轻美女自拍.mp4", 43)
    assert "-chat-" in name, name
    assert "年轻美女自拍" in name, name
    # chat 应在类型位，不应作为非标准标签被滤掉
    assert "非标准标签「chat」" not in "; ".join(warns)


def test_short_kol_preserved_with_dash_keep():
    name, _warns, _ = merge("AR-KOL-hamo.mp4", 44)
    assert "hamo" in name and "KOL" in name, name


if __name__ == "__main__":
    test_no_dash_kol_name()
    test_chat_as_type_not_tag()
    test_short_kol_preserved_with_dash_keep()
    print("ALL PASSED")
