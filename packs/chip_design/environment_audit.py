"""Collect and validate EDA, PDK, FPGA, and compiler/runtime readiness.

Standalone; adapted from the Argus chip_design environment_audit and the curated tool registry helpers.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

REGISTRY_PATH = Path(__file__).resolve().parent / "references" / "specialized_tool_registry.json"
LEGACY_STATUSES = frozenset({"archived", "deprecated", "moved"})
STAGE_ORDER = (
    "definition",
    "architecture",
    "environment",
    "rtl",
    "verification",
    "ppa",
    "prototype",
    "benchmark",
    "signoff",
)
WORKFLOW_PROFILES: dict[str, tuple[str, ...]] = {
    "architecture": ("definition", "architecture"),
    "rtl": ("definition", "architecture", "environment", "rtl", "verification"),
    "verification": ("verification",),
    "control": ("verification",),
    "ppa": ("verification", "ppa"),
    "prototype": ("verification", "ppa", "prototype"),
    "benchmark": ("verification", "ppa", "benchmark"),
    "full": STAGE_ORDER,
}
# A custom workflow adds the transitive closure of these companions to its requested stages.
WORKFLOW_STAGE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "definition": (),
    "architecture": ("definition",),
    "environment": (),
    "rtl": ("architecture", "environment", "verification"),
    "verification": (),
    "ppa": ("verification",),
    "prototype": ("ppa",),
    "benchmark": ("ppa",),
    "signoff": STAGE_ORDER[:-1],
}

SCHEMA_VERSION = 1
DEFAULT_REPORT = Path("research/ENVIRONMENT_AUDIT.json")
DEFAULT_MARKDOWN = Path("research/ENVIRONMENT_AUDIT.md")

CAPABILITY_TOOL_BUNDLES: dict[str, tuple[tuple[str, ...], ...]] = {
    "simulation": (("verilator",), ("iverilog",)),
    "formal": (("symbiyosys", "yosys"),),
    "lint": (("verilator",), ("verible",), ("slang",)),
    "synthesis": (("yosys",), ("vivado",), ("quartus",)),
    "fpga": (("nextpnr", "yosys"), ("vivado",), ("quartus",)),
    "physical_design": (("openroad",), ("librelane",)),
    "signoff": (
        ("opensta", "klayout", "netgen"),
        ("openroad", "klayout", "netgen"),
        ("librelane",),
    ),
    "pdk": (("sky130",), ("ihp_sg13g2",), ("gf180mcu",)),
    "compiler_runtime": (
        ("gemmini",),
        ("tvm_vta",),
        ("buddy_mlir",),
        ("iree",),
        ("circt",),
        ("chisel",),
    ),
}
CAPABILITY_NAMES = tuple(CAPABILITY_TOOL_BUNDLES)
TOOL_EXECUTABLE_BUNDLES: dict[str, tuple[tuple[str, ...], ...]] = {
    "verilator": (("verilator",),),
    "iverilog": (("iverilog", "vvp"),),
    "verible": (("verible-verilog-lint",),),
    "slang": (("slang",),),
    "yosys": (("yosys",),),
    "symbiyosys": (("sby",),),
    "nextpnr": (
        ("nextpnr-ice40",),
        ("nextpnr-ecp5",),
        ("nextpnr-nexus",),
        ("nextpnr-himbaechel",),
    ),
    "vivado": (("vivado",),),
    "quartus": (("quartus_sh",),),
    "openroad": (("openroad",),),
    "librelane": (("librelane",),),
    "opensta": (("sta",), ("opensta",)),
    "klayout": (("klayout",),),
    "netgen": (("netgen",),),
}
DELIVERY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "rtl_ip": ("simulation", "lint", "synthesis"),
    "fpga": ("simulation", "lint", "synthesis", "fpga"),
    "gds": ("simulation", "lint", "synthesis", "physical_design", "signoff", "pdk"),
    "pre_tapeout": (
        "simulation",
        "formal",
        "lint",
        "synthesis",
        "physical_design",
        "signoff",
        "pdk",
    ),
    "tapeout": ("simulation", "formal", "lint", "synthesis", "physical_design", "signoff", "pdk"),
}


def resolve_workflow(profile: str, stages: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Effective stage order of a named profile, or of a custom profile's requested stages."""
    if profile != "custom":
        if profile not in WORKFLOW_PROFILES:
            raise ValueError(f"unknown workflow profile {profile!r}")
        return WORKFLOW_PROFILES[profile]
    if not stages or len(set(stages)) != len(stages) or not set(stages) <= set(STAGE_ORDER):
        raise ValueError("custom workflow stages must be a nonempty list of distinct known stages")
    selected = set(stages)
    while not (required := {need for stage in selected for need in WORKFLOW_STAGE_REQUIREMENTS[stage]}) <= selected:
        selected |= required
    return tuple(stage for stage in STAGE_ORDER if stage in selected)


