#!/usr/bin/env python3
"""Build the store catalog for argus-verticals.

The Argus Vertical Store installs verticals from this repository one directory
at a time: it downloads a per-vertical zip from a GitHub Release, verifies its
sha256, extracts it under ``<ARGUS_SKILL_HOME>/verticals/argus_verticals/<name>/``
and loads ``argus_verticals.<name>.stages`` from there. This script is the
producer side of that contract.

* Every vertical ships a ``vertical.json`` next to its ``stages.py``
  (schema: ``catalog/vertical.schema.json``). The one-line purpose is not
  repeated there; it is read from ``stages.py`` with ``ast``.
* ``python scripts/build_catalog.py`` validates every manifest against the
  schema and against ``pyproject.toml`` and rewrites ``catalog.json`` at the
  repository root (the browsing index, committed).
* ``--check`` fails when the committed ``catalog.json`` is stale.
* ``--release <tag> --dist <dir>`` also builds one deterministic zip per
  vertical, ``<dir>/catalog.json`` with the download URLs and digests, and
  ``<dir>/SHA256SUMS``.
* ``--verify <dir>`` re-reads a release directory, checks every digest and
  every archive's member list, and rebuilds it in a temporary directory to
  prove the build is byte-identical.

Standard library only (``tomllib`` is 3.11+); nothing here imports Argus.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "argus_verticals"
SCHEMA_PATH = REPO_ROOT / "catalog" / "vertical.schema.json"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
CATALOG_PATH = REPO_ROOT / "catalog.json"
ENTRY_POINT_GROUP = "argus.verticals"
GITHUB_REPO = "Argus-AiTeam/argus-verticals"
CATALOG_SCHEMA_VERSION = 1

# Fields the manifest may not carry because the generator derives them.
DERIVED_FIELDS = ("purpose", "skill_parents", "has_skills", "api_version", "size_bytes", "archive")

# Files never shipped or counted.
EXCLUDED_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"})
EXCLUDED_FILE_SUFFIXES = (".pyc", ".pyo")
EXCLUDED_FILE_NAMES = frozenset({".DS_Store"})

# Fixed zip metadata so a rebuild of unchanged sources is byte-identical.
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
ZIP_FILE_MODE = 0o100644 << 16
ZIP_COMPRESSLEVEL = 9


class CatalogError(Exception):
    """A manifest, the tree, or the committed catalog violates the contract."""


# --------------------------------------------------------------------------- #
# Minimal JSON Schema (draft 2020-12 subset) validator; jsonschema is not a
# runtime dependency of this repository and the generator must stay stdlib.
# --------------------------------------------------------------------------- #

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def _schema_issues(instance: Any, schema: dict[str, Any], where: str) -> list[str]:
    issues: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        ok = any(
            isinstance(instance, _TYPES[t]) and not (t in ("integer", "number") and isinstance(instance, bool))
            for t in types
        )
        if not ok:
            return [f"{where}: expected {expected}, got {type(instance).__name__}"]
    if "const" in schema and instance != schema["const"]:
        issues.append(f"{where}: must equal {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        issues.append(f"{where}: must be one of {schema['enum']!r}")
    if isinstance(instance, str):
        pattern = schema.get("pattern")
        if pattern and not re.search(pattern, instance):
            issues.append(f"{where}: {instance!r} does not match {pattern}")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            issues.append(f"{where}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            issues.append(f"{where}: longer than {schema['maxLength']}")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            issues.append(f"{where}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            issues.append(f"{where}: more than {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            seen = [json.dumps(item, sort_keys=True) for item in instance]
            if len(set(seen)) != len(seen):
                issues.append(f"{where}: items are not unique")
        if "items" in schema:
            for index, item in enumerate(instance):
                issues.extend(_schema_issues(item, schema["items"], f"{where}[{index}]"))
    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                issues.append(f"{where}: missing required field {key!r}")
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    issues.append(f"{where}: unexpected field {key!r}")
        for key, sub in properties.items():
            if key in instance:
                issues.extend(_schema_issues(instance[key], sub, f"{where}.{key}"))
    return issues


def validate_against_schema(instance: Any, schema: dict[str, Any], where: str) -> None:
    issues = _schema_issues(instance, schema, where)
    if issues:
        raise CatalogError("\n".join(issues))


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #


def _rel(path: Path) -> str:
    """Repo-relative path for messages; absolute when outside the repository."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CatalogError(f"{_rel(path)}: invalid JSON: {exc}") from exc


