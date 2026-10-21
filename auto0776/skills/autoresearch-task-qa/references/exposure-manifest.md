> 三期V4更新：先读 [当前教程合同](phase3-v4-contract.md)。本文件保留旧版工具的参考细节；与V4冲突时，以V4为准，包括可复用Solver镜像、资源/GPU估算、轨迹可选sessions与四项指纹。旧脚本不代表官方0.3.10或当前内场验收。

# Exposure manifest

Place `qa_exposure_manifest.json` at the workspace root when the actual Agent
view is narrower than the authoring bundle. Example:

```json
{
  "schema_version": 1,
  "agent_visible_paths": [
    "INIT_PROMPT.md",
    "harbor_task/instruction.md",
    "harbor_task/task.toml",
    "harbor_task/environment/starter",
    "harbor_task/environment/public_assets",
    "harbor_task/environment/public_eval"
  ],
  "agent_writable_paths": ["/workspace/solution"],
  "trusted_only_paths": ["harbor_task/tests", "expert_evidence"],
  "final_image_digest": "sha256:...",
  "verifier_image_digest": "sha256:...",
  "generated_agent_view_manifest": "evidence/agent-view-files.sha256",
  "verified_as_uid": 1000
}
```

Paths inside the bundle are workspace-relative; runtime-only paths are absolute.
The checker currently uses `agent_visible_paths` to scope static leak detection.
Final private evaluation materials belong only in the separate Verifier
environment. Hidden paths may vary; preparation may be prebuilt, generated, or
securely injected with implementation and invocation evidence. Public Dev
evaluation belongs in the Agent view. Source `harbor_task/solution` is optional
Oracle material, not the Agent runtime submission directory. Private materials
must be absent from Agent image layers and runtime mounts. Cite both image digests and the actual Agent view when
reviewing isolation.
All other fields guide manual/dynamic checks. A trusted runner must regenerate a
recursive path/type/mode/owner/hash list from the final image plus mounts and
compare it with `generated_agent_view_manifest`. Reject extra files, symlinks,
special files, unexpected writable ancestors, and digest mismatches.
