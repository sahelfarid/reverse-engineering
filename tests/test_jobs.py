import time
from unittest.mock import MagicMock, patch

import pytest

from adb import jobs, manager


def test_job_lifecycle_completes_successfully():
    job_id = jobs.create_job("test", label="demo")
    assert jobs.get_job(job_id)["status"] == "pending"

    def task(job_id):
        jobs.update_job(job_id, progress=50)
        return {"done": True}

    thread = jobs.run_in_background(job_id, task)
    thread.join(timeout=2)

    job = jobs.get_job(job_id)
    assert job["status"] == "done"
    assert job["progress"] == 100
    assert job["result"] == {"done": True}


def test_job_cancel_before_running():
    job_id = jobs.create_job("test")
    assert jobs.cancel_job(job_id) is True
    assert jobs.get_job(job_id)["status"] == "cancelled"


def test_job_cancel_is_idempotent_after_completion():
    job_id = jobs.create_job("test")
    jobs.update_job(job_id, status="done")
    assert jobs.cancel_job(job_id) is False


def test_job_error_is_captured():
    job_id = jobs.create_job("test")

    def failing_task(job_id):
        raise ValueError("boom")

    thread = jobs.run_in_background(job_id, failing_task)
    thread.join(timeout=2)

    job = jobs.get_job(job_id)
    assert job["status"] == "error"
    assert "boom" in job["error"]


def _fake_process(lines, returncode=0):
    proc = MagicMock()
    proc.stdout = iter(lines)
    proc.returncode = returncode
    proc.wait = MagicMock()
    return proc


def test_run_adb_with_progress_parses_and_dedupes_percentages():
    job_id = jobs.create_job("test")
    lines = ["Pulling... 10%\n", "Pulling... 10%\n", "Pulling... 55%\n", "Done\n"]
    fake_proc = _fake_process(lines, returncode=0)
    with patch("adb.jobs.subprocess.Popen", return_value=fake_proc):
        jobs.run_adb_with_progress(job_id, "/usr/bin/adb", ["pull", "x"])
    job = jobs.get_job_raw(job_id)
    assert job["progress"] == 55
    assert job["message"] == "Pulling... 55%"  # the trailing "Done" line has no %, so it leaves no new update


def test_run_adb_with_progress_sets_process_on_job():
    job_id = jobs.create_job("test")
    fake_proc = _fake_process(["no progress here\n"], returncode=0)
    with patch("adb.jobs.subprocess.Popen", return_value=fake_proc):
        jobs.run_adb_with_progress(job_id, "/usr/bin/adb", ["pull", "x"])
    assert jobs.get_job_raw(job_id)["_process"] is fake_proc


def test_run_adb_with_progress_raises_on_nonzero_exit():
    job_id = jobs.create_job("test")
    fake_proc = _fake_process(["no progress here\n"], returncode=1)
    with patch("adb.jobs.subprocess.Popen", return_value=fake_proc):
        with pytest.raises(manager.AdbError, match="exit code 1"):
            jobs.run_adb_with_progress(job_id, "/usr/bin/adb", ["pull", "x"])


def test_run_adb_with_progress_cancellation_terminates_and_raises():
    job_id = jobs.create_job("test")
    fake_proc = _fake_process(["line1\n", "line2\n"], returncode=0)
    with patch("adb.jobs.subprocess.Popen", return_value=fake_proc), \
         patch("adb.jobs.is_cancelled", return_value=True):
        with pytest.raises(jobs.JobCancelled):
            jobs.run_adb_with_progress(job_id, "/usr/bin/adb", ["pull", "x"])
    fake_proc.terminate.assert_called_once()


def test_run_adb_with_progress_raises_adb_error_on_timeout():
    job_id = jobs.create_job("test")
    fake_proc = _fake_process(["line1\n", "line2\n"], returncode=0)
    times = iter([0.0, 0.0, 100.0])  # start, then per-iteration elapsed checks
    with patch("adb.jobs.subprocess.Popen", return_value=fake_proc), \
         patch("adb.jobs.time.time", side_effect=lambda: next(times)):
        with pytest.raises(manager.AdbError, match="timed out"):
            jobs.run_adb_with_progress(job_id, "/usr/bin/adb", ["pull", "x"], timeout=5)
    fake_proc.terminate.assert_called_once()


def test_run_adb_with_progress_raises_job_cancelled_after_process_exits():
    # Cancelled between the last stdout line and process.wait() returning --
    # the loop's own cancel check never fires (only one line, not cancelled
    # yet), but the post-wait() check does.
    job_id = jobs.create_job("test")
    fake_proc = _fake_process(["line1\n"], returncode=0)
    with patch("adb.jobs.subprocess.Popen", return_value=fake_proc), \
         patch("adb.jobs.is_cancelled", side_effect=[False, True]):
        with pytest.raises(jobs.JobCancelled):
            jobs.run_adb_with_progress(job_id, "/usr/bin/adb", ["pull", "x"])
    fake_proc.terminate.assert_not_called()  # not cancelled mid-stream, so no mid-loop terminate() call
