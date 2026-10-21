#!/usr/bin/env python3
"""Check credential redaction, fail-fast behavior, and process timeout cleanup."""

import os
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import control
import remote_worker as worker


class WorkerSafetyTests(unittest.TestCase):
    def test_masked_key_redaction_preserves_serialized_json(self):
        payload = {"stderr": "Logged in with sk-test***abcd\n", "ok": True}
        sanitized = json.loads(worker.clean(json.dumps(payload), []))
        self.assertEqual(sanitized, {"stderr": "Logged in with [REDACTED]\n", "ok": True})

    def test_logged_in_ark_key_stays_in_memory_and_reply_is_verified(self):
        key = "test-ark-profile-key"
        response = json.dumps({"status": "completed", "usage": {"total_tokens": 87}})
        with patch.object(worker, "run", side_effect=[(0, key + "\n", "", False),
                                                      (0, response, "", False)]) as run:
            secrets = []
            result = worker.execute({"operation": "ark-profile", "cwd": tempfile.gettempdir(),
                                     "prompt": "Reply exactly SEED_CLI_OK."}, secrets)
        command, env, _, _ = run.call_args.args
        self.assertEqual(run.call_args_list[0].args[0], [worker.ARKCLI, "profile", "apikey", "get", "--plain"])
        self.assertEqual(env["ARK_API_KEY"], key)
        self.assertNotIn(key, " ".join(command))
        payload = json.loads(command[command.index("--params") + 1])
        self.assertEqual(payload["reasoning"], {"effort": "high"})
        self.assertFalse(payload["store"])
        self.assertTrue(result["model_request_verified"])
        self.assertEqual(worker.clean(key, secrets), "[REDACTED]")

    def test_seed_profile_sandbox_failure_prevents_key_read(self):
        with patch.object(worker, "run", return_value=(1, "", "namespace denied", False)) as run:
            result = worker.execute({"operation": "codex-seed-profile", "cwd": tempfile.gettempdir()}, [])
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], [worker.CODEX, "sandbox", "linux", "/bin/true"])
        self.assertEqual(result["status"], "preflight_error")

    @unittest.skipIf(sys.version_info < (3, 11), "Saved configuration uses remote Python 3.11+ tomllib")
    def test_saved_config_route_is_read_without_inline_provider_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".codex/config.toml"
            config.parent.mkdir()
            config.write_text('model_provider="custom"\nmodel="gpt-6.1-sol"\n'
                              'review_model="gpt-6.1-sol"\nmodel_reasoning_effort="xhigh"\n'
                              '[model_providers.custom]\nbase_url="https://modcon.top/v1"\n'
                              'env_key="AUTORESEARCH_CUSTOM_API_KEY"\nwire_api="responses"\n'
                              'requires_openai_auth=false\n'
                              'http_headers={"x-openai-actor-authorization"="local-image-extension"}\n')
            with patch.object(worker, "environment", return_value={"HOME": directory}), \
                    patch.object(worker, "run", return_value=(0, '{"type":"turn.completed"}', "", False)) as run:
                result = worker.execute({"operation": "codex-custom", "cwd": directory,
                                         "requires_tools": False, "use_saved_config": True,
                                         "credentials": {"custom_api_key": "test-relay-key"}}, [])
            command = run.call_args.args[0]
            self.assertEqual(command[0], "/opt/conda/bin/codex-modcon")
            self.assertNotIn("--ignore-user-config", command)
            self.assertFalse(any(value.startswith("model_providers.custom=") for value in command))
            self.assertTrue(result["saved_config_requested"])
            self.assertEqual(result["status"], "ok")

    @unittest.skipIf(sys.version_info < (3, 11), "Saved configuration uses remote Python 3.11+ tomllib")
    def test_saved_config_mismatch_stops_before_model_request(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".codex/config.toml"
            config.parent.mkdir()
            config.write_text('model_provider="openai"\nmodel="gpt-6.1-sol"\n')
            with patch.object(worker, "environment", return_value={"HOME": directory}), \
                    patch.object(worker, "run") as run:
                with self.assertRaisesRegex(ValueError, "differs"):
                    worker.execute({"operation": "codex-custom", "cwd": directory,
                                    "requires_tools": False, "use_saved_config": True,
                                    "credentials": {"custom_api_key": "test-relay-key"}}, [])
            run.assert_not_called()

    def test_custom_provider_uses_transient_key_and_skips_native_login(self):
        key = "test-relay-credential"
        events = json.dumps({"type": "turn.completed", "usage": {"output_tokens": 3}})
        with patch.object(worker, "run", return_value=(0, events, "", False)) as run:
            secrets = []
            result = worker.execute({"operation": "codex-custom", "cwd": tempfile.gettempdir(),
                                     "requires_tools": False,
                                     "use_forwarded_proxy": True,
                                     "credentials": {"custom_api_key": key}}, secrets)
        run.assert_called_once()
        command, env, _, _ = run.call_args.args
        self.assertNotIn(key, " ".join(command))
        self.assertEqual(env["AUTORESEARCH_CUSTOM_API_KEY"], key)
        self.assertEqual(env["HTTPS_PROXY"], "http://127.0.0.1:17892")
        self.assertIn("apps", command)
        self.assertIn('model_provider="custom"', command)
        self.assertIn('model_reasoning_effort="xhigh"', command)
        self.assertIn('review_model="gpt-6.1-sol"', command)
        self.assertIn("disable_response_storage=true", command)
        provider = next(value for value in command if value.startswith("model_providers.custom="))
        self.assertIn("requires_openai_auth=false", provider)
        self.assertIn(worker.CUSTOM_URL, provider)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["model_request_verified"])
        self.assertEqual(worker.clean(key, secrets), "[REDACTED]")

    def test_custom_provider_does_not_fallback_to_native_auth(self):
        with patch.object(worker, "run") as run:
            with self.assertRaisesRegex(ValueError, "custom_api_key"):
                worker.execute({"operation": "codex-custom", "cwd": tempfile.gettempdir(),
                                "requires_tools": False}, [])
        run.assert_not_called()

    def test_custom_failed_sandbox_prevents_model_request(self):
        with patch.object(worker, "run", return_value=(1, "", "namespace denied", False)) as run:
            result = worker.execute({"operation": "codex-custom", "cwd": tempfile.gettempdir(),
                                     "credentials": {"custom_api_key": "test-relay"}}, [])
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], [worker.CODEX, "sandbox", "linux", "/bin/true"])
        self.assertEqual(result["status"], "preflight_error")
        self.assertFalse(result["model_request_verified"])

    def test_long_credentials_do_not_reach_child_environment(self):
        with patch.dict(os.environ, {"VOLC_ACCESSKEY": "test-ak", "VOLC_SECRETKEY": "test-sk",
                                     "OPENAI_API_KEY": "test-openai", "HTTPS_PROXY": "http://proxy"}):
            env = worker.environment()
        self.assertFalse({"VOLC_ACCESSKEY", "VOLC_SECRETKEY", "OPENAI_API_KEY"} & env.keys())
        self.assertEqual(env["HTTPS_PROXY"], "http://proxy")

    def test_invalid_job_does_not_mint_key(self):
        with patch.object(worker, "temporary_key") as mint:
            with self.assertRaises(ValueError):
                worker.execute({"operation": "codex-seed", "cwd": tempfile.gettempdir(),
                                "sandbox": "danger-full-access"}, [])
        mint.assert_not_called()

    def test_redaction_preserves_log_information(self):
        self.assertEqual(worker.clean("before secret-key after", ["secret-key"]),
                         "before [REDACTED] after")

    def test_zero_cli_exit_does_not_prove_tool_execution(self):
        import json
        events = [
            {"type": "item.completed", "item": {"type": "command_execution", "status": "failed", "exit_code": 1}},
            {"type": "turn.completed", "usage": {"input_tokens": 10}},
        ]
        evidence = worker.runtime_evidence("codex-seed", "\n".join(json.dumps(event) for event in events))
        self.assertTrue(evidence["model_request_verified"])
        self.assertEqual(evidence["tool_commands_succeeded"], 0)
        self.assertEqual(evidence["tool_commands_failed"], 1)

    def test_timeout_kills_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "unexpected-child-output"
            child = "import time,pathlib;time.sleep(2);pathlib.Path(" + repr(str(marker)) + ").touch()"
            parent = "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c'," + repr(child) + "]);time.sleep(20)"
            code, _, _, timed_out = worker.run([sys.executable, "-c", parent], os.environ.copy(), directory, 0.2)
            self.assertTrue(timed_out)
            self.assertNotEqual(code, 0)
            import time
            time.sleep(2.1)
            self.assertFalse(marker.exists())

    def test_large_interactive_request_is_not_truncated(self):
        import json
        import subprocess
        import termios

        master, slave = os.openpty()
        process = subprocess.Popen([sys.executable, "-c", "import control,json;print(json.dumps(control.read_request()))"],
                                   cwd=Path(__file__).parent, stdin=slave,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertIn("REQUEST_INPUT_READY", process.stderr.readline())
            self.assertFalse(termios.tcgetattr(slave)[3] & termios.ECHO)
            value = {"prompt": "x" * 12000}
            data = (json.dumps(value) + "\n").encode()
            for start in range(0, len(data), 512):
                os.write(master, data[start:start + 512])
            stdout, _ = process.communicate(timeout=5)
            self.assertEqual(json.loads(stdout), value)
            self.assertTrue(termios.tcgetattr(slave)[3] & termios.ECHO)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)


if __name__ == "__main__":
    unittest.main()
