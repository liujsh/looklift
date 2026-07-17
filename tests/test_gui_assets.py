"""GUI 资源包装测试：导入、静态文件存在、tokens.css 内容一致性、视觉 token 合规扫描。"""

import importlib.resources
import re
from pathlib import Path


def test_gui_import():
    """导入 looklift.gui 包应该成功。"""
    import looklift.gui
    assert looklift.gui.__doc__ is not None


def test_gui_static_files_exist():
    """已安装包下的五个关键静态文件应该存在。"""
    static_dir = importlib.resources.files("looklift") / "gui" / "static"

    # HTML 文件
    assert (static_dir / "index.html").is_file()

    # CSS 文件
    assert (static_dir / "css" / "app.css").is_file()
    assert (static_dir / "vendor" / "claude" / "tokens.css").is_file()
    assert (static_dir / "vendor" / "claude" / "components.css").is_file()

    # JS 文件
    assert (static_dir / "js" / "app.js").is_file()


def test_tokens_css_matches_source():
    """已安装包的 tokens.css 内容应与源文件字节一致。"""
    # 读取源文件
    source_path = Path(__file__).parent.parent / "assets" / "design-system" / "claude" / "tokens.css"
    source_content = source_path.read_text(encoding="utf-8")

    # 读取已安装包内的副本
    vendored = importlib.resources.files("looklift") / "gui" / "static" / "vendor" / "claude" / "tokens.css"
    vendored_content = vendored.read_text(encoding="utf-8")

    # 字节一致（防止漂移）
    assert vendored_content == source_content, "vendored tokens.css drifted from source"


# ─── GUI-T5：视觉 token 合规扫描 ────────────────────────────────────────
#
# 扫描 looklift/gui/static/** 下的 .css/.html/.js，禁止出现 token 变量之外的
# 裸 hex 颜色（如 `#c96442`）——颜色必须一律通过 vendor/claude/tokens.css 的
# CSS 变量表达。
#
# 排除范围（对 tasks.md T15 的修订）：整个 vendor/claude/** 目录都排除在扫描
# 之外，不只是 tokens.css 本身。理由：vendor/claude/components.css 是从
# assets/design-system/claude/components.html 原样摘录的上游文件（见该文件
# 开头的来源注释），合法带有 2 处上游 hex（`#d1cfc5` 按钮 ring 阴影、
# `#3898ec` 表单聚焦色），这些颜色是上游设计系统自己的实现细节，不受本项目
# "自己写的样式只能用 token" 的规范约束；扫描它们只会产生误报，逼着后人去
# "修复"一份本不该改的第三方文件。
#
# 启发式说明（刻意从简，避免在 `#panel-analyze` 这类 id 选择器/锚点上误报，
# 同时也不追求解析完整的 CSS/HTML/JS 语法树）：
#   - .css：先剥掉 /* 注释 */，再按 `{ ... }` 取出每条规则的声明体，声明体内部
#     按 `;` 切出单条声明，只在每条声明第一个 `:` 之后的值部分找 hex——这样
#     跨行换行的声明值（DESIGN.md 的 ring-shadow 语法常见，比如
#     `box-shadow: var(--accent) 0 0 0 0,\n  #c96442 0 0 0 1px;` 把 hex
#     写在续行）也能被扫到，不依赖"同一行"这个假设。选择器（`.nav-item[aria-current="page"]`
#     这类，含 `#id`/`:pseudo`）本身在 `{ }` 块之外，天然不会被当成声明体。
#   - .html：只看 `style="..."`/`style='...'` 内联样式属性的值（单双引号都认）。
#   - .js：只看字符串字面量（`'...'`/`"..."`/`` `...` ``）内容，跳过其余代码。

_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_JS_STRING_RE = re.compile(r"""(['"`])((?:\\.|(?!\1)[^\\])*)\1""")
_HTML_STYLE_ATTR_RE = re.compile(r"""style\s*=\s*(["'])((?:(?!\1).)*)\1""")
_HTML_HREF_SRC_RE = re.compile(r'(?:href|src)\s*=\s*"([^"]+)"')
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_BLOCK_RE = re.compile(r"\{([^{}]*)\}", re.DOTALL)

