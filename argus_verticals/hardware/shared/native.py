"""Run one owned native command with live caller-defined resource limits."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import TextIO


def run_monitored(
    command: list[str], *, root: Path, stream: TextIO,
    deadline: float, limit: Callable[[float], str],
) -> tuple[int, str]:
    stopped = ""
    with subprocess.Popen(
        command, cwd=root, stdout=stream, stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    ) as process:
        while process.poll() is None:
            if stopped := limit(deadline):
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        process.wait()
                else:
                    process.kill()
                break
            time.sleep(0.05)
        exit_code = process.wait()
    return exit_code, stopped or limit(deadline)
