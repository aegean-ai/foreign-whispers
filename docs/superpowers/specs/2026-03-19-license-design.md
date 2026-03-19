# License Design: Foreign Whispers

**Date**: 2026-03-19
**Issue**: fw-up3
**Status**: Approved

## Decision

License the Foreign Whispers repository as **source-available** under **AGPL-3.0-only + Commons Clause**. This is not an OSI-approved open-source license — the Commons Clause removes the right to sell, making it a source-available license with an AGPL copyleft base.

## Context

Foreign Whispers is a public GitHub repository. The goal is to allow open research, education, and internal use while preventing commercial productization — someone repackaging the pipeline as a paid dubbing service.

Key dependency constraints:
- XTTS-v2 model weights use CPML (non-commercial only), fetched at runtime, not bundled
- pyrubberband wraps Rubber Band Library (GPLv2+); compatible with AGPL because the "or later" clause allows receiving under GPLv3, which is AGPL-3.0-compatible
- Coqui TTS toolkit is MPL-2.0 (compatible with AGPL per MPL-2.0 Section 3)
- All other deps are permissive (MIT, BSD, ISC, Unlicense)

## License Structure

### Base License: AGPL-3.0-only

Covers all source code in the repository — both the Python backend/library and the Next.js frontend. Requires anyone who modifies and deploys the software (including as a network service) to share their source under AGPL.

### Commons Clause Addendum

Added as a preamble to the LICENSE file, before the AGPL text. The Commons Clause applies **only to the project's own original code**, not to third-party dependencies which retain their own license terms:

> "The Software is provided to you by the Licensor under the License, as defined below, subject to the following condition: Without limiting other conditions in the License, the grant of rights under the License will not include, and the License does not grant to you, the right to Sell the Software."

This scoping is necessary because GPL Section 7 prohibits adding "further restrictions" beyond those in the GPL. The Commons Clause restriction applies to the Foreign Whispers project code as a whole work; individual GPL-licensed components (e.g., Rubber Band) retain their original license terms without additional restriction.

**"Sell"** is defined as providing the software (or a service substantially derived from it) to third parties for a fee.

**Explicitly excluded from "Sell"** (always permitted):
- Internal use by any organization, including for-profit companies
- Academic and research use at any institution (university, corporate research lab, independent researcher)
- Consulting or professional services where the software is not the primary deliverable of the engagement (e.g., a consultant who uses Foreign Whispers as one tool among many, not a consultant who delivers a Foreign Whispers-based dubbing workflow as the engagement's output)

## File Layout

### `LICENSE`

Single file containing:
1. Commons Clause header (~10 lines) identifying Pantelis Monogioudis as Licensor, defining "Sell", and noting that the clause applies to the project's own code
2. Full AGPL-3.0-only text

### `NOTICE`

Contains:
- Copyright line: `Copyright (c) 2026 Pantelis Monogioudis`
- Plain-English summary of the license terms and what is/isn't permitted, with an explicit disclaimer: "This summary is provided for convenience only. The LICENSE file is the authoritative legal text."
- Dependency attribution table covering key dependencies and their licenses
- Note that XTTS-v2 model weights are separately licensed under CPML (non-commercial)

### `pyproject.toml`

Update the license field (non-standard SPDX, using `LicenseRef-` prefix):
```toml
license = { text = "LicenseRef-AGPL-3.0-only-with-Commons-Clause" }
```

Note: this package cannot be uploaded to PyPI under a recognized SPDX identifier. This is acceptable since the project is not intended for PyPI distribution.

### README

Add a license badge linking to the LICENSE file, labeled "Source Available" rather than "Open Source."

## Dependency Compatibility

| Dependency | License | AGPL Compatible | Notes |
|---|---|---|---|
| pyrubberband / Rubber Band | GPLv2+ | Yes | "or later" clause allows GPLv3, which is AGPL-3.0-compatible |
| Coqui TTS toolkit | MPL-2.0 | Yes | MPL-2.0 Section 3 permits combination with GPL-family |
| openai-whisper | MIT | Yes | Permissive |
| argostranslate | MIT/CC0 | Yes | Permissive |
| yt-dlp | Unlicense | Yes | Permissive; bundled executables may contain GPLv3+ (server deployment only, no issue) |
| XTTS-v2 model weights | CPML | N/A | Not bundled; fetched at runtime by TTS container |
| FastAPI, pydantic, etc. | MIT | Yes | Permissive |
| moviepy | MIT | Yes | Permissive |
| silero-vad | MIT | Yes | Optional, permissive |
| pyannote.audio | MIT | Yes | Optional, permissive |
| logfire | Proprietary | N/A | Optional SaaS client, not distributed |

No blockers. All dependencies are compatible with AGPL-3.0. The Commons Clause is scoped to project code only, avoiding GPL anti-further-restriction conflicts.

## Docker Image Distribution

Docker images that bundle the project code with OS-level packages constitute "distribution" under AGPL. The Commons Clause applies to Docker images containing the project code — they may not be sold as part of a commercial product or service.

## Enforcement

- Violations are standard copyright infringement (using software outside granted license rights)
- AGPL is well-litigated and provides strong legal footing
- Commercial licensing available on request — standard dual-license model

## Future Considerations

- **DCO (Developer Certificate of Origin)**: Implement as a day-one requirement — a lightweight `Signed-off-by` line in commits. This is important because retroactively requiring sign-off on past contributions is problematic, and DCO preserves the right to enforce the Commons Clause and offer commercial licenses.
- **Commercial license terms**: Define per-deal as needed. No pricing structure required upfront.
