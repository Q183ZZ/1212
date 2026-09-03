import math
import threading
import time
from dataclasses import dataclass
from typing import Optional

import serial


@dataclass
class GPSFix:
    latitude: float
    longitude: float
    altitude: Optional[float]
    speed_mps: float
    heading_deg: Optional[float]
    satellites: Optional[int]
    hdop: Optional[float]
    quality: int
    timestamp: float


def _nmea_coord(raw: str, direction: str) -> Optional[float]:
    if not raw or not direction:
        return None
    try:
        value = float(raw)
        degrees = int(value / 100)
        minutes = value - degrees * 100
        result = degrees + minutes / 60.0
        if direction in ("S", "W"):
            result = -result
        return result
    except (ValueError, TypeError):
        return None


def _knots_to_mps(knots: str) -> float:
    try:
        return float(knots) * 0.514444
    except (ValueError, TypeError):
        return 0.0


class NMEAParser:
    def __init__(self):
        self.lat = None
        self.lon = None
        self.alt = None
        self.speed = 0.0
        self.heading = None
        self.satellites = None
        self.hdop = None
        self.quality = 0

    def feed(self, sentence: str) -> Optional[GPSFix]:
        sentence = sentence.strip()
        if not sentence.startswith("$"):
            return None

        if "*" in sentence:
            sentence = sentence.split("*", 1)[0]

        fields = sentence.split(",")
        kind = fields[0][3:] if fields[0].startswith("$GP") or fields[0].startswith("$GN") else fields[0]

        if kind in ("GGA", "GNS"):
            if len(fields) >= 10:
                self.lat = _nmea_coord(fields[2], fields[3])
                self.lon = _nmea_coord(fields[4], fields[5])
                try:
                    self.quality = int(fields[6] or 0)
                except ValueError:
                    self.quality = 0
                try:
                    self.satellites = int(fields[7] or 0)
                except ValueError:
                    self.satellites = None
                try:
                    self.hdop = float(fields[8]) if fields[8] else None
                except ValueError:
                    self.hdop = None
                try:
                    self.alt = float(fields[9]) if fields[9] else None
                except ValueError:
                    self.alt = None

        elif kind == "RMC":
            if len(fields) >= 9 and fields[2] == "A":
                self.lat = _nmea_coord(fields[3], fields[4])
                self.lon = _nmea_coord(fields[5], fields[6])
                self.speed = _knots_to_mps(fields[7])
                try:
                    self.heading = float(fields[8]) if fields[8] else None
                except ValueError:
                    self.heading = None

        if self.lat is None or self.lon is None or self.quality <= 0:
            return None

        return GPSFix(
            latitude=self.lat,
            longitude=self.lon,
            altitude=self.alt,
            speed_mps=self.speed,
            heading_deg=self.heading,
            satellites=self.satellites,
            hdop=self.hdop,
            quality=self.quality,
            timestamp=time.time(),
        )


class GTU7Reader:
    def __init__(self, device="/dev/ttyUSB0", baudrate=9600, on_fix=None, on_error=None):
        self.device = device
        self.baudrate = baudrate
        self.on_fix = on_fix
        self.on_error = on_error
        self._stop = threading.Event()
        self._thread = None
        self._last_fix = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    @staticmethod
    def _distance_m(a: GPSFix, b: GPSFix) -> float:
        r = 6371000.0
        p1, p2 = math.radians(a.latitude), math.radians(b.latitude)
        dp = math.radians(b.latitude - a.latitude)
        dl = math.radians(b.longitude - a.longitude)
        h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(min(1, math.sqrt(h)))

    def _valid(self, fix: GPSFix) -> bool:
        if not (-90 <= fix.latitude <= 90 and -180 <= fix.longitude <= 180):
            return False
        if fix.hdop is not None and fix.hdop > 8.0:
            return False
        if self._last_fix:
            dt = max(0.1, fix.timestamp - self._last_fix.timestamp)
            jump = self._distance_m(self._last_fix, fix)
            # GT-U7 突然跳到几百公里外时直接丢弃，防止错误定位污染导航。
            if jump > 500 and jump / dt > 120:
                return False
        return True

    def _run(self):
        while not self._stop.is_set():
            try:
                with serial.Serial(self.device, self.baudrate, timeout=1) as ser:
                    while not self._stop.is_set():
                        raw = ser.readline()
                        if not raw:
                            continue
                        try:
                            sentence = raw.decode("ascii", errors="ignore")
                        except Exception:
                            continue
                        fix = parser.feed(sentence)
                        if fix and self._valid(fix):
                            self._last_fix = fix
                            if self.on_fix:
                                self.on_fix(fix)
            except Exception as exc:
                if self.on_error:
                    self.on_error(exc)
                time.sleep(2)


parser = NMEAParser()
