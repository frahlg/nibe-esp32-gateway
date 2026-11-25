# /// script
# requires-python = ">=3.10"
# dependencies = ["pyserial>=3.5"]
# ///
"""Bench tester: plays a NIBE heat pump on the RS-485 bus.

Wire a USB-RS485 adapter to the gateway's A, B and GND and power the gateway
from USB-C. Then:

    uv run tools/pump_simulator.py --port /dev/tty.usbserial-XXXX --duration 60

The tester sends what a pump sends to a MODBUS 40 accessory (data telegrams,
read and write tokens, the accessory version request, and telegrams for other
addresses), checks every reply (checksum, ACK/NAK, timing) and applies the
pump's alarm rule: no valid reply for 15 s means alarm 251.

With --gateway-ip it also acts like Home Assistant: it sends read and write
requests to the gateway over UDP (ports 9999 and 10000) and checks that they
travel over the bus and that the answers come back over UDP.

Protocol notes: docs/protocol.md.
"""
from __future__ import annotations

import argparse
import socket
import statistics
import struct
import sys
import time
from dataclasses import dataclass, field

START_PUMP = 0x5C
START_ACC = 0xC0
ACK = 0x06
NAK = 0x15

MODBUS40 = 0x20
RMU40_S1 = 0x19

CMD_DATA = 0x68
CMD_READ_TOKEN = 0x69
CMD_READ_RESP = 0x6A
CMD_WRITE_TOKEN = 0x6B
CMD_WRITE_RESP = 0x6C
CMD_ACCESSORY = 0xEE


class FrameError(ValueError):
    pass


# --------------------------------------------------------------------------- frames
def xor(data: bytes) -> int:
    x = 0
    for b in data:
        x ^= b
    return x


def checksum(data: bytes) -> int:
    """XOR checksum; 0x5C is sent as 0xC5 so it cannot look like a start byte."""
    x = xor(data)
    return 0xC5 if x == 0x5C else x


def checksum_ok(data: bytes, chk: int) -> bool:
    x = xor(data)
    return chk == x or (x == 0x5C and chk == 0xC5)


def escape(data: bytes) -> bytes:
    """The pump sends a 0x5C data byte twice."""
    return data.replace(b"\x5c", b"\x5c\x5c")


def unescape(data: bytes) -> bytes:
    return data.replace(b"\x5c\x5c", b"\x5c")


def pump_frame(address: int, cmd: int, data: bytes = b"") -> bytes:
    """5C ADDR_H ADDR_L CMD LEN DATA CHK. LEN and CHK cover the escaped data."""
    body = struct.pack(">HBB", address, cmd, len(escape(data))) + escape(data)
    return bytes([START_PUMP]) + body + bytes([checksum(body)])


def parse_pump_frame(raw: bytes) -> tuple[int, int, bytes]:
    """Return (address, cmd, unescaped data) or raise FrameError."""
    if len(raw) < 6 or raw[0] != START_PUMP:
        raise FrameError("not a pump frame")
    address, cmd, length = struct.unpack(">HBB", raw[1:5])
    if len(raw) != 6 + length:
        raise FrameError("length %d does not match %d bytes" % (length, len(raw)))
    if not checksum_ok(raw[1:-1], raw[-1]):
        raise FrameError("bad checksum")
    return address, cmd, unescape(raw[5:-1])


def accessory_frame(cmd: int, data: bytes = b"") -> bytes:
    """C0 CMD LEN DATA CHK, checksum over everything from C0."""
    body = bytes([START_ACC, cmd, len(data)]) + data
    return body + bytes([checksum(body)])


def parse_accessory_frame(raw: bytes) -> tuple[int, bytes]:
    if len(raw) < 4 or raw[0] != START_ACC:
        raise FrameError("not an accessory frame")
    cmd, length = raw[1], raw[2]
    if len(raw) != 4 + length:
        raise FrameError("length %d does not match %d bytes" % (length, len(raw)))
    if not checksum_ok(raw[:-1], raw[-1]):
        raise FrameError("bad checksum")
    return cmd, raw[3:-1]


