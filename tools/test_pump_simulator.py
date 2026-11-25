"""Tests for the bench tester.

    uv run --with pyserial --with pytest pytest -p no:cacheprovider tools -q

The loopback tests run the simulated pump against a small Python model of a
MODBUS 40 accessory over a pseudo-terminal pair, so no hardware is needed.
"""
import os
import select
import struct
import sys
import threading
import time
import tty

import pytest
import serial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pump_simulator as ps  # noqa: E402


# --------------------------------------------------------------------------- frame vectors
def test_read_token_vector_from_docs():
    assert ps.pump_frame(0x20, 0x69) == bytes.fromhex("5C 00 20 69 00 49")
    assert ps.parse_pump_frame(bytes.fromhex("5C 00 20 69 00 49")) == (0x20, 0x69, b"")


def test_read_request_vector_from_docs():
    raw = bytes.fromhex("C0 69 02 24 AC 23")
    assert ps.read_request(0xAC24) == raw
    assert ps.parse_accessory_frame(raw) == (0x69, bytes.fromhex("24 AC"))


def test_escaped_read_response_vector_from_docs():
    raw = bytes.fromhex("5C 00 20 6A 07 73 B0 5C 5C 00 00 00 8E")
    address, cmd, data = ps.parse_pump_frame(raw)
    assert (address, cmd) == (0x20, 0x6A)
    assert data == bytes.fromhex("73 B0 5C 00 00 00")
    # building the same frame gives the same bytes
    assert ps.pump_frame(0x20, 0x6A, data) == raw


def test_write_request_vector_from_nibepi():
    # NibePi resets alarms by writing 1 to register 45171
    assert ps.write_request(45171, 1) == bytes.fromhex("C0 6B 06 73 B0 01 00 00 00 6F")


def test_checksum_0x5c_is_sent_as_0xc5():
    # C0 ^ 69 ^ 02 = AB, and AB ^ F7 = 5C
    body = bytes([0xC0, 0x69, 0x02, 0xF7, 0x00])
    assert ps.xor(body) == 0x5C
    frame = ps.accessory_frame(0x69, bytes([0xF7, 0x00]))
    assert frame[-1] == 0xC5
    assert ps.parse_accessory_frame(frame) == (0x69, bytes([0xF7, 0x00]))


def test_bad_checksum_is_rejected():
    raw = bytearray(ps.pump_frame(0x20, 0x68, ps.data_payload({40004: 215})))
    raw[-1] ^= 0x01
    with pytest.raises(ps.FrameError):
        ps.parse_pump_frame(bytes(raw))


def test_data_payload_round_trip_with_5c_bytes():
    regs = {40004: 215, 40008: 0x5C5C, 0x5C5C: 7}
    frame = ps.pump_frame(0x20, 0x68, ps.data_payload(regs))
    assert frame.count(b"\x5c\x5c") >= 2
    _, _, data = ps.parse_pump_frame(frame)
    assert dict(struct.iter_unpack("<HH", data)) == regs


# --------------------------------------------------------------------------- reference accessory
class Accessory(threading.Thread):
    """Minimal MODBUS 40 accessory (what NibeGW does), talking on a pty fd."""

    def __init__(self, fd, delay=0.002, silent_after=None, corrupt=False):
        super().__init__(daemon=True)
        self.fd = fd
        self.delay = delay
        self.silent_after = silent_after
        self.corrupt = corrupt
        self.reads = [43086, 0x9F00]
        self.writes = [(47137, 12)]
        self.stop = threading.Event()
        self.daemon = True
        self.t0 = time.monotonic()
        self.got = []

    def close(self):
        self.stop.set()
        self.join(2)

    def _read_frame(self):
        buf = b""
        while not self.stop.is_set():
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if not r:
                continue
            b = os.read(self.fd, 1)
            if not buf and b != b"\x5c":
                continue
            buf += b
            if len(buf) >= 5 and len(buf) == 6 + buf[4]:
                return buf
        return None

    def _send(self, data):
        time.sleep(self.delay)
        os.write(self.fd, data)

    def run(self):
        while not self.stop.is_set():
            raw = self._read_frame()
            if raw is None:
                return
            if self.silent_after is not None and time.monotonic() - self.t0 > self.silent_after:
                continue
            try:
                address, cmd, data = ps.parse_pump_frame(raw)
            except ps.FrameError:
                self._send(bytes([ps.NAK]))
                continue
            if address != ps.MODBUS40:
                continue
            self.got.append((cmd, data))
            if cmd == ps.CMD_READ_TOKEN and self.reads:
                self._send(ps.read_request(self.reads.pop(0)))
            elif cmd == ps.CMD_WRITE_TOKEN and self.writes:
                self._send(ps.write_request(*self.writes.pop(0)))
            elif cmd == ps.CMD_ACCESSORY:
                self._send(ps.accessory_frame(ps.CMD_ACCESSORY, bytes([0x0A, 0x00, 0x01])))
            elif self.corrupt and cmd == ps.CMD_DATA:
                self._send(bytes([0x42]))
            else:
                self._send(bytes([ps.ACK]))


