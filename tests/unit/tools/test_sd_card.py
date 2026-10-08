"""Image and destructive-path checks without root, disks, mounts or card writes."""

import copy
import json
import lzma
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools import sd_card as sd


def card(**updates):
    result = dict(path="/dev/sdz", type="disk", size=32 * 1024**3,
                  tran="usb", rm=True, ro=False, serial="reader", model="SD", **{"maj:min": "8:240"},
                  mountpoints=[None], children=[dict(path="/dev/sdz1", type="part",
                                                   mountpoints=["/media/user/boot fs"])])
    result.update(updates)
    return result


@pytest.mark.parametrize("device", [card(type="part"), card(type="loop"),
                                    card(tran="nvme", rm=False), card(size=0),
                                    card(children=[dict(type="part", mountpoints=["/"])]),
                                    card(children=[dict(type="part", mountpoints=["/home"])]),
                                    card(children=[dict(type="part", mountpoints=["[SWAP]"])]),
                                    card(children=[dict(type="crypt", mountpoints=[])]),
                                    card(ro=True)])
def test_system_partitions_mapped_disks_and_write_protection_refused(device):
    with pytest.raises(ValueError):
        sd.safe_device(device, writing=True)


def test_read_only_card_can_be_backed_up():
    assert sd.safe_device(card(ro=True))


def test_unmount_preserves_mountpoint_spaces_and_rechecks(monkeypatch):
    original = card()
    current = copy.deepcopy(original)
    run = Mock()
    monkeypatch.setattr(sd, "run", run)
    monkeypatch.setattr(sd, "privileged", lambda args: ["sudo", *args])
    calls = [original, current]
    monkeypatch.setattr(sd, "recheck_device", lambda _: calls.pop(0))
    current["children"][0]["mountpoints"] = [None]
    sd.unmount_device(original)
    assert run.call_args_list[0].args[0] == ["sudo", "umount", "--", "/media/user/boot fs"]


def test_desktop_remount_stops_before_write(monkeypatch):
    monkeypatch.setattr(sd, "run", Mock())
    monkeypatch.setattr(sd, "recheck_device", lambda device: device)
    with pytest.raises(ValueError, match="remounted"):
        sd.unmount_device(card())


def test_device_replacement_refused(monkeypatch):
    monkeypatch.setattr(sd, "inventory", lambda: [card(serial="replacement")])
    with pytest.raises(ValueError, match="identity changed"):
        sd.recheck_device(card())


def test_image_on_selected_card_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(sd.subprocess, "check_output", lambda *args, **kwargs:
                        json.dumps({"filesystems": [{"source": "/dev/sdz1"}]}))
    with pytest.raises(ValueError, match="on the selected card"):
        sd.separate_storage(tmp_path, card())


def test_checksum_and_compressed_payload(tmp_path):
    payload = b"test image data" * 4096
    image = tmp_path / "sample.img.xz"
    image.write_bytes(lzma.compress(payload))
    expected = sd.checksum(image)
    assert sd.verify(image) == expected
    size, checksum = sd.image_details(image)
    assert size == len(payload)
    assert checksum == sd.hashlib.sha256(payload).hexdigest()
    image.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="mismatch"):
        sd.verify(image)


def test_missing_checksum_refused(tmp_path):
    image = tmp_path / "sample.img"
    image.write_bytes(b"data")
    with pytest.raises(ValueError, match="Missing checksum"):
        sd.verify(image)


def test_compression_corruption_refused_even_with_matching_file_checksum(tmp_path):
    image = tmp_path / "sample.img.xz"
    image.write_bytes(b"invalid compression")
    sd.checksum(image)
    sd.verify(image)
    with pytest.raises(lzma.LZMAError):
        sd.image_details(image)


def test_restore_capacity_refusal_does_not_confirm_or_spawn_writer(tmp_path, monkeypatch):
    image = tmp_path / "sample.img"
    image.write_bytes(b"image payload")
    sd.checksum(image)
    monkeypatch.setattr(sd, "check_tools", Mock())
    monkeypatch.setattr(sd, "choose_device", lambda *args, **kwargs: card(size=2))
    monkeypatch.setattr(sd, "separate_storage", Mock())
    confirm, writer = Mock(), Mock()
    monkeypatch.setattr(sd, "confirm", confirm)
    monkeypatch.setattr(sd.subprocess, "Popen", writer)
    with pytest.raises(ValueError, match="capacity"):
        sd.restore(image)
    confirm.assert_not_called()
    writer.assert_not_called()


def test_cancellation_refuses_operation(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "wrong device")
    with pytest.raises(ValueError, match="Cancelled"):
        sd.confirm("ERASE /dev/sdz")


def test_cached_pishrink_is_verified_before_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    cache = tmp_path / "pixeagle" / "sd-tools"
    cache.mkdir(parents=True)
    (cache / f"pishrink-{sd.PISHRINK_COMMIT}.sh").write_text("unexpected script")
    with pytest.raises(ValueError, match="checksum differs"):
        sd.pishrink_tool()
