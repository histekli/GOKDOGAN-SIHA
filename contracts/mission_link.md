# `mission_link` Protokolü (DONDURULMUŞ — SAD §9)

> Jetson (ROS2/Linux) ↔ GCS (WPF/.NET/Windows) **diller-arası tek sınır.**
> rosbridge / C# ROS2 binding **YOK** (kırmızı çizgi §2.1). Şema dil-bağımsız (MessagePack).
> Makine-okur sözleşme: [`mission_link.schema.json`](mission_link.schema.json). Bu ikisi çeliştiğinde **JSON Schema esastır.**
>
> **Bu kontrat Faz 0'da dondurulmuştur.** Değişiklik için açık onay gerekir; iki taraf (onboard + WPF) buna yazar.

## Taşıma

| Kanal | Port | Taşıma | Kullanım |
|---|---|---|---|
| **UDP akış** | 5005 | tek datagram = tek MessagePack mesaj | `aircraft_vision` (~15–30Hz), latest-wins, kayıp-toleranslı. Yalnız **gösterim/overlay** (kontrol değil). |
| **TCP kontrol** | 5006 | 4B big-endian uzunluk öneki + MessagePack gövde | Kritik olay/komut: `lock_valid`, `kamikaze_result` ↑ · `operator_cmd`, `server_data`, `config` ↓. Kalıcı bağlantı, sıralı. |

Her iki kanalda **1Hz app-level `heartbeat`** (kopma tespiti). TCP kopması → onboard **otonom devam eder** (İ2);
GCS "mission_link kopuk" uyarısı + exponential-backoff reconnect. UDP >0.5s paket yok → GCS overlay "stale".

## Zarf (tüm mesajlar)

| Alan | Tip | Açıklama |
|---|---|---|
| `type` | string | Mesaj türü (aşağıdaki enum) |
| `seq` | uint | Kanal başına monotonik sıra no (kayıp/gecikme istatistiği) |
| `ts` | number | Gönderen saati (s, float) — tek-yön gecikme ölçümü |

## Mesajlar

### ▲ Yukarı (onboard → GCS)

- **`aircraft_vision`** (UDP): `target_center_x/y`, `target_width/height`, `is_locked`, `lock_progress_s`,
  `target_team_number`, `score`, `fsm_state`, `active_service`.
- **`lock_valid`** (TCP): `valid`, `target_id`, `target_team_number`, `center[2]`, `box{bbox}`, `lock_end_ts`.
- **`kamikaze_result`** (TCP): `success`, `qr_text`, `max_g`, `detail`.

### ▼ Aşağı (GCS → onboard)

- **`operator_cmd`** (TCP): `cmd` ∈ {START_LOCK, ABORT, SELECT_TARGET, START_KAMIKAZE, SET_MODE}, `target_id`, `mode`, `params`.
- **`server_data`** (TCP): `opponents[]`, `hss[]`, `qr{lat,lon,alt}`, `server_time` (ServerClock).
- **`config`** (TCP): `autonomy_weights{mesafe,aci,gecmis,risk}` = 0.40/0.30/0.20/0.10.

## WPF `FlightState` birebir eşleme (SAD §14, prompt §1.3)

`aircraft_vision` **görüntü alanlarını** doğrudan WPF `FlightState`'e yazar (uçuş alanları ayrı yoldan — RF MAVLink):

| mission_link (`aircraft_vision`) | WPF `FlightState` |
|---|---|
| `target_center_x` | `TargetCenterX` |
| `target_center_y` | `TargetCenterY` |
| `target_width` | `TargetWidth` |
| `target_height` | `TargetHeight` |
| `is_locked` | `IsLocked` |
| `target_team_number` | `TargetTeamNumber` |

> Uçuş alanları (`Latitude/Longitude/Altitude/Roll/Pitch/Heading/GroundSpeed/Airspeed/BatteryPercent/Mode/IsArmed/IsAutonomous`)
> `MavlinkFlightStateSource` (RF MAVLink) tarafından yazılır — bu protokolde taşınmaz.

## Hata davranışı (SAD §9, prompt §5)

- **partial/bozuk frame** → drop + log, **çökme yok**.
- **şema-versiyon uyumsuzluğu** → reddet + log.
- **UDP loss/disorder** → `seq` + latest-wins; stale bayrağı.
- **heartbeat timeout** → link-lost olayı; onboard otonom devam.
- **clock skew** → `ts` ile offset; ServerClock GCS→onboard `server_data.server_time` ile taşınır.
