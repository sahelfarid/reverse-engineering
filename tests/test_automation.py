import pytest

from adb import manager
from adb.automation import MAX_MACRO_STEPS, MAX_MACRO_WAIT_MS, validate_macro_steps


def test_validate_macro_steps_accepts_known_types():
    steps = [{"type": "tap", "x": 1, "y": 2}, {"type": "wait", "wait_ms": 100}, {"type": "text", "text": "hi"}]
    validate_macro_steps(steps)  # should not raise


def test_validate_macro_steps_rejects_unknown_type():
    with pytest.raises(manager.AdbError):
        validate_macro_steps([{"type": "launch_nuclear_missiles"}])


def test_validate_macro_steps_rejects_too_many_steps():
    steps = [{"type": "tap", "x": 0, "y": 0}] * (MAX_MACRO_STEPS + 1)
    with pytest.raises(manager.AdbError):
        validate_macro_steps(steps)


def test_validate_macro_steps_rejects_excessive_wait():
    steps = [{"type": "wait", "wait_ms": MAX_MACRO_WAIT_MS + 1}]
    with pytest.raises(manager.AdbError):
        validate_macro_steps(steps)
