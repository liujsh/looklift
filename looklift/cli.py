"""looklift 命令行入口。

用法示例:
  # 分析一张大师成片,输出参数讲解 + 生成 LR 预设
  python -m looklift analyze master.jpg --name "胶片青橙"

  # 有原片对照,分析更准
  python -m looklift analyze after.jpg --original before.jpg --name "我的风格"

  # 直接把分析出的参数写到 RAW 的 sidecar,LR 打开即生效
  python -m looklift analyze master.jpg --sidecar D:/photos/IMG_0001.CR3

  # 照片里如果嵌了 Lightroom 元数据,直接读出精确参数(不花钱、100% 准确)
  python -m looklift read exported.jpg --preset stolen-look.xmp

  # 用之前保存的分析结果(模版)套用到新的 RAW
  python -m looklift apply saved.json --sidecar D:/photos/IMG_0002.CR3
"""

from __future__ import annotations

import argparse
import glob as globlib
import json
import shutil
import sys
from pathlib import Path

from . import analyzer, report, xmp_reader, xmp_writer

LOOKS_DIR = Path("looks")  # 风格库目录(相对当前工作目录)


def _resolve_template(name_or_path: str) -> Path:
    """模版参数既可以是 JSON 文件路径,也可以是风格库里的名字。"""
    p = Path(name_or_path)
    if p.is_file():
        return p
    candidate = LOOKS_DIR / f"{name_or_path}.json"
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"找不到模版: {name_or_path}(也不在 {LOOKS_DIR}/ 风格库中)")


def _expand_raws(patterns: list[str] | None) -> list[str]:
    """展开 --sidecar 的通配符(如 D:/photos/*.CR3)。"""
    raws: list[str] = []
    for pat in patterns or []:
        matched = globlib.glob(pat)
        if matched:
            raws.extend(matched)
        elif any(ch in pat for ch in "*?["):
            print(f"警告: 通配符 {pat} 没有匹配到文件", file=sys.stderr)
        else:
            raws.append(pat)  # 字面路径,交给 write_sidecar 报错
    return raws


def _print_analysis(analysis: dict) -> None:
    print("\n=== 风格分析 ===")
    print(analysis.get("summary", ""))
    steps = analysis.get("steps", [])
    if steps:
        print("\n=== 后期步骤 ===")
        for i, s in enumerate(steps, 1):
            print(f"{i}. {s}")
    b = analysis.get("basic", {})
    print("\n=== 基本面板 ===")
    label = {
        "temperature_shift": "色温", "tint_shift": "色调", "exposure": "曝光",
        "contrast": "对比度", "highlights": "高光", "shadows": "阴影",
        "whites": "白色", "blacks": "黑色", "texture": "纹理",
        "clarity": "清晰度", "dehaze": "去朦胧", "vibrance": "自然饱和度",
        "saturation": "饱和度",
    }
    for key, cn in label.items():
        v = b.get(key, 0)
        if v:
            print(f"  {cn:<6} {v:+g}")
    cg = analysis.get("color_grading", {})
    print("\n=== 颜色分级 ===")
    for zone, cn in [("shadows", "阴影"), ("midtones", "中间调"), ("highlights", "高光"), ("global_", "全局")]:
        z = cg.get(zone, {})
        if z.get("saturation"):
            print(f"  {cn:<4} 色相 {z.get('hue', 0):g}°  饱和度 {z.get('saturation', 0):g}  明亮度 {z.get('luminance', 0):+g}")
    hsl = [h for h in analysis.get("hsl", []) if h.get("hue") or h.get("saturation") or h.get("luminance")]
    if hsl:
        cn_color = {"red": "红", "orange": "橙", "yellow": "黄", "green": "绿",
                    "aqua": "浅绿", "blue": "蓝", "purple": "紫", "magenta": "品红"}
        print("\n=== HSL 混色器 ===")
        for h in hsl:
            print(f"  {cn_color.get(h['color'], h['color']):<3} 色相 {h.get('hue', 0):+g}  饱和度 {h.get('saturation', 0):+g}  明亮度 {h.get('luminance', 0):+g}")
    curve = analysis.get("tone_curve", [])
    if curve:
        pts = "  ".join(f"({round(p['input'])},{round(p['output'])})" for p in curve)
        print(f"\n=== 曲线控制点 ===\n  {pts}")