def data_payload(registers: dict[int, int]) -> bytes:
    """Data telegram (0x68): pairs of u16 register and u16 value, little endian."""
    return b"".join(struct.pack("<HH", r & 0xFFFF, v & 0xFFFF) for r, v in registers.items())


def read_request(register: int) -> bytes:
    return accessory_frame(CMD_READ_TOKEN, struct.pack("<H", register))


def write_request(register: int, value: int) -> bytes:
    return accessory_frame(CMD_WRITE_TOKEN, struct.pack("<Hi", register, value))


# --------------------------------------------------------------------------- statistics
@dataclass
class Stats:
    sent: dict = field(default_factory=dict)
    acks: int = 0
    naks: int = 0
    timeouts: int = 0
    bad_replies: list = field(default_factory=list)
    replied_to_others: int = 0
    latencies_ms: list = field(default_factory=list)
    late: int = 0
    reads_requested: int = 0
    writes_requested: int = 0
    accessory_replies: int = 0
    alarm: bool = False
    longest_silence_s: float = 0.0
    udp_reads_ok: int = 0
    udp_writes_ok: int = 0
    udp_failures: int = 0
    udp_telegrams: int = 0

    def count(self, name):
        self.sent[name] = self.sent.get(name, 0) + 1

    def ok(self) -> bool:
        return (not self.alarm and self.timeouts == 0 and not self.bad_replies and self.replied_to_others == 0
                and self.naks == 0 and self.udp_failures == 0)

    def report(self, late_ms: float) -> str:
        lines = ["frames sent: " + ", ".join("%s %d" % kv for kv in sorted(self.sent.items()))]
        if self.latencies_ms:
            lat = sorted(self.latencies_ms)
            p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
            lines.append("reply latency ms: min %.1f  median %.1f  p95 %.1f  max %.1f  (%d over %d ms)"
                         % (lat[0], statistics.median(lat), p95, lat[-1], self.late, late_ms))
        lines.append("ACK %d  NAK %d  timeouts %d  bad replies %d  replies to other addresses %d"
                     % (self.acks, self.naks, self.timeouts, len(self.bad_replies), self.replied_to_others))
        lines.append("read requests %d  write requests %d  accessory replies %d"
                     % (self.reads_requested, self.writes_requested, self.accessory_replies))
        if self.udp_reads_ok or self.udp_writes_ok or self.udp_failures or self.udp_telegrams:
            lines.append("UDP: reads ok %d  writes ok %d  failures %d  telegrams forwarded %d"
                         % (self.udp_reads_ok, self.udp_writes_ok, self.udp_failures, self.udp_telegrams))
        lines.append("longest time without a valid reply: %.1f s" % self.longest_silence_s)
        for b in self.bad_replies[:5]:
            lines.append("  bad reply: " + b)
        lines.append("ALARM 251 (no valid reply within the alarm time)" if self.alarm else "no alarm")
        lines.append("RESULT: " + ("PASS" if self.ok() else "FAIL"))
        return "\n".join(lines)


