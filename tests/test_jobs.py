import time

from adb import jobs


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
