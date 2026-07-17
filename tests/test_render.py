import numpy as np
import pytest
from PIL import Image
from looklift import render


def _flat_gray(v=0.5, size=(32, 32)):
    return np.full((*size, 3), v, dtype=np.float32)


def _zero_analysis(sample_analysis):
    """把 fixture 里的所有调整清零,便于单项测试。"""
    import copy
    a = copy.deepcopy(sample_analysis)
    a["basic"] = {k: 0 for k in a["basic"]}
    a["tone_curve"] = []
    a["hsl"] = []
    for zone in ("shadows", "midtones", "highlights", "global_"):
        a["color_grading"][zone] = {"hue": 0, "saturation": 0, "luminance": 0}
    a["effects"] = {"vignette_amount": 0, "grain_amount": 0}
    return a


def test_identity_analysis_is_noop(sample_analysis):
    a = _zero_analysis(sample_analysis)
    arr = _flat_gray()
    out = render._apply_color_ops(arr.copy(), a)
    assert np.allclose(out, arr, atol=1e-3)


def test_exposure_positive_brightens(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["basic"]["exposure"] = 1.0
    out = render._apply_color_ops(_flat_gray(0.25), a)
    # D5 线性光重标:原阈值 0.4 → 0.3；实测 +1EV 输出约 0.352，方向仍为提亮。
    assert out.mean() > 0.3


def test_temperature_warm_lifts_red_over_blue(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["basic"]["temperature_shift"] = 50
    out = render._apply_color_ops(_flat_gray(), a)
    assert out[..., 0].mean() > out[..., 2].mean()


def test_contrast_spreads_histogram(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["basic"]["contrast"] = 50
    arr = np.stack([_flat_gray(0.3), _flat_gray(0.7)]).reshape(-1, 2, 3)
    out = render._apply_color_ops(arr, a)
    assert out[..., 0].max() - out[..., 0].min() > 0.4  # 原本 0.4 差距被拉大


def test_shadows_positive_lifts_dark_pixels_only(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["basic"]["shadows"] = 80
    dark = render._apply_color_ops(_flat_gray(0.15), a).mean()
    bright = render._apply_color_ops(_flat_gray(0.85), a).mean()
    assert dark > 0.15 + 0.03           # 暗部被抬
    assert abs(bright - 0.85) < 0.03    # 亮部基本不动


def test_tone_curve_lifted_black(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["tone_curve"] = [{"input": 0, "output": 40}, {"input": 255, "output": 255}]
    out = render._apply_color_ops(_flat_gray(0.0), a)
    assert out.mean() > 0.1  # 40/255 ≈ 0.157


def test_tone_curve_near_endpoints_leave_black_and_white_untouched():
    """曲线控制点接近但不等于 (0,0)/(255,255) 时(GUI-T9 review 发现的域外
    夹平问题),定义域外应按斜率 1 外推——纯黑/纯白必须严格不变,而不是被
    np.interp 夹到端点 y 值。"""
    a = {"tone_curve": [
        {"input": 15, "output": 15}, {"input": 128, "output": 128}, {"input": 240, "output": 240},
    ]}
    black = render._apply_color_ops(_flat_gray(0.0), a)
    white = render._apply_color_ops(_flat_gray(1.0), a)
    # D5 线性光重标:严格相等 → atol=1e-4；EOTF/OETF 往返有 float32 末位误差。
    assert np.allclose(black, np.zeros_like(black), atol=1e-4)
    assert np.allclose(white, np.ones_like(white), atol=1e-4)


def test_tone_curve_matte_black_extrapolates_by_slope_one():
    """端点不接近 0 的哑光黑曲线:x=0 处的输出应按斜率 1 从最近控制点外推
    (40 - 15 = 25),而不是被夹到 40。"""
    a = {"tone_curve": [{"input": 15, "output": 40}, {"input": 255, "output": 255}]}
    out = render._apply_color_ops(_flat_gray(0.0), a)
    assert out.mean() == pytest.approx(25 / 255, abs=1e-3)


def test_saturation_negative_desaturates(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["basic"]["saturation"] = -100
    arr = np.zeros((4, 4, 3), dtype=np.float32); arr[..., 0] = 0.8  # 纯红
    out = render._apply_color_ops(arr, a)
    assert out.std(axis=-1).mean() < 0.05  # 通道间差异消失=去饱和


def test_vignette_darkens_corners_not_center(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["effects"]["vignette_amount"] = -80
    out = render._apply_spatial_ops(_flat_gray(0.5, (64, 64)), a)
    assert out[0, 0].mean() < out[32, 32].mean() - 0.05


def test_render_returns_image(sample_analysis):
    img = Image.new("RGB", (48, 32), (128, 128, 128))
    out = render.render(img, sample_analysis)
    assert isinstance(out, Image.Image) and out.size == (48, 32)


# --- 补充:HSV 往返与通道正确性(验证 _rgb_to_hsv/_hsv_to_rgb 自身实现) ---

def test_hsv_roundtrip_random():
    rng = np.random.default_rng(0)
    arr = rng.random((16, 16, 3)).astype(np.float32)
    hsv = render._rgb_to_hsv(arr)
    back = render._hsv_to_rgb(hsv)
    assert np.allclose(back, arr, atol=1e-4)


def test_hsv_hue_channel_order():
    arr = np.array(
        [[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]], dtype=np.float32
    )  # 红、绿、蓝
    hsv = render._rgb_to_hsv(arr)
    assert np.isclose(hsv[0, 0, 0], 0.0, atol=1e-3)
    assert np.isclose(hsv[0, 1, 0], 120.0, atol=1e-3)
    assert np.isclose(hsv[0, 2, 0], 240.0, atol=1e-3)
    assert np.allclose(hsv[..., 1], 1.0, atol=1e-3)  # 纯色饱和度=1
    assert np.allclose(hsv[..., 2], 1.0, atol=1e-3)  # 纯色明度=1


def test_hsv_gray_has_zero_saturation():
    arr = _flat_gray(0.4, (4, 4))
    hsv = render._rgb_to_hsv(arr)
    assert np.allclose(hsv[..., 1], 0.0, atol=1e-3)
    assert np.allclose(hsv[..., 2], 0.4, atol=1e-3)


# --- 补充:color_grading 回归测试(reviewer 发现的两处问题) ---

def test_color_grading_saturation_keeps_float32(sample_analysis):
    """_apply_color_grading 混色分支不得把 dtype 提升为 float64。"""
    a = _zero_analysis(sample_analysis)
    a["color_grading"]["shadows"] = {"hue": 210, "saturation": 40, "luminance": 0}
    out = render._apply_color_ops(_flat_gray(0.3), a)
    assert out.dtype == np.float32


def test_color_grading_luminance_only_brightens_without_saturation(sample_analysis):
    """saturation=0 时 luminance 调整不应被跳过(阴影区 +80 应提亮暗部)。"""
    a = _zero_analysis(sample_analysis)
    a["color_grading"]["shadows"] = {"hue": 0, "saturation": 0, "luminance": 80}
    out = render._apply_color_ops(_flat_gray(0.15), a)
    assert out.mean() > 0.15 + 0.03


# --- 还原度评分 score() ---

def _noise_img(seed, size=(64, 64)):
    rng = np.random.default_rng(seed)
    return Image.fromarray((rng.random((*size, 3)) * 255).astype(np.uint8), "RGB")


def test_score_identical_is_high():
    img = _noise_img(1)
    assert render.score(img, img) > 95


def test_score_monotonic_under_known_perturbation(sample_analysis):
    """扰动越大分越低——评分单调性,auto-refine 的可用性前提。"""
    base = _noise_img(2)
    import copy
    def perturbed(ev):
        a = copy.deepcopy(sample_analysis)
        a["basic"] = {k: 0 for k in a["basic"]}
        a["tone_curve"] = []; a["hsl"] = []
        for z in ("shadows", "midtones", "highlights", "global_"):
            a["color_grading"][z] = {"hue": 0, "saturation": 0, "luminance": 0}
        a["effects"] = {"vignette_amount": 0, "grain_amount": 0}
        a["basic"]["exposure"] = ev
        return render.render(base, a)
    s_small = render.score(perturbed(0.3), base)
    s_big = render.score(perturbed(1.5), base)
    assert s_small > s_big
    assert render.score(base, base) > s_small
