---
name: spec-pilot
description: Apply when the user requests implementation of a non-trivial feature, module, or subsystem. Enforces the order — interview, specification, implementation, verification — and blocks parallel delegation until the specification is explicitly approved. Do not apply for trivial edits, non-implementation operations, or automation requests.
---

# spec-pilot

Enforces a mandatory execution order that eliminates wasted iterations caused by undefined requirements. Each step depends on the output of the previous one — the order must not be changed.

## Activation

Apply when the user requests implementation of non-trivial functionality: a new feature, module, integration, or subsystem. Also apply on an explicit `spec-pilot:` prefix.

Do not apply for:
- trivial single-step edits (rename, fix typo, adjust formatting) — execute directly;
- non-implementation operations (run build, commit, apply review comments, write a summary);
- automation requests (`automate this`) — see Failure Modes;
- ambiguous scope — ask one scoping question first.

---

## Execution Order

| Step | Action | Purpose |
|------|--------|---------|
| 1 | Requirements interview | Extract requirements through targeted questions |
| 2 | Specification | Document decisions explicitly; obtain user confirmation |
| 3 | Delegation | Distribute tasks per the specification — only after approval |
| 4 | Verification | Validate the result before handoff |

Steps 5–6 are outside the implementation pipeline: **skill packaging** (repeatable patterns + known issues) and **automation** (deterministic, measurable operations only — see Failure Modes).

---

## Constraints

### Constraint 1 — Scope assessment

| Scope | Criteria | Action |
|-------|----------|--------|
| Trivial | Single atomic action, solution is unambiguous | Execute immediately; no questions, no pipeline |
| Medium | Single feature, 2–4 non-obvious technical decisions | Interview ≤ 3 questions → brief spec → implement → verify |
| Large | Multiple subsystems or interdependent components | Full interview → detailed spec → parallel delegation → verify |

When scope is ambiguous, apply the higher level. Downgrade only on explicit user instruction.

### Constraint 2 — No parallel delegation without an approved specification (critical)

Parallel execution without a shared specification causes each agent to resolve ambiguities independently. Results diverge; the correction overhead exceeds the benefit of parallelisation.

- The specification is approved only by **explicit user confirmation** in response to a direct question: "Specification approved? Proceeding to implementation?"
- Responses such as "looks fine", "do as you see fit", and silence are not confirmations — ask again.
- The constraint applies to all parallel delegation, including exploratory subtasks during the interview phase.
- If the user requests parallelisation before a specification exists — decline and propose forming the specification first.
- If the specification is rejected — return to Step 2; do not begin implementation.

### Constraint 3 — User responsibility zones (irreversible operations)

The following operations require explicit user confirmation before execution:
- financial transactions and payment data handling;
- data deletion, database migrations;
- sending notifications and bulk messages;
- deployment to production environments;
- irreversible shell operations: `git push --force`, `rm -rf`, bulk data modifications;
- use of production API keys and secrets;
- webhooks and external system integrations in production.

When in doubt, classify the operation as irreversible and request confirmation.

### Constraint 4 — Context budget

- Parallel agents consume the same shared context limit as sequential execution.
- The methodology reduces consumption by eliminating iterations over undefined requirements — it does not increase the available limit.
- Decompose tasks only into genuinely independent parts; excessive fragmentation increases overhead without benefit.

---

## Algorithm

**Step 1 — Interview.** Per the assessed scope (Constraint 1), ask targeted questions that surface key technical decisions: data structure, storage approach, edge cases, completion criteria. If the user delegates choices to the agent, state the accepted assumptions explicitly.

**Step 2 — Specification.** Produce a document: objective, implementation steps, accepted technical decisions, completion criteria. Present to the user and wait for explicit confirmation (Constraint 2). On rejection — revise; do not begin implementation.

**Step 3 — Implementation (only after specification approval).** Decompose the specification into independent parts. Default to sequential execution. Apply parallel delegation only when genuinely independent blocks exist and the parallelisation mechanism is available and stable.

**Step 4 — Verification.** Three layers:
1. Declare the verification method before executing it.
2. Automated checks: tests, linter, manual browser review — agent records its own result.
3. User responsibility zones (Constraint 3): verified by the user manually.

**Step 5 (optional) — Skill packaging.** When a repeatable, reproducible pattern is identified, propose packaging it as a skill with a mandatory known issues section.

---

## Failure Modes

| Symptom | Corrective Action |
|---------|-------------------|
| Parallel execution started without specification approval | Stop execution; return to Step 2 |
| Interview contains excessive questions | Constraint 1: medium scope — max 3 questions; trivial — 0 |
| Parallel delegation unavailable or unstable | Switch to sequential execution on the same specification |
| Request to automate an arbitrary process | Apply automation only to deterministic measurable operations. Operations requiring judgment are performed in augmentation mode (agent proposes, user decides). Do not remove the user from the control loop for irreversible or high-cost operations |

---

## Guarantees

- Implementation does not begin until requirements are complete and the specification is explicitly approved.
- Parallel delegation is not initiated without an approved specification.
- Irreversible operations are not executed autonomously.
- The pipeline is not started for trivial tasks.
- Expected efficiency gain: **3–5× reduction in corrective iterations** on medium and large-scope tasks.