def load_registry(path: Path | None = None) -> dict[str, Any]:
    source = path or REGISTRY_PATH
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise ValueError(f"invalid chip tool registry: {source}")
    return payload


def filter_entries(
    registry: dict[str, Any],
    *,
    categories: Iterable[str] = (),
    platforms: Iterable[str] = (),
    query: str = "",
    include_legacy: bool = False,
) -> list[dict[str, Any]]:
    wanted_categories = {str(value).strip().lower() for value in categories if str(value).strip()}
    wanted_platforms = {str(value).strip().lower() for value in platforms if str(value).strip()}
    needle = query.strip().lower()
    result: list[dict[str, Any]] = []
    for raw in registry.get("entries", []):
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status") or "active").strip().lower()
        if not include_legacy and status in LEGACY_STATUSES:
            continue
        entry_categories = {str(value).lower() for value in raw.get("categories", [])}
        entry_platforms = {str(value).lower() for value in raw.get("platforms", [])}
        if wanted_categories and not wanted_categories.intersection(entry_categories):
            continue
        if wanted_platforms and not wanted_platforms.intersection(entry_platforms):
            continue
        if needle:
            searchable = " ".join(
                [
                    str(raw.get("id") or ""),
                    str(raw.get("name") or ""),
                    str(raw.get("use_when") or ""),
                    " ".join(str(value) for value in raw.get("categories", [])),
                    " ".join(str(value) for value in raw.get("platforms", [])),
                ]
            ).lower()
            if needle not in searchable:
                continue
        result.append(raw)
    return result


