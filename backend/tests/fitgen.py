"""A minimal FIT writer for tests: a synthetic run with records, laps, a session and an activity (no CRC: the reader
doesn't check it). Field numbers and types from the FIT SDK profile."""

import struct
from datetime import datetime, timezone

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)
ENUM, UINT8, UINT16, UINT32, SINT32 = 0x00, 0x02, 0x84, 0x86, 0x85
FMT = {ENUM: "B", UINT8: "B", UINT16: "H", UINT32: "I", SINT32: "i"}


def ts(t: datetime) -> int:
    return int((t - FIT_EPOCH).total_seconds())


class Writer:
    def __init__(self):
        self.body, self.local = b"", {}

    def msg(self, glob: int, fields: list[tuple[int, int, int]]):
        """fields: (field number, base type, value)."""
        key = (glob, tuple((n, b) for n, b, _ in fields))
        if key not in self.local:
            self.local[key] = len(self.local) % 16
            lt = self.local[key]
            self.body += struct.pack("<BBBHB", 0x40 | lt, 0, 0, glob, len(fields))
            for n, b, _ in fields:
                self.body += struct.pack("<BBB", n, struct.calcsize(FMT[b]), b)
        self.body += struct.pack("<B", self.local[key])
        for _, b, v in fields:
            self.body += struct.pack("<" + FMT[b], v)

    def bytes(self) -> bytes:
        return struct.pack("<BBHI4sH", 14, 0x20, 2132, len(self.body), b".FIT", 0) + self.body + b"\x00\x00"


def run(start: datetime, seconds: int = 480, speed: float = 3.0, hr: int = 145, strides: int = 82, offset_h: int = 3,
        rest_from: int | None = 300) -> bytes:
    """A run going north at `speed`, with heart rate and cadence (FIT's strides a minute), a work lap and, from
    `rest_from` seconds, a rest lap."""
    w, t0 = Writer(), ts(start)
    w.msg(0, [(0, ENUM, 4), (1, UINT16, 255), (4, UINT32, t0)])  # file_id: activity, development
    for s in range(seconds):
        lat = int((32.0 + s * speed / 110_540) / (180 / 2 ** 31))
        w.msg(20, [(253, UINT32, t0 + s), (0, SINT32, lat), (1, SINT32, int(34.8 / (180 / 2 ** 31))),
                   (2, UINT16, int((20 + 500) * 5)), (3, UINT8, hr), (4, UINT8, strides),
                   (5, UINT32, int(s * speed * 100)), (6, UINT16, int(speed * 1000))])
    laps = [(0, rest_from or seconds, 0), (rest_from, seconds, 1)] if rest_from else [(0, seconds, 0)]
    for a, b, intensity in laps:
        w.msg(19, [(253, UINT32, t0 + b), (2, UINT32, t0 + a), (7, UINT32, (b - a) * 1000), (8, UINT32, (b - a) * 1000),
                   (9, UINT32, int((b - a) * speed * 100)), (15, UINT8, hr), (23, ENUM, intensity)])
    w.msg(18, [(253, UINT32, t0 + seconds), (2, UINT32, t0), (7, UINT32, seconds * 1000), (8, UINT32, seconds * 1000),
               (9, UINT32, int(seconds * speed * 100)), (5, ENUM, 1), (6, ENUM, 0), (16, UINT8, hr)])
    w.msg(34, [(253, UINT32, t0 + seconds), (5, UINT32, t0 + seconds + offset_h * 3600), (1, UINT16, 1)])
    return w.bytes()
