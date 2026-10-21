"""Use the exact pinned Alpine config in an offline legacy Docker image store.

Harbor 0.23's upstream kernel probe pins Alpine 3.23.4 OCI index
sha256:5b10f432ef3da1b8d4c7eb6c487f2f5a8f096bc91145e68878dd4a5019afde11.
Docker save/load into overlay2 preserves the amd64 image config, but does not
preserve its OCI index reference. The config below is that exact amd64 image;
the inherited Harbor kernel probe script and its success condition are unchanged.
Provision this image from the verified upstream OCI archive before using this
adapter. This is an organizer adapter outside candidate build contexts.
"""
from onedc_harbor import OneDCDockerEnvironment


class OfflineOneDCDockerEnvironment(OneDCDockerEnvironment):
    _EGRESS_CONTROL_KERNEL_PROBE_IMAGE = (
        "sha256:3cb067eab609612d81b4d82ff8ad71d73482bb3059a87b642d7e14f0ed659cde"
    )
