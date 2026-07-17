"""对冻结 sidecar 执行最终离线发布冒烟。

验证真实引擎预热、localhost API、随包内置模板、临时用户库写入和预设导出。
脚本只访问本机随机端口，不调用任何 AI/provider。
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXE = (
    ROOT / "build" / "pyinstaller" / "dist" / "looklift-engine" / "looklift-engine.exe"
)


def _probe(executable: Path, env: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run(
        [str(executable), "probe"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )
    payload = json.loads(result.stdout.strip())
    if payload.get("rendered") is not True:
        raise RuntimeError(f"冻结引擎未完成真实渲染：{payload}")
    return payload


def _wait_ready(process: subprocess.Popen[str], timeout: float = 120) -> dict[str, Any]:
    lines: queue.Queue[str] = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line)

    threading.Thread(target=read_output, daemon=True).start()
    deadline = time.monotonic() + timeout
    seen: list[str] = []
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=0.2).strip()
        except queue.Empty:
            if process.poll() is not None:
                break
            continue
        if not line:
            continue
        seen.append(line)
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("event") == "ready":
            return payload
    raise RuntimeError(f"冻结 sidecar 未就绪（退出码 {process.poll()}）：{' | '.join(seen)}")


def _json_request(
    base_url: str,
    token: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        method=method,
        headers={"X-Looklift-Token": token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def smoke(executable: Path) -> dict[str, Any]:
    """在临时用户环境中完成两次预热和收藏导出闭环。"""
    executable = executable.resolve()
    if not executable.is_file():
        raise FileNotFoundError(f"找不到冻结 sidecar：{executable}")

    with tempfile.TemporaryDirectory(prefix="looklift-release-smoke-") as raw_temp:
        temp = Path(raw_temp)
        user_looks = temp / "user-looks"
        env = os.environ.copy()
        env.update(
            {
                "USERPROFILE": str(temp / "home"),
                "LOCALAPPDATA": str(temp / "local-app-data"),
                "LOOKLIFT_CACHE_DIR": str(temp / "cache"),
                "LOOKLIFT_LOOKS_DIR": str(user_looks),
                "LOOKLIFT_STARTUP_TOKEN": "release-smoke-token",
            }
        )

        cold = _probe(executable, env)
        warm = _probe(executable, env)
        process = subprocess.Popen(
            [str(executable), "serve", "--port", "0"],
            cwd=temp,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        try:
            ready = _wait_ready(process)
            base_url = f"http://127.0.0.1:{ready['port']}"
            token = env["LOOKLIFT_STARTUP_TOKEN"]
            looks = _json_request(base_url, token, "/api/looks")["looks"]
            built_ins = [item for item in looks if item.get("source") == "built_in"]
            if len(built_ins) < 3 or not all(item.get("readonly") is True for item in built_ins):
                raise RuntimeError(f"随包内置模板不完整或非只读：{built_ins}")

            source_name = built_ins[0]["name"]
            encoded_source = urllib.parse.quote(source_name, safe="")
            analysis = _json_request(base_url, token, f"/api/looks/{encoded_source}")
            saved_name = "发布冒烟风格"
            _json_request(
                base_url,
                token,
                "/api/looks",
                method="POST",
                payload={"name": saved_name, "analysis": analysis, "factor": 0.7},
            )
            encoded_saved = urllib.parse.quote(saved_name, safe="")
            exported = _json_request(
                base_url,
                token,
                f"/api/looks/{encoded_saved}/export",
                method="POST",
                payload={},
            )
            preset = Path(exported["preset"]).resolve()
            if not preset.is_file() or not preset.is_relative_to(user_looks.resolve()):
                raise RuntimeError(f"预设未写入临时用户库：{preset}")
            refreshed = _json_request(base_url, token, "/api/looks")["looks"]
            saved = next((item for item in refreshed if item.get("name") == saved_name), None)
            if not saved or saved.get("source") != "user" or saved.get("readonly") is not False:
                raise RuntimeError(f"用户风格读写属性错误：{saved}")
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

        return {
            "cold": cold,
            "warm": warm,
            "built_in_count": len(built_ins),
            "user_preset": preset.name,
            "sidecar_reaped": process.poll() is not None,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", nargs="?", type=Path, default=DEFAULT_EXE)
    result = smoke(parser.parse_args().executable)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