_VENDOR_EXCLUDE = ("vendor", "claude")


def _gui_static_dir() -> Path:
    return Path(__file__).parent.parent / "looklift" / "gui" / "static"


def _iter_scannable_files(static_dir: Path):
    """遍历 static_dir 下要做裸 hex 扫描的 .css/.html/.js 文件，排除 vendor/claude/**。"""
    for path in sorted(static_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".css", ".html", ".js"):
            continue
        rel_parts = path.relative_to(static_dir).parts
        if rel_parts[: len(_VENDOR_EXCLUDE)] == _VENDOR_EXCLUDE:
            continue
        yield path


def _bare_hex_hits_css(path: Path) -> list[str]:
    """扫描单个 CSS 文件：剥注释 → 按 `{ ... }` 取声明体 → 按 `;` 切单条声明 →
    只在每条声明第一个 `:` 之后的值部分找 hex。跨行换行的声明值也覆盖到，因为
    这里操作的是整块声明体字符串（可能跨多行），不是逐行扫描。
    """
    hits = []
    text = path.read_text(encoding="utf-8")
    text_no_comments = _CSS_COMMENT_RE.sub("", text)
    for block_match in _CSS_BLOCK_RE.finditer(text_no_comments):
        block_start = block_match.start(1)
        block_body = block_match.group(1)
        for decl_match in re.finditer(r"[^;]+", block_body):
            decl = decl_match.group(0)
            colon_idx = decl.find(":")
            if colon_idx == -1:
                continue
            value = decl[colon_idx + 1 :]
            value_start_in_block = decl_match.start() + colon_idx + 1
            for m in _HEX_RE.finditer(value):
                abs_pos = block_start + value_start_in_block + m.start()
                lineno = text_no_comments.count("\n", 0, abs_pos) + 1
                hits.append(f"{path}:{lineno}: 裸 hex {m.group(0)}")
    return hits


def _bare_hex_hits_html(path: Path) -> list[str]:
    hits = []
    text = path.read_text(encoding="utf-8")
    for attr_match in _HTML_STYLE_ATTR_RE.finditer(text):
        for m in _HEX_RE.finditer(attr_match.group(2)):
            hits.append(f"{path}: style 属性中出现裸 hex {m.group(0)}")
    return hits


def _bare_hex_hits_js(path: Path) -> list[str]:
    hits = []
    text = path.read_text(encoding="utf-8")
    for str_match in _JS_STRING_RE.finditer(text):
        for m in _HEX_RE.finditer(str_match.group(2)):
            hits.append(f"{path}: 字符串字面量中出现裸 hex {m.group(0)}")
    return hits


def test_css_hex_scan_catches_wrapped_multiline_declaration_value(tmp_path):
    """回归测试：裸 hex 扫描要能抓到跨行换行的声明值。DESIGN.md 的 ring-shadow
    语法常把 box-shadow 的多个逗号分隔值换行写，hex 出现在续行开头、续行本身
    没有 `:`——旧版"按行扫描、找每行第一个冒号之后的文本"启发式会漏掉这种情况；
    这里用一个临时 CSS 文件固定住"必须能跨行检出"这个行为。
    """
    css_file = tmp_path / "wrapped.css"
    css_file.write_text(
        ".btn-primary {\n"
        "  box-shadow:\n"
        "    var(--accent) 0px 0px 0px 0px,\n"
        "    #c96442 0px 0px 0px 1px;\n"
        "}\n",
        encoding="utf-8",
    )
    hits = _bare_hex_hits_css(css_file)
    assert any("#c96442" in hit for hit in hits), f"未检出跨行换行声明值里的裸 hex，hits={hits}"


