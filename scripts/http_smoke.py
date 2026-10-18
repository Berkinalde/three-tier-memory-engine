"""Local authenticated HTTP smoke, using only temporary synthetic data."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from uuid import uuid4


def main():
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        token = uuid4().hex
        token_file = folder / "tokens.json"
        token_file.write_text(json.dumps({token: {"tenant_id": "smoke", "user_id": "learner"}}))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {
            **os.environ,
            "MEMORY_TOKEN_FILE": str(token_file),
            "MEMORY_DB": str(folder / "memory.db"),
            "MEMORY_DEVELOPMENT": "0",
        }
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "memory_engine.api:app_from_env",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}"

        def request(path, data=None, method=None):
            req = urllib.request.Request(
                base + path,
                data=None if data is None else json.dumps(data).encode(),
                method=method,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as response:
                return response.status, json.load(response)

        try:
            for _ in range(50):
                try:
                    assert request("/health")[0] == 200
                    break
                except (OSError, urllib.error.URLError):
                    if process.poll() is not None:
                        raise RuntimeError("server_exited")
                    time.sleep(0.1)
            else:
                raise RuntimeError("server_start_timeout")
            status, record = request("/v1/memories", {"tier": "episodic", "content": "IAM HTTP smoke"})
            assert status == 201
            assert request("/v1/memories/search", {"query": "IAM"})[1][0]["id"] == record["id"]
            updated = request(
                "/v1/memories/" + record["id"],
                {"expected_version": 1, "changes": {"content": "IAM updated"}},
                "PATCH",
            )[1]
            assert updated["version"] == 2
            assert request("/v1/memories/" + record["id"], method="DELETE")[1]["deleted"] == 1
            assert request("/v1/memories/search", {"query": "IAM"})[1] == []
            print(json.dumps({"health": "passed", "authenticated_http_crud": "passed", "host": "127.0.0.1"}))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
