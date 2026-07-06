import struct
from unittest.mock import patch

import pytest

from adb import clipboard
from adb.clipboard import _parse_service_call_reply


def _build_service_call_reply(text: str) -> str:
    length = len(text)
    words = [f"{0:08x}", f"{length:08x}"]
    units = [ord(c) for c in text]
    if len(units) % 2 == 1:
        units.append(0)
    for i in range(0, len(units), 2):
        chunk = struct.pack("<H", units[i]) + struct.pack("<H", units[i + 1])
        words.append(chunk.hex())
    return "0x00000000: " + " ".join(words)


def test_parse_service_call_reply_roundtrip():
    assert _parse_service_call_reply(_build_service_call_reply("hello")) == "hello"


def test_parse_service_call_reply_empty_or_garbage_returns_none():
    assert _parse_service_call_reply("") is None
    assert _parse_service_call_reply("Result: Parcel(00000000 ") is None


def test_parse_service_call_reply_exception_code_nonzero_returns_none():
    # exception code 1 (word[0] != 0) signals a binder exception -> no usable text
    line = "0x00000000: 00000001 00000005"
    assert _parse_service_call_reply(line) is None


@pytest.fixture(autouse=True)
def clear_clipboard_history():
    clipboard._history.clear()
    yield
    clipboard._history.clear()


def test_get_clipboard_success_records_history():
    reply = _build_service_call_reply("hello")
    with patch("adb.clipboard.manager.validate_serial", return_value="s1"), \
         patch("adb.clipboard.manager.shell", return_value=(reply, "", 0)):
        result = clipboard.get_clipboard("s1")
    assert result == {"ok": True, "text": "hello"}
    assert clipboard.get_clipboard_history("s1") == ["hello"]


def test_get_clipboard_does_not_duplicate_consecutive_history_entries():
    reply = _build_service_call_reply("hello")
    with patch("adb.clipboard.manager.validate_serial", return_value="s1"), \
         patch("adb.clipboard.manager.shell", return_value=(reply, "", 0)):
        clipboard.get_clipboard("s1")
        clipboard.get_clipboard("s1")
    assert clipboard.get_clipboard_history("s1") == ["hello"]


def test_get_clipboard_service_unavailable():
    with patch("adb.clipboard.manager.validate_serial", return_value="s1"), \
         patch("adb.clipboard.manager.shell", return_value=("", "err", 1)):
        result = clipboard.get_clipboard("s1")
    assert result == {"ok": False, "error": "clipboard_service_unavailable"}


def test_get_clipboard_unparseable_reply():
    with patch("adb.clipboard.manager.validate_serial", return_value="s1"), \
         patch("adb.clipboard.manager.shell", return_value=("garbage output", "", 0)):
        result = clipboard.get_clipboard("s1")
    assert result["ok"] is False
    assert result["error"] == "could_not_read_clipboard"


def test_get_clipboard_history_empty_for_unknown_serial():
    assert clipboard.get_clipboard_history("never-seen") == []


def test_set_clipboard_success_and_failure():
    with patch("adb.clipboard.manager.validate_serial", return_value="s1"), \
         patch("adb.clipboard.manager.shell", return_value=("", "", 0)) as mock_shell:
        result = clipboard.set_clipboard("s1", "hello world")
    assert result["ok"] is True
    assert "clipper.set" in mock_shell.call_args[0][1]

    with patch("adb.clipboard.manager.validate_serial", return_value="s1"), \
         patch("adb.clipboard.manager.shell", return_value=("", "err", 1)):
        result = clipboard.set_clipboard("s1", "hello world")
    assert result == {
        "ok": False, "error": "clipboard_write_unsupported",
        "detail": (
            "Writing the clipboard has no built-in ADB command; it requires a helper app "
            "(e.g. Clipper) installed and listening for this broadcast."
        ),
    }
