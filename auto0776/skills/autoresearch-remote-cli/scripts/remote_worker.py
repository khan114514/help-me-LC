#!/usr/bin/env python3
"""Run one bounded remote preparation job. This is not a Harbor harness."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import re

SEED_MODEL = "doubao-seed-2-1-turbo-260628"
ARK_URL = "https://ark.cn-beijing.volces.com/api/v3"
CODEX = "/opt/conda/bin/codex"
ARKCLI = "/opt/conda/bin/arkcli"
CUSTOM_URL = "https://modcon.top/v1"


def clean(value, secrets):
    for secret in secrets:
        if isinstance(secret, str) and secret:
            value = value.replace(secret, "[REDACTED]")
    # `codex login status` may expose a masked-but-still-sensitive key suffix.
    value = re.sub(r"sk-[A-Za-z0-9_*-]+", "[REDACTED]", value)
    return value


def run(command, env, cwd, timeout):
    process = subprocess.Popen(command, env=env, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, stdout, stderr, False
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        return process.returncode, stdout, stderr, True
    except BaseException:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise


def environment():
    names = {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "CUDA_VISIBLE_DEVICES",
             "HF_ENDPOINT", "HF_HOME", "HF_HUB_CACHE", "TORCH_HOME", "XDG_CACHE_HOME",
             "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
             "http_proxy", "https_proxy", "all_proxy", "no_proxy"}
    env = {key: value for key, value in os.environ.items() if key in names}
    env["PATH"] = env.get("PATH", "/opt/conda/bin:/usr/bin:/bin")
    return env


def runtime_evidence(operation, stdout):
    evidence = {"model_request_verified": False, "tool_commands_succeeded": 0,
                "tool_commands_failed": 0}
    if operation in {"ark", "ark-profile"}:
        try:
            response = json.loads(stdout)
            evidence["model_request_verified"] = response.get("status") == "completed"
            evidence["usage"] = response.get("usage")
        except (ValueError, AttributeError):
            pass
        return evidence
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "turn.completed":
            evidence["model_request_verified"] = True
            evidence["usage"] = event.get("usage")
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") == "command_execution":
            success = item.get("status") == "completed" and item.get("exit_code") == 0
            field = "tool_commands_succeeded" if success else "tool_commands_failed"
            evidence[field] += 1
    return evidence


def temporary_key(credentials, model, sdk_path):
    sys.path.insert(0, sdk_path)
    from volcenginesdkcore import ApiClient, Configuration
    import volcenginesdkark

    if not credentials.get("ark_ak") or not credentials.get("ark_sk"):
        raise ValueError("Missing Ark AK/SK in runtime memory.")
    cfg = Configuration()
    cfg.ak, cfg.sk = credentials["ark_ak"], credentials["ark_sk"]
    cfg.region, cfg.host, cfg.debug = "cn-beijing", "ark.cn-beijing.volcengineapi.com", False
    api = volcenginesdkark.ARKApi(ApiClient(cfg))
    return api.get_api_key(volcenginesdkark.GetApiKeyRequest(
        duration_seconds=600, project_name="default", resource_type="presetendpoint",
        resource_ids=[model]), _request_timeout=30).api_key


def doctor(env):
    commands = {
        "codex": [CODEX, "--version"], "arkcli": [ARKCLI, "--version"],
        "codex_login": [CODEX, "login", "status"],
        "sandbox_probe": [CODEX, "sandbox", "linux", "/bin/true"],
        "storage": ["df", "-h", "/", "${TRUSTED_RUNTIME_ROOT}/rivermind-data", "/tmp"],
        "gpu": ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader"],
    }
    result = {}
    for name, command in commands.items():
        try:
            code, stdout, stderr, timed_out = run(command, env, "/tmp", 15)
            result[name] = {"exit_code": code, "stdout": stdout, "stderr": stderr, "timed_out": timed_out}
        except OSError:
            result[name] = {"status": "unavailable"}
    safe_result = json.loads(clean(json.dumps(result), []))
    return {"status": "observed", "host": socket.gethostname(), "checks": safe_result,
            "model_request_verified": False, "research_score_verified": False}


def execute(request, secrets):
    operation = request.get("operation", "doctor")
    env = environment()
    if operation == "doctor":
        return doctor(env)
    if operation not in {"ark", "ark-profile", "codex-seed", "codex-seed-profile", "codex-openai", "codex-custom"}:
        raise ValueError("Unsupported operation.")
    timeout = request.get("timeout_seconds", 240)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 480:
        raise ValueError("timeout_seconds must be an integer from 1 to 480.")
    cwd = Path(request.get("cwd", "/tmp"))
    if not cwd.is_absolute() or not cwd.is_dir():
        raise ValueError("cwd must be an existing absolute remote directory.")
    prompt = request.get("prompt", "Reply exactly CLI_OK.")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a nonempty string.")
    credentials = request.get("credentials", {})
    model = request.get("model", "gpt-6.1-sol" if operation in {"codex-openai", "codex-custom"} else SEED_MODEL)
    output_limit = request.get("max_output_tokens", 128)
    sandbox = request.get("sandbox", "read-only")
    effort = request.get("reasoning_effort", "xhigh" if operation == "codex-custom" else "high")
    if operation in {"ark", "ark-profile"}:
        if isinstance(output_limit, bool) or not isinstance(output_limit, int) or not 1 <= output_limit <= 2048:
            raise ValueError("max_output_tokens must be from 1 to 2048.")
        if operation == "ark-profile" and effort not in {"minimal", "low", "medium", "high"}:
            raise ValueError("Unsupported Ark reasoning effort.")
    else:
        if sandbox not in {"read-only", "workspace-write"}:
            raise ValueError("Only read-only and workspace-write preparation modes are supported.")
        if effort not in {"minimal", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Unsupported reasoning effort; verify it against the actual model.")
        if request.get("requires_tools", True):
            probe = [CODEX, "sandbox", "linux", "/bin/true"]
            code, stdout, stderr, expired = run(probe, env, str(cwd), 15)
            if code != 0 or expired:
                return {"status": "preflight_error", "operation": operation,
                        "host": socket.gethostname(), "model_requested": model,
                        "message": "Remote sandbox probe failed; model request was not sent.",
                        "sandbox_probe": {"command": probe, "exit_code": code,
                                          "stdout": stdout, "stderr": stderr, "timed_out": expired},
                        "model_request_verified": False, "research_score_verified": False}
    if operation in {"ark", "codex-seed"}:
        key = temporary_key(credentials, model, request.get("sdk_path", "/tmp/autoresearch-volc-sdk"))
        secrets.append(key)
        env.update(ARK_API_KEY=key, ARK_BASE_URL=ARK_URL)
    elif operation in {"ark-profile", "codex-seed-profile"}:
        code, value, _, expired = run([ARKCLI, "profile", "apikey", "get", "--plain"], env, str(cwd), 20)
        if code != 0 or expired:
            raise ValueError("Unable to obtain the logged-in Ark profile key; complete remote arkcli login.")
        key = value.strip()
        secrets.append(key)
        if len(key) < 10 or any(character.isspace() for character in key):
            raise ValueError("Ark profile key output was not a valid single-line credential.")
        env.update(ARK_API_KEY=key, ARK_BASE_URL=ARK_URL)
    elif operation == "codex-custom":
        key = credentials.get("custom_api_key")
        if not isinstance(key, str) or not key:
            raise ValueError("Missing custom_api_key in runtime memory.")
        secrets.append(key)
        env["AUTORESEARCH_CUSTOM_API_KEY"] = key
        if request.get("use_forwarded_proxy", False):
            env.update(HTTPS_PROXY="http://127.0.0.1:17892", HTTP_PROXY="http://127.0.0.1:17892",
                       https_proxy="http://127.0.0.1:17892", http_proxy="http://127.0.0.1:17892")
    else:
        key = credentials.get("openai_api_key")
        if not key:
            code, _, _, expired = run([CODEX, "login", "status"], env, str(cwd), 15)
            if code != 0 or expired:
                raise ValueError("Remote OpenAI credentials missing: provide an authorized API key or fresh remote login; never copy local OAuth.")
        else:
            env["OPENAI_API_KEY"] = key
    if operation in {"ark", "ark-profile"}:
        payload = {"model": model, "input": prompt, "max_output_tokens": output_limit,
                   "thinking": {"type": "disabled"}, "store": False}
        if operation == "ark-profile":
            payload.update(thinking={"type": "enabled"}, reasoning={"effort": effort})
        command = [ARKCLI, "api", "arkruntime.create_responses", "--params", json.dumps(payload), "--format", "json"]
    else:
        saved_config = bool(request.get("use_saved_config", False))
        if saved_config:
            import tomllib
            if operation != "codex-custom":
                raise ValueError("use_saved_config is only supported for ModCon.")
            configuration = tomllib.loads((Path(env["HOME"]) / ".codex/config.toml").read_text())
            provider = configuration.get("model_providers", {}).get("custom", {})
            expected = {"base_url": CUSTOM_URL, "env_key": "AUTORESEARCH_CUSTOM_API_KEY",
                        "wire_api": "responses", "requires_openai_auth": False,
                        "http_headers": {"x-openai-actor-authorization": "local-image-extension"}}
            if (configuration.get("model_provider") != "custom" or
                    configuration.get("model") != model or
                    configuration.get("review_model") != model or
                    configuration.get("model_reasoning_effort") != effort or
                    any(provider.get(key) != value for key, value in expected.items())):
                raise ValueError("Saved remote ModCon configuration differs from the requested route.")
        command = [CODEX, "exec", "--ephemeral", "--json", "--ignore-user-config",
                   "--skip-git-repo-check", "-c", 'approval_policy="never"',
                   "--sandbox", sandbox, "-C", str(cwd), "-m", model,
                   "-c", "model_reasoning_effort=" + json.dumps(effort),
                   "-c", "shell_environment_policy.ignore_default_excludes=false",
                   "-c", 'shell_environment_policy.filters={"*KEY*"="exclude","*SECRET*"="exclude","*TOKEN*"="exclude","*PASSWORD*"="exclude"}',
                   "-c", "project_doc_max_bytes=8192"]
        if operation in {"codex-seed", "codex-seed-profile"}:
            command += ["--disable", "apps", "-c", 'model_provider="doubao"', "-c",
                        'model_providers.doubao={name="Doubao",base_url="' + ARK_URL + '",env_key="ARK_API_KEY",wire_api="responses"}']
        elif operation == "codex-custom" and not saved_config:
            command += ["--disable", "apps", "-c", 'model_provider="custom"',
                        "-c", "review_model=" + json.dumps(model),
                        "-c", "disable_response_storage=true", "-c",
                        'model_providers.custom={name="ModCon",base_url="' + CUSTOM_URL +
                        '",env_key="AUTORESEARCH_CUSTOM_API_KEY",wire_api="responses",requires_openai_auth=false,'
                        'http_headers={"x-openai-actor-authorization"="local-image-extension"}}']
        if saved_config:
            command.remove("--ignore-user-config")
            command[0] = "/opt/conda/bin/codex-modcon"
        command += [prompt]
    started = datetime.now(timezone.utc).isoformat()
    before = time.monotonic()
    code, stdout, stderr, timed_out = run(command, env, str(cwd), timeout)
    elapsed = time.monotonic() - before
    evidence = runtime_evidence(operation, stdout)
    status = "timeout" if timed_out else "ok" if code == 0 else "cli_error"
    if status == "ok" and not evidence["model_request_verified"]:
        status = "model_error"
    if status == "ok" and evidence["tool_commands_failed"] and not evidence["tool_commands_succeeded"]:
        status = "tool_error"
    return {"status": status,
            "host": socket.gethostname(), "operation": operation, "model_requested": model,
            "cwd": str(cwd), "command": command, "started_at": started,
            "provider": "ModCon" if operation == "codex-custom" else operation,
            "provider_base_url": CUSTOM_URL if operation == "codex-custom" else None,
            "reasoning_effort_requested": effort if operation != "ark" else None,
            "credential_source": "remote_arkcli_profile" if operation in {"ark-profile", "codex-seed-profile"} else "request_or_native_login",
            "forwarded_proxy_requested": bool(request.get("use_forwarded_proxy", False)),
            "saved_config_requested": bool(request.get("use_saved_config", False)),
            "response_storage_setting_status": ("unsupported" if "`disable_response_storage` is ignored" in stdout
                                                else "unverified") if operation == "codex-custom" else None,
            "finished_at": datetime.now(timezone.utc).isoformat(), "duration_seconds": elapsed,
            "exit_code": code, "stdout": stdout, "stderr": stderr,
            "research_score_verified": False, **evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    request, secrets, directory = {}, [], None
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            request = {}
            raise ValueError("Request must be a JSON object.")
        credentials = request.get("credentials", {})
        if not isinstance(credentials, dict):
            raise ValueError("credentials must be an object.")
        secrets.extend(value for value in credentials.values() if isinstance(value, str))
        if request.get("log_dir"):
            target = Path(request["log_dir"])
            if not target.is_absolute():
                raise ValueError("log_dir must be absolute.")
            target.mkdir(parents=True, mode=0o700, exist_ok=False)
            directory = target
        result = execute(request, secrets)
    except Exception as exc:
        result = {"status": "worker_error", "error_type": type(exc).__name__,
                  "message": clean(str(exc), secrets), "research_score_verified": False}
    output = clean(json.dumps(result, ensure_ascii=False), secrets)
    sanitized = json.loads(output)
    if directory:
        try:
            for name, field in [("stdout.log", "stdout"), ("stderr.log", "stderr")]:
                (directory / name).write_text(sanitized.get(field, ""))
            (directory / "execution.json").write_text(output + "\n")
        except (OSError, ValueError):
            sanitized["log_error"] = "Unable to persist private CLI evidence."
    print(json.dumps(sanitized, ensure_ascii=False), flush=True)
    return 0 if sanitized.get("status") in {"ok", "observed"} and "log_error" not in sanitized else 1


if __name__ == "__main__":
    raise SystemExit(main())
