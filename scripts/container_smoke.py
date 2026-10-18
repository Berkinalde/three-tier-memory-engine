"""Start one isolated dev container; test health+restart persistence; remove own resources."""

import argparse
import json
import subprocess
import time
import urllib.request
from uuid import uuid4


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="memory-engine:local")
    args = parser.parse_args()
    name = "memory-smoke-" + uuid4().hex[:10]
    volume = name + "-data"
    identifier = None
    try:
        docker("volume", "create", volume)
        identifier = docker(
            "run",
            "-d",
            "--name",
            name,
            "-e",
            "MEMORY_DEVELOPMENT=1",
            "-v",
            volume + ":/data",
            "-p",
            "127.0.0.1::8000",
            args.image,
        )

        def address():
            return "http://" + docker("port", name, "8000/tcp").splitlines()[0]

        def wait_health():
            deadline = time.monotonic() + 50
            while time.monotonic() < deadline:
                state = json.loads(docker("inspect", name))[0]["State"]
                if state.get("Health", {}).get("Status") == "healthy":
                    return
                if not state["Running"]:
                    raise RuntimeError("container_exited")
                time.sleep(1)
            raise RuntimeError("container_health_timeout")

        def request(path, data):
            req = urllib.request.Request(
                address() + path,
                data=json.dumps(data).encode(),
                headers={"Content-Type": "application/json", "X-Dev-Tenant": "smoke", "X-Dev-User": "test"},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.load(response)

        wait_health()
        record = request("/v1/memories", {"tier": "episodic", "content": "IAM container persistence"})
        docker("restart", name)
        wait_health()
        found = request("/v1/memories/search", {"query": "IAM"})
        assert found[0]["id"] == record["id"]
        print(json.dumps({"health": "passed", "restart_persistence": "passed", "image": args.image}))
    finally:
        if identifier:
            docker("rm", "-f", identifier)
        docker("volume", "rm", volume)


if __name__ == "__main__":
    main()