@pytest.fixture
def link():
    master, slave = os.openpty()
    tty.setraw(master)
    tty.setraw(slave)
    port = serial.Serial(os.ttyname(slave), 9600, timeout=0.1)
    yield master, port
    port.close()
    os.close(master)


def make_pump(port, **kw):
    log = []
    pump = ps.Pump(port, reply_timeout=0.3, echo="off", log=log.append, **kw)
    return pump, log


def test_loopback_full_exchange(link):
    master, port = link
    acc = Accessory(master)
    acc.start()
    pump, log = make_pump(port, alarm_s=2.0)
    stats = pump.run(cycles=6, gap=0.0)
    acc.close()
    assert stats.ok(), stats.report(100) + "\n" + "\n".join(log)
    assert stats.reads_requested == 2 and stats.writes_requested == 1
    assert pump.written == {47137: 12}
    assert stats.accessory_replies >= 1
    assert stats.replied_to_others == 0
    # the accessory saw the escaped register value come through intact
    data = [d for c, d in acc.got if c == ps.CMD_DATA][0]
    assert dict(struct.iter_unpack("<HH", data))[40008] == 0x5C5C


def test_loopback_alarm_when_the_accessory_goes_quiet(link):
    master, port = link
    acc = Accessory(master, silent_after=0.3)
    acc.start()
    pump, log = make_pump(port, alarm_s=1.0)
    stats = pump.run(duration=2.5, gap=0.05)
    acc.close()
    assert stats.alarm
    assert stats.timeouts > 0
    assert not stats.ok()


def test_loopback_garbage_reply_fails(link):
    master, port = link
    acc = Accessory(master, corrupt=True)
    acc.start()
    pump, log = make_pump(port, alarm_s=5.0)
    stats = pump.run(cycles=2, gap=0.0)
    acc.close()
    assert stats.bad_replies
    assert not stats.ok()


def test_loopback_slow_replies_are_counted_late(link):
    master, port = link
    acc = Accessory(master, delay=0.15)
    acc.start()
    pump, log = make_pump(port, alarm_s=5.0, late_ms=100)
    stats = pump.run(cycles=2, gap=0.0)
    acc.close()
    assert stats.late > 0


# --------------------------------------------------------------------------- UDP side
class BridgeAccessory(Accessory):
    """Accessory that also bridges to UDP like NibeGW: requests in, telegrams out."""

    def __init__(self, fd, **kw):
        super().__init__(fd, **kw)
        import socket
        self.reads, self.writes = [], []
        self.read_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.write_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.read_sock.bind(("127.0.0.1", 0))
        self.write_sock.bind(("127.0.0.1", 0))
        self.read_port = self.read_sock.getsockname()[1]
        self.write_port = self.write_sock.getsockname()[1]
        self.read_queue, self.write_queue = [], []
        self.target = None

    def close(self):
        super().close()
        self.read_sock.close()
        self.write_sock.close()

    def _read_frame(self):
        buf = b""
        while not self.stop.is_set():
            r, _, _ = select.select([self.fd, self.read_sock, self.write_sock], [], [], 0.05)
            for s, queue in ((self.read_sock, self.read_queue), (self.write_sock, self.write_queue)):
                if s in r:
                    pkt, src = s.recvfrom(512)
                    ps.parse_accessory_frame(pkt)
                    queue.append(pkt)
                    self.target = src
            if self.fd not in r:
                continue
            b = os.read(self.fd, 1)
            if not buf and b != b"\x5c":
                continue
            buf += b
            if len(buf) >= 5 and len(buf) == 6 + buf[4]:
                try:
                    address, _, _ = ps.parse_pump_frame(buf)
                    if address == ps.MODBUS40 and self.target:
                        self.read_sock.sendto(buf, self.target)
                except ps.FrameError:
                    pass
                return buf
        return None

    def run(self):
        while not self.stop.is_set():
            raw = self._read_frame()
            if raw is None:
                return
            try:
                address, cmd, data = ps.parse_pump_frame(raw)
            except ps.FrameError:
                self._send(bytes([ps.NAK]))
                continue
            if address != ps.MODBUS40:
                continue
            if cmd == ps.CMD_READ_TOKEN and self.read_queue:
                self._send(self.read_queue.pop(0))
            elif cmd == ps.CMD_WRITE_TOKEN and self.write_queue:
                self._send(self.write_queue.pop(0))
            elif cmd == ps.CMD_ACCESSORY:
                self._send(ps.accessory_frame(ps.CMD_ACCESSORY, bytes([0x0A, 0x00, 0x01])))
            else:
                self._send(bytes([ps.ACK]))


def test_loopback_udp_reads_and_writes_reach_home_assistant(link):
    master, port = link
    acc = BridgeAccessory(master)
    acc.start()
    udp = ps.UdpClient("127.0.0.1", read_port=acc.read_port, write_port=acc.write_port, listen_port=0,
                       log=lambda *a: None)
    pump, log = make_pump(port, alarm_s=5.0, udp=udp)
    stats = pump.run(cycles=12, gap=0.0)
    acc.close()
    assert stats.ok(), stats.report(100) + "\n" + "\n".join(log)
    assert stats.udp_reads_ok >= 2
    assert stats.udp_writes_ok >= 1
    assert stats.udp_telegrams > 0
