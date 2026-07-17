"""Tauri Python sidecar 入口：运行时准备、真实引擎预热与 HTTP 服务。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import MutableMapping, Sequence


def configure_runtime(environ: MutableMapping[str, str] | None = None) -> Path:
    """在导入 numba 前设置可写 cache 目录并返回该路径。"""
    env = os.environ if environ is None else environ
    explicit_root = env.get("LOOKLIFT_CACHE_DIR")
    if explicit_root:
        cache_root = Path(explicit_root)
    elif env.get("LOCALAPPDATA"):
        cache_root = Path(env["LOCALAPPDATA"]) / "looklift" / "cache"
    else:
        cache_root = Path.home() / ".looklift" / "cache"
    numba_cache = cache_root / "numba"
    numba_cache.mkdir(parents=True, exist_ok=True)
    env["NUMBA_CACHE_DIR"] = str(numba_cache)
    return numba_cache


def warm_engine() -> dict[str, object]:
    """真实调用 pyvips，并用引擎的融合管线触发 numba JIT。"""
    import numba
    import pyvips

    from ..render import pipeline

    vips_mean = float(pyvips.Image.black(1, 1).avg())
    pipeline.warmup()
    libvips = ".".join(str(pyvips.version(index)) for index in range(3))
    return {
        "numba": numba.__version__,
        "pyvips": pyvips.__version__,
        "libvips": libvips,
        "vips_mean": vips_mean,
        "rendered": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="looklift Tauri 引擎 sidecar")
    parser.add_argument("command", choices=("probe", "serve"))
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--token", default=os.environ.get("LOOKLIFT_STARTUP_TOKEN"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """准备运行时并执行一次性门禁或常驻 HTTP 服务。"""
    args = _parser().parse_args(argv)
    cache_dir = configure_runtime()
    engine = warm_engine()
    if args.command == "probe":
        print(
            json.dumps(
                {"event": "probe", "cache_dir": str(cache_dir), **engine},
                ensure_ascii=True,
            ),
            flush=True,
        )
        return 0

    from .server import create_server

    server = create_server(port=args.port, token=args.token)
    print(
        json.dumps(
            {
                "event": "ready",
                "port": server.server_port,
                "cache_dir": str(cache_dir),
                **engine,
            },
            ensure_ascii=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
