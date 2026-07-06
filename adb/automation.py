"""Input automation: tap/swipe/text/keyevent + simple macro record/playback."""
import re
import time

import config
from . import manager

_KEYCODE_RE = re.compile(r"^[A-Za-z0-9_]+$")
MAX_MACRO_STEPS = 200
MAX_MACRO_WAIT_MS = 60_000


def tap(serial: str, x: int, y: int) -> dict:
    _stdout, _stderr, rc = manager.shell(serial, f"input tap {int(x)} {int(y)}", timeout=10)
    return {"ok": rc == 0}


def swipe(serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> dict:
    _stdout, _stderr, rc = manager.shell(
        serial, f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(duration_ms)}", timeout=10
    )
    return {"ok": rc == 0}


def long_press(serial: str, x: int, y: int, duration_ms: int = 800) -> dict:
    return swipe(serial, x, y, x, y, duration_ms)


def type_text(serial: str, text: str) -> dict:
    android_escaped = text.replace(" ", "%s")
    _stdout, _stderr, rc = manager.shell(serial, f"input text {manager.quote_remote(android_escaped)}", timeout=10)
    return {"ok": rc == 0}


def get_screen_size(serial: str) -> dict:
    stdout, _stderr, rc = manager.shell(serial, "wm size", timeout=10)
    match = re.search(r"(?:Override|Physical) size:\s*(\d+)x(\d+)", stdout)
    if not match:
        match = re.search(r"(\d+)x(\d+)", stdout)
    if rc != 0 or not match:
        return {"width": None, "height": None}
    return {"width": int(match.group(1)), "height": int(match.group(2))}


def keyevent(serial: str, code: str) -> dict:
    code = str(code).strip()
    if not _KEYCODE_RE.match(code):
        return {"ok": False, "error": "invalid_keycode"}
    _stdout, _stderr, rc = manager.shell(serial, f"input keyevent {code}", timeout=10)
    return {"ok": rc == 0}


_STEP_HANDLERS = {
    "tap": lambda serial, s: tap(serial, s["x"], s["y"]),
    "swipe": lambda serial, s: swipe(serial, s["x1"], s["y1"], s["x2"], s["y2"], s.get("duration_ms", 300)),
    "long_press": lambda serial, s: long_press(serial, s["x"], s["y"], s.get("duration_ms", 800)),
    "text": lambda serial, s: type_text(serial, s["text"]),
    "keyevent": lambda serial, s: keyevent(serial, s["code"]),
}


def validate_macro_steps(steps: list) -> None:
    if len(steps) > MAX_MACRO_STEPS:
        raise manager.AdbError(f"macro has too many steps (max {MAX_MACRO_STEPS})")
    total_wait = sum(s.get("wait_ms", 0) for s in steps if s.get("type") == "wait")
    if total_wait > MAX_MACRO_WAIT_MS:
        raise manager.AdbError("macro total wait time exceeds limit")
    for step in steps:
        if step.get("type") not in (*_STEP_HANDLERS, "wait"):
            raise manager.AdbError(f"unknown macro step type: {step.get('type')}")


def play_macro(serial: str, steps: list) -> dict:
    validate_macro_steps(steps)
    results = []
    for step in steps:
        step_type = step["type"]
        if step_type == "wait":
            time.sleep(min(step.get("wait_ms", 0), MAX_MACRO_WAIT_MS) / 1000)
            results.append({"type": "wait", "ok": True})
            continue
        result = _STEP_HANDLERS[step_type](serial, step)
        results.append({"type": step_type, **result})
    return {"ok": all(r.get("ok") for r in results), "results": results}


def list_macros() -> dict:
    return config.load_macros()


def save_macro(name: str, steps: list) -> dict:
    validate_macro_steps(steps)
    macros = config.load_macros()
    macros[name] = steps
    config.save_macros(macros)
    return {"ok": True}


def delete_macro(name: str) -> dict:
    macros = config.load_macros()
    if name in macros:
        del macros[name]
        config.save_macros(macros)
    return {"ok": True}
