# Remote execution under tutorial V4

Read [the V4 contract](phase3-v4-contract.md) for the phase-three rules. This reference describes remote preparation; it does not authorize requests or resume historical tasks. `requirements.txt` and `server-context.md` retain earlier task-specific requirements and observations. Current user instructions and V4 override their incompatible model, route, build-context and deployment examples.

## Check the selected server and route

1. Resolve the user's task and host from the session. Do not default new work to the old A100 alias or process named old tasks merely because they appear in a reference.
2. Inspect authorized live processes, filesystem boundaries, resources and tools over SSH without printing proxy tokens or secrets. A `doctor` result is inventory only. Recheck dated sandbox failures; do not bypass failed isolation.
3. Use the trusted controller and a tested credential-free model gateway. All Ark/Doubao/Seed requests terminate at Coding Plan `/api/coding/v3/chat/completions`. Only the trusted controller reads `${AUTHOR_HOME}/.config/ark/current.json`; keys never reach an Actor, candidate, request file, log or evidence archive.
4. Verify the exact requested model, supported effort, actual backend route and successful coding-tool events. Record what was actually served. If unsupported, stop that dependent call and report it; do useful independent preparation without replacing the model or falling back to `/api/v3`.

The legacy worker's `ark`, `ark-profile`, `codex-seed`, `codex-seed-profile` operations use obsolete routes/credential arrangements and are disabled by the current skill contract. Do not send them jobs. Merely changing their URL would not adapt a Responses client to Coding Plan Chat Completions. A working protocol gateway must be verified independently before use.

The retained worker may be used for read-only `doctor` or a separately authorized non-Ark route only after checking its actual implementation. A legacy test's exit code or old profile login is not a current route test. Never place credentials in a prompt, argv or `--request-file`; do not rely on redaction to authorize key delivery to an Actor.

## Prepare the task outside the candidate

Freeze method interface, data/version, complete formal seeds, metric/aggregation, budgets, B/R/U, quality gates, allowed files and actual runtime configuration. Record user-selected model settings separately from method-training seeds. Preserve raw failed and successful runs. No paid request is necessary to inspect or edit a skill.

Use the standard `workspace/harbor_task/` task root. Build Agent with `environment/` context and copy only public inputs. For a dedicated Verifier use `tests/` context; when reusing the Solver image, preinstall verifier dependencies and have Harbor upload tests into the new Verifier sandbox. Do not build with the historical task-root context or copy private tests into the public image.

Provide Public/Dev scoring inside the Agent sandbox, keep Hidden/Reference/expert/optimization evidence private, and declare exact artifact transfer paths. Each sandbox is one container. Agent and candidate execute directly on their allocated CPU/GPU; extra work containers, DinD/sibling Docker, remote GPU services and Compose are not valid task dependencies. An ordinary subprocess is allowed. The framework creates the final separate Verifier after Agent exit.

For actual phase-three GPU runs select H20 preferred or L20; CPU tasks remain at gpus=0. Other candidate gpu_types entries alone are not failure if H20/L20 is supported and actually selected. Preserve old hardware labels and recheck affected scores, timing and anchors after migration. Full round ≤2h, ≤8 allowed GPUs and ≤64 CPUs, with logs supporting estimates. Do not declare unsupported storage/network limits.

## Execute, transfer and record

- Perform real reproduction and complete formal paired B/R runs under the frozen protocol. Training tasks save required per-training checkpoints and reload/rescore evidence; random evaluation of one fixed model identifies the shared model instead of claiming independent training. Do not add empty model directories to nontraining tasks.
- Run two independently isolated model trajectories only after routes, scoring and prerequisites work. Same prompt/task/resources/protocol, separate empty outputs, ≥10 effective hours each, or all V4 ≥7h exception conditions. Sessions are optional evidence; if provided, inspect them.
- Append exactly eight fields per round: round, policy_name, method_summary, status, score, failure_reason, retained_best, time. Score is the actual declared Public/Dev raw/proxy metric; unavailable scores are null. Preserve failures. Actual models/efforts and effective time belong in run_summary and the expert explanation.
- Before exit put the retested best candidate and its required checkpoint/config in `/workspace/solution` or the declared equivalent. Framework artifacts transfer this directory only; no `/logs`, reward, evaluator or whole workspace. The Verifier executes `/tests/test.sh` and atomically writes finite reward.txt or a numeric reward.json object. Final Hidden is not iterative feedback.
- Choose one final best by valid normalized Public/Dev aggregate; keep only final code/entry/config in best_method, and clean-rerun it. Required trained model artifacts travel by the actual submission contract or approved immutable asset mechanism.
- Collect same-version NOP config/result/reward/log from the same Trial; platform complete records may be reused. Record actual build/run commands, contexts, image identities, upload/preload branch and results. NOP=0 alone is not failure.
- Use the real published task_fingerprint.py for task_binding over environment/, task.toml, tests/, instruction.md recursively, including hidden files and empty directories. Do not invent a compatible hash. Obtain missing official scripts before claiming that check complete.
- Format/GPU-check the repaired full ZIP, fix ERROR and address CHECK; recheck the final upload bytes and save ZIP SHA-256. Deliver workspace/, expert_evidence/, optimization_evidence/ together. Source-defined models/restricted assets retain their approved immutable/safe delivery mechanism.

Keep static inspection, local smoke, target Docker/Harbor validation, official Hidden, effective research time and 12h stability as separate evidence statuses. Report missing official 0.3.10 tools accurately. Do not modify old logs, reports or task records to imply current platform acceptance.
