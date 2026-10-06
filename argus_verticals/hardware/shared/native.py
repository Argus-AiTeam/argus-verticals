"""Run one owned native command with live caller-defined resource limits."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TextIO

MAX_CONSOLE_BYTES = 32 * 1024 * 1024


def run_monitored(
    command: list[str], *, root: Path, stream: TextIO,
    deadline: float, limit: Callable[[float], str], env: Mapping[str, str] | None = None,
) -> tuple[int, str]:
    stopped = ""
    with subprocess.Popen(
        command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    ) as process:
        try:
            while process.poll() is None:
                if stopped := limit(deadline):
                    break
                time.sleep(0.05)
        finally:
            finished = process.poll() is not None
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    if finished and not stopped:
                        stopped = "native command left owned child processes running"
                except ProcessLookupError:
                    pass
            elif not finished:
                process.kill()
            exit_code = process.wait()
    return exit_code, stopped or limit(deadline)


def run_logged(
    command: list[str], *, root: Path, log: Path, timeout: float,
    env: Mapping[str, str] | None = None,
) -> tuple[int, str]:
    def limit(deadline: float) -> str:
        if time.monotonic() >= deadline:
            return f"native command exceeded {timeout:g} seconds"
        if log.stat().st_size > MAX_CONSOLE_BYTES:
            return f"native console output exceeded {MAX_CONSOLE_BYTES} bytes"
        return ""

    with log.open("w", encoding="utf-8") as stream:
        return run_monitored(
            command, root=root, stream=stream, env=env,
            deadline=time.monotonic() + timeout, limit=limit,
        )