def _emit_outputs(crs: dict, args) -> None:
    if getattr(args, "preset", None) or getattr(args, "name", None):
        name = args.name or Path(args.preset or "preset").stem
        if args.preset:
            out = Path(args.preset)
        else:
            LOOKS_DIR.mkdir(exist_ok=True)
            out = LOOKS_DIR / f"{name}.xmp"
        path = xmp_writer.write_preset(crs, name, out)
        print(f"\n[预设] 已生成: {path}  (Lightroom → 预设面板 → 导入预设)")
    for raw in _expand_raws(getattr(args, "sidecar", None)):
        path = xmp_writer.write_sidecar(crs, raw)
        print(f"[sidecar] 已生成: {path}  (LR/Camera Raw 打开 {Path(raw).name} 时自动应用)")


def cmd_analyze(args) -> int:
    label = args.edited[0] if len(args.edited) == 1 else f"{len(args.edited)} 张成片(归纳共同风格)"
    print(f"正在分析 {label} ...(后端: {analyzer.resolve_backend(args.backend)})")
    analysis = analyzer.analyze(
        args.edited, original=args.original, style_hint=args.hint, backend=args.backend
    )
    _print_analysis(analysis)

    json_out = args.json
    if not json_out and args.name:
        LOOKS_DIR.mkdir(exist_ok=True)
        json_out = str(LOOKS_DIR / f"{args.name}.json")
    if json_out:
        Path(json_out).write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n[模版] 分析结果已保存: {json_out}  (之后可用 apply/refine 命令复用)")

    crs = xmp_writer.analysis_to_crs(analysis)
    _emit_outputs(crs, args)
    return 0


def cmd_read(args) -> int:
    settings = xmp_reader.read_crs_settings(args.photo)
    if settings is None:
        print("这张照片没有嵌入 Lightroom/Camera Raw 元数据。")
        print("提示:大部分网图的元数据已被剥离,可以用 analyze 命令让 AI 视觉分析。")
        return 1
    print(f"读取到 {len(settings)} 个 crs 参数:")
    for k, v in sorted(settings.items()):
        print(f"  {k} = {v}")
    if args.preset:
        name = args.name or Path(args.preset).stem
        path = xmp_writer.write_preset(settings, name, args.preset)
        print(f"\n[预设] 已生成: {path}  (参数来自照片元数据,100% 精确)")
    for raw in args.sidecar or []:
        path = xmp_writer.write_sidecar(settings, raw)
        print(f"[sidecar] 已生成: {path}")
    return 0


def cmd_apply(args) -> int:
    template = _resolve_template(args.template)
    analysis = json.loads(template.read_text(encoding="utf-8"))
    crs = xmp_writer.analysis_to_crs(analysis)
    if not args.preset and not args.name and not args.sidecar:
        print("请至少指定 --preset / --name / --sidecar 中的一个输出。")
        return 1
    _emit_outputs(crs, args)
    return 0


def cmd_list(args) -> int:
    if not LOOKS_DIR.is_dir():
        print(f"风格库为空({LOOKS_DIR}/ 不存在)。用 analyze --name 某某 来收藏第一个风格。")
        return 0
    templates = sorted(LOOKS_DIR.glob("*.json"))
    if not templates:
        print("风格库为空。用 analyze --name 某某 来收藏第一个风格。")
        return 0
    print(f"风格库({LOOKS_DIR}/,共 {len(templates)} 个):\n")
    for t in templates:
        try:
            data = json.loads(t.read_text(encoding="utf-8"))
            summary = (data.get("summary", "") or "").replace("\n", " ")
            if len(summary) > 50:
                summary = summary[:50] + "…"
        except (json.JSONDecodeError, OSError):
            summary = "(无法读取)"
        has_preset = " [预设✓]" if t.with_suffix(".xmp").exists() else ""
        print(f"  {t.stem}{has_preset}")
        if summary:
            print(f"      {summary}")
    print("\n套用: python -m looklift apply <名字> --sidecar 照片.CR3")
    return 0


