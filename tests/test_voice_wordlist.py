"""The moved vertical files stay in Argus's voice.

Ported from Argus's ``tests/test_voice_wordlist.py`` for the files that now
live in this package. The word list, the discipline phrases, and the allowed
literals are kept identical to Argus's so the two suites cannot drift; when
Argus retires a word, mirror it here.

One exemption is specific to this package: the module-level
``VERTICAL_PURPOSE`` string of each ``stages.py`` is the Manager-menu line
copied verbatim from Argus's ``VERTICAL_PURPOSES`` table. That text is owned
by the routing contract (changing it changes which tasks a vertical wins), so
the scan skips exactly that one assignment and nothing else.


Argus's ``docs/how-argus-speaks.md`` retires the machinery words — gate, verdict,
handoff, audit, pipeline, checklist, artifact, and their kin — from every
sentence written for a person or a model. The 48-hour billing forensics found
tens of thousands of engineer.progress lines echoing exactly those words, and
their direct upstream was a handful of shared template files. This test keeps
those files clean once they have been rewritten, so the vocabulary cannot leak
back in through one edited string.

What is scanned, and what is exempt:

- Only the files in ``VOICE_CLEAN_FILES`` are scanned. A file joins the list
  when its model- and operator-visible prose has been rewritten to the
  standard; extend the tuple with the repo-relative path and nothing else.
- Only string constants are scanned (via ``ast``), so comments never trip the
  scan, and module/class/function docstrings are explicitly excluded — both
  may quote the retired words when explaining history or intent.
- String constants with no whitespace are exempt: field names, enum values,
  event types, paths, and regexes (``artifact_root``, ``artifacts``,
  ``reviewed_handoff``) are the machine's tokens and stay as the code expects
  them (principle 9 of the doc).
- Backtick spans inside prose are exempt for the same reason: writing
  "emit a `verdict` field" names the machine's own key, exactly as the doc
  allows, so `...` spans are removed from a string before the scan.
- A discipline's own use of a word survives: the phrases in
  ``DISCIPLINE_PHRASES`` mirror the "disciplines keep their words" section of
  the doc and are removed from a string before the scan. Extend both together.
- A specific prose-shaped literal that must keep a word (for example a
  verbatim quote of an old message) goes into ``ALLOWED_LITERALS`` as its
  exact full value, ideally with a comment saying why.

The word list mirrors the word map in ``docs/how-argus-speaks.md``. When a new
word is retired there, add its forms to ``BANNED_WORD_PATTERNS`` here.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Files whose model- and operator-visible prose has been brought up to the
# standard of Argus's docs/how-argus-speaks.md. Append a repo-relative path once
# a file's prose is rewritten; never remove one to silence a failure.
VOICE_CLEAN_FILES: tuple[str, ...] = (
    "argus_verticals/quant/integrations/adata_cn/fundamentals.py",
    "argus_verticals/quant/integrations/adata_cn/loader.py",
    "argus_verticals/quant/stages.py",
    "argus_verticals/ale_last_exam/stages.py",
    "argus_verticals/physics/context_policy.py",
    "argus_verticals/physics/downgrade.py",
    "argus_verticals/physics/stages.py",
    "argus_verticals/physics/tiers.py",
    "argus_verticals/chip_design/environment_audit.py",
    "argus_verticals/chip_design/evidence.py",
    "argus_verticals/chip_design/stages.py",
    "argus_verticals/digital_circuit/benchmark/stages.py",
    "argus_verticals/digital_circuit/stages.py",
    "argus_verticals/fiction_writing/stages.py",
    "argus_verticals/fiction_writing/novelty.py",
    "argus_verticals/fiction_writing/evaluations/run_evals.py",
    "argus_verticals/classical_poetry/stages.py",
    "argus_verticals/modern_poetry/stages.py",
    "argus_verticals/prose/stages.py",
    "argus_verticals/literary_editor/stages.py",
    "argus_verticals/literary/shared/artifact_manifest.py",
    "argus_verticals/literary/shared/review_contract.py",
    "argus_verticals/medical/stages.py",
    "argus_verticals/medical/dossier.py",
    "argus_verticals/materials/stages.py",
    "argus_verticals/kernelbench/stages.py",
    "argus_verticals/nanochat/stages.py",
    "argus_verticals/speedrun/stages.py",
)

# One pattern per retired word family, matched case-insensitively on word
# boundaries. Mirrors the word map in docs/how-argus-speaks.md.
BANNED_WORD_PATTERNS: tuple[str, ...] = (
    r"gate[sd]?",
    r"gating",
    r"verdicts?",
    r"hand-?offs?",
    r"audit(?:s|ed|ing)?",
    r"pipelines?",
    r"checklists?",
    r"artifacts?",
    r"deliverables?",
    r"blockers?",
    r"sign-?offs?",
    r"kill\s+(?:condition|argument)s?",
    r"work\s+packages?",
)

_BANNED = re.compile(
    r"\b(?:" + "|".join(BANNED_WORD_PATTERNS) + r")\b",
    re.IGNORECASE,
)

# The disciplines keep their words (see the section of the same name in
# docs/how-argus-speaks.md). These phrases are removed before the scan, so
# "a data pipeline in the method figure" passes while "the review pipeline"
# fails. Keep this list and the doc's list in step.
DISCIPLINE_PHRASES: tuple[str, ...] = (
    "data pipeline",
    "data pipelines",
    "method pipeline",
    "CPU pipeline",
    "logic gate",
    "logic gates",
    "AND gate",
    "OR gate",
    "NAND gate",
    "gate count",
    "clock gating",
    "measurement artifact",
    "measurement artifacts",
    "imaging artifact",
    "imaging artifacts",
    "compression artifact",
    "compression artifacts",
    "timing sign-off",
    "design sign-off",
    # Software sense of "package" (a Python package, `pip install <name>`);
    # inert while bare "package" stays out of BANNED_WORD_PATTERNS, kept in
    # step with the doc's whitelist for the adata_cn install-hint strings.
    "Python package",
    "'adata' package",
    # The method-pipeline figure and its machine tokens (doc: "pipeline
    # figure"): the drawn pipeline itself, the required SVG group id, and the
    # skill file named after it.
    "pipeline figure",
    "pipeline-content",
    "research-svg-pipeline.md",
    # A venue's own required submission checklist (doc: "checklist").
    "reproducibility checklist",
    # A rendering artifact in a compiled PDF, kin to the imaging sense
    # (doc: "artifact (the ML literature's own senses)").
    "post-processing artifact",
    # The data-synthesis pipeline math_synth ships as the object under study
    # (doc: "synthesis pipeline"); also covers "data-synthesis pipeline".
    "synthesis pipeline",
    # Machine tokens (doc principle 9) quoted verbatim inside prose-shaped
    # strings: CLI flags of the math ledger commands, and the frozen config
    # path the math_synth banner must name exactly.
    "--verdict",
    "--artifact",
    "configs/pipeline.yaml",
    # Chip design's EDA sense of sign-off, with and without the hyphen (doc:
    # "signoff / sign-off checks"): the signoff stage that closes a hardware
    # flow, sign-off checks (STA, DRC, LVS), a hardware sign-off reviewer, and
    # the signoff/ evidence paths quoted verbatim in prose-shaped strings.
    "sign-off check",
    "sign-off checks",
    "sign-off reviewer",
    "signoff stage",
    "signoff/SIGNOFF.json",
    "signoff/ARTIFACT_MANIFEST.json",
)

# Exact full values of prose-shaped string constants that may keep a retired
# word — verbatim quotes of historical output, or a story's own words.
ALLOWED_LITERALS: frozenset[str] = frozenset({
    # A fiction routing-eval sample whose gate is a physical gate in the
    # story's world (doc: "gate (in a story)").
    "Continue this English fantasy chapter: the gate had not been opened "
    "in a hundred years.",
})


def _docstring_constants(tree: ast.AST) -> set[int]:
    """Node ids of every docstring constant, which the scan must skip."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _vertical_purpose_constants(tree: ast.AST) -> set[int]:
    """Node ids of the ``VERTICAL_PURPOSE = "..."`` value (see module docstring)."""
    ids: set[int] = set()
    for node in getattr(tree, "body", []):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "VERTICAL_PURPOSE" for t in node.targets)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            ids.add(id(node.value))
    return ids


