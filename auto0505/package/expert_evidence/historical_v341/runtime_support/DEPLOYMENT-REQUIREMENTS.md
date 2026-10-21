# Expert runtime deployment requirements

Tested Harbor version: 0.23.0. This is recorded independently in the current
NOP native harbor-job/lock.json, formal-run04-installed-precheck.json and
task-v341-static-qa/remote-readonly-task-check.stdout. Task schema_version1.3
is a separate configuration field, not the installed Harbor version.
See ../TASK-AND-RUNTIME-BINDING.json for exact task name/directory bindings.

The tested Task uses separate CPU Actor/Verifier containers (2 CPU, 2048 MiB,
GPU0), with real FLUX scoring performed on the expert private A100 runtime.
NOP and Reference full16 passed under this deployment. The ZIP alone does not
establish acceptance on an arbitrary platform or bare Docker installation.

Provision the numeric controller and socket gateway, frozen GPU worker, model
weights, private Hidden inputs, and separate Public/formal UDS. Provision the
GPT/Seed model bridges and separate model UDS with authorized backend identities.
Credentials must be acquired in runtime memory, never bundled in this archive.
Apply the documented read-only mounts, isolated resources and private verifier.

source/ contains the existing tested nonsecret controller/gateway/worker/bridge
code for deployment review. Production absolute paths and SSH aliases describe
this experiment, not a verified platform installation. External platform
deployment and registration remain unverified; task_id is null.
