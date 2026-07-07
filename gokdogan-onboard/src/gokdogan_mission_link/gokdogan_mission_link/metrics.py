"""mission_link kalite metrikleri (saf Python). SAD §22: seq-kayıp %, tek-yön gecikme.

Onboard/GCS iki tarafta da kullanılır; GCS Sistem Sağlığı panelinde gösterilir (§22).
Sıra-dışı/tekrar paketler last_seq'i geriletmez (UDP latest-wins toleransı).
"""


class LinkStats:
    def __init__(self):
        self.received = 0
        self.lost = 0
        self.duplicates = 0
        self.reordered = 0
        self.last_seq = None
        self._lat_sum = 0.0
        self._lat_n = 0
        self.latency_last = 0.0

    def observe(self, seq, ts=None, now=None):
        """Gelen paketi işle: seq boşluğu → kayıp; ts+now → tek-yön gecikme."""
        self.received += 1
        if self.last_seq is not None:
            if seq > self.last_seq + 1:
                self.lost += seq - self.last_seq - 1
            elif seq == self.last_seq:
                self.duplicates += 1
            elif seq < self.last_seq:
                self.reordered += 1
        if self.last_seq is None or seq > self.last_seq:
            self.last_seq = seq
        if ts is not None and now is not None:
            lat = max(0.0, now - ts)
            self.latency_last = round(lat, 4)
            self._lat_sum += lat
            self._lat_n += 1

    @property
    def loss_pct(self):
        total = self.received + self.lost
        return 0.0 if total == 0 else round(100.0 * self.lost / total, 3)

    @property
    def latency_avg(self):
        return 0.0 if self._lat_n == 0 else round(self._lat_sum / self._lat_n, 4)

    def snapshot(self):
        return {
            "received": self.received,
            "lost": self.lost,
            "duplicates": self.duplicates,
            "reordered": self.reordered,
            "loss_pct": self.loss_pct,
            "latency_avg_s": self.latency_avg,
            "latency_last_s": round(self.latency_last, 4),
        }