_BACKTICK_SPAN = re.compile(r"`[^`\s][^`]*`")


def _strip_machine_spans(text: str) -> str:
    """Backtick spans name the machine's own keys and stay verbatim."""
    return _BACKTICK_SPAN.sub(" ", text)


def _strip_discipline_phrases(text: str) -> str:
    for phrase in DISCIPLINE_PHRASES:
        text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)
    return text


def _violations_in_file(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    docstrings = _docstring_constants(tree) | _vertical_purpose_constants(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in docstrings:
            continue
        text = node.value
        if text in ALLOWED_LITERALS:
            continue
        # Machine tokens carry no whitespace: keys, enums, paths, regexes.
        if not any(ch.isspace() for ch in text):
            continue
        match = _BANNED.search(_strip_discipline_phrases(_strip_machine_spans(text)))
        if match:
            snippet = " ".join(text.split())[:120]
            found.append(
                f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                f"{match.group(0)!r} in {snippet!r}"
            )
    return found


def test_voice_clean_files_exist() -> None:
    missing = [name for name in VOICE_CLEAN_FILES if not (REPO_ROOT / name).is_file()]
    assert not missing, (
        "These files moved or were deleted; update VOICE_CLEAN_FILES so the "
        f"voice standard keeps covering them: {missing}"
    )


def test_no_retired_words_in_visible_prose() -> None:
    violations: list[str] = []
    for name in VOICE_CLEAN_FILES:
        violations.extend(_violations_in_file(REPO_ROOT / name))
    assert not violations, (
        "Retired machinery words reappeared in prose that a model or the "
        "operator reads. Rewrite the sentence in the words of the field (see "
        "docs/how-argus-speaks.md, word map), or — only for a discipline's own "
        "term or a verbatim historical quote — extend DISCIPLINE_PHRASES or "
        "ALLOWED_LITERALS:\n" + "\n".join(violations)
    )
