"""Yapısal JSON log + tek zaman tabanı (saf Python). SAD §22.

- Olaylar (faz/state geçişi, failsafe, latency) tek satır JSON → post-mortem + test grafiği.
- **Tek zaman tabanı:** ServerClock otoritedir; sys↔server offset her kayıtta taşınır (dış paketler
  ServerClock damgalı). Saf → sink enjekte edilir (test), rclpy'ye bağımlı değil.
"""

import json
import time


class TimeBase:
    """sys ↔ server (ServerClock) ↔ ros zaman offset takibi (SAD §22)."""

    def __init__(self, clock=time.time):
        self._clock = clock
        self.server_offset = 0.0  # server_time - sys_time (GCS ServerClock'tan gelir)
        self.ros_offset = 0.0  # ros_time - sys_time (SITL sim-zamanında ≠ 0)

    def set_server_offset(self, offset):
        self.server_offset = float(offset)

    def set_ros_offset(self, offset):
        self.ros_offset = float(offset)

    def stamp(self, sys_time=None):
        t = self._clock() if sys_time is None else sys_time
        return {
            "sys": round(t, 4),
            "server": round(t + self.server_offset, 4),
            "server_offset": round(self.server_offset, 4),
            "ros_offset": round(self.ros_offset, 4),
        }


class StructuredLogger:
    """JSON olay üretici. emit() → tek satır JSON (sink'e yazar, string döndürür)."""

    def __init__(self, source, timebase=None, sink=None):
        self.source = source
        self.tb = timebase or TimeBase()
        self.sink = sink  # callable(str) | None

    def event(self, kind, **fields):
        rec = {"src": self.source, "kind": kind}
        rec.update(self.tb.stamp())
        rec.update(fields)
        return rec

    def emit(self, kind, **fields):
        line = json.dumps(self.event(kind, **fields), ensure_ascii=False, sort_keys=True)
        if self.sink is not None:
            self.sink(line)
        return line
