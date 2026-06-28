---
name: spec-pilot
description: Use whenever the user asks Claude Code to build, create, or implement something non-trivial from a short or vague request — e.g. "build a bot for requests", "I want an auth feature", "make a landing page for booking", "build me a dashboard". Also activate on an explicit `spec-pilot:` prefix. Runs the build in the proven order — interview the user, write a spec, get explicit approval, then delegate to sub-agents, then self-verify — and holds a rule to never start parallel agents before an approved spec, so the user doesn't burn tokens on guesswork. Do NOT trigger for trivial one-step edits (rename, fix a typo, tweak spacing), for non-build operations (running a build, commits, applying review fixes, writing a summary), or for "automate this" requests. When unsure whether a request is trivial or a real build, ask one scoping question first.
---

# 🧭 spec-pilot

> Autopilot for the correct ORDER of working with Claude Code. You speak in plain words (in any language!) about what you want to build — the skill runs the build in order: **interview → spec → sub-agents → verify**. And enforces the rule: **don't go parallel until the spec is approved by you.** If you see Claude rush into parallel without your "ok" — stop phrase below.

> Lead magnet for the "6 Phrases for Claude Code" video (Nikita Vels | AI).

⚠️ English "phrases" (`interview me`, `launch sub agents`…) do NOT need to be typed — they're mnemonics from the video. Write the task in plain words, the skill guides you through the order.

Six "power phrases" alone are almost useless. The power is in the ORDER. If you launch sub-agents BEFORE the spec, each starts guessing their own way — and you get not acceleration but multiple parallel "messes" and limit overrun. This skill holds the order and the guards.

---

## When to Activate

Activate when the user asks in plain language to BUILD SOMETHING:
- "build / make / create me a <bot / app / script / landing page>"
- "I want a <feature> in the project", "help implement <idea>" — when details are scarce
- **`spec-pilot: <task>`** — explicit invocation

**DO NOT activate:**
- trivial edits: "rename variable", "fix indent", "add one button", "fix typo" — do directly (Guard 1);
- non-build operations: run build, make commit, apply review fixes, write summary/text;
- request "automate this" — this is the last, most dangerous phrase, it's NOT part of the build pipeline (see Gotchas);
- unsure if trivial or real build — **first ask one clarifying question about scope**.

---

## 🧠 CORE: The Correct ORDER

One spine, four steps. Each next step builds on the previous — order must not be broken.

| # | Phrase (mnemonic) | What it does | Why HERE |
|---|---|---|---|
| 1 | interview me | Claude asks YOU questions and extracts the spec | you don't know which details matter — without answers there's nothing to build from |
| 2 | write me a spec | assembles spec from answers, shows for confirmation | locks in YOUR choices → Claude doesn't blindly try 125 variants |
| 3 | launch sub agents | delegates chunks PER SPEC to sub-agents | speed — but only when there's a shared approved spec |
| 4 | verify before build | Claude self-checks result before handoff | catches "done but broken" before you get it |

Phrases 5–6 are the next level: **build me a skill** (package success into a skill + gotchas) and **automate this** (most dangerous — see Gotchas). They're not part of the build pipeline.

---

## 🛡 GUARDS (ALWAYS enforce)

### Guard 1 — Task scope first (no overhead)
- **Trivial** (1 action, obvious solution): pipeline NOT run. 0 questions, do immediately.
- **Medium** (one feature, 2–4 non-obvious decisions): interview **≤ 3** questions → brief spec → build → verify.
- **Large** (multiple parts/subsystems): full interview → detailed spec → sub-agents → verify.
- **When in doubt between levels — pick HIGHER.** Can only downgrade after explicit "this is trivial, don't run the order".

### Guard 2 — NEVER launch parallel agents without approved spec ⛔ (core)
Parallel without shared spec = N independent guesses that must also align. That's the limit burn.
- Spec approval = **only explicit "yes"** from user to direct question "Spec ok? Launch build?". Silence, "looks ok", "do as you think best" — NOT approval, ask again.
- Ban applies to **ALL parallel agents**, including "scouts" during interview phase.
- If user asks "launch sub-agents / parallelize" but no spec — **refuse** and propose building spec first (even if skill triggered by accident).
- Spec rejected — back to Step 2, clarify, do NOT start build.

### Guard 3 — Human zones (irreversible & external)
**STOP on everything irreversible or touching real resources:** payments, sending money, data deletion, DB migrations, mailouts, deploy/`publish`, `git push --force`, `rm -rf`, production API keys/secrets, webhooks in prod. **If unsure — treat as irreversible and ask.** This applies to sub-agents on Step 3 too: they don't execute such actions — only human, manually.

### Guard 4 — Budget & limit honesty
- Sub-agents consume the **SAME shared limit** as regular chat. Skill protects from overruns **on guessing and rework**, but doesn't make the limit unlimited.
- On Pro, full parallel quickly hits the 5-hour limit window — that's normal, **go sequentially per spec**.
- Don't spawn agents "just in case". Split per spec only on truly independent chunks.

---

## 📋 ALGORITHM

**Step 1 — interview me.** Per scope (Guard 1) ask targeted questions surfacing key decisions (what data, where to store, edge cases, what counts as "done"). If user says "your call" — proceed but **state assumptions**.

**Step 2 — write me a spec.** Assemble brief spec: goal, steps, key decisions, done criteria. **Show and wait for explicit "yes"** (Guard 2). Rejected — clarify, don't build.

**Step 3 — delegation (only after "yes").** Break spec into independent chunks.
- **Default — sub-agents** (Task tool): built-in, work on any plan, Claude delegates chunk and pulls result into session.
- "Real" multi-session parallelism — **Agent Teams**: experimental, enabled via `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in settings.json, **may be unavailable on Pro**.
- Parallel unavailable/unstable → build **sequentially per same spec**, don't stall.

**Step 4 — verify before build/handoff.** Three layers:
1. rule line in `CLAUDE.md`, e.g.: "Before handoff, describe how you'll verify result, then run verification — tests, browser, or linter";
2. auto-check — tests / linter / open in browser so Claude sees own result;
3. human zones (Guard 3) — payments/deletion/prod you verify manually.

**Step 5 (optional) — build me a skill.** Successful & repeatable → propose packaging into skill, with dedicated **gotchas** section.

---

## 🪤 GOTCHAS

| Symptom | What to do |
|---|---|
| Skill didn't auto-activate | Matching is probabilistic. Say explicitly: "`spec-pilot: <task>`" — guarantees it |
| Claude rushed into parallel without your "ok" | **Stop phrase: "stop, spec first".** Must return to Step 2 |
| Interview turned into interrogation | Guard 1: on medium task ≤ 3 questions, on trivial — 0 |
| Sub-agents glitchy / Agent Teams unavailable | Guard 4: go sequentially per spec, meaning and order preserved |
| "automate this" tempts to automate everything | Automate only the **measurable**; where your TASTE is needed → augment (stay in loop). Don't step out of the loop on expensive/irreversible actions |

---

## ✅ What This Skill Guarantees

- Won't let Claude guess — first pulls spec from you via interview + spec.
- Holds Claude back from parallel without approved spec (rule baked into instructions; rushed without "ok" — catch with stop phrase). **Saves limit from burn on guessing & rework** — but doesn't make limit unlimited.
- Won't auto-act on payments, data deletion, prod, or other irreversible actions.
- Won't create overhead on trivial edits.
- **Skill itself works on any tier including Pro** (it's a skill, not a workflow). For true multi-session parallelism (Agent Teams) may need higher plan — check yours.