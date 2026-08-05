"""浮层落版：旋转归一 + 全屏贴合 + 有声/无声主片音频 冒烟测试"""
from core.overlay_processor import (
    build_endcard_audio_filter,
    build_endcard_overlay_filter,
    combine_endcard_filters,
    normalize_rotation,
    rotation_vf,
)


def test_rotation_vf():
    assert rotation_vf(90) == "transpose=1"
    assert rotation_vf(270) == "transpose=2"
    assert rotation_vf(180) == "transpose=1,transpose=1"
    assert rotation_vf(0) == ""
    assert normalize_rotation(-90) == 270


def test_filter_applies_transpose_and_fit():
    # 主片 coded 横屏但旋转 90 → 显示竖屏；落版竖屏
    filt = build_endcard_overlay_filter(
        extend=2.0,
        main_width=1080,
        main_height=1920,
        overlay_width=1080,
        overlay_height=1920,
        scale_percent=100,
        position="居中",
        main_rotation=90,
        overlay_rotation=0,
        start_time=12.0,
        logo_duration=3.0,
    )
    assert "transpose=1" in filt
    assert "setsar=1" in filt
    assert "tpad=" in filt
    assert "pad=1080:1920" in filt or "crop=1080:1920" in filt or "scale=1080:1920" in filt
    assert "trim=duration=" in filt
    assert "setpts=PTS-STARTPTS+12.0/TB" in filt
    # 不应再走「同宽底对齐且不缩放」把竖屏落版塞进未旋转的横屏画布
    assert "H-h" not in filt or "transpose" in filt


def test_audio_extend_never_empty_when_main_has_audio():
    af, amap = build_endcard_audio_filter(
        start_time=12.0,
        total_duration=16.0,
        main_has_audio=True,
        overlay_has_audio=False,
        keep_overlay_audio=False,
        extend=2.0,
    )
    assert "apad" in af
    assert amap == "[aout]"


def test_audio_extend_with_overlay_mix():
    af, amap = build_endcard_audio_filter(
        start_time=12.0,
        total_duration=16.0,
        main_has_audio=True,
        overlay_has_audio=True,
        keep_overlay_audio=False,
        extend=2.0,
        timeline_already_offset=False,
    )
    assert "amix" in af
    assert "adelay=12000|12000" in af
    assert amap == "[aout]"


def test_silent_main_keeps_overlay_audio():
    """主片无声时，即使未勾选保留，只要落版有声也必须出声。"""
    af, amap = build_endcard_audio_filter(
        start_time=12.0,
        total_duration=16.0,
        main_has_audio=False,
        overlay_has_audio=True,
        keep_overlay_audio=False,
        extend=0.0,
        timeline_already_offset=False,
    )
    assert "[1:a]" in af
    assert "adelay=12000|12000" in af
    assert amap == "[aout]"
    assert "[0:a]" not in af


def test_main_with_audio_keep_overlay_mixes():
    """主片有声 + 勾选保留：必须 amix，且用 adelay（不能靠 itsoffset 导致落版音丢失）。"""
    af, amap = build_endcard_audio_filter(
        start_time=8.5,
        total_duration=14.0,
        main_has_audio=True,
        overlay_has_audio=True,
        keep_overlay_audio=True,
        extend=0.0,
        timeline_already_offset=False,
    )
    assert "amix" in af
    assert "normalize=0" in af
    assert "adelay=8500|8500" in af
    assert "[0:a]" in af and "[1:a]" in af
    assert amap == "[aout]"


def test_main_with_audio_no_keep_no_extend_skips_overlay():
    """主片有声 + 未勾选 + 无延长：重叠段不混入落版音（与勾选项一致）。"""
    af, amap = build_endcard_audio_filter(
        start_time=8.0,
        total_duration=12.0,
        main_has_audio=True,
        overlay_has_audio=True,
        keep_overlay_audio=False,
        extend=0.0,
    )
    assert af == ""
    assert amap == "0:a?"


def test_combine():
    v = build_endcard_overlay_filter(
        extend=0, main_width=1080, main_height=1920,
        overlay_width=1080, overlay_height=1920, scale_percent=100,
        start_time=0,
    )
    a, am = build_endcard_audio_filter(
        start_time=0, total_duration=10, main_has_audio=True,
        overlay_has_audio=False, keep_overlay_audio=False, extend=0,
    )
    c = combine_endcard_filters(v, a)
    assert "[v]" in c


if __name__ == "__main__":
    test_rotation_vf()
    test_filter_applies_transpose_and_fit()
    test_audio_extend_never_empty_when_main_has_audio()
    test_audio_extend_with_overlay_mix()
    test_silent_main_keeps_overlay_audio()
    test_main_with_audio_keep_overlay_mixes()
    test_main_with_audio_no_keep_no_extend_skips_overlay()
    test_combine()
    print("ALL PASSED")
