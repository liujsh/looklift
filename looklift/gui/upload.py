"""上传文件处理：multipart 解析、文件名清洗、临时目录落盘。

从 `api.py` 拆出来——`api.py` 按项目分层约定只做「HTTP 参数 → 核心调用 →
JSON 响应」的粘合，这里的 multipart/文件名/文件系统细节属于实现，不该堆在
handler 里。本模块不碰 HTTP 层（不知道 status code、不认识请求上下文 dict），
`api.py` 的 `_upload` handler 负责把这里抛出的异常翻译成 HTTP 错误。
"""
from __future__ import annotations

import email
import re
import tempfile
import uuid
from email.policy import default as _email_default_policy
from pathlib import Path

# `POST /api/upload` 大小上限：50MB。测试里会 monkeypatch 这个模块级常量来验
# 证 413 分支，别把它内联进函数体。
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Windows 保留字符集 `< > : " | ? *`，加上所有控制字符（含 NUL，`\x00`-`\x1f`）。
# 这些字符要么在 NTFS 上有特殊含义（`:` 触发备用数据流、`\` `/` 是路径分隔符），
# 要么会被文件系统 API 直接拒绝（`<` `>` `|` `?` `*` `"`），静默截断或抛
# 未捕获的 OSError 都不可接受。
_UNSAFE_CHARS_RE = re.compile(r'[<>:"|?*\x00-\x1f]')

# 本进程的上传临时目录，`tempfile.mkdtemp` 只在第一次真正用到时创建（惰性），
# 之后一直复用到进程退出——不是每次上传都新建一个目录。
_upload_dir_path: Path | None = None


def upload_dir() -> Path:
    """本进程的上传临时目录，惰性创建、之后复用（模块级缓存）。"""
    global _upload_dir_path
    if _upload_dir_path is None:
        _upload_dir_path = Path(tempfile.mkdtemp(prefix="looklift-upload-"))
    return _upload_dir_path


def parse_multipart_first_file(body: bytes, content_type: str) -> tuple[str, bytes] | None:
    """从 multipart/form-data 请求体里解析出第一个带文件名的字段，返回
    `(filename, content_bytes)`；没有文件字段时返回 `None`。

    实现选择：用 stdlib `email` 模块而不是手写 boundary 切分——Python 3.13
    移除了曾经常用于这个场景的 `cgi.FieldStorage`，`email.message_from_bytes`
    本身就能正确处理 multipart 的边界解析（转义、结尾 `--`、CRLF 细节），比
    自己重新实现一遍这些边角情况更可靠。做法是把 HTTP 请求已经拿到的
    `Content-Type`（含 boundary 参数）当成一封 MIME 邮件的头部，拼在 body 前面
    交给 `email` 解析，再遍历各 part 找 `Content-Disposition` 带 `filename` 的
    那个。
    """
    header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
    message = email.message_from_bytes(header + body, policy=_email_default_policy)
    if not message.is_multipart():
        return None
    for part in message.iter_parts():
        filename = part.get_filename()
        if filename:
            return filename, part.get_payload(decode=True) or b""
    return None


def sanitize_filename(filename: str) -> str:
    """把上传文件名清洗成能安全落盘的形式：

    1. 去掉路径分隔符（`/` 或 `\\`），只留最后一段——防止 `../` 之类的段试图
       跳出上传目录。
    2. 把 Windows 保留字符集（`< > : " | ? *`）和所有控制字符（含 NUL）替换成
       `_`——这些字符要么有特殊文件系统含义，要么直接被拒绝。
    3. 去掉首尾的点/空格（Windows 不允许文件名以点或空格结尾；纯 `.`/`..`
       在这一步也被清空)。
    4. 清洗完是空字符串（比如原文件名整个是点或空格）就退回固定文件名
       `upload.bin`，不落一个空名字的文件。
    """
    normalized = filename.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    name = _UNSAFE_CHARS_RE.sub("_", name)
    name = name.strip(" .")
    return name or "upload.bin"


def save_upload(dest_dir: Path, filename: str, content: bytes) -> Path:
    """按 `{uuid}_{清洗后的文件名}` 落盘到 `dest_dir`，返回完整路径。

    `sanitize_filename` 已经挡掉了已知的非法字符，但文件系统总有考虑不到的
    边角情况（比如保留设备名撞车、路径总长度超限），这里不吞异常——写入失败
    时原样抛出 `OSError`，交给 `api.py` 的 handler 翻译成不泄漏本地路径的
    通用 HTTP 错误。
    """
    dest = dest_dir / f"{uuid.uuid4().hex}_{sanitize_filename(filename)}"
    dest.write_bytes(content)
    return dest
