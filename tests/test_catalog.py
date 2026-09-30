"""Store metadata: manifests, the catalog generator, and the release archives.

The Argus Vertical Store installs a vertical by downloading
``<name>-<version>.zip`` from a GitHub Release of this repository, checking its
sha256 against ``catalog.json``, extracting it under a private site directory
next to a synthetic ``argus_verticals/__init__.py``, and importing
``argus_verticals.<name>.stages`` from there. These tests pin the producer side
of that contract:

* every ``vertical.json`` validates against ``catalog/vertical.schema.json`` and
  agrees with ``pyproject.toml`` (same names, same module targets);
* ``requires`` and ``shared`` are exactly what the vertical's code imports
  (plus catalog skill parents), and ``python_requirements`` covers every
  unguarded third-party import of the bundle;
* the committed ``catalog.json`` is current and deterministic;
* a release build yields one zip per vertical whose members are exactly the
  vertical's trees, whose digests match, and whose rebuild is byte-identical;
* every archive extracts to an importable ``argus_verticals.<name>.stages``
  (this last test needs Argus and skips without it).

Everything but the last test is standard library plus pytest; ``jsonschema``
adds a second, full validation when installed.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "argus_verticals"
SCHEMA_PATH = REPO_ROOT / "catalog" / "vertical.schema.json"
CATALOG_PATH = REPO_ROOT / "catalog.json"
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_catalog.py"
ENTRY_POINT_GROUP = "argus.verticals"
RELEASE_TAG = "v9.9.9-test"

# Import name -> distribution name where they differ.
IMPORT_TO_DISTRIBUTION = {"sklearn": "scikit-learn", "skrf": "scikit-rf", "yaml": "PyYAML"}
STDLIB = set(sys.stdlib_module_names)
# Imports that are not pip requirements of a vertical: the Argus framework
# (``argus``; its pre-rename spelling ``argus_skill`` is deliberately absent so
# a stray old import is reported as an undeclared requirement) and this package.
NOT_THIRD_PARTY = frozenset({"argus", "argus_verticals"})


def _load_generator():
    spec = importlib.util.spec_from_file_location("build_catalog", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


build_catalog = _load_generator()
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
PYPROJECT = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
ENTRY_POINTS: dict[str, str] = dict(PYPROJECT["project"]["entry-points"][ENTRY_POINT_GROUP])
MANIFEST_PATHS: dict[str, Path] = {
    path.parent.relative_to(REPO_ROOT).as_posix(): path
    for path in sorted(PACKAGE_ROOT.rglob("vertical.json"))
    if "__pycache__" not in path.parts
}
MANIFESTS: dict[str, dict] = {}
for _path in MANIFEST_PATHS.values():
    _manifest = json.loads(_path.read_text(encoding="utf-8"))
    MANIFESTS[_manifest["name"]] = _manifest
NAMES = sorted(MANIFESTS)
ALL_VERTICAL_PATHS: dict[str, list[str]] = {name: m["paths"] for name, m in MANIFESTS.items()}
PYPROJECT_REQUIREMENTS: set[str] = {
    requirement
    for extra in PYPROJECT["project"]["optional-dependencies"].values()
    for requirement in extra
}

@pytest.mark.parametrize("raw", ["hardware/digital_circuit", ("hardware",), ("Hardware", "digital_circuit"), ("hardware", 7)])
def test_invalid_provider_routing_path_is_rejected(tmp_path, raw):
    source = tmp_path / "stages.py"
    source.write_text(
        "VERTICAL_PURPOSE = 'test purpose'\nVERTICAL_SKILL_PARENTS = ()\n"
        f"ARGUS_VERTICAL_API_VERSION = 1\nVERTICAL_ROUTING_PATH = {raw!r}\n"
    )
    with pytest.raises(build_catalog.CatalogError, match="VERTICAL_ROUTING_PATH"):
        build_catalog.read_plugin_attributes(source)


def test_catalog_derives_specialty_path_separately_from_skill_parents():
    attributes = build_catalog.read_plugin_attributes(
        PACKAGE_ROOT / "digital_circuit/verification/stages.py"
    )
    assert attributes["routing_path"] == ["hardware", "digital_circuit", "verification"]
    assert attributes["skill_parents"] == ["digital_circuit"]


def _module_dir(module: str) -> Path:
    return REPO_ROOT.joinpath(*module.split(".")[:-1])


def _requirement_name(requirement: str) -> str:
    match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
    assert match, f"unparsable requirement {requirement!r}"
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def _import_distribution(import_name: str) -> str:
    return _requirement_name(IMPORT_TO_DISTRIBUTION.get(import_name, import_name))


def _python_files(trees: list[str], exclude_nested_of: list[str]) -> list[Path]:
    files: list[Path] = []
    for tree in trees:
        nested = tuple(f"{other}/" for other in exclude_nested_of if other.startswith(f"{tree}/"))
        for path in sorted((REPO_ROOT / tree).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if nested and rel.startswith(nested):
                continue
            files.append(path)
    return files


def _imports(path: Path) -> list[tuple[str, bool]]:
    """(dotted module, guarded) for every import statement in the file.

    Guarded means inside ``try``, ``if``, or a function body: the module works
    when the import fails or is never reached.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, bool]] = []

    def visit(node: ast.AST, guarded: bool) -> None:
        for child in ast.iter_child_nodes(node):
            child_guarded = guarded or isinstance(
                node, (ast.Try, ast.If, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            if isinstance(child, ast.Import):
                for alias in child.names:
                    found.append((alias.name, child_guarded))
            elif isinstance(child, ast.ImportFrom) and child.level == 0 and child.module:
                found.append((child.module, child_guarded))
            visit(child, child_guarded)

    visit(tree, False)
    return found


def _other_paths(name: str) -> list[str]:
    return [p for other, paths in ALL_VERTICAL_PATHS.items() if other != name for p in paths]


def _classify_argus_verticals_import(dotted: str, name: str) -> tuple[str, str] | None:
    """('vertical', <name>) or ('shared', <dir>) for an ``argus_verticals.…`` import."""
    parts = dotted.split(".")
    if parts[0] != "argus_verticals" or len(parts) < 2:
        return None
    # Longest vertical directory that is a prefix of the import.
    best: tuple[str, str] | None = None
    best_len = 0
    for vertical, paths in ALL_VERTICAL_PATHS.items():
        for path in paths:
            components = path.split("/")
            if parts[: len(components)] == components and len(components) > best_len:
                best, best_len = ("vertical", vertical), len(components)
    if best is not None:
        return None if best[1] == name else best
    for shared in {s for m in MANIFESTS.values() for s in m["shared"]}:
        components = shared.split("/")
        if parts[: len(components)] == components:
            return ("shared", shared)
    raise AssertionError(f"{dotted}: neither a catalog vertical nor a declared shared helper")


# --------------------------------------------------------------------------- #
# Manifests
# --------------------------------------------------------------------------- #


def test_schema_is_a_valid_draft_2020_12_schema() -> None:
    assert SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_every_stages_module_has_a_manifest_and_vice_versa() -> None:
    stage_dirs = {
        p.parent.relative_to(REPO_ROOT).as_posix()
        for p in PACKAGE_ROOT.rglob("stages.py")
        if "__pycache__" not in p.parts
    }
    assert stage_dirs == set(MANIFEST_PATHS), (
        f"stages.py without vertical.json: {sorted(stage_dirs - set(MANIFEST_PATHS))}; "
        f"vertical.json without stages.py: {sorted(set(MANIFEST_PATHS) - stage_dirs)}"
    )
    assert len(MANIFESTS) == len(MANIFEST_PATHS), "two manifests share a name"


def test_manifests_and_pyproject_declare_the_same_verticals() -> None:
    assert set(MANIFESTS) == set(ENTRY_POINTS)
    for name, target in ENTRY_POINTS.items():
        assert MANIFESTS[name]["module"] == target, f"{name}: module differs from the entry point"


@pytest.mark.parametrize("name", NAMES)
def test_manifest_matches_the_schema(name: str) -> None:
    manifest = MANIFESTS[name]
    build_catalog.validate_against_schema(manifest, SCHEMA, name)
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator(SCHEMA).validate(manifest)


@pytest.mark.parametrize("name", NAMES)
def test_manifest_points_at_its_own_directory(name: str) -> None:
    manifest = MANIFESTS[name]
    own = _module_dir(manifest["module"])
    assert MANIFEST_PATHS[own.relative_to(REPO_ROOT).as_posix()].parent == own
    assert manifest["paths"][0] == own.relative_to(REPO_ROOT).as_posix()
    for tree in manifest["paths"] + manifest["shared"]:
        assert (REPO_ROOT / tree).is_dir(), f"{name}: {tree} is not a directory"
    assert "purpose" not in manifest, "the purpose lives in stages.py only"
    assert manifest["version"] and manifest["min_argus"]


@pytest.mark.parametrize("name", NAMES)
def test_requires_and_shared_match_the_imports(name: str) -> None:
    manifest = MANIFESTS[name]
    imported_verticals: set[str] = set()
    imported_shared: set[str] = set()
    evidence: dict[str, str] = {}
    for path in _python_files(manifest["paths"], _other_paths(name)):
        for dotted, _guarded in _imports(path):
            kind_target = _classify_argus_verticals_import(dotted, name)
            if kind_target is None:
                continue
            kind, target = kind_target
            (imported_verticals if kind == "vertical" else imported_shared).add(target)
            evidence.setdefault(target, f"{path.relative_to(REPO_ROOT)}: {dotted}")

    stages = _module_dir(manifest["module"]) / "stages.py"
    parents = set(build_catalog.read_plugin_attributes(stages)["skill_parents"])
    catalog_parents = parents & set(MANIFESTS)
    expected_requires = imported_verticals | catalog_parents
    assert set(manifest["requires"]) == expected_requires, (
        f"{name}: requires {sorted(manifest['requires'])} but the code imports "
        f"{sorted(imported_verticals)} and the catalog skill parents are {sorted(catalog_parents)} "
        f"(evidence: {evidence})"
    )
    assert set(manifest["shared"]) == imported_shared, (
        f"{name}: shared {sorted(manifest['shared'])} but the code imports {sorted(imported_shared)}"
    )
    assert name not in manifest["requires"]


def test_shared_helpers_are_not_verticals() -> None:
    for name, manifest in MANIFESTS.items():
        for shared in manifest["shared"]:
            for other, paths in ALL_VERTICAL_PATHS.items():
                for path in paths:
                    assert shared != path and not shared.startswith(f"{path}/"), (
                        f"{name}: shared {shared} is inside vertical {other}; use requires"
                    )
            assert not (REPO_ROOT / shared / "stages.py").exists()


@pytest.mark.parametrize("name", NAMES)
def test_python_requirements_match_the_third_party_imports(name: str) -> None:
    manifest = MANIFESTS[name]
    unguarded: dict[str, str] = {}
    anywhere: set[str] = set()
    for path in _python_files(manifest["paths"] + manifest["shared"], _other_paths(name)):
        for dotted, guarded in _imports(path):
            top = dotted.split(".")[0]
            if top in STDLIB or top == "__future__" or top in NOT_THIRD_PARTY:
                continue
            distribution = _import_distribution(top)
            anywhere.add(distribution)
            if not guarded:
                unguarded.setdefault(distribution, f"{path.relative_to(REPO_ROOT)}: {dotted}")

    required = {_requirement_name(r) for r in manifest["python_requirements"]}
    optional = {_requirement_name(r) for r in manifest.get("optional_python_requirements", [])}
    assert not (required & optional), f"{name}: a requirement is both required and optional"
    missing = set(unguarded) - required
    assert not missing, (
        f"{name}: unguarded third-party imports not in python_requirements: "
        f"{ {m: unguarded[m] for m in sorted(missing)} }"
    )
    assert not (optional & set(unguarded)), (
        f"{name}: optional requirements imported unguarded: {sorted(optional & set(unguarded))}"
    )
    unused = (required | optional) - anywhere
    assert not unused, f"{name}: declared requirements nothing imports: {sorted(unused)}"
    for requirement in manifest["python_requirements"] + manifest.get("optional_python_requirements", []):
        assert requirement in PYPROJECT_REQUIREMENTS, (
            f"{name}: {requirement!r} is not spelled exactly like an extra in pyproject.toml"
        )


def test_purpose_zh_lines_are_distinct() -> None:
    lines = {name: m["purpose_zh"] for name, m in MANIFESTS.items() if "purpose_zh" in m}
    assert len(set(lines.values())) == len(lines), "two verticals share a purpose_zh"


@pytest.mark.parametrize("name", NAMES)
def test_every_vertical_readme_names_the_manifest(name: str) -> None:
    readme = _module_dir(MANIFESTS[name]["module"]) / "README.md"
    assert "vertical.json" in readme.read_text(encoding="utf-8"), f"{name}: README.md does not mention vertical.json"


# --------------------------------------------------------------------------- #
# The generator and the committed catalog
# --------------------------------------------------------------------------- #


def test_generator_reads_plugin_attributes_without_importing(tmp_path: Path) -> None:
    good = tmp_path / "stages.py"
    good.write_text(
        'ARGUS_VERTICAL_API_VERSION = 1\n'
        'VERTICAL_PURPOSE = (\n    "one line "\n    "in two parts"\n)\n'
        'VERTICAL_SKILLS = object()\n'
        'VERTICAL_SKILL_PARENTS: tuple[str, ...] = ("digital_circuit",)\n',
        encoding="utf-8",
    )
    attributes = build_catalog.read_plugin_attributes(good)
    assert attributes == {
        "purpose": "one line in two parts",
        "skill_parents": ["digital_circuit"],
        "has_skills": True,
        "api_version": 1,
        "routing_path": [],
    }

    bad = tmp_path / "bad.py"
    bad.write_text(
        'ARGUS_VERTICAL_API_VERSION = 1\n'
        'VERTICAL_PURPOSE = "x" + y\n'
        'VERTICAL_SKILL_PARENTS: tuple[str, ...] = ()\n',
        encoding="utf-8",
    )
    with pytest.raises(build_catalog.CatalogError, match="VERTICAL_PURPOSE must be a literal"):
        build_catalog.read_plugin_attributes(bad)

    missing = tmp_path / "missing.py"
    missing.write_text('VERTICAL_PURPOSE = "p"\n', encoding="utf-8")
    with pytest.raises(build_catalog.CatalogError, match="VERTICAL_SKILL_PARENTS"):
        build_catalog.read_plugin_attributes(missing)


def test_committed_catalog_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--check"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr


def test_committed_catalog_has_the_store_shape() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert catalog["schema"] == 1
    assert catalog["generated_from"]["repo"] == "Argus-AiTeam/argus-verticals"
    assert re.fullmatch(r"[0-9a-f]{40}|unknown", catalog["generated_from"]["commit"])
    assert set(catalog["verticals"]) == set(ENTRY_POINTS)
    for name, entry in catalog["verticals"].items():
        manifest = MANIFESTS[name]
        for key, value in manifest.items():
            assert entry[key] == value, f"{name}: catalog {key} differs from vertical.json"
        stages = _module_dir(manifest["module"]) / "stages.py"
        attributes = build_catalog.read_plugin_attributes(stages)
        assert entry["purpose"] == attributes["purpose"]
        assert entry["skill_parents"] == attributes["skill_parents"]
        assert entry["has_skills"] is attributes["has_skills"]
        assert entry["has_skills"] == (_module_dir(manifest["module"]) / "skills").is_dir()
        assert entry["api_version"] == 1
        assert isinstance(entry["size_bytes"], int) and entry["size_bytes"] > 0
        assert "archive" not in entry, "the committed index carries no download URLs"
    # Deterministic serialisation: sorted keys, two-space indent, trailing newline.
    text = CATALOG_PATH.read_text(encoding="utf-8")
    assert text == build_catalog.dumps(catalog)


def test_index_build_is_deterministic_and_check_ignores_the_commit() -> None:
    first = build_catalog.build_index()
    second = build_catalog.build_index()
    assert first == second
    assert build_catalog.check_committed(first) == []
    first["generated_from"]["commit"] = "0" * 40
    assert build_catalog.check_committed(first) == [], "--check must not depend on HEAD"
    first["verticals"][NAMES[0]]["version"] = "99.0.0"
    diffs = build_catalog.check_committed(first)
    assert diffs and NAMES[0] in diffs[0] and "version" in diffs[0]


def test_generator_rejects_a_manifest_that_disagrees_with_pyproject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bogus = tmp_path / "pyproject.toml"
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    bogus.write_text(text.replace('quant = "argus_verticals.quant.stages"', 'quant = "argus_verticals.quant.other"'), encoding="utf-8")
    monkeypatch.setattr(build_catalog, "PYPROJECT_PATH", bogus)
    with pytest.raises(build_catalog.CatalogError, match="quant: vertical.json module"):
        build_catalog.build_index()


# --------------------------------------------------------------------------- #
# Release archives
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def release(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    dist = tmp_path_factory.mktemp("dist")
    index = build_catalog.build_index()
    payload = build_catalog.build_release(index, RELEASE_TAG, dist)
    return dist, payload


def _expected_members(name: str) -> list[str]:
    """Independent walk: every file under paths+shared, minus caches and nested verticals."""
    manifest = MANIFESTS[name]
    members: set[str] = set()
    for tree in manifest["paths"] + manifest["shared"]:
        nested = tuple(f"{other}/" for other in _other_paths(name) if other.startswith(f"{tree}/"))
        for path in (REPO_ROOT / tree).rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if nested and rel.startswith(nested):
                continue
            members.add(rel)
    return sorted(members)


@pytest.mark.parametrize("vertical,stage,directory,reference", [
    ("analog_mixed_signal", "simulation", "analog", "run_reference"),
    ("analog_mixed_signal", "simulation", "analog", "run_robustness_reference"),
    ("rf_design", "analysis", "rf", "run_reference"),
    ("pcb_design", "verification", "pcb", "run_reference"),
    ("pcb_design", "verification", "pcb", "run_zone_reference"),
    ("package_design", "thermal", "package", "run_reference"),
    ("package_design", "thermal", "package", "run_convection_reference"),
    ("power_electronics", "simulation", "power", "run_reference"),
    ("power_electronics", "simulation", "power", "run_robustness_reference"),
])
def test_hardware_archive_executes_and_checks_in_fresh_store_only_processes(release: tuple[Path, dict], tmp_path: Path, vertical: str, stage: str, directory: str, reference: str) -> None:
    import os
    import shutil
    import sysconfig
    import venv

    import argus

    if vertical in {"analog_mixed_signal", "power_electronics"} and shutil.which("ngspice") is None:
        pytest.skip("ngspice is required for the archive-only executable check")
    if vertical == "pcb_design" and shutil.which("kicad-cli") is None:
        pytest.skip("KiCad 9 is required for the archive-only executable check")
    if vertical == "package_design" and any(shutil.which(tool) is None for tool in ("gmsh", "ccx")):
        pytest.skip("Gmsh and CalculiX are required for the archive-only executable check")
    dist, payload = release
    local_catalog = json.loads(json.dumps(payload))
    for entry in local_catalog["verticals"].values():
        entry["archive"]["url"] = (dist / entry["archive"]["file"]).as_uri()
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(local_catalog), encoding="utf-8")
    dependency_paths = sorted({sysconfig.get_path("purelib"), sysconfig.get_path("platlib")})
    isolated = tmp_path / "interpreter"
    venv.EnvBuilder(with_pip=False).create(isolated)
    python = isolated / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    site_packages = Path(subprocess.check_output(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        text=True,
    ).strip())
    # Share dependency wheels without executing the parent's editable-project .pth files.
    (site_packages / "dependency-wheels.pth").write_text("\n".join(dependency_paths) + "\n", encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if not key.startswith("ARGUS_SKILL_")}
    env.update({
        "ARGUS_SKILL_HOME": str(tmp_path / "home"),
        "ARGUS_VERTICAL_CATALOG": str(catalog_path),
        "PYTHONPATH": str(Path(argus.__file__).resolve().parents[1]),
    })
    script = """
import json
import importlib
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from argus.verticals import store
from argus.verticals._base import load_vertical_contract

vertical, stage, directory, reference = sys.argv[1:]
installed = store.install(vertical, wait=True)
assert installed["status"] == "done", installed
load_vertical_contract(vertical)
stages = importlib.import_module(f"argus_verticals.{vertical}.stages")
prepare_reference = importlib.import_module(f"argus_verticals.{vertical}.{reference}").prepare_reference
from argus_verticals.hardware.shared import evidence
assert Path(stages.__file__).resolve().is_relative_to(store.store_root().resolve())
assert Path(evidence.__file__).resolve().is_relative_to(store.store_root().resolve())
project = Path.cwd() / "circuit"
prepare_reference(project)
if directory == "power" or reference == "run_robustness_reference":
    os.environ["ARGUS_SKILL_SESSION_ROOT"] = str(Path.cwd() / "runtime-state")
prompt = stages.render_role_prompt_fragment(
    role="engineer", operation="mission", stage=stage, scope="", project_root=project,
)
commands = re.findall(r"```bash\\n(.*?)\\n```", prompt, re.DOTALL)
execute = [command for command in commands if "run_analysis(Path.cwd())" in command]
check = [command for command in commands if "completion_issues" in command]
assert len(execute) == len(check) == 1
for command in (execute[0], check[0]):
    result = subprocess.run(shlex.split(command), cwd=project, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, (result.stdout, result.stderr)
assert result.stdout.strip() == "[]", result.stdout
record = json.loads((project / directory / "results/RESULTS.json").read_text())
if directory == "pcb":
    expected = (["refill"] if reference == "run_zone_reference" else []) + ["erc", "drc", "gerbers", "drill"]
    assert [row["kind"] for row in record["commands"]] == expected
    assert record["kicad_version"].startswith("9.")
    if reference == "run_zone_reference":
        refill = json.loads((project / directory / "results/native/refill.json").read_text())
        assert {zone["layer"] for zone in refill["zones"]} == {"F.Cu", "In1.Cu", "In2.Cu", "B.Cu"}
        assert all(zone["filled_area_mm2"] > 143.9 for zone in refill["zones"])
        assert (project / "design/coupon.kicad_pcb").read_bytes() == (project / "pcb/results/inputs/design/coupon.kicad_pcb").read_bytes()
elif directory == "package":
    assert len(record["runs"]) == (6 if reference == "run_convection_reference" else 4)
    assert record["versions"]["gmsh"].startswith("4.")
    assert record["versions"]["calculix"].startswith("2.")
    assert all(row["temperature_reference_k"] == (300 if reference == "run_convection_reference" else 0) for row in record["runs"])
elif directory == "power":
    assert len(record["runs"]) == (10 if reference == "run_robustness_reference" else 4)
    assert int(record["ngspice_version"].split(".")[0]) >= 42
    if reference == "run_robustness_reference":
        assessment = json.loads((project / directory / "results/ASSESSMENT.json").read_text())
        assert assessment["task_accepted"] and assessment["status"] == "passed"
        assert assessment["coverage"]["expected_scenarios"] == 5
elif directory == "analog" and reference == "run_robustness_reference":
    assert len(record["runs"]) == 136
    assessment = json.loads((project / directory / "results/ASSESSMENT.json").read_text())
    assert assessment["task_accepted"] and assessment["status"] == "passed"
    assert assessment["coverage"]["expected_scenarios"] == 17
    assert len(assessment["comparisons"]) == 136
else:
    assert len(record["runs" if directory == "analog" else "studies"]) == 6
if directory == "power" or reference == "run_robustness_reference":
    saved = Path(os.environ["ARGUS_SKILL_SESSION_ROOT"]) / f"{directory}-validation"
    assert (saved / "VALIDATED.json").is_file()
    (project / directory / "REVIEW.md").write_text("Report-only clarification; no hardware approval.")
    reuse = '''
from pathlib import Path
import sys
from argus.verticals._base import load_vertical_contract
vertical = sys.argv[1]
contract = load_vertical_contract(vertical)
def no_replay(*args, **kwargs):
    raise AssertionError("unchanged Store evidence was replayed")
if vertical == "power_electronics":
    from argus_verticals.power_electronics import native
    native.execute = no_replay
else:
    from argus_verticals.analog_mixed_signal import robustness
    robustness._execute = no_replay
assert not contract.completion_issues("review", Path.cwd())
'''
    checked = subprocess.run([sys.executable, "-c", reuse, vertical], cwd=project, capture_output=True, text=True, timeout=20)
    assert checked.returncode == 0, (checked.stdout, checked.stderr)
print("Store-only native execution and read-only check passed")
"""
    result = subprocess.run(
        [str(python), "-c", script, vertical, stage, directory, reference], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Store-only native execution and read-only check passed" in result.stdout


def test_release_builds_one_archive_per_vertical(release: tuple[Path, dict]) -> None:
    dist, payload = release
    expected = {f"{name}-{m['version']}.zip" for name, m in MANIFESTS.items()}
    assert {p.name for p in dist.glob("*.zip")} == expected
    assert (dist / "catalog.json").is_file() and (dist / "SHA256SUMS").is_file()
    assert payload["release"] == {"tag": RELEASE_TAG}
    on_disk = json.loads((dist / "catalog.json").read_text(encoding="utf-8"))
    assert on_disk == payload
    for name, entry in on_disk["verticals"].items():
        archive = entry["archive"]
        assert archive["file"] == f"{name}-{entry['version']}.zip"
        assert archive["url"] == (
            f"https://github.com/Argus-AiTeam/argus-verticals/releases/download/{RELEASE_TAG}/{archive['file']}"
        )
        without_archive = {k: v for k, v in entry.items() if k != "archive"}
        assert without_archive == json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["verticals"][name]


@pytest.mark.parametrize("name", NAMES)
def test_archive_members_are_exactly_the_vertical_trees(release: tuple[Path, dict], name: str) -> None:
    dist, payload = release
    manifest = MANIFESTS[name]
    with zipfile.ZipFile(dist / payload["verticals"][name]["archive"]["file"]) as zf:
        infos = zf.infolist()
        assert zf.testzip() is None
    members = sorted(info.filename for info in infos)
    assert members == _expected_members(name)
    assert members, f"{name}: empty archive"
    prefixes = tuple(f"{tree}/" for tree in manifest["paths"] + manifest["shared"])
    for info in infos:
        assert info.filename.startswith(prefixes), f"{name}: stray member {info.filename}"
        assert not info.is_dir(), f"{name}: directory entry {info.filename}"
        assert "__pycache__" not in info.filename and not info.filename.endswith(".pyc")
        assert not info.filename.startswith("tests/")
        assert info.date_time == (1980, 1, 1, 0, 0, 0), f"{name}: {info.filename} carries a real timestamp"
        assert info.external_attr >> 16 == 0o100644
    assert f"{manifest['paths'][0]}/stages.py" in members
    assert f"{manifest['paths'][0]}/vertical.json" in members
    for other in _other_paths(name):
        if any(other.startswith(f"{tree}/") for tree in manifest["paths"]):
            assert not any(m.startswith(f"{other}/") for m in members), f"{name}: contains nested vertical {other}"


def test_release_catalog_digests_match_the_files(release: tuple[Path, dict]) -> None:
    dist, payload = release
    sums = dict(
        reversed(line.split("  ", 1)) for line in (dist / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    )
    for name, entry in payload["verticals"].items():
        path = dist / entry["archive"]["file"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert entry["archive"]["sha256"] == digest, name
        assert entry["archive"]["size"] == path.stat().st_size, name
        assert sums[entry["archive"]["file"]] == digest, name
    assert sums["catalog.json"] == hashlib.sha256((dist / "catalog.json").read_bytes()).hexdigest()
    assert set(sums) == {e["archive"]["file"] for e in payload["verticals"].values()} | {"catalog.json"}


def test_release_rebuild_is_byte_identical(release: tuple[Path, dict], tmp_path: Path) -> None:
    dist, payload = release
    again = tmp_path / "again"
    build_catalog.build_release(build_catalog.build_index(), RELEASE_TAG, again)
    for entry in payload["verticals"].values():
        file_name = entry["archive"]["file"]
        assert (again / file_name).read_bytes() == (dist / file_name).read_bytes(), file_name
    assert (again / "catalog.json").read_bytes() == (dist / "catalog.json").read_bytes()
    assert (again / "SHA256SUMS").read_bytes() == (dist / "SHA256SUMS").read_bytes()


def test_verify_accepts_the_release_and_rejects_tampering(release: tuple[Path, dict], tmp_path: Path) -> None:
    dist, payload = release
    assert build_catalog.verify_release(dist) == []
    tampered = tmp_path / "tampered"
    shutil.copytree(dist, tampered)
    victim = tampered / payload["verticals"][NAMES[0]]["archive"]["file"]
    with victim.open("ab") as handle:
        handle.write(b"\0")
    problems = build_catalog.verify_release(tampered)
    assert any("sha256 mismatch" in p for p in problems), problems


# --------------------------------------------------------------------------- #
# What the store does: extract next to a synthetic package and import
# --------------------------------------------------------------------------- #


def _argus_root() -> Path:
    argus = pytest.importorskip("argus")
    return Path(argus.__file__).resolve().parents[1]


def _closure(name: str) -> list[str]:
    """``name`` plus everything it requires, transitively (what the store installs)."""
    order: list[str] = []
    pending = [name]
    while pending:
        current = pending.pop()
        if current in order:
            continue
        order.append(current)
        pending.extend(MANIFESTS[current]["requires"])
    return order


@pytest.mark.parametrize("name", NAMES)
def test_archive_extracts_to_an_importable_vertical(release: tuple[Path, dict], tmp_path: Path, name: str) -> None:
    argus_root = _argus_root()
    dist, payload = release
    site = tmp_path / "site"
    site.mkdir()
    for member in _closure(name):
        with zipfile.ZipFile(dist / payload["verticals"][member]["archive"]["file"]) as zf:
            zf.extractall(site)
    (site / "argus_verticals" / "__init__.py").write_text(
        '"""Synthetic package root written by the Argus Vertical Store."""\n', encoding="utf-8"
    )
    module = MANIFESTS[name]["module"]
    shared_packages = [s.replace("/", ".") for s in MANIFESTS[name]["shared"]]
    probe = (
        "import importlib, json, sys\n"
        f"module = importlib.import_module({module!r})\n"
        f"shared = [importlib.import_module(s) for s in {shared_packages!r}]\n"
        "print(json.dumps({'file': module.__file__, 'purpose': module.VERTICAL_PURPOSE,\n"
        "  'parents': list(module.VERTICAL_SKILL_PARENTS), 'shared': [s.__file__ or s.__path__[0] for s in shared]}))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(site), str(argus_root)])
    env["PYTHONSAFEPATH"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, env=env, cwd=tmp_path,
    )
    assert result.returncode == 0, f"{name}: import from the extracted archive failed\n{result.stderr}"
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert Path(report["file"]).resolve().is_relative_to(site.resolve()), (
        f"{name}: stages imported from {report['file']}, not from the extracted archive"
    )
    assert report["purpose"].split() == payload["verticals"][name]["purpose"].split()
    assert report["parents"] == payload["verticals"][name]["skill_parents"]
    for location in report["shared"]:
        assert Path(location).resolve().is_relative_to(site.resolve()), location