# --------------------------------------------------------------------------- the pump
class Pump:
    """Plays the heat pump: sends frames, checks the replies."""

    def __init__(self, port, reply_timeout=0.5, late_ms=100.0, alarm_s=15.0, echo="auto", log=print,
                 udp=None):
        self.port = port
        self.reply_timeout = reply_timeout
        self.late_ms = late_ms
        self.alarm_s = alarm_s
        self.echo = echo
        self.log = log
        self.udp = udp
        self.stats = Stats()
        self.last_valid = time.monotonic()
        self.registers = {40004: 215, 40008: 0x5C5C, 40012: 330, 43005: -120 & 0xFFFF, 40013: 485}
        self.values = {}          # register -> value the pump returns on read requests
        self.written = {}         # register -> value written by the accessory
        self.counter = 0
        self._pending, self._first_t, self._last_latency_ms = b"", None, None

    # ---- low level
    BYTE_S = 10 / 9600  # one byte on the wire at 9600 8N1

    def _read_byte(self, deadline: float):
        self.port.timeout = max(0.0, deadline - time.monotonic())
        b = self.port.read(1)
        return (b, time.monotonic()) if b else (b"", None)

    def _send(self, frame: bytes) -> float:
        """Send a frame. Returns the time its last byte left the adapter (estimated)."""
        self.port.reset_input_buffer()
        t0 = time.monotonic()
        self.port.write(frame)
        self.port.flush()
        t_end = max(time.monotonic(), t0 + len(frame) * self.BYTE_S)
        self._pending, self._first_t = b"", None
        if self.echo in ("auto", "on"):
            # half-duplex adapters may echo our own bytes; drop them
            deadline = t_end + 0.05
            for i, want in enumerate(frame):
                b, t = self._read_byte(deadline)
                if not b:
                    if self.echo == "on" and i == 0:
                        self.stats.bad_replies.append("no echo from the adapter")
                    break
                if b[0] != want:
                    if i:  # part of our echo matched: the line is garbled
                        self.stats.bad_replies.append("echo mismatch at byte %d" % i)
                    self._pending, self._first_t = b, t
                    break
        return t_end

    def _reply(self, t_end: float) -> bytes:
        """Read one reply and remember when its first byte came."""
        deadline = time.monotonic() + self.reply_timeout
        buf, first = self._pending, self._first_t
        self._pending = b""
        while True:
            if buf:
                if len(buf) == 1 and buf[0] in (ACK, NAK):
                    break
                if buf[0] != START_ACC or (len(buf) >= 3 and len(buf) == buf[2] + 4):
                    break
            b, t = self._read_byte(deadline)
            if not b:
                break
            buf += b
            first = first or t
        self._last_latency_ms = None if first is None else max(0.0, (first - t_end) * 1000)
        return buf

    def _track(self, valid: bool, latency_ms: float | None):
        now = time.monotonic()
        if valid:
            self.stats.longest_silence_s = max(self.stats.longest_silence_s, now - self.last_valid)
            self.last_valid = now
            if latency_ms is not None:
                self.stats.latencies_ms.append(latency_ms)
                if latency_ms > self.late_ms:
                    self.stats.late += 1
        if now - self.last_valid > self.alarm_s and not self.stats.alarm:
            self.stats.alarm = True
            self.log("ALARM 251: no valid reply for %.1f s" % (now - self.last_valid))

    def _expect_ack(self, name: str, t_sent: float, reply: bytes) -> bool:
        lat = self._last_latency_ms
        if reply == bytes([ACK]):
            self.stats.acks += 1
            self._track(True, lat)
            return True
        if reply == bytes([NAK]):
            self.stats.naks += 1
            self.log("%s: NAK" % name)
        elif not reply:
            self.stats.timeouts += 1
            self.log("%s: no reply" % name)
        else:
            self.stats.bad_replies.append("%s: %s" % (name, reply.hex(" ")))
        self._track(False, None)
        return False

    # ---- one exchange of each kind
    def data_telegram(self):
        self.counter += 1
        regs = dict(self.registers)
        regs[40004] = 200 + self.counter % 50
        frame = pump_frame(MODBUS40, CMD_DATA, data_payload(regs))
        self.stats.count("data 0x68")
        t = self._send(frame)
        return self._expect_ack("data 0x68", t, self._reply(t))

    def read_token(self):
        self.stats.count("read token 0x69")
        t = self._send(pump_frame(MODBUS40, CMD_READ_TOKEN))
        reply = self._reply(t)
        if reply in (bytes([ACK]), bytes([NAK]), b"") or reply[:1] != bytes([START_ACC]):
            return self._expect_ack("read token 0x69", t, reply)
        lat = self._last_latency_ms
        try:
            cmd, data = parse_accessory_frame(reply)
            if cmd != CMD_READ_TOKEN or len(data) != 2:
                raise FrameError("expected a read request, got cmd 0x%02X" % cmd)
        except FrameError as e:
            self.stats.bad_replies.append("read token: %s (%s)" % (e, reply.hex(" ")))
            self._track(False, None)
            return False
        self._track(True, lat)
        self.stats.reads_requested += 1
        register = struct.unpack("<H", data)[0]
        value = self.values.get(register, register * 3 % 1000)
        self.stats.count("read response 0x6A")
        t2 = self._send(pump_frame(MODBUS40, CMD_READ_RESP, struct.pack("<Hi", register, value)))
        self.log("read request for register %d, answered %d" % (register, value))
        return self._expect_ack("read response 0x6A", t2, self._reply(t2))

    def write_token(self):
        self.stats.count("write token 0x6B")
        t = self._send(pump_frame(MODBUS40, CMD_WRITE_TOKEN))
        reply = self._reply(t)
        if reply in (bytes([ACK]), bytes([NAK]), b"") or reply[:1] != bytes([START_ACC]):
            return self._expect_ack("write token 0x6B", t, reply)
        lat = self._last_latency_ms
        try:
            cmd, data = parse_accessory_frame(reply)
            if cmd != CMD_WRITE_TOKEN or len(data) != 6:
                raise FrameError("expected a write request, got cmd 0x%02X" % cmd)
        except FrameError as e:
            self.stats.bad_replies.append("write token: %s (%s)" % (e, reply.hex(" ")))
            self._track(False, None)
            return False
        self._track(True, lat)
        self.stats.writes_requested += 1
        register, value = struct.unpack("<Hi", data)
        self.written[register] = value
        self.stats.count("write result 0x6C")
        t2 = self._send(pump_frame(MODBUS40, CMD_WRITE_RESP, b"\x01"))
        self.log("write request: register %d = %d" % (register, value))
        return self._expect_ack("write result 0x6C", t2, self._reply(t2))

    def accessory_request(self):
        self.stats.count("accessory 0xEE")
        t = self._send(pump_frame(MODBUS40, CMD_ACCESSORY))
        reply = self._reply(t)
        lat = self._last_latency_ms
        try:
            cmd, data = parse_accessory_frame(reply)
            if cmd != CMD_ACCESSORY:
                raise FrameError("cmd 0x%02X" % cmd)
        except FrameError as e:
            if not reply:
                self.stats.timeouts += 1
                self.log("accessory 0xEE: no reply")
            else:
                self.stats.bad_replies.append("accessory 0xEE: %s (%s)" % (e, reply.hex(" ")))
            self._track(False, None)
            return False
        self.stats.accessory_replies += 1
        self._track(True, lat)
        return True

    def other_address(self):
        """A telegram for an RMU 40. The gateway must stay silent."""
        self.stats.count("other address")
        self._send(pump_frame(RMU40_S1, CMD_DATA, data_payload({40004: 210})))
        self.port.timeout = 0.08
        reply = self._pending or self.port.read(16)
        self._pending = b""
        if reply:
            self.stats.replied_to_others += 1
            self.log("gateway answered a telegram for another address: %s" % reply.hex(" "))
            return False
        return True

    def bad_checksum(self):
        """A data telegram with a broken checksum. A NAK or silence is fine, an ACK is not."""
        self.stats.count("bad checksum")
        frame = bytearray(pump_frame(MODBUS40, CMD_DATA, data_payload({40004: 1})))
        frame[-1] ^= 0xFF
        t = self._send(bytes(frame))
        reply = self._reply(t)
        if reply == bytes([ACK]):
            self.stats.bad_replies.append("ACK on a frame with a bad checksum")
            return False
        return True

    # ---- schedule
    def cycle(self):
        self.data_telegram()
        self.other_address()
        self.read_token()
        self.write_token()
        if self.counter % 10 == 1:
            self.accessory_request()
        if self.counter % 25 == 2:
            self.bad_checksum()
        if self.udp is not None:
            self.udp.poll(self)
        self._track(False, None)

    def run(self, duration: float | None = None, cycles: int | None = None, gap: float = 0.05):
        t_end = None if duration is None else time.monotonic() + duration
        n = 0
        while True:
            if cycles is not None and n >= cycles:
                break
            if t_end is not None and time.monotonic() >= t_end:
                break
            self.cycle()
            n += 1
            time.sleep(gap)
        return self.stats


