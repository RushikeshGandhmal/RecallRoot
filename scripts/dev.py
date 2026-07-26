#!/usr/bin/env python3
"""Run the API and web development servers with coordinated shutdown."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(command: str) -> str:
    resolved = shutil.which(command)
    if not resolved:
        print(f"error: required command is not installed: {command}", file=sys.stderr)
        raise SystemExit(1)
    return resolved


def main() -> None:
    uv = require(os.getenv("UV", "uv"))
    npm = require(os.getenv("NPM", "npm"))
    api_port = os.getenv("API_PORT", "8000")
    api_host = os.getenv("API_HOST", "127.0.0.1")
    web_port = os.getenv("WEB_PORT", "3000")
    web_host = os.getenv("WEB_HOST", "127.0.0.1")
    web_environment = os.environ.copy()
    web_environment.setdefault("RECALLROOT_API_URL", f"http://127.0.0.1:{api_port}")

    commands = [
        (
            [
                uv,
                "run",
                "--project",
                str(ROOT / "apps" / "api"),
                "uvicorn",
                "recallgraph.main:app",
                "--app-dir",
                str(ROOT / "apps" / "api"),
                "--reload",
                "--host",
                api_host,
                "--port",
                api_port,
            ],
            None,
        ),
        (
            [
                npm,
                "--prefix",
                str(ROOT / "apps" / "web"),
                "run",
                "dev",
                "--",
                "--hostname",
                web_host,
                "--port",
                web_port,
            ],
            web_environment,
        ),
    ]
    processes: list[subprocess.Popen[bytes]] = []
    stopping = False

    def stop(_: int | None = None, __: object | None = None) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        for process in processes:
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        for command, environment in commands:
            processes.append(subprocess.Popen(command, cwd=ROOT, env=environment))
        print(f"RecallRoot API: http://localhost:{api_port}")
        print(f"RecallRoot web: http://localhost:{web_port}")
        while not stopping:
            exited = next((process for process in processes if process.poll() is not None), None)
            if exited is not None:
                stop()
                return_code = exited.returncode or 0
                if return_code:
                    raise SystemExit(return_code)
                break
            time.sleep(0.25)
    finally:
        stop()
        deadline = time.monotonic() + 5
        for process in processes:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()
        for process in processes:
            process.wait()


if __name__ == "__main__":
    main()
