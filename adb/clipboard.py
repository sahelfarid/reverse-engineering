"""Best-effort clipboard read via a raw `service call clipboard` binder request,
plus a write path that requires a helper app. Android has no built-in ADB
command for clipboard access, and since Android 10 the clipboard service
itself restricts reads to the focused app, so this is inherently fragile
across OS versions/OEMs -- callers should treat failures as expected, not
exceptional.
"""
import re
import struct
from collections import deque

from . import manager

_HEX_WORD_RE = re.compile(r"[0-9a-fA-F]{8}")
_MAX_HISTORY = 50
_history: dict[str, deque] = {}


def _parse_service_call_reply(output: str) -> str | None:
    hex_words = []
    for line in output.splitlines():
        if ":" not in line:
            continue
        _prefix, _, rest = line.partition(":")
        rest = rest.split("'")[0]
        hex_words.extend(_HEX_WORD_RE.findall(rest))

    if len(hex_words) < 2:
        return None
    try:
        exception_code = int(hex_words[0], 16)
        length = int(hex_words[1], 16)
    except ValueError:
        return None
    if exception_code != 0 or length <= 0 or length > 100_000:
        return None

    code_units = []
    for word in hex_words[2:]:
        raw = bytes.fromhex(word)
        code_units.append(struct.unpack("<H", raw[0:2])[0])
        code_units.append(struct.unpack("<H", raw[2:4])[0])
        if len(code_units) >= length:
            break
    if not code_units:
        return None
    text = "".join(chr(c) for c in code_units[:length])
    return text or None


def get_clipboard(serial: str) -> dict:
    manager.validate_serial(serial)
    stdout, _stderr, rc = manager.shell(serial, "service call clipboard 2", timeout=10)
    if rc != 0 or not stdout.strip():
        return {"ok": False, "error": "clipboard_service_unavailable"}
    text = _parse_service_call_reply(stdout)
    if text is None:
        return {"ok": False, "error": "could_not_read_clipboard",
                 "detail": "Android 10+ restricts clipboard reads to the focused app, or this OEM's "
                           "binder reply format didn't match what we parse."}
    history = _history.setdefault(serial, deque(maxlen=_MAX_HISTORY))
    if not history or history[-1] != text:
        history.append(text)
    return {"ok": True, "text": text}


def get_clipboard_history(serial: str) -> list[str]:
    return list(_history.get(serial, []))


def set_clipboard(serial: str, text: str) -> dict:
    manager.validate_serial(serial)
    _stdout, _stderr, rc = manager.shell(
        serial, f"am broadcast -a clipper.set -e text {manager.quote_remote(text)}", timeout=10
    )
    if rc == 0:
        return {"ok": True, "note": "Sent via the 'Clipper' broadcast convention -- requires that helper "
                                     "app to be installed on the device; there is no built-in ADB clipboard-write."}
    return {"ok": False, "error": "clipboard_write_unsupported",
            "detail": "Writing the clipboard has no built-in ADB command; it requires a helper app "
                      "(e.g. Clipper) installed and listening for this broadcast."}