def load_schema() -> dict[str, Any]:
    return load_json(SCHEMA_PATH)


def load_entry_points(pyproject: Path | None = None) -> dict[str, str]:
    import tomllib

    data = tomllib.loads((pyproject or PYPROJECT_PATH).read_text(encoding="utf-8"))
    return dict(data["project"]["entry-points"][ENTRY_POINT_GROUP])


def module_dir(module: str) -> Path:
    """``argus_verticals.digital_circuit.benchmark.stages`` -> its directory."""
    parts = module.split(".")
    return REPO_ROOT.joinpath(*parts[:-1])


def find_manifests(package_root: Path = PACKAGE_ROOT) -> dict[Path, dict[str, Any]]:
    manifests: dict[Path, dict[str, Any]] = {}
    for path in sorted(package_root.rglob("vertical.json")):
        if EXCLUDED_DIR_NAMES.intersection(path.parts):
            continue
        manifests[path] = load_json(path)
    return manifests


def _module_constant(tree: ast.Module, name: str, path: Path) -> ast.AST | None:
    """The value node of the module-level assignment to ``name`` (Assign or AnnAssign)."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                if node.value is None:
                    raise CatalogError(f"{_rel(path)}:{node.lineno}: {name} is annotated but never assigned")
                return node.value
    return None


def _literal(node: ast.AST, name: str, path: Path) -> Any:
    try:
        return ast.literal_eval(node)
    except ValueError as exc:
        raise CatalogError(
            f"{_rel(path)}:{node.lineno}: {name} must be a literal "
            f"(a string or tuple of strings), got {ast.dump(node)[:80]}"
        ) from exc


def read_plugin_attributes(stages_path: Path) -> dict[str, Any]:
    """Read the plugin attributes from ``stages.py`` without importing it."""
    tree = ast.parse(stages_path.read_text(encoding="utf-8"), filename=str(stages_path))
    purpose_node = _module_constant(tree, "VERTICAL_PURPOSE", stages_path)
    if purpose_node is None:
        raise CatalogError(f"{_rel(stages_path)}: no module-level VERTICAL_PURPOSE")
    purpose = _literal(purpose_node, "VERTICAL_PURPOSE", stages_path)
    if not isinstance(purpose, str) or not purpose.strip():
        raise CatalogError(f"{_rel(stages_path)}: VERTICAL_PURPOSE must be a non-empty string")

    parents_node = _module_constant(tree, "VERTICAL_SKILL_PARENTS", stages_path)
    if parents_node is None:
        raise CatalogError(f"{_rel(stages_path)}: no module-level VERTICAL_SKILL_PARENTS")
    parents = _literal(parents_node, "VERTICAL_SKILL_PARENTS", stages_path)
    if not isinstance(parents, (tuple, list)) or not all(isinstance(p, str) for p in parents):
        raise CatalogError(
            f"{_rel(stages_path)}: VERTICAL_SKILL_PARENTS must be a tuple of strings"
        )

    api_node = _module_constant(tree, "ARGUS_VERTICAL_API_VERSION", stages_path)
    if api_node is None:
        raise CatalogError(f"{_rel(stages_path)}: no module-level ARGUS_VERTICAL_API_VERSION")
    api_version = _literal(api_node, "ARGUS_VERTICAL_API_VERSION", stages_path)
    if not isinstance(api_version, int) or isinstance(api_version, bool):
        raise CatalogError(f"{_rel(stages_path)}: ARGUS_VERTICAL_API_VERSION must be an int")

    has_skills = _module_constant(tree, "VERTICAL_SKILLS", stages_path) is not None
    return {
        "purpose": " ".join(purpose.split()),
        "skill_parents": list(parents),
        "has_skills": has_skills,
        "api_version": api_version,
    }


# --------------------------------------------------------------------------- #
# File collection
# --------------------------------------------------------------------------- #


def _is_excluded(path: Path) -> bool:
    if EXCLUDED_DIR_NAMES.intersection(path.parts):
        return True
    if path.name in EXCLUDED_FILE_NAMES or path.suffix in EXCLUDED_FILE_SUFFIXES:
        return True
    return False


def collect_files(tree_paths: list[str], other_vertical_paths: list[str]) -> list[Path]:
    """Repo-relative files under ``tree_paths`` excluding caches and nested verticals.

    ``other_vertical_paths`` are the ``paths`` of every other vertical; a
    directory nested inside one of ours (``digital_circuit/benchmark`` inside
    ``digital_circuit``) belongs to that vertical's archive, not to ours.
    """
    files: set[Path] = set()
    for tree in tree_paths:
        root = REPO_ROOT / tree
        if not root.is_dir():
            raise CatalogError(f"{tree}: not a directory")
        # Only directories strictly inside this tree are foreign; a vertical
        # that itself sits inside another's directory keeps its own files.
        nested = tuple(f"{other}/" for other in other_vertical_paths if other.startswith(f"{tree}/"))
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink() or _is_excluded(path):
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if nested and rel.startswith(nested):
                continue
            files.add(path.relative_to(REPO_ROOT))
    return sorted(files, key=lambda p: p.as_posix())


def archive_file_name(name: str, version: str) -> str:
    return f"{name}-{version}.zip"


def archive_url(tag: str, file_name: str) -> str:
    return f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{file_name}"


# --------------------------------------------------------------------------- #
# The index
# --------------------------------------------------------------------------- #


def git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip() or "unknown"


def build_index() -> dict[str, Any]:
    """Validate every manifest and return the catalog (without archives)."""
    schema = load_schema()
    entry_points = load_entry_points()
    manifests = find_manifests()
    problems: list[str] = []

    by_name: dict[str, dict[str, Any]] = {}
    for path, manifest in manifests.items():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            validate_against_schema(manifest, schema, rel)
        except CatalogError as exc:
            problems.append(str(exc))
            continue
        name = manifest["name"]
        if name in by_name:
            problems.append(f"{rel}: duplicate vertical name {name!r}")
            continue
        for field in DERIVED_FIELDS:
            if field in manifest:
                problems.append(f"{rel}: {field!r} is derived by the generator; remove it")
        expected_dir = module_dir(manifest["module"])
        if path.parent != expected_dir:
            problems.append(f"{rel}: module {manifest['module']} does not point at this directory")
        own_dir = path.parent.relative_to(REPO_ROOT).as_posix()
        if manifest["paths"][0] != own_dir:
            problems.append(f"{rel}: paths[0] must be the vertical's own directory {own_dir!r}")
        if not (path.parent / "stages.py").is_file():
            problems.append(f"{rel}: no stages.py next to the manifest")
        by_name[name] = manifest

    # Same set of names and same module targets as pyproject.toml.
    declared = set(entry_points)
    present = set(by_name)
    if declared != present:
        problems.append(
            "pyproject.toml entry points and vertical.json manifests disagree:\n"
            f"  registered but no manifest: {sorted(declared - present)}\n"
            f"  manifest but not registered: {sorted(present - declared)}"
        )
    for name in sorted(declared & present):
        if entry_points[name] != by_name[name]["module"]:
            problems.append(
                f"{name}: vertical.json module {by_name[name]['module']!r} != "
                f"pyproject entry point {entry_points[name]!r}"
            )
    # Every stages.py must have a manifest.
    stage_dirs = {
        p.parent for p in PACKAGE_ROOT.rglob("stages.py") if not EXCLUDED_DIR_NAMES.intersection(p.parts)
    }
    manifest_dirs = {p.parent for p in manifests}
    for directory in sorted(stage_dirs - manifest_dirs):
        problems.append(f"{directory.relative_to(REPO_ROOT).as_posix()}: stages.py without vertical.json")

    if problems:
        raise CatalogError("\n".join(problems))

    all_paths = {name: m["paths"] for name, m in by_name.items()}
    verticals: dict[str, Any] = {}
    for name in sorted(by_name):
        manifest = by_name[name]
        for required in manifest["requires"]:
            if required not in by_name:
                problems.append(f"{name}: requires unknown vertical {required!r}")
            if required == name:
                problems.append(f"{name}: requires itself")
        for shared in manifest["shared"]:
            if not (REPO_ROOT / shared).is_dir():
                problems.append(f"{name}: shared directory {shared!r} does not exist")
            if any(shared == p or shared.startswith(f"{p}/") for paths in all_paths.values() for p in paths):
                problems.append(f"{name}: shared directory {shared!r} is (inside) a vertical; use requires")
        attributes = read_plugin_attributes(module_dir(manifest["module"]) / "stages.py")
        for parent in attributes["skill_parents"]:
            if parent in by_name and parent not in manifest["requires"]:
                problems.append(f"{name}: skill parent {parent!r} is a catalog vertical; add it to requires")
        other_paths = [p for other, paths in all_paths.items() if other != name for p in paths]
        files = collect_files(manifest["paths"] + manifest["shared"], other_paths)
        entry = dict(manifest)
        entry.update(attributes)
        entry["size_bytes"] = sum((REPO_ROOT / f).stat().st_size for f in files)
        verticals[name] = entry

    if problems:
        raise CatalogError("\n".join(problems))

    return {
        "schema": CATALOG_SCHEMA_VERSION,
        "generated_from": {"repo": GITHUB_REPO, "commit": git_head()},
        "verticals": verticals,
    }


def dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _without_commit(catalog: dict[str, Any]) -> dict[str, Any]:
    copy = json.loads(json.dumps(catalog))
    copy.get("generated_from", {}).pop("commit", None)
    return copy


def check_committed(index: dict[str, Any]) -> list[str]:
    """Differences between the committed catalog.json and a fresh build.

    ``generated_from.commit`` is ignored: the commit that includes the file
    cannot know its own hash, so the committed value is always one behind.
    """
    if not CATALOG_PATH.is_file():
        return ["catalog.json is missing; run python scripts/build_catalog.py"]
    committed = load_json(CATALOG_PATH)
    if _without_commit(committed) == _without_commit(index):
        return []
    diffs: list[str] = []
    old = committed.get("verticals", {})
    new = index["verticals"]
    for name in sorted(set(old) | set(new)):
        if name not in old:
            diffs.append(f"+ {name} (not in the committed catalog)")
        elif name not in new:
            diffs.append(f"- {name} (no longer in the tree)")
        elif old[name] != new[name]:
            changed = sorted(k for k in set(old[name]) | set(new[name]) if old[name].get(k) != new[name].get(k))
            diffs.append(f"~ {name}: {', '.join(changed)}")
    for key in ("schema", "generated_from"):
        if _without_commit(committed).get(key) != _without_commit(index).get(key):
            diffs.append(f"~ {key}")
    return diffs or ["catalog.json differs (formatting)"]


# --------------------------------------------------------------------------- #
# Release archives
# --------------------------------------------------------------------------- #


def write_archive(destination: Path, files: list[Path]) -> None:
    """Deterministic zip: sorted members, fixed timestamps and modes, no dirs."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=ZIP_COMPRESSLEVEL) as zf:
        for rel in sorted(files, key=lambda p: p.as_posix()):
            info = zipfile.ZipInfo(rel.as_posix(), date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ZIP_FILE_MODE
            info.create_system = 3
            zf.writestr(info, (REPO_ROOT / rel).read_bytes(), compresslevel=ZIP_COMPRESSLEVEL)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def vertical_files(index: dict[str, Any], name: str) -> list[Path]:
    verticals = index["verticals"]
    other_paths = [p for other, entry in verticals.items() if other != name for p in entry["paths"]]
    entry = verticals[name]
    return collect_files(entry["paths"] + entry["shared"], other_paths)


def build_release(index: dict[str, Any], tag: str, dist: Path) -> dict[str, Any]:
    dist.mkdir(parents=True, exist_ok=True)
    release = json.loads(json.dumps(index))
    release["release"] = {"tag": tag}
    sums: list[tuple[str, str]] = []
    for name, entry in release["verticals"].items():
        file_name = archive_file_name(name, entry["version"])
        target = dist / file_name
        write_archive(target, vertical_files(index, name))
        digest = sha256_of(target)
        entry["archive"] = {
            "file": file_name,
            "url": archive_url(tag, file_name),
            "sha256": digest,
            "size": target.stat().st_size,
        }
        sums.append((digest, file_name))
    catalog_path = dist / "catalog.json"
    catalog_path.write_text(dumps(release), encoding="utf-8")
    sums.append((sha256_of(catalog_path), "catalog.json"))
    (dist / "SHA256SUMS").write_text(
        "".join(f"{digest}  {file_name}\n" for digest, file_name in sorted(sums, key=lambda s: s[1])),
        encoding="utf-8",
    )
    return release


def verify_release(dist: Path) -> list[str]:
    """Self-test of a release directory; returns a list of problems."""
    problems: list[str] = []
    catalog_path = dist / "catalog.json"
    if not catalog_path.is_file():
        return [f"{catalog_path}: missing"]
    release = load_json(catalog_path)
    index = build_index()
    if "release" not in release or "tag" not in release["release"]:
        return [f"{catalog_path}: no release.tag"]
    released_index = {
        "schema": release.get("schema"),
        "generated_from": release.get("generated_from", {}),
        "verticals": {
            name: {k: v for k, v in entry.items() if k != "archive"}
            for name, entry in release.get("verticals", {}).items()
        },
    }
    if _without_commit(released_index) != _without_commit(index):
        problems.append(f"{catalog_path}: index fields differ from a fresh build of the tree")

    sums = {}
    sums_path = dist / "SHA256SUMS"
    if sums_path.is_file():
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            digest, _, file_name = line.partition("  ")
            sums[file_name] = digest
    else:
        problems.append(f"{sums_path}: missing")

    for name, entry in release["verticals"].items():
        archive = entry.get("archive")
        if not archive:
            problems.append(f"{name}: no archive entry")
            continue
        path = dist / archive["file"]
        if not path.is_file():
            problems.append(f"{name}: {path} missing")
            continue
        if archive["file"] != archive_file_name(name, entry["version"]):
            problems.append(f"{name}: archive file name {archive['file']!r} does not follow <name>-<version>.zip")
        if archive["url"] != archive_url(release["release"]["tag"], archive["file"]):
            problems.append(f"{name}: archive url does not point at release {release['release']['tag']}")
        digest = sha256_of(path)
        if digest != archive["sha256"]:
            problems.append(f"{name}: sha256 mismatch ({digest} on disk)")
        if path.stat().st_size != archive["size"]:
            problems.append(f"{name}: size mismatch")
        if sums.get(archive["file"]) != digest:
            problems.append(f"{name}: SHA256SUMS disagrees with the file")
        expected = [p.as_posix() for p in vertical_files(index, name)]
        with zipfile.ZipFile(path) as zf:
            members = sorted(zf.namelist())
            bad = zf.testzip()
        if bad is not None:
            problems.append(f"{name}: corrupt member {bad}")
        if members != expected:
            problems.append(
                f"{name}: archive members differ from the tree\n"
                f"  only in zip:  {sorted(set(members) - set(expected))[:5]}\n"
                f"  only in tree: {sorted(set(expected) - set(members))[:5]}"
            )
    if sums.get("catalog.json") != sha256_of(catalog_path):
        problems.append("SHA256SUMS disagrees with catalog.json")

    # Byte-identical rebuild.
    with tempfile.TemporaryDirectory(prefix="argus-verticals-verify-") as tmp:
        rebuilt = Path(tmp)
        build_release(index, release["release"]["tag"], rebuilt)
        for entry in release["verticals"].values():
            file_name = entry["archive"]["file"]
            if (rebuilt / file_name).read_bytes() != (dist / file_name).read_bytes():
                problems.append(f"{file_name}: rebuild is not byte-identical")
    return problems


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if the committed catalog.json is stale")
    parser.add_argument("--release", metavar="TAG", help="also build per-vertical zips for this release tag")
    parser.add_argument("--dist", metavar="DIR", type=Path, help="output directory for --release (default dist/)")
    parser.add_argument("--verify", metavar="DIR", type=Path, help="self-test a built release directory")
    args = parser.parse_args(argv)

    try:
        if args.verify is not None:
            problems = verify_release(args.verify)
            if problems:
                print("release verification failed:\n  " + "\n  ".join(problems), file=sys.stderr)
                return 1
            print(f"{args.verify}: every archive matches its digest, member list and a fresh rebuild")
            return 0

        index = build_index()
        if args.check:
            diffs = check_committed(index)
            if diffs:
                print("catalog.json is stale; run python scripts/build_catalog.py:\n  " + "\n  ".join(diffs), file=sys.stderr)
                return 1
            print(f"catalog.json is current ({len(index['verticals'])} verticals)")
        else:
            CATALOG_PATH.write_text(dumps(index), encoding="utf-8")
            print(f"wrote {CATALOG_PATH.relative_to(REPO_ROOT)} ({len(index['verticals'])} verticals)")

        if args.release:
            if not re.fullmatch(r"v\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?", args.release):
                print(f"warning: release tag {args.release!r} does not look like vX.Y.Z", file=sys.stderr)
            dist = args.dist if args.dist is not None else REPO_ROOT / "dist"
            release = build_release(index, args.release, dist)
            print(f"wrote {len(release['verticals'])} archives, catalog.json and SHA256SUMS to {dist}")
        elif args.dist is not None:
            parser.error("--dist requires --release")
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
