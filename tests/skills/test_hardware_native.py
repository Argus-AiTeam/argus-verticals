from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import pytest

from argus_verticals.hardware.shared import native
from argus_verticals.hardware.shared.evidence import EvidenceError


def test_monitor_cleans_up_when_observation_raises(tmp_path):
    def unavailable(_deadline):
        raise OSError("cannot inspect native output")

    started = time.monotonic()
    with (tmp_path / "console.log").open("w") as stream:
        with pytest.raises(OSError, match="cannot inspect"):
            native.run_monitored(
                [sys.executable, "-c", "import time; time.sleep(2)"],
                root=tmp_path, stream=stream, deadline=started + 10, limit=unavailable,
            )
    assert time.monotonic() - started < 1.5


@pytest.mark.skipif(os.name != "posix", reason="owned POSIX process groups")
def test_exited_parent_cannot_leave_children_running(tmp_path):
    child = "import pathlib,time; time.sleep(0.4); pathlib.Path('escaped').write_text('wrong'); time.sleep(2)"
    parent = (
        "import pathlib,subprocess,sys; "
        f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
        "pathlib.Path('child.pid').write_text(str(p.pid))"
    )
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"]) as unrelated:
        try:
            with (tmp_path / "console.log").open("w") as stream:
                exit_code, stopped = native.run_monitored(
                    [sys.executable, "-c", parent], root=tmp_path, stream=stream,
                    deadline=time.monotonic() + 3, limit=lambda _: "",
                )
            assert exit_code == 0 and "owned child processes" in stopped
            time.sleep(0.5)
            assert not (tmp_path / "escaped").exists()
            assert unrelated.poll() is None
        finally:
            if (tmp_path / "child.pid").exists():
                try:
                    os.kill(int((tmp_path / "child.pid").read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            unrelated.kill()


@pytest.mark.parametrize("failure", ["timeout", "output"])
def test_logged_command_stops_live_and_retains_partial_output(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(native, "MAX_CONSOLE_BYTES", 1024, raising=False)
    script = "import time; print('partial',flush=True); "
    script += "print('x'*4096,flush=True); " if failure == "output" else ""
    script += "time.sleep(2); print('UNSTOPPED')"
    log = tmp_path / "console.log"
    exit_code, stopped = native.run_logged(
        [sys.executable, "-c", script], root=tmp_path, log=log,
        timeout=0.15 if failure == "timeout" else 5,
    )
    assert exit_code != 0
    assert "seconds" in stopped if failure == "timeout" else "bytes" in stopped
    assert "partial" in log.read_text() and "UNSTOPPED" not in log.read_text()


def test_logged_command_preserves_environment_and_actual_exit(tmp_path):
    log = tmp_path / "console.log"
    exit_code, stopped = native.run_logged(
        [sys.executable, "-c", "import os,sys; print(os.environ['ARGUS_TEST_VALUE']); sys.exit(5)"],
        root=tmp_path, log=log, timeout=5, env={**os.environ, "ARGUS_TEST_VALUE": "expected"},
    )
    assert exit_code == 5 and not stopped
    assert log.read_text().strip() == "expected"


@pytest.mark.parametrize("size,exceeds", [(1024, False), (1025, True)])
def test_logged_output_limit_is_inclusive_and_checked_after_exit(tmp_path, monkeypatch, size, exceeds):
    assert native.MAX_CONSOLE_BYTES == 32 * 1024 * 1024
    monkeypatch.setattr(native, "MAX_CONSOLE_BYTES", 1024)
    launch = native.subprocess.Popen

    def finished(*args, **kwargs):
        process = launch(*args, **kwargs)
        process.wait(timeout=5)
        return process

    monkeypatch.setattr(native.subprocess, "Popen", finished)
    exit_code, stopped = native.run_logged(
        [sys.executable, "-c", f"import sys; sys.stdout.write('x'*{size})"],
        root=tmp_path, log=tmp_path / "console.log", timeout=5,
    )
    assert exit_code == 0
    assert bool(stopped) == exceeds


@pytest.mark.parametrize("domain", ["pcb_design", "package_design"])
@pytest.mark.parametrize("failure", ["timeout", "output"])
def test_native_adapters_save_actual_stopped_exit_and_partial_logs(tmp_path, monkeypatch, domain, failure):
    import importlib

    adapter = importlib.import_module(f"argus_verticals.{domain}.native")
    script = "import time; print('partial',flush=True); "
    script += "print('x'*4096,flush=True); " if failure == "output" else ""
    script += "time.sleep(2); print('UNSTOPPED')"
    command = [sys.executable, "-c", script]
    monkeypatch.setattr(native, "MAX_CONSOLE_BYTES", 1024)
    original = adapter.run_logged

    def bounded(*args, **kwargs):
        assert kwargs["timeout"] == 180
        if failure == "timeout":
            kwargs["timeout"] = 0.15
        return original(*args, **kwargs)

    monkeypatch.setattr(adapter, "run_logged", bounded)
    output = tmp_path / "native"
    saved = []
    if domain == "pcb_design":
        monkeypatch.setattr(adapter, "steps", lambda *_: [("erc", command)])
        arguments = (tmp_path, {}, output)
        log = output / "erc.log"
    else:
        monkeypatch.setattr(adapter, "geometry", lambda *_: "// synthetic process test\n")
        monkeypatch.setattr(adapter, "arguments", lambda _: command)
        arguments = ({}, {"mesh_size_m": 1}, output)
        log = output / "gmsh.log"
    with pytest.raises(EvidenceError, match="seconds|bytes"):
        adapter.execute(*arguments, save=lambda rows: saved.append([dict(row) for row in rows]))
    assert saved[0][0]["exit_code"] is None
    assert saved[-1][0]["exit_code"] != 0 and saved[-1][0]["stop_reason"]
    assert "partial" in log.read_text() and "UNSTOPPED" not in log.read_text()


@pytest.mark.parametrize("failure", ["timeout", "output"])
def test_spice_adapter_preserves_original_budgets_and_stopped_exit(tmp_path, failure):
    from argus_verticals.hardware.spice.batch import run_batch

    script = "import time; print('partial',flush=True); "
    script += "print('x'*4096,flush=True); " if failure == "output" else ""
    script += "time.sleep(2); print('UNSTOPPED')"
    saved = []
    with pytest.raises(EvidenceError, match="seconds|bytes"):
        run_batch(
            [sys.executable, "-c", script], tmp_path, tmp_path, ("console.log",),
            timeout=0.15 if failure == "timeout" else 5, output_budget=1024,
            save=lambda row: saved.append(dict(row)),
        )
    assert saved[0]["exit_code"] is None and saved[-1]["exit_code"] != 0
    text = (tmp_path / "console.log").read_text()
    assert "partial" in text and "UNSTOPPED" not in text
