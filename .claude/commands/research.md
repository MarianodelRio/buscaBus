---
name: research
description: Conversational research session to mature an idea into a concrete solution design. Reads project context, explores options with the user, uses researcher and advisor subagents, and produces a formal Research Design Solution only when explicitly requested.
---

# /research — Research & Design Session

You run an interactive research session to mature a vague idea into a concrete, implementable solution for this project.

## Phase 1 — Load project context (do this first, silently)

Before asking anything, read:
- `design.md` — the single source of truth: scope, data model, conversation flow, infrastructure, open questions (D1–D14)
- `README.md` — repo layout and current state
- `CLAUDE.md` — module map and invariants (note which modules are still `(pendiente)`)
- Any already-implemented modules relevant to the idea (e.g. `app/services/horarios/`, `app/handlers/conversation.py`) — read what exists, don't assume

Then greet the user and ask your first clarifying question.

## Phase 2 — Clarifying conversation

Ask focused questions to understand:

1. **What problem are you solving?** — A new conversation step, an importer rule for a specific sheet, a matching/text-normalization improvement, or a non-functional concern (performance, security, monitoring)?
2. **Who is affected?** — The client via WhatsApp? The company maintaining the Excel? Both?
3. **What triggers it?** — Inbound message, a new Excel import, a scheduled job, or a manual admin action?
4. **What are the constraints?** — WhatsApp API limits (row/button counts), the importer's "never guess" rule, in-memory-only state, no external API per query.
5. **What does success look like?** — Specific user journey, specific CSV/diff output, specific test passing.
6. **Does this touch an open question in `design.md` section 10 (D1–D14)?** If so, say which one — it needs the user's decision, not an assumption.

Explore 2–3 options before converging. For each option mention:
- Where it fits in the current architecture (which module it touches)
- Key risk or limitation for this system
- Rough scope (1 file? 2–3 files? new service?)

## Phase 3 — Invoke subagents as needed

- **Invoke `researcher`** when: you need to verify an API capability (WhatsApp message type, openpyxl feature), find a pattern in the codebase, or explore external approaches before deciding.
- **Invoke `advisor`** when: there are 2+ valid approaches with genuine architectural tradeoffs — e.g. how to model a calendar exception, matching threshold tuning, diff format for the importer.

Always show the user the subagent's output before continuing.

## Phase 4 — Research Design Solution (only when user asks explicitly)

Produce this document only when the user says something like "write the RDS", "create the design doc", "formalize it", or "I'm ready to implement".

```markdown
# Research Design Solution — [Feature Name]

## Overview
[One paragraph: what this adds to Buscabus and why]

## Problem / Motivation
[Current limitation or gap versus design.md. Reference the specific section if applicable.]

## Proposed Solution
[Concrete description of the solution — no pseudocode, no implementation details]

## Integration Points
| Component | Change type | Notes |
|-----------|------------|-------|
| `app/handlers/conversation.py` | New state / modified handler | ... |
| `app/services/horarios/query.py` | New function / modified rule | ... |
| `app/utils/interactive.py` | New message builder | ... |
| `app/utils/messages.py` | New text strings | ... |

## Key Design Decisions
1. **[Decision]** — [Why this over alternatives]
2. ...

## Edge Cases
- [Edge case]: [how it's handled]
- WhatsApp retry / duplicate message: [handling]
- Ambiguous or unrecognized place name: [handling, per design.md 4.7]
- Day with no service: [handling, per design.md 4.8]

## Acceptance Criteria
- [ ] [Specific, testable condition]
- [ ] All existing pytest tests pass
- [ ] `/health` endpoint still returns `{"status":"ok"}`
- [ ] No regression in existing conversation flows
- [ ] No open design question (Dn) silently resolved instead of flagged

## Scope Estimate
- Files to modify: [list]
- Complexity: [Low / Medium / High]
- Fits in one planner→coder→reviewer cycle: [Yes / No — if No, explain split]
```

After producing the RDS, ask: "Ready to implement? Use `/new-feature` with this RDS to start the planning phase."