def _completed(argv: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _probe_python_entries(
    entries: list[dict[str, Any]], target_python: str
) -> dict[str, dict[str, Any]]:
    mapping = {
        str(entry["id"]): {
            "imports": [str(value) for value in entry.get("python_imports", [])],
            "distributions": [str(value) for value in entry.get("distributions", [])],
        }
        for entry in entries
        if entry.get("python_imports") or entry.get("distributions")
    }
    if not mapping:
        return {}
    probe = r"""
import importlib.metadata, importlib.util, json, sys
mapping = json.loads(sys.argv[1])
out = {}
for key, spec in mapping.items():
    imports = spec.get("imports") or []
    dists = spec.get("distributions") or []
    found_imports = []
    for name in imports:
        try:
            if importlib.util.find_spec(name) is not None:
                found_imports.append(name)
        except (ImportError, ModuleNotFoundError, ValueError):
            pass
    version = ""
    distribution = ""
    for name in dists:
        try:
            version = importlib.metadata.version(name)
            distribution = name
            break
        except importlib.metadata.PackageNotFoundError:
            pass
    out[key] = {
        "found_imports": found_imports,
        "distribution": distribution,
        "version": version,
    }
print(json.dumps(out))
"""
    result = _completed([target_python, "-c", probe, json.dumps(mapping)])
    if result is None or result.returncode != 0:
        return {}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def probe_entries(
    registry: dict[str, Any],
    *,
    target_python: str,
    project_root: Path,
) -> list[dict[str, Any]]:
    entries = [entry for entry in registry.get("entries", []) if isinstance(entry, dict)]
    python_records = _probe_python_entries(entries, target_python)
    root = project_root.resolve()
    detected: list[dict[str, Any]] = []
    for entry in entries:
        entry_id = str(entry.get("id") or "")
        py = python_records.get(entry_id, {})
        executables: dict[str, str] = {}
        for name in entry.get("executables", []):
            path = shutil.which(name)
            if path:
                executables[name] = path
        env_vars = [name for name in entry.get("env_vars", []) if os.environ.get(name)]
        source_markers = [
            marker for marker in entry.get("source_markers", []) if (root / str(marker)).exists()
        ]
        found_imports = list(py.get("found_imports") or [])
        distribution = str(py.get("distribution") or "")
        available = bool(found_imports or distribution or executables or env_vars or source_markers)
        detectable = bool(
            entry.get("python_imports")
            or entry.get("distributions")
            or entry.get("executables")
            or entry.get("env_vars")
            or entry.get("source_markers")
        )
        detected.append(
            {
                "id": entry_id,
                "name": entry.get("name"),
                "status": entry.get("status", "active"),
                "categories": entry.get("categories", []),
                "platforms": entry.get("platforms", []),
                "available": available,
                "detectable": detectable,
                "version": str(py.get("version") or ""),
                "found_imports": found_imports,
                "distribution": distribution,
                "executables": executables,
                "env_vars": env_vars,
                "source_markers": source_markers,
            }
        )
    return detected


def render_catalog(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "No matching chip tools."
    lines = ["id\tstatus\tplatforms\tcategories\tname\tuse_when"]
    for entry in entries:
        lines.append(
            "\t".join(
                [
                    str(entry.get("id") or ""),
                    str(entry.get("status") or "active"),
                    ",".join(str(value) for value in entry.get("platforms", [])),
                    ",".join(str(value) for value in entry.get("categories", [])),
                    str(entry.get("name") or ""),
                    str(entry.get("use_when") or "").replace("\t", " ").replace("\n", " "),
                ]
            )
        )
    return "\n".join(lines)


def validate_registry(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    allowed_statuses = {"active", "maintenance", "experimental", *LEGACY_STATUSES}
    for index, entry in enumerate(registry.get("entries", [])):
        prefix = f"entries[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} is not an object")
            continue
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            errors.append(f"{prefix}.id is empty")
        elif entry_id in seen:
            errors.append(f"duplicate id: {entry_id}")
        seen.add(entry_id)
        for key in ("name", "official_url", "use_when"):
            if not str(entry.get(key) or "").strip():
                errors.append(f"{prefix}.{key} is empty")
        if not str(entry.get("official_url") or "").startswith("https://"):
            errors.append(f"{prefix}.official_url must be https")
        if not entry.get("categories"):
            errors.append(f"{prefix}.categories is empty")
        if not entry.get("platforms"):
            errors.append(f"{prefix}.platforms is empty")
        status = str(entry.get("status") or "active")
        if status not in allowed_statuses:
            errors.append(f"{prefix}.status is invalid: {status}")
    return errors


def _required_capabilities(
    level: str, profile: str, effective: tuple[str, ...],
) -> list[str]:
    if profile == "rtl" or (
        profile == "custom"
        and set(effective) & {"rtl", "verification"}
        and not set(effective) & {"ppa", "prototype", "benchmark", "signoff"}
    ):
        return ["simulation", "lint"]
    if profile == "custom" and not set(effective) & {"environment", "rtl", "verification", "ppa", "prototype", "benchmark", "signoff"}:
        return []
    return list(DELIVERY_REQUIREMENTS.get(level, ()))


def _first_line(text: str) -> str:
    return next((line.strip()[:500] for line in text.splitlines() if line.strip()), "")


def _scope(project_root: Path) -> dict[str, Any]:
    path = project_root / "design" / "CHIP_SCOPE.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: invalid chip scope: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _selected_pdk(scope: dict[str, Any], project_root: Path) -> str:
    target_path = project_root / "design" / "TARGET.json"
    try:
        target = json.loads(target_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        target = {}
    if not isinstance(target, dict):
        target = {}
    text = " ".join(
        str(value)
        for value in (
            scope.get("technology_or_board"),
            scope.get("target"),
            target.get("target"),
            target.get("technology"),
            target.get("pdk"),
        )
        if value is not None
    ).casefold()
    aliases = {
        "sky130": ("sky130", "skywater"),
        "ihp_sg13g2": ("ihp", "sg13g2"),
        "gf180mcu": ("gf180", "globalfoundries 180"),
    }
    matches = [
        entry_id
        for entry_id, needles in aliases.items()
        if any(needle in text for needle in needles)
    ]
    return matches[0] if len(matches) == 1 else ""


def _normalize_pdk_detection(
    entries: list[dict[str, Any]],
    registry: dict[str, Any],
) -> None:
    """Do not treat a generic PDK_ROOT variable as proving every open PDK."""
    specs = {
        str(entry.get("id") or ""): entry
        for entry in registry.get("entries", [])
        if isinstance(entry, dict)
    }
    for record in entries:
        entry_id = str(record.get("id") or "")
        if entry_id not in {"sky130", "ihp_sg13g2", "gf180mcu"}:
            continue
        spec = specs.get(entry_id, {})
        roots = [
            Path(value).expanduser()
            for name in spec.get("env_vars", [])
            if (value := os.environ.get(str(name)))
        ]
        markers = [Path(str(value)) for value in spec.get("source_markers", [])]
        env_matches = [
            str(root / marker)
            for root in roots
            for marker in markers
            if (root / marker).exists()
        ]
        project_matches = list(record.get("source_markers") or [])
        record["pdk_paths"] = sorted({*env_matches, *project_matches})
        record["available"] = bool(record["pdk_paths"])


def _normalize_command_detection(entries: list[dict[str, Any]]) -> None:
    """Require the exact command set needed by each EDA tool capability."""
    for record in entries:
        entry_id = str(record.get("id") or "")
        bundles = TOOL_EXECUTABLE_BUNDLES.get(entry_id)
        if not bundles:
            continue
        found = set((record.get("executables") or {}).keys())
        satisfied = [
            list(bundle) for bundle in bundles if all(command in found for command in bundle)
        ]
        record["command_bundles"] = satisfied
        record["available"] = bool(satisfied)


def _capability(
    by_id: dict[str, dict[str, Any]],
    bundles: tuple[tuple[str, ...], ...],
) -> dict[str, Any]:
    satisfied = [
        list(bundle)
        for bundle in bundles
        if all(by_id.get(tool_id, {}).get("available") for tool_id in bundle)
    ]
    available = sorted(
        {
            tool_id
            for bundle in bundles
            for tool_id in bundle
            if by_id.get(tool_id, {}).get("available")
        }
    )
    return {
        "ready": bool(satisfied),
        "available_tools": available,
        "satisfied_bundles": satisfied,
        "acceptable_bundles": [list(bundle) for bundle in bundles],
    }


def _safe_output_path(project_root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe project-relative output path: {relative}")
    root = project_root.resolve()
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"output path must not be a symlink: {relative}")
    if not path.parent.resolve().is_relative_to(root):
        raise ValueError(f"output path resolves outside project: {relative}")
    return path


def _project_signals(project_root: Path) -> dict[str, list[str]]:
    groups = {
        "instructions": ("AGENTS.md", "CONTRIBUTING.md", "README.md", "Makefile", "justfile"),
        "containers": ("Dockerfile", "docker-compose.yml", "compose.yml", "flake.nix"),
        "flows": ("OpenLane", "librelane", "openroad", "flow", "scripts"),
        "hardware": ("rtl", "src", "tb", "formal", "constraints", "fpga", "physical"),
        "compiler": ("chipyard", "gemmini", "tvm", "mlir", "runtime", "software"),
    }
    return {
        group: [name for name in names if (project_root / name).exists()]
        for group, names in groups.items()
    }


def _safe_project_marker(value: object) -> str | None:
    """Return a portable relative marker, never a host path.

    ``Path('/pdks/...').is_absolute()`` is false for ``WindowsPath`` because it
    has no drive, even though it is an absolute POSIX path and must not be
    persisted in a shareable audit. Check both path grammars so collecting on
    one OS cannot leak a path written for the other.
    """
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if posix.is_absolute() or windows.is_absolute() or windows.root:
        return None
    if ".." in posix.parts or ".." in windows.parts:
        return None
    return raw


def collect(
    project_root: Path,
    *,
    target_python: str,
    required: list[str],
    workflow_profile: str = "full",
    workflow_stages: tuple[str, ...] = (),
) -> dict[str, Any]:
    root = project_root.resolve()
    registry = load_registry()
    errors = validate_registry(registry)
    if errors:
        raise ValueError("invalid chip tool registry: " + "; ".join(errors))
    entries = probe_entries(registry, target_python=target_python, project_root=root)
    _normalize_command_detection(entries)
    _normalize_pdk_detection(entries, registry)
    by_id = {str(entry.get("id") or ""): entry for entry in entries}
    scope = _scope(root)
    level = str(scope.get("delivery_level") or "").strip()
    if level not in DELIVERY_REQUIREMENTS:
        raise ValueError(f"unsupported or missing delivery_level: {level!r}")
    effective_stages = resolve_workflow(workflow_profile, workflow_stages)
    inferred = _required_capabilities(level, workflow_profile, effective_stages)
    selected = list(dict.fromkeys([*inferred, *required]))
    invalid = sorted(set(selected) - set(CAPABILITY_NAMES))
    if invalid:
        raise ValueError(f"unknown required capabilities: {', '.join(invalid)}")

    capabilities: dict[str, dict[str, Any]] = {}
    for name, bundles in CAPABILITY_TOOL_BUNDLES.items():
        capabilities[name] = _capability(by_id, bundles)
    selected_pdk = _selected_pdk(scope, root)
    if "pdk" in selected and not selected_pdk:
        raise ValueError(
            "GDS/pre-tapeout/tapeout scope must name exactly one supported target PDK "
            "(sky130, ihp_sg13g2, or gf180mcu)"
        )
    if selected_pdk:
        capabilities["pdk"] = _capability(by_id, ((selected_pdk,),))
    version = _completed([target_python, "--version"], timeout=20.0)

    return {
        "schema_version": SCHEMA_VERSION,
        "collected_at": datetime.now(UTC).isoformat(),
        "project_root": ".",
        "delivery_level": level,
        "workflow_profile": workflow_profile,
        "workflow_stages": list(effective_stages),
        "selected_pdk": selected_pdk,
        "required_capabilities": selected,
        "ready": all(capabilities[name]["ready"] for name in selected),
        "capabilities": capabilities,
        "detected_tools": [
            {
                "id": record.get("id"),
                "name": record.get("name"),
                "available": bool(record.get("available")),
                "version": record.get("version", ""),
                "commands": sorted((record.get("executables") or {}).keys()),
                "environment_variables": sorted(record.get("env_vars") or []),
                "project_markers": sorted(
                    marker
                    for value in record.get("source_markers") or []
                    if (marker := _safe_project_marker(value)) is not None
                ),
            }
            for record in entries
        ],
        "project_signals": _project_signals(root),
        "runtime": {
            "platform": platform.platform(),
            "python": Path(target_python).name,
            "python_version": _first_line(version.stdout or version.stderr) if version else "",
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Chip design environment readiness",
        "",
        f"- Collected: `{payload.get('collected_at', '')}`",
        f"- Delivery level: `{payload.get('delivery_level') or 'unset'}`",
        f"- Workflow profile: `{payload.get('workflow_profile', 'full')}`",
        f"- Target Python: `{payload.get('runtime', {}).get('python', '')}`",
        f"- Ready: `{str(bool(payload.get('ready'))).lower()}`",
        "",
        "| Capability | Required | Ready | Available tools |",
        "| --- | --- | --- | --- |",
    ]
    required = set(payload.get("required_capabilities") or [])
    for name, result in payload.get("capabilities", {}).items():
        lines.append(
            f"| `{name}` | {'yes' if name in required else 'no'} | "
            f"{'yes' if result.get('ready') else 'no'} | "
            f"{', '.join(str(value) for value in result.get('available_tools', [])) or '—'} |"
        )
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def check(
    project_root: Path,
    report: Path = DEFAULT_REPORT,
    *,
    target_python: str | None = None,
    workflow_profile: str = "full",
    workflow_stages: tuple[str, ...] = (),
) -> tuple[bool, list[str]]:
    path = project_root / report
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"{path}: invalid or missing readiness report: {exc}"]
    if not isinstance(payload, dict):
        return False, [f"{path}: expected a JSON object"]
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("project_root") != ".":
        errors.append("project_root must use the sanitized project-relative marker '.'")
    try:
        scope = _scope(project_root.resolve())
    except ValueError as exc:
        errors.append(str(exc))
        scope = {}
    level = str(payload.get("delivery_level") or "")
    current_level = str(scope.get("delivery_level") or "")
    if level != current_level or level not in DELIVERY_REQUIREMENTS:
        errors.append(f"delivery_level does not match current scope: {level!r}")
    effective_stages = resolve_workflow(workflow_profile, workflow_stages)
    expected_required = _required_capabilities(current_level, workflow_profile, effective_stages)
    if payload.get("workflow_profile", "full") != workflow_profile:
        errors.append("workflow_profile does not match the active task")
    if (
        workflow_profile == "custom" or "workflow_stages" in payload
    ) and payload.get("workflow_stages") != list(effective_stages):
        errors.append("workflow_stages do not match the active task")
    reported_required = payload.get("required_capabilities")
    if not isinstance(reported_required, list):
        reported_required = []
        errors.append("required_capabilities must be a list")
    invalid_required = sorted(set(reported_required) - set(CAPABILITY_NAMES))
    if invalid_required:
        errors.append(f"unknown required capabilities: {', '.join(invalid_required)}")
    if not set(expected_required).issubset(reported_required):
        errors.append(
            "required_capabilities omit current scope requirements: "
            f"required {expected_required!r}"
        )
    expected_pdk = _selected_pdk(scope, project_root.resolve())
    if "pdk" in expected_required and not expected_pdk:
        errors.append(
            "current GDS/pre-tapeout/tapeout scope does not name one supported target PDK"
        )
    if payload.get("selected_pdk", "") != expected_pdk:
        errors.append("selected_pdk does not match current target")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict):
        errors.append("capabilities must be an object")
        capabilities = {}
    runtime = payload.get("runtime")
    if not isinstance(runtime, dict) or not str(runtime.get("python") or ""):
        errors.append("runtime.python metadata is required")
    trusted_target_python = target_python or sys.executable
    try:
        registry = load_registry()
        registry_errors = validate_registry(registry)
        if registry_errors:
            raise ValueError("; ".join(registry_errors))
        fresh_entries = probe_entries(
            registry,
            target_python=trusted_target_python,
            project_root=project_root.resolve(),
        )
        _normalize_command_detection(fresh_entries)
        _normalize_pdk_detection(fresh_entries, registry)
        fresh_by_id = {
            str(record.get("id") or ""): record for record in fresh_entries
        }
    except (OSError, ValueError) as exc:
        errors.append(f"fresh tool probe failed: {exc}")
        fresh_by_id = {}
    for name in reported_required:
        if name not in CAPABILITY_TOOL_BUNDLES:
            continue
        bundles = CAPABILITY_TOOL_BUNDLES[name]
        if name == "pdk" and expected_pdk:
            bundles = ((expected_pdk,),)
        fresh = _capability(fresh_by_id, bundles)
        if not fresh["ready"]:
            errors.append(f"fresh probe found required capability unavailable: {name}")
        result = capabilities.get(name)
        if not isinstance(result, dict) or not result.get("ready"):
            errors.append(f"required capability is not ready: {name}")
        elif result.get("satisfied_bundles") != fresh["satisfied_bundles"]:
            errors.append(f"required capability does not match fresh probe: {name}")
    if bool(payload.get("ready")) != (not errors):
        errors.append("ready does not match required capability results")
    return not errors, errors


def _catalog(args: argparse.Namespace) -> int:
    registry = load_registry()
    errors = validate_registry(registry)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    if args.list_categories:
        categories = sorted(
            {str(category) for entry in registry["entries"] for category in entry.get("categories", [])}
        )
        print("\n".join(categories))
        return 0
    entries = filter_entries(
        registry,
        categories=args.category,
        platforms=args.platform,
        query=args.query,
        include_legacy=args.include_legacy,
    )
    print(render_catalog(entries))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chip-design-environment-audit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--project-root", default=".")
    collect_parser.add_argument("--target-python", default=sys.executable)
    collect_parser.add_argument("--require", action="append", default=[])
    collect_parser.add_argument("--workflow-profile", choices=(*WORKFLOW_PROFILES, "custom"), default="full")
    collect_parser.add_argument("--workflow-stages", nargs="+", default=[])
    collect_parser.add_argument("--output", default=str(DEFAULT_REPORT))
    collect_parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))

    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--project-root", default=".")
    check_parser.add_argument("--report", default=str(DEFAULT_REPORT))
    check_parser.add_argument("--target-python", default=None)
    check_parser.add_argument("--workflow-profile", choices=(*WORKFLOW_PROFILES, "custom"), default="full")
    check_parser.add_argument("--workflow-stages", nargs="+", default=[])

    catalog_parser = subparsers.add_parser("catalog")
    catalog_parser.add_argument("--category", action="append", default=[])
    catalog_parser.add_argument("--platform", action="append", default=[])
    catalog_parser.add_argument("--query", default="")
    catalog_parser.add_argument("--include-legacy", action="store_true")
    catalog_parser.add_argument("--list-categories", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "catalog":
        return _catalog(args)
    root = Path(args.project_root).resolve()
    if args.workflow_stages and args.workflow_profile != "custom":
        parser.error("--workflow-stages requires --workflow-profile custom")
    try:
        effective_stages = resolve_workflow(args.workflow_profile, tuple(args.workflow_stages))
    except ValueError as exc:
        parser.error(str(exc))
    if args.command == "collect":
        try:
            payload = collect(
                root,
                target_python=str(Path(args.target_python).expanduser()),
                required=list(args.require),
                workflow_profile=args.workflow_profile,
                workflow_stages=effective_stages,
            )
        except ValueError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2
        output = Path(args.output)
        markdown = Path(args.markdown)
        _write(
            _safe_output_path(root, output),
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
        )
        _write(_safe_output_path(root, markdown), render_markdown(payload))
        print(f"wrote {output} and {markdown}; ready={str(payload['ready']).lower()}")
        return 0 if payload["ready"] else 1
    ok, errors = check(
        root,
        Path(args.report),
        target_python=args.target_python,
        workflow_profile=args.workflow_profile,
        workflow_stages=effective_stages,
    )
    if not ok:
        print("\n".join(f"FAIL: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"OK: validated {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
