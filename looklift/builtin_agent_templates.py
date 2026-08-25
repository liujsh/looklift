"""v2.6 内置 Agent Template 目录。

Template 是只读的相对白盒参数先验；目录不承担渲染、权限或持久化职责。
"""

from __future__ import annotations

from dataclasses import dataclass

from .agent_tool_contract import AgentTemplate, ScalarOperation


@dataclass(frozen=True)
class BuiltinAgentTemplate:
    """带来源标记的官方 Template。"""

    template: AgentTemplate
    source: str = "built_in"
    readonly: bool = True


def _template(
    template_id: str,
    name: str,
    *,
    scene_tags: tuple[str, ...],
    intent_tags: tuple[str, ...],
    expected_effect: str,
    contraindications: tuple[str, ...],
    risks: tuple[str, ...],
    compatible_skills: tuple[str, ...],
    operations: tuple[ScalarOperation, ...],
) -> BuiltinAgentTemplate:
    return BuiltinAgentTemplate(
        template=AgentTemplate(
            template_id=template_id,
            version=1,
            name=name,
            scene_tags=scene_tags,
            intent_tags=intent_tags,
            expected_effect=expected_effect,
            contraindications=contraindications,
            risks=risks,
            compatible_skills=compatible_skills,
            operations=operations,
        )
    )


_TEMPLATES = (
    _template(
        "portrait-natural-soft",
        "自然人像柔和起点",
        scene_tags=("portrait",),
        intent_tags=("natural", "soft"),
        expected_effect="降低生硬反差并保留面部层次。",
        contraindications=("需要局部磨皮", "主体面部不可见"),
        risks=("全局降反差可能使背景变平",),
        compatible_skills=("portrait-natural",),
        operations=(
            ScalarOperation(path="basic.contrast", mode="delta", value=-8, reason="降低生硬反差"),
            ScalarOperation(path="basic.highlights", mode="delta", value=-6, reason="保留面部高光"),
        ),
    ),
    _template(
        "portrait-natural-backlight",
        "逆光人像层次",
        scene_tags=("portrait", "backlight"),
        intent_tags=("subject-readable",),
        expected_effect="小幅抬高主体暗部并控制逆光高光。",
        contraindications=("高光已完全裁切",),
        risks=("抬阴影过多会带来灰雾",),
        compatible_skills=("portrait-natural",),
        operations=(
            ScalarOperation(path="basic.shadows", mode="delta", value=10, reason="恢复主体暗部"),
            ScalarOperation(path="basic.highlights", mode="delta", value=-10, reason="控制逆光高光"),
        ),
    ),
    _template(
        "product-neutral-catalog",
        "商品中性目录",
        scene_tags=("product", "catalog"),
        intent_tags=("neutral", "consistent"),
        expected_effect="建立克制、可比较的商品曝光和色彩起点。",
        contraindications=("需要替换品牌色", "需要局部抠图"),
        risks=("压低饱和度可能削弱包装色彩",),
        compatible_skills=("product-consistency",),
        operations=(
            ScalarOperation(path="basic.contrast", mode="delta", value=-4, reason="保持目录反差一致"),
            ScalarOperation(path="basic.highlights", mode="delta", value=-8, reason="保留包装高光"),
        ),
    ),
    _template(
        "product-material-clarity",
        "商品材质清晰",
        scene_tags=("product",),
        intent_tags=("material", "clarity"),
        expected_effect="轻微增强材质可读性，避免过度锐化。",
        contraindications=("主体严重失焦",),
        risks=("全局清晰度会同时影响背景",),
        compatible_skills=("product-consistency",),
        operations=(
            ScalarOperation(path="basic.texture", mode="delta", value=5, reason="增强材质纹理"),
            ScalarOperation(path="basic.clarity", mode="delta", value=3, reason="保持边缘可读"),
        ),
    ),
    _template(
        "highlight-natural-recovery",
        "自然高光恢复",
        scene_tags=("highlight", "exposure"),
        intent_tags=("recovery", "natural"),
        expected_effect="压回可恢复高光并保持整体反差。",
        contraindications=("亮部完全裁切",),
        risks=("降低高光过多会使画面发灰",),
        compatible_skills=("highlight-recovery",),
        operations=(
            ScalarOperation(path="basic.highlights", mode="delta", value=-14, reason="恢复高光层次"),
            ScalarOperation(path="basic.contrast", mode="delta", value=2, reason="抵消灰雾"),
        ),
    ),
    _template(
        "highlight-backlight-balance",
        "逆光曝光平衡",
        scene_tags=("highlight", "backlight"),
        intent_tags=("balance",),
        expected_effect="在高光可控的前提下改善主体可读性。",
        contraindications=("需要局部主体蒙版",),
        risks=("抬升阴影会暴露噪声",),
        compatible_skills=("highlight-recovery",),
        operations=(
            ScalarOperation(path="basic.shadows", mode="delta", value=8, reason="改善主体暗部"),
            ScalarOperation(path="basic.highlights", mode="delta", value=-8, reason="平衡逆光亮部"),
        ),
    ),
)


def list_builtin_agent_templates() -> tuple[BuiltinAgentTemplate, ...]:
    """返回稳定顺序的官方只读目录。"""
    return _TEMPLATES


def get_builtin_agent_template(template_id: str) -> BuiltinAgentTemplate:
    """按 ID 获取官方 Template，不接受路径或未知条目。"""
    for entry in _TEMPLATES:
        if entry.template.template_id == template_id:
            return entry
    raise KeyError(f"未知内置 Agent Template：{template_id}")
