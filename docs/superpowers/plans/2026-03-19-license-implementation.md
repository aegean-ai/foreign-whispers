# License Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add AGPL-3.0-only + Commons Clause license files, update project metadata, and add a README badge.

**Architecture:** Three new files (LICENSE, NOTICE), one modified file (pyproject.toml), one modified file (README.md). No code changes — purely documentation and metadata.

**Tech Stack:** Git, AGPL-3.0 legal text, Commons Clause 1.0 text

**Spec:** `docs/superpowers/specs/2026-03-19-license-design.md`

---

### Task 1: Create LICENSE file

**Files:**
- Create: `LICENSE`

- [ ] **Step 1: Create LICENSE with Commons Clause preamble + AGPL-3.0 text**

The file has two sections:

**Section 1 — Commons Clause preamble** (adapt from the standard Commons Clause 1.0 template):

```text
Commons Clause License Condition v1.0

The Software is provided to you by the Licensor under the License,
as defined below, subject to the following condition.

Without limiting other conditions in the License, the grant of rights
under the License will not include, and the License does not grant to
you, the right to Sell the Software.

For purposes of the foregoing, "Sell" means practicing any or all of
the rights granted to you under the License to provide to third parties,
for a fee or other consideration (including without limitation fees for
hosting or consulting/support services related to the Software), a
product or service whose value derives, entirely or substantially, from
the functionality of the Software. "Sell" does not include:

  (a) internal use by any organization, including for-profit companies;
  (b) academic and research use at any institution; or
  (c) consulting or professional services where the Software is not the
      primary deliverable of the engagement.

This condition applies to the Foreign Whispers project code. Third-party
dependencies retain their original license terms without additional
restriction.

License: AGPL-3.0-only
Licensor: Pantelis Monogioudis
```

**Section 2 — Full AGPL-3.0-only text.** Fetch the canonical text from:
`https://www.gnu.org/licenses/agpl-3.0.txt`

Concatenate both sections into `LICENSE` with a blank line separator.

- [ ] **Step 2: Verify LICENSE file structure**

Run: `head -35 LICENSE && echo "..." && tail -5 LICENSE`
Expected: Commons Clause header at top, AGPL-3.0 text at bottom ending with "end of terms and conditions"

- [ ] **Step 3: Commit**

```bash
git add LICENSE
git commit -m "chore: add AGPL-3.0 + Commons Clause LICENSE file"
```

---

### Task 2: Create NOTICE file

**Files:**
- Create: `NOTICE`

- [ ] **Step 1: Create NOTICE file**

```text
Foreign Whispers
Copyright (c) 2026 Pantelis Monogioudis

This software is source-available under the AGPL-3.0-only license with
a Commons Clause restriction. This summary is provided for convenience
only. The LICENSE file is the authoritative legal text.

PERMITTED:
  - Research and academic use at any institution
  - Internal use by any organization
  - Modification and redistribution under AGPL-3.0 terms
  - Consulting where the software is not the primary deliverable

NOT PERMITTED (without a separate commercial license):
  - Selling the software or a service substantially derived from it

THIRD-PARTY DEPENDENCIES AND THEIR LICENSES:

| Component               | License        | Notes                                    |
|-------------------------|----------------|------------------------------------------|
| pyrubberband/Rubber Band| GPLv2+         | "or later" — used under GPLv3 terms      |
| Coqui TTS toolkit       | MPL-2.0        | Compatible per MPL-2.0 Section 3         |
| OpenAI Whisper           | MIT            |                                          |
| argostranslate          | MIT/CC0        |                                          |
| yt-dlp                  | Unlicense      |                                          |
| FastAPI                 | MIT            |                                          |
| pydantic                | MIT            |                                          |
| moviepy                 | MIT            |                                          |
| PyTorch                 | BSD-3-Clause   |                                          |
| silero-vad              | MIT            | Optional                                 |
| pyannote.audio          | MIT            | Optional                                 |

XTTS-v2 model weights are NOT bundled with this software. They are
fetched at runtime by the TTS container and are licensed separately
under the Coqui Public Model License (CPML), which restricts use to
non-commercial purposes.
```

- [ ] **Step 2: Commit**

```bash
git add NOTICE
git commit -m "chore: add NOTICE with attribution and license summary"
```

---

### Task 3: Update pyproject.toml

**Files:**
- Modify: `pyproject.toml:1-5`

- [ ] **Step 1: Add license field to pyproject.toml**

Add after the `description` line (line 4):

```toml
license = { text = "LicenseRef-AGPL-3.0-only-with-Commons-Clause" }
```

- [ ] **Step 2: Verify pyproject.toml is valid**

Run: `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add license field to pyproject.toml"
```

---

### Task 4: Add license badge to README.md

**Files:**
- Modify: `README.md:1-3`

- [ ] **Step 1: Add badge after the title line**

Insert after line 1 (`# Foreign Whispers`):

```markdown
[![License: AGPL-3.0 + Commons Clause](https://img.shields.io/badge/License-Source_Available-blue.svg)](./LICENSE)
```

- [ ] **Step 2: Verify badge renders**

Run: `head -5 README.md`
Expected: Title on line 1, badge on line 3, blank line, then description

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "chore: add source-available license badge to README"
```
