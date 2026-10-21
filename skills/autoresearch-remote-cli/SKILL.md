---
name: autoresearch-remote-cli
description: Prepare and execute authorized AutoResearch work over SSH, including real reproduction, method optimization, complete paired evidence, isolated model trajectories and Harbor delivery. Apply phase-three tutorial V4 and the user's current model routes; historical server settings are not defaults for new tasks.
---

# AutoResearch Remote CLI

Use SSH and task-specific CLIs for authorized remote work. Skill maintenance does not start old tasks, resume a pause, spend model tokens or launch long trajectories.

## Current requirements

For phase-three work, first read [the V4 contract](references/phase3-v4-contract.md), then [the remote workflow](references/workflow.md). The user supplied the V4 tutorial on 2026-10-21; it corresponds to review Skill 0.3.10, whose official package and independent format/GPU/fingerprint scripts were not supplied. Keep actual tool versions and missing validation explicit. Read [server-context.md](references/server-context.md) only when the user selected that server or its historical tasks; recheck its dated observations. [requirements.txt](references/requirements.txt) preserves the old source and is historical where it conflicts with V4 or later user instructions.

Models are configurable; verify actual identities, supported reasoning levels and independent execution. The historical GPT-6.1 Sol / Seed 2.1 Turbo pair, GPT xhigh / Seed high and ModCon settings apply only to tasks that still explicitly select them. Keep selected models unless the user changes them; an unsupported model must be reported, never silently replaced.

## Coding Plan and credentials

All Doubao / Ark / Seed requests use the user's Volcengine Coding Plan: base URL `https://ark.cn-beijing.volces.com/api/coding/v3`, Chat Completions path `/chat/completions`. The trusted controller reads the latest credentials from `${AUTHOR_HOME}/.config/ark/current.json` (0600) at safe call boundaries. Never echo keys or write them into requests on disk, logs, task packages, repositories, Actor environments or remote candidate processes. Refresh cached routes safely without interrupting in-flight runs or resuming paused work.

Codex uses a tested credential-free gateway that adapts its required protocol to Coding Plan. Verify the requested model and coding tools through the real route; a plain chat response is not a Coding Agent trajectory. No automatic fallback to metered `/api/v3`, temporary AK/SK keys, old arkcli profiles or published-model substitutions. When the plan cannot serve the selected model or the adapter is unavailable, report that fact and leave that track incomplete.

The bundled legacy `control.py` / `remote_worker.py` still implement old Ark Responses/profile routes and child key injection. **Do not invoke their `ark`, `ark-profile`, `codex-seed` or `codex-seed-profile` operations for current work.** They are not Coding Plan adapters. Their historical tests and server probe logs do not establish current compatibility. No live route or remote process was changed merely by this documentation update.

## Remote operations

The helper [remote_worker.py](scripts/remote_worker.py) runs on the selected server; [control.py](scripts/control.py) transports JSON over SSH. Resolve helper paths relative to this skill and recheck the selected host, worker path and authorization before use. `doctor` is a read-only inventory, not a model probe or Harbor validation.

Use existing SSH authentication; do not embed passwords or copy local OAuth files. Keep controller, private evidence and candidate directories separate. The worker is a command runner, not a security boundary. A failing sandbox must be repaired; disabling it does not prove Hidden/Reference isolation. Inspect completed tool events: a CLI exit of zero after failed shell tools is not successful execution.

`codex-custom` and `codex-openai` are retained for separately authorized non-Ark routes. Verify current model/provider/effort and the trusted credential arrangement before any request; saved historical defaults, profile logins or local successes cannot prove current remote availability. Do not pass model keys into an Actor merely because an old helper accepts them. Nonsecret request files are allowed; secret-bearing files and prompt credentials are forbidden.

## Execution gates

1. Recheck live processes, selected host, CPU/GPU/RAM, data/model licenses and hashes, dependencies, official commands and the real task contract. For phase-three target runs use H20 preferred or L20; keep CPU tasks CPU-only. Other hardware logs remain historical with true device names. Separate resource estimates from target measurements and rerun affected results after migration.
2. Run a small real reproduction when authorized; preserve actual argv, seed, timestamps, resources, exit code, unedited logs and artifacts. Mark smoke results separately from formal B/R and Hidden. Do not infer training reproduction from inference-only code.
3. Freeze a genuine method interface, data, complete formal seed set, quality gates, budgets and B/R/U. Check G01/G02/G03 from all paired evidence; fixed-model random evaluation is not independent training. Same method across seeds keeps the same code and non-seed configuration.
4. Build native Harbor layout: Agent context `environment/`; dedicated Verifier context `tests/`, or reuse Solver image and upload tests into a new Verifier sandbox. Verify the chosen branch and dependencies in the target version. Do not use the old task-root build contract, require two Dockerfiles, or expose the whole task to the Agent.
5. Before long trajectories, verify real model routes, public scoring, honest B/R, and isolation. Run each model with the same prompt/task/protocol/resources and separate empty outputs. Each sandbox uses one container and its own GPU; no Agent-deployed containers, extra GPU sandboxes, remote compute services or Compose. Framework-managed final Verifier remains separate.
6. Count each track's effective time independently: normally ≥10h; ≥7h only with every nontraining fast-iteration exception condition. Keep eight fields per round; store actual model, reasoning and duration in run_summary/expert prose. Existing timing records can suffice; no invented independent timer requirement. Preserve failed and worse runs.
7. Restore the Public/Dev best candidate and required models/config into the artifact directory before Agent exit. Harbor transfers only this candidate; the independent Verifier then performs Hidden scoring. Select the unique final best by valid normalized Public/Dev aggregate and rerun in a clean task snapshot. Do not tune from final Hidden.
8. Complete same-version NOP, actual four-input task fingerprint, format/GPU checks and final ZIP check. Deliver all three directories after repair, keep final ZIP SHA-256 and actual tool versions. Platform AIDP/Harbor acceptance, 12h stability and official Hidden need real evidence; static checks do not imply them.

For each failure or gap: fact and file location → unmet rule → concrete repair → acceptance evidence. Never invent missing command/time/exit-code values; use null and explain. Close only the task sessions you created when done; preserve shared user tunnels and in-flight runs. [validation.md](references/validation.md) describes dated helper tests, not current Coding Plan or formal task acceptance.