def test_css_hex_scan_ignores_id_selector_and_comment(tmp_path):
    """健全性检查：`#panel-analyze` 这类 id 选择器、以及注释里的 hex 不应被误报——
    前者在 `{ }` 块外（不是声明体），后者已被注释剥离逻辑去掉。
    """
    css_file = tmp_path / "sanity.css"
    css_file.write_text(
        "/* old value was #ff00ff, replaced by token */\n"
        "#panel-analyze { color: var(--fg); }\n",
        encoding="utf-8",
    )
    hits = _bare_hex_hits_css(css_file)
    assert not hits, f"不应误报 id 选择器/注释里的 hex：{hits}"


def test_html_style_attr_hex_scan_covers_single_and_double_quotes(tmp_path):
    """`style="..."` 和 `style='...'` 两种引号都要被扫到（Minor 修订）。"""
    html_file = tmp_path / "inline.html"
    html_file.write_text(
        '<div style="color: #123456;"></div>\n' "<div style='color: #abcdef;'></div>\n",
        encoding="utf-8",
    )
    hits = _bare_hex_hits_html(html_file)
    joined = "\n".join(hits)
    assert "#123456" in joined
    assert "#abcdef" in joined


def test_no_bare_hex_outside_vendor():
    """looklift/gui/static/**（排除 vendor/claude/**）下的 .css/.html/.js 不得出现裸 hex。"""
    static_dir = _gui_static_dir()
    hits: list[str] = []
    for path in _iter_scannable_files(static_dir):
        suffix = path.suffix.lower()
        if suffix == ".css":
            hits.extend(_bare_hex_hits_css(path))
        elif suffix == ".html":
            hits.extend(_bare_hex_hits_html(path))
        elif suffix == ".js":
            hits.extend(_bare_hex_hits_js(path))
    assert not hits, "发现裸 hex，应改用 tokens.css 里的变量：\n" + "\n".join(hits)


def test_vendor_claude_excluded_but_carries_known_upstream_hex():
    """确认 vendor/claude/** 确实被排除在扫描之外——它本身合法带有 2 处上游 hex，
    如果排除逻辑失效，上面那条扫描测试会先挂掉；这里额外锁定排除清单没被意外收窄。
    """
    static_dir = _gui_static_dir()
    scanned = set(_iter_scannable_files(static_dir))
    components_css = static_dir / "vendor" / "claude" / "components.css"
    assert components_css.is_file()
    assert components_css not in scanned
    hex_count = len(_HEX_RE.findall(components_css.read_text(encoding="utf-8")))
    assert hex_count >= 2, "vendor components.css 预期至少带 2 处上游 hex（此断言本身也验证了排除有生效）"


# ─── GUI-T5：index.html 结构校验 ────────────────────────────────────────


def test_index_html_references_resolve():
    """index.html 里的本地 href/src 必须以 /static/ 开头（server.py 只认
    "/"、"/static/*"、"/api/*"、"/report/* 四类前缀，裸相对路径会 404——
    这条断言本身就是防止未来新面板往 index.html 里加不带前缀引用的回归门），
    且去掉 /static/ 前缀后在磁盘上真实存在。
    """
    static_dir = _gui_static_dir()
    text = (static_dir / "index.html").read_text(encoding="utf-8")
    refs = _HTML_HREF_SRC_RE.findall(text)
    assert refs, "index.html 应至少引用一个静态资源"
    for ref in refs:
        if ref.startswith(("http://", "https://", "//")):
            continue
        assert ref.startswith("/static/"), f"index.html 的本地引用必须以 /static/ 开头：{ref}"
        resolved = (static_dir / ref[len("/static/") :]).resolve()
        assert resolved.is_file(), f"index.html 引用的文件不存在：{ref}"


def test_index_html_has_three_panel_containers():
    """三个面板容器 id 必须都在：#panel-analyze / #panel-looks / #panel-settings。"""
    static_dir = _gui_static_dir()
    text = (static_dir / "index.html").read_text(encoding="utf-8")
    for panel_id in ("panel-analyze", "panel-looks", "panel-settings"):
        assert f'id="{panel_id}"' in text, f"index.html 缺少面板容器 #{panel_id}"