# --------------------------------------------------------------------------- Home Assistant side
class UdpClient:
    """Acts like Home Assistant's NibeGW connection: UDP requests in, telegrams back."""

    def __init__(self, gateway_ip: str, read_port=9999, write_port=10000, listen_port=0, log=print):
        self.gw = gateway_ip
        self.read_port, self.write_port = read_port, write_port
        self.log = log
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", listen_port))
        self.sock.setblocking(False)
        self.pending_read = None      # (register, value, time)
        self.pending_write = None
        self.next_register = 43086

    def poll(self, pump: Pump):
        # collect what the gateway forwarded
        while True:
            try:
                pkt, _ = self.sock.recvfrom(512)
            except BlockingIOError:
                break
            try:
                _, cmd, data = parse_pump_frame(pkt)
            except FrameError:
                continue
            pump.stats.udp_telegrams += 1
            if cmd == CMD_READ_RESP and self.pending_read:
                reg, val = struct.unpack("<Hi", data[:6])
                if reg == self.pending_read[0]:
                    want = pump.values.get(reg, reg * 3 % 1000)
                    if val == want:
                        pump.stats.udp_reads_ok += 1
                    else:
                        pump.stats.udp_failures += 1
                        self.log("UDP read of %d gave %d, pump sent %d" % (reg, val, want))
                    self.pending_read = None
        now = time.monotonic()
        if self.pending_read and now - self.pending_read[2] > 5:
            pump.stats.udp_failures += 1
            self.log("UDP read of register %d got no answer in 5 s" % self.pending_read[0])
            self.pending_read = None
        if self.pending_write:
            reg, val, t0 = self.pending_write
            if pump.written.get(reg) == val:
                pump.stats.udp_writes_ok += 1
                self.pending_write = None
            elif now - t0 > 5:
                pump.stats.udp_failures += 1
                self.log("UDP write of register %d never reached the bus" % reg)
                self.pending_write = None
        # send new requests
        if self.pending_read is None:
            reg = self.next_register
            self.next_register = 43086 if reg >= 43100 else reg + 1
            self.sock.sendto(read_request(reg), (self.gw, self.read_port))
            self.pending_read = (reg, None, now)
        if self.pending_write is None:
            reg, val = 47137, int(now) % 100
            self.sock.sendto(write_request(reg, val), (self.gw, self.write_port))
            self.pending_write = (reg, val, now)


