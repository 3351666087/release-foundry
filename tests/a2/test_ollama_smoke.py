import json
import os
import subprocess
import sys
import threading
import time
import unittest
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).parents[2]


class OllamaSmokeCliTests(unittest.TestCase):
    def run_smoke(self, handler, *extra):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(ROOT)
            return subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "scripts/a2_ollama_smoke.py",
                    "--model",
                    "unit-vision",
                    "--model-digest",
                    "sha256:" + "a" * 64,
                    "--base-url",
                    f"http://127.0.0.1:{server.server_port}",
                    *extra,
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_completion_is_public_safe_and_records_callable_digest(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                request_body = json.loads(self.rfile.read(length))
                self.assertEqual(request_body["options"]["num_predict"], 8)
                body = json.dumps({
                    "message": {"content": '{"passed":true}'},
                    "prompt_eval_count": 4,
                    "eval_count": 2,
                }).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                return

        Handler.assertEqual = self.assertEqual
        completed = self.run_smoke(Handler, "--num-predict", "8")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        evidence = json.loads(completed.stdout)
        self.assertEqual(evidence["status"], "completed")
        self.assertEqual(evidence["capability_state"], "callable")
        self.assertEqual(evidence["calibration_state"], "uncalibrated")
        self.assertEqual(evidence["model_digest"], "sha256:" + "a" * 64)
        self.assertIn(evidence["duration_bucket"], {"under_1s", "1_to_10s", "10_to_60s", "1_to_5m", "over_5m"})
        self.assertNotIn("output_text", evidence)
        self.assertNotIn("prompt", evidence)
        self.assertFalse(evidence["raw_payload_included"])
        self.assertFalse(evidence["secret_included"])

    def test_timeout_is_exit_two_and_never_marks_capability_callable(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                time.sleep(0.2)

            def log_message(self, *_):
                return

        completed = self.run_smoke(Handler, "--timeout-seconds", "0.02")
        self.assertEqual(completed.returncode, 2)
        evidence = json.loads(completed.stdout)
        self.assertEqual(evidence["status"], "timeout")
        self.assertEqual(evidence["capability_state"], "protocol_reachable")
        self.assertEqual(evidence["calibration_state"], "uncalibrated")
        self.assertNotEqual(evidence["capability_state"], "callable")
        self.assertFalse(evidence["raw_payload_included"])

    def test_timeout_must_be_finite_and_positive(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(value=value):
                completed = subprocess.run(
                    [
                        sys.executable, "-B", "scripts/a2_ollama_smoke.py",
                        "--model", "unit", "--timeout-seconds", value,
                    ],
                    cwd=ROOT,
                    env={**os.environ, "PYTHONPATH": str(ROOT)},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertIn("finite and strictly positive", completed.stderr)

    def test_num_predict_is_strictly_bounded_and_integer(self):
        for value in ("0", "257", "1.5"):
            with self.subTest(value=value):
                completed = subprocess.run(
                    [sys.executable, "-B", "scripts/a2_ollama_smoke.py", "--model", "unit", "--num-predict", value],
                    cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)},
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(completed.returncode, 2)

    def test_image_suffix_and_size_are_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            unsupported = Path(directory) / "evidence.gif"
            unsupported.write_bytes(b"x")
            completed = subprocess.run(
                [sys.executable, "-B", "scripts/a2_ollama_smoke.py", "--model", "unit", "--image", str(unsupported)],
                cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)},
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("must use", completed.stderr)
            oversized = Path(directory) / "evidence.png"
            oversized.write_bytes(b"xx")
            completed = subprocess.run(
                [sys.executable, "-B", "scripts/a2_ollama_smoke.py", "--model", "unit", "--image", str(oversized), "--max-image-bytes", "1"],
                cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)},
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("exceeds", completed.stderr)


if __name__ == "__main__":
    unittest.main()
