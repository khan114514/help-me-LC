# Formal02 image-name contract audit

The first GPT checkpoint was rejected by an expert-ledger schema error. Frozen scorer `tests/run_eval.py` line208 uses `os.path.splitext(os.path.basename(path))[0]`, and line225 writes that stem into `per_image.image`. Ledger8ad lines41–45 contains asset filenames ending in `.png`; lines383–384 incorrectly compare metric names against those filenames. Lines456–458 correctly use the filename namespace for the public asset-hash map.

All five actual checkpoint rounds were rejected with `metrics_public_images`, with native_tools_verified=true and zero credited seconds. Native segment records exit0, pipeline0, turn.completed, no terminal model failure and67 successful tool calls of69attempted. Twenty exact data files are privately preserved with SHA. Five archived trusted receipts each match the expert-only source root's corresponding SHA; source files are0600 and root-owned. All trajectory rows have exactly eight canonical fields. These facts do not imply all remaining gates passed; the name guard was encountered first.

The old CPU fixture repeated the same mistake: line33 uses ledger.PUBLIC_NAMES for asset keys, and line111 also uses it for metric images. Thus the fixture and implementation agreed on a schema the frozen scorer never produces.

## Strict proposed repair

Split the fixed namespaces. `PUBLIC_ASSET_NAMES` remains the exact twelve `.png` asset filenames and continues to validate policy/receipt asset hashes. `PUBLIC_METRIC_NAMES` is the exact stem projection of that fixed whitelist. For the metric guard, require twelve dictionary rows, twelve unique string names equal to the exact stem whitelist, and split=public on every row. Do not call basename/stem on incoming metric data, case-fold it, accept paths, or accept a mix of stem and filename formats. No Task/scorer/prompt or other ledger gate needs weakening.

Adjust the CPU fixture so assets use filename keys while metrics use actual scorer stems, and add real frozen-scorer data as a contract test. Keep model/effort, source hashes, trusted mirror provenance, native process/tool evidence, code/node binding, Public12/25steps/100NFE/GPU, closure decisions, monotonic scorer duration, serial lease, exact/near duplicate exclusion and fixture zero-credit rules unchanged.

## Read-only reproduction and required full replay

The new audit script never imports the scorer, production ledger, or candidate. Pure-data replay confirms all five actual metric name sets fail the old guard and match the proposed exact stem guard. Eighteen positive/negative data cases pass: real stems and reordered rows; rejection of all `.png` names, a mixed suffix, path aliases, duplicate/unknown/case-changed/missing/extra/nonstring names, hidden split, nondictionary rows, and asset-map stems. This is a predicate/schema reproduction, not a repaired ledger or a full qualification replay. All data and fixture credit is zero.

Before a new formal attempt, a private repaired ledger needs a distinct frozen SHA and a complete meaningful CPU gate suite plus the actual five-round replay in explicit fixture/historical mode. Do not edit sealed formal02 receipts or restore its hours. The real-data replay must retain source/native/receipt hashes or transparently relocate read-only references; synthetic mutations must remain fixtures and can never pass the formal gate. Full replay may expose another independent rejection, which must be reported rather than assuming the namespace change admits every round.

Rounds1–3 use Starter or already known historical nodes. Round4 uses `f57fc7bd93c1ca12aa78f394eb68a3b77cefb356d5554307755ccf75f3a49f32`; round5 clean-reruns that same vector. For a fresh attempt, conservatively add that actual previously scored vector to the expert-private historical pool with its exact26nodes and trusted receipt provenance. This suggestion awards no old credit and does not claim its full prior admission. It need not be exposed to the Agent.

LedgerSourceSHA: `8ad72cdb73f4d27e1e2e941d29c3ef5ce339a51feb995779b216b7924ff23131`. ScorerSourceSHA: `23993adad6641121c03950e777089cb702a14e3c7a9f4cb0e9e55685542afaf9`. Task90bb and full prompt6bb are unchanged. Original files, production services, model/GPU work and qualification state were not modified by this audit.
