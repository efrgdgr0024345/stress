"""Document parser supervisor; untrusted input never receives API credentials."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import secrets
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


class WorkerUnavailable(RuntimeError):
    pass


def execute(path, mode, page=0, heartbeat=lambda: None):
    """Use Docker isolation, Landlock, or an explicitly enabled restricted pilot."""
    with tempfile.TemporaryDirectory(prefix="caesar-parse-") as directory:
        work = Path(directory)
        shutil.copyfile(path, work / "input.pdf")
        container = os.environ.get("CAESAR_PIPELINE_IMAGE", "caesar-worker:local")
        use_docker = shutil.which("docker") and subprocess.run(
            ["docker", "image", "inspect", container], capture_output=True, timeout=10).returncode == 0
        if use_docker:
            container_name="caesar-parse-"+secrets.token_hex(8)
            command = ["docker", "run", "--name",container_name,"--rm", "--network=none", "--read-only",
                       "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=48",
                       "--memory=1536m", "--cpus=1", "--user", f"{os.getuid()}:{os.getgid()}",
                       "--mount", f"type=bind,src={work},dst=/job",
                       "--mount", f"type=bind,src={ROOT/'packages'},dst=/app/packages,readonly",
                       "--mount", f"type=bind,src={ROOT/'services'},dst=/app/services,readonly",
                       "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=64m", "--workdir=/job",
                       "--env", "CAESAR_SANDBOX_CONTAINER=1", "--env", "TMPDIR=/job", "--env", "PYTHONPATH=/app",
                       container, "/job/input.pdf", str(page), mode, "/job/result.json"]
            environment = {k:v for k,v in os.environ.items() if k in ("PATH", "DOCKER_HOST", "DOCKER_CONTEXT")}
            isolation = "container-no-network"
        else:
            pilot = os.environ.get("CAESAR_PIPELINE_ALLOW_BOUNDED") == "1"
            command = [sys.executable, "-m", "services.api.extract_worker", str(work/"input.pdf"),
                       str(page), mode, str(work/"result.json")]
            environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH":str(ROOT),
                           "HOME":str(work), "TMPDIR":str(work), "OMP_THREAD_LIMIT":"1"}
            if pilot:
                environment["CAESAR_BOUNDED_PILOT"] = "1"
            isolation = "bounded-pilot" if pilot else "landlock-seccomp"
        with (work/"private-stderr").open("wb") as errors:
            process = subprocess.Popen(command, cwd=work, env=environment,
                                       stdout=subprocess.DEVNULL, stderr=errors)
            import time
            started = time.monotonic()
            try:
                while process.poll() is None:
                    heartbeat()
                    if time.monotonic()-started > 225:
                        raise TimeoutError("EXTRACTION_TIMEOUT")
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        continue
                if process.returncode:
                    error = (work/"private-stderr").read_bytes()[-2000:]
                    if b"PARSER_ISOLATION_UNAVAILABLE" in error:
                        raise WorkerUnavailable("PARSER_ISOLATION_UNAVAILABLE")
                    raise ValueError("DOCUMENT_PROCESSING_FAILED")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                if use_docker:
                    subprocess.run(["docker","rm","-f",container_name],capture_output=True,timeout=15)
        result = work/"result.json"
        if result.is_symlink() or not result.is_file() or result.stat().st_size > 16*1024**2:
            raise ValueError("INVALID_WORKER_RESULT")
        value = json.loads(result.read_text())
        if isinstance(value, dict):
            value["isolation"] = isolation
        return value
