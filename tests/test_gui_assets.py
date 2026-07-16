"""GUI 资源包装测试：导入、静态文件存在、tokens.css 内容一致性。"""

import importlib.resources
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
