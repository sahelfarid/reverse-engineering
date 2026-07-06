"""In-memory background job registry: async execution + progress + cancel
for long-running operations (APK installs, large pulls/exports). Fine for a
single-user local dev tool -- state doesn't need to survive a server restart.
"""
import re
import subprocess
import threading
import time
import uuid

from . import manager

_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_PROGRESS_RE = re.compile(r"(\d{1,3})%")


class JobCancelled(Exception):
    pass


def create_job(job_type: str, label: str = "") -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "id": job_id, "type": job_type, "label": label, "status": "pending",
            "progress": None, "message": "", "result": None, "error": None,
            "created_at": time.time(),
            "_cancel_event": threading.Event(), "_process": None,
        }
    return job_id


def _public(job: dict) -> dict:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def get_job(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return _public(job) if job else None


def get_job_raw(job_id: str) -> dict | None:
    with _lock:
        return _jobs.get(job_id)


def list_jobs() -> list[dict]:
    with _lock:
        ordered = sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)
        return [_public(j) for j in ordered[:50]]


def update_job(job_id: str, **fields) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def set_job_process(job_id: str, process) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["_process"] = process


def is_cancelled(job_id: str) -> bool:
    with _lock:
        job = _jobs.get(job_id)
        return bool(job and job["_cancel_event"].is_set())


def cancel_job(job_id: str) -> bool:
    with _lock:
        job = _jobs.get(job_id)
        if not job or job["status"] not in ("pending", "running"):
            return False
        job["_cancel_event"].set()
        proc = job.get("_process")
    if proc is not None:
        try:
            proc.terminate()
        except OSError:
            pass
    update_job(job_id, status="cancelled", message="Cancelled by user")
    return True


def run_in_background(job_id: str, target, *args, **kwargs) -> threading.Thread:
    def _runner():
        update_job(job_id, status="running")
        try:
            result = target(job_id, *args, **kwargs)
            if not is_cancelled(job_id):
                update_job(job_id, status="done", progress=100, result=result)
        except JobCancelled:
            pass
        except manager.AdbError as exc:
            if not is_cancelled(job_id):
                update_job(job_id, status="error", error=str(exc)[:500])
        except Exception as exc:  # noqa: BLE001 -- surfaced to the UI, not swallowed
            if not is_cancelled(job_id):
                update_job(job_id, status="error", error=f"unexpected error: {exc}"[:500])

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    return thread


def run_adb_with_progress(job_id: str, adb_path, args_after_adb: list[str], timeout: int | None = None) -> None:
    """Runs an adb subprocess, parsing any NN% occurrences in its output into
    job progress. adb's own progress output format isn't guaranteed stable
    across versions, so this is best-effort: absence of a match just leaves
    progress indeterminate rather than failing."""
    process = subprocess.Popen(
        [str(adb_path), *args_after_adb], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    set_job_process(job_id, process)
    last_progress = None
    start = time.time()
    for line in process.stdout:
        if is_cancelled(job_id):
            process.terminate()
            raise JobCancelled()
        if timeout and (time.time() - start) > timeout:
            process.terminate()
            raise manager.AdbError("operation timed out")
        match = _PROGRESS_RE.search(line)
        if match:
            pct = int(match.group(1))
            if pct != last_progress:
                update_job(job_id, progress=pct, message=line.strip()[:200])
                last_progress = pct
    process.wait(timeout=10)
    if is_cancelled(job_id):
        raise JobCancelled()
    if process.returncode != 0:
        raise manager.AdbError(f"command failed (exit code {process.returncode})")
