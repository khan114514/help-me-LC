# Frozen codec quantization

## Goal
Given a residual latent tensor and frozen entropy scales, implement a deterministic
integer quantizer that minimizes reconstruction DISTS under a fixed actual-bitstream
bitrate cap. Submit solution/method.py exporting quantize(y_res, scales, ctx).

## Task Setting
The codec weights, entropy coder and decoder are frozen. Your initial method is the
runnable naive dead-zone Baseline. There are 16 public development images; eight
separate images are injected only into the verifier. This task has no training.
The Baseline public DISTS is 0.1234255917 and mean bpp is 0.0200157166.

## Objective and Metrics
DISTS is minimized and measured from decoded images. Rate is the length of the real
entropy-coded bitstream, not an estimated proxy. On each scored split, mean bpp
must be at most the frozen Baseline mean bpp times 1.005. Full verification applies
this cap separately to public and hidden subsets, then averages DISTS over all 24
images in the fixed public-then-hidden order, in a fresh process.
Valid score = (B - DISTS) / (B - U), with no clipping; higher score is better.
B and U are frozen split anchors. A non-cheating hard-gate violation is invalid
and receives -1, excluded from valid ranking. Format, timeout, resource and
infrastructure failures have separate failure_type values and no valid score.

## Allowed Scope
Only /workspace/solution/method.py may be changed. Update its contents in place; its parent directory and solve.sh are protected. The interface is
quantize(y_res, scales, ctx) -> y_q. Inputs are same-shaped (B,C,H,W) tensors;
ctx contains shape, device and dtype. Return finite integer values with that shape.
You may read the frozen codec source, public inputs and public anchors. Do not
write the frozen source, weights, evaluator, public images or solve.sh.
Run /workspace/evaluate.sh to obtain trusted public development metrics.

## Hard Boundaries
Do not read hidden inputs, Reference or expert evidence, another trajectory,
credentials or host files. Do not modify scoring or fabricate results. Candidate
code runs in an unprivileged worker with no network creation, process execution
or privileged syscalls. It receives tensors only and cannot access verifier inputs
or reward files. A quantization call has a 60-second timeout; the evaluation
budget is 3600 seconds, with one GPU, eight CPUs and 32 GiB RAM. method.py must
be a regular file of at most 4 MiB. Every quantization call is checked twice; repeated input fingerprints must retain the same output.
The verifier uses a fresh environment and validates frozen assets and data hashes.
Public literature lookup follows platform tool policy; task tensors, weights,
images and bitstreams must not be sent to external services.

## Submission Instructions
Keep /workspace/solution/method.py as your most recent valid best method.
/workspace/solution/solve.sh is a frozen convenience entry point. No submitted
metrics or reward files are accepted as scores. The verifier loads method.py
through its isolated tensor worker and computes the score independently.

## Workflow & Iteration
This is an anytime task: implement a method, run /workspace/evaluate.sh, inspect
the trusted public score, then keep an improvement or restore the current best.
Each round records round, policy_name, method_summary, status, score,
failure_reason, retained_best and time. score records the actual public DISTS
raw metric; use null if unavailable. time is YYYY-MM-DD HH:mm:ss in the declared
run timezone. Failure rounds are preserved. The public evaluator serializes GPU
use when the platform supplies the shared trusted GPU lease.

## Completion Criteria
The submitted method runs, obeys the interface and deterministic/rate constraints,
produces a finite valid score, and leaves frozen assets unchanged. Preserve a
current best that successfully reruns under the same public protocol. The grader
independently verifies the final submission on the full fixed-order split.