def cmd_report(args) -> int:
    template = _resolve_template(args.template)
    analysis = json.loads(template.read_text(encoding="utf-8"))
    out = Path(args.out) if args.out else template.with_suffix(".html")
    out.write_text(report.render_report(analysis, template.stem), encoding="utf-8")
    print(f"[报告] 已生成: {out}  (浏览器打开查看)")
    return 0


def cmd_refine(args) -> int:
    template = _resolve_template(args.template)
    current = json.loads(template.read_text(encoding="utf-8"))
    print(f"正在校准 {template.stem} ...(后端: {analyzer.resolve_backend(args.backend)})")
    updated = analyzer.refine(current, args.attempt, args.target, backend=args.backend)
    _print_analysis(updated)

    backup = template.with_suffix(".json.bak")
    shutil.copy2(template, backup)
    template.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[模版] 已更新: {template}  (上一版备份在 {backup.name})")

    crs = xmp_writer.analysis_to_crs(updated)
    preset = template.with_suffix(".xmp")
    if preset.exists():
        xmp_writer.write_preset(crs, template.stem, preset)
        print(f"[预设] 已重新生成: {preset}  (LR 中需删除旧预设重新导入)")
    for raw in _expand_raws(args.sidecar):
        path = xmp_writer.write_sidecar(crs, raw)
        print(f"[sidecar] 已生成: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK,统一按 UTF-8 输出
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        prog="looklift",
        description="从照片提取调色参数,生成 Lightroom 预设 / RAW sidecar",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyze", help="AI 分析成片的调色参数")
    p.add_argument("edited", nargs="+",
                   help="后期完成的成片(可多张,多张时归纳共同风格,上限 5 张)")
    p.add_argument("--original", help="修图前的原片(仅单张成片时可用)")
    p.add_argument("--hint", help="风格提示,如摄影师名字、胶片型号等")
    p.add_argument("--name", help="风格名称:预设和模版自动存入 looks/ 风格库")
    p.add_argument("--preset", help="预设输出路径(.xmp),覆盖默认的 looks/ 位置")
    p.add_argument("--sidecar", action="append", metavar="RAW",
                   help="RAW 文件路径或通配符(如 D:/photos/*.CR3),可多次")
    p.add_argument("--json", help="模版输出路径,覆盖默认的 looks/ 位置")
    p.add_argument("--backend", choices=["auto", "cli", "api"], default="auto",
                   help="auto: 有 API key 走 API,否则走本地 Claude Code CLI")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("read", help="读取照片内嵌的 Lightroom 元数据(精确参数)")
    p.add_argument("photo", help="Lightroom 导出且包含元数据的 JPEG")
    p.add_argument("--name", help="生成的预设名称")
    p.add_argument("--preset", help="预设输出路径(.xmp)")
    p.add_argument("--sidecar", action="append", metavar="RAW", help="RAW 文件路径,生成同名 sidecar")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("apply", help="把保存的分析模版套用为预设/sidecar")
    p.add_argument("template", help="模版文件路径,或风格库中的名字")
    p.add_argument("--name", help="生成的预设名称")
    p.add_argument("--preset", help="预设输出路径(.xmp)")
    p.add_argument("--sidecar", action="append", metavar="RAW",
                   help="RAW 文件路径或通配符(如 D:/photos/*.CR3),可多次")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("list", help="列出风格库(looks/)中收藏的风格")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("report", help="生成 HTML 风格报告(参数表+曲线图+讲解)")
    p.add_argument("template", help="模版文件路径,或风格库中的名字")
    p.add_argument("-o", "--out", help="输出路径,默认与模版同名 .html")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("refine", help="迭代校准:对比套用效果和目标成片,修正模版参数")
    p.add_argument("template", help="要校准的模版(路径或风格库名字)")
    p.add_argument("--attempt", required=True, help="套用当前参数后导出的效果图")
    p.add_argument("--target", required=True, help="想要达到的目标成片")
    p.add_argument("--sidecar", action="append", metavar="RAW", help="顺便用新参数生成 sidecar")
    p.add_argument("--backend", choices=["auto", "cli", "api"], default="auto")
    p.set_defaults(func=cmd_refine)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:  # noqa: BLE001 - CLI 顶层统一报错
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
