from adb.devices import _parse_devices_line


def test_parse_devices_line_authorized_usb():
    entry = _parse_devices_line(
        "R3CN30XXXX      device usb:1-1 product:redfin model:Pixel_5 device:redfin transport_id:1"
    )
    assert entry["serial"] == "R3CN30XXXX"
    assert entry["state"] == "device"
    assert entry["model"] == "Pixel_5"
    assert entry["transport_id"] == "1"
    assert entry["is_wireless"] is False


def test_parse_devices_line_unauthorized():
    entry = _parse_devices_line("R3CN30XXXX      unauthorized usb:1-1 transport_id:1")
    assert entry["state"] == "unauthorized"
    assert entry["model"] is None


def test_parse_devices_line_wireless():
    entry = _parse_devices_line("192.168.1.50:5555 device product:x model:y device:z transport_id:4")
    assert entry["is_wireless"] is True
    assert entry["serial"] == "192.168.1.50:5555"


def test_parse_devices_line_header_and_blank_ignored():
    assert _parse_devices_line("List of devices attached") is None
    assert _parse_devices_line("") is None
    assert _parse_devices_line("   ") is None
