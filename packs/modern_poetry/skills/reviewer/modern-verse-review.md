---
name: "Modern Free-Verse Review"
description: "Review free verse against declared constraints and live poetic craft."
---

# 现代诗审阅 · Modern Free-Verse Review

Free verse has NO metrical machine layer, so this review method is honest about
the split: a THIN machine layer (declared hard constraints) and a LIVE-reviewer
craft layer that is never mechanized.

## 一 · 硬约束（机检层 · BLOCKING · 由 `poem_check.py draft` / `final` 机检）

Decided mechanically against `poetry/form_spec.json` only — these catch declared
violations, not poetic quality:

- **language**：诗是否为声明的语言（zh Han / en Latin）。
- **line_count**：若 form_spec 声明了行数/上下限，实际行数须满足。
- **banned_word**：命中禁用陈词清单（仅清单内，非通用陈词检测）。
- **empty_line**：诗不能为空（至少一行非空白；节间空行不触发此项）。

## 二 · 技法（live-reviewer 层 · 非机检 · NON-blocking heuristic）

These require reading and judgement; recorded as NON-blocking live findings, never
mechanized or scored:

- **imagery（意象）**：意象是否具体、彼此关联，而非罗列。
- **lineation（断行）**：断行/分节是否服务节奏与语义，避免无意义断行。
- **tone（语调）**：语调是否统一，避免抽象解释过满。
- **cliche（陈词）**：清单之外的陈词滥调、机械排比（人工判）。
- **coherence（连贯）**：整首是否有一个中心张力/落点。
- **reference_fidelity**：若给了参考文本，是否尊重其约束而非漂移。

## 输出

Emit `poetry/review.json` as `{verdict, findings[]}`. Each finding has `id`,
`type`, `severity` (critical|major|minor|note), `blocking` (true|false),
`location`, `evidence`, `suggested_action`, and optionally `violated_constraint`,
`must_not_break` (strings the revision must preserve) and `confidence` (0–1); no
other keys. `severity` is importance and `blocking` is the gate, so a serious
craft note can be `critical` yet non-blocking. `type` ∈ the modern vocabulary
(language/line_count/banned_word/empty_line + imagery/lineation/tone/cliche/
coherence/reference_fidelity). Hard-constraint findings are `blocking`; craft
findings are non-blocking judgements. Any blocking finding means `verdict`
`revise`; no findings means `done`. Never fake a numeric aesthetic score.
`poem_check.py review` (see the pack's SKILL.md) checks this file.
