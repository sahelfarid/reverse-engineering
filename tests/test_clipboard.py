import struct

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
