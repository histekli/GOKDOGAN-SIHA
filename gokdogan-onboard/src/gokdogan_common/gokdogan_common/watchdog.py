"""Node heartbeat watchdog (saf Python). SAD §18 katman-3: bir node ölürse güvenli state.

Her kritik node 1Hz heartbeat yayınlar; `Watchdog` son atış zamanlarını izler. `timeout`u aşan
kritik node → sistem 'unhealthy' → mission_fsm failsafe (RTL). Saf → birim test edilir.
"""


class Watchdog:
    def __init__(self, timeout_s=3.0):
        self.timeout_s = float(timeout_s)
        self._last_beat = {}  # name -> son heartbeat ts (None = hiç görülmedi)
        self._required = set()  # kritik node isimleri

    def register(self, name, required=True, now=None):
        """Node kaydet. now verilirse ilk heartbeat olarak sayılır (başlangıç grace'i)."""
        self._last_beat[name] = now
        if required:
            self._required.add(name)
        else:
            self._required.discard(name)

    def beat(self, name, now):
        """Heartbeat kaydı (kayıtlı değilse otomatik kaydeder, kritik değil)."""
        if name not in self._last_beat:
            self._last_beat[name] = now
        else:
            self._last_beat[name] = now

    def age(self, name, now):
        """Son heartbeat'ten bu yana geçen süre (hiç görülmediyse +inf)."""
        t = self._last_beat.get(name)
        return float("inf") if t is None else (now - t)

    def stale(self, now):
        """timeout'u aşan (veya hiç görülmemiş) TÜM node isimleri."""
        return [n for n in self._last_beat if self.age(n, now) > self.timeout_s]

    def stale_required(self, now):
        """Bayat olan KRİTİK node isimleri."""
        return [n for n in self._required if self.age(n, now) > self.timeout_s]

    def healthy(self, now):
        """Tüm kritik node'lar taze mi (failsafe kararı için)."""
        return not self.stale_required(now)
