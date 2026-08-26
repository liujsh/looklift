"""Windows 当前用户 DPAPI 凭据存储。"""

from __future__ import annotations

import ctypes
import os
import re
from ctypes import wintypes
from pathlib import Path


class CredentialStoreError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


def _blob(content: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(content)
    return (
        _DataBlob(len(content), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))),
        buffer,
    )


class DpapiCredentialStore:
    """密文落应用目录，解密权限绑定当前 Windows 用户。"""

    def __init__(self, root: Path) -> None:
        if os.name != "nt":
            raise CredentialStoreError("当前系统不支持 DPAPI 安全存储")
        self._root = root

    def put(self, provider_id: str, secret: str) -> str:
        path = self._path(provider_id)
        if not secret:
            raise CredentialStoreError("凭据不能为空")
        encrypted = self._protect(secret.encode("utf-8"))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(encrypted)
        temporary.replace(path)
        return f"dpapi://{provider_id}"

    def get(self, reference: str) -> str:
        provider_id = self._provider_id(reference)
        path = self._path(provider_id)
        if not path.is_file():
            raise KeyError(reference)
        return self._unprotect(path.read_bytes()).decode("utf-8")

    def delete(self, reference: str) -> None:
        path = self._path(self._provider_id(reference))
        if path.exists():
            path.unlink()

    def _path(self, provider_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", provider_id):
            raise CredentialStoreError("Provider ID 不安全")
        return self._root / f"{provider_id}.bin"

    @staticmethod
    def _provider_id(reference: str) -> str:
        if not reference.startswith("dpapi://"):
            raise CredentialStoreError("凭据引用无效")
        return reference.removeprefix("dpapi://")

    @staticmethod
    def _protect(content: bytes) -> bytes:
        source, source_buffer = _blob(content)
        target = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        if not crypt32.CryptProtectData(
            ctypes.byref(source),
            "LookLift",
            None,
            None,
            None,
            0,
            ctypes.byref(target),
        ):
            raise CredentialStoreError("凭据加密失败")
        try:
            return ctypes.string_at(target.data, target.size)
        finally:
            ctypes.windll.kernel32.LocalFree(target.data)
            del source_buffer

    @staticmethod
    def _unprotect(content: bytes) -> bytes:
        source, source_buffer = _blob(content)
        target = _DataBlob()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
        ):
            raise CredentialStoreError("凭据解密失败")
        try:
            return ctypes.string_at(target.data, target.size)
        finally:
            ctypes.windll.kernel32.LocalFree(target.data)
            del source_buffer