# --------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", required=True, help="serial port of the USB-RS485 adapter")
    ap.add_argument("--duration", type=float, default=60.0, help="seconds to run (default 60)")
    ap.add_argument("--cycles", type=int, help="stop after this many cycles instead")
    ap.add_argument("--gateway-ip", help="also test the UDP side, like Home Assistant does")
    ap.add_argument("--reply-timeout", type=float, default=0.5, help="seconds to wait for a reply")
    ap.add_argument("--late-ms", type=float, default=100.0, help="replies slower than this count as late")
    ap.add_argument("--alarm-s", type=float, default=15.0, help="the pump's alarm time")
    ap.add_argument("--echo", choices=["auto", "on", "off"], default="auto",
                    help="whether the adapter echoes what it sends")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    import serial
    port = serial.Serial(args.port, 9600, bytesize=8, parity="N", stopbits=1, timeout=0.1)
    log = (lambda *a: None) if args.quiet else print
    udp = UdpClient(args.gateway_ip, log=log) if args.gateway_ip else None
    pump = Pump(port, reply_timeout=args.reply_timeout, late_ms=args.late_ms, alarm_s=args.alarm_s,
                echo=args.echo, log=log, udp=udp)
    print("playing the heat pump on %s for %s" % (args.port, "%d cycles" % args.cycles if args.cycles
                                                    else "%.0f s" % args.duration))
    try:
        stats = pump.run(duration=None if args.cycles else args.duration, cycles=args.cycles)
    except KeyboardInterrupt:
        stats = pump.stats
    print(stats.report(args.late_ms))
    return 0 if stats.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
