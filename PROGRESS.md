# GÖKDOĞAN — İLERLEME DEFTERİ (PROGRESS)

> Faz checklist'i, geçilen Kabul Kapıları, açık sorunlar, kararlar. Her faz sonunda güncellenir.

---

## SAD ÖZETİ (docs/GOKDOGAN_YAZILIM_MIMARISI.md — tek doğruluk kaynağı)

**İlkeler:** (İ1) Tek otorite — her sorumluluğun tek karar vericisi. (İ2) Kritik döngü uçakta + izole
(algı→güdüm→MAVROS; Wi-Fi koparsa uçuş kopmaz). (İ3) Diller arası tek ince sınır = `mission_link`
(rosbridge/C# ROS2 binding YOK). (İ4) DDS lokal (`ROS_LOCALHOST_ONLY=1`, CycloneDDS yalnız `lo`).
(İ5) Sim = gerçek graph (otonomi node'ları SITL/Pixhawk ayrımını bilmez — MAVROS arkasında).
(İ6) Kontrat-önce (`.msg` + `mission_link` şeması gün 1-2 dondurulur).

**İki runtime:** Onboard (Jetson · Docker · ROS2 Humble + MAVROS→Pixhawk UART) ve GCS (WPF/.NET 10, Windows).
Beş hat: ① RF MAVLink (uçuş telem) · ② UART MAVLink (MAVROS otonomi) · ③ mission_link Wi-Fi (UDP vision↑ / TCP komut↓)
· ④ RTSP Wi-Fi (kamera) · ⑤ HTTP Ethernet (sunucu).

**Node grafiği (§5):** perception→tracking→(lock_validator, target_selector); guidance; kamikaze; hss; mission_fsm→MAVROS;
mission_link_node (ROS↔soket köprü); video_streamer→RTSP. Kritik döngü (perception+tracking+lock_validator+guidance)
tek ComponentContainer'da, intra-process (zero-copy). MultiThreadedExecutor: cb_perception(Reentrant) /
cb_control(MutuallyExclusive 50/10Hz, asla bloklanmaz) / cb_io(Reentrant).

**QoS (§6):** yüksek-hız akış → BEST_EFFORT depth=1 (en taze); olay/komut/durum → RELIABLE; mod/seçim → TRANSIENT_LOCAL.
Pub/sub QoS uyumsuzluğu Humble'da sessiz kopma → merkezî `gokdogan_qos`.

**Mesajlar (§7):** BBox, Track, Tracks, LockEvent, Target, MissionMode, MissionCommand, Opponents, HssList,
AircraftState; srv SetMissionMode, ArmDisarm; action ExecuteKamikaze.

**MAVROS (§8):** ENU (ROS/REP-103) ↔ NED (Pixhawk); `yaw_enu = π/2 − heading_ned`. Dönüşüm **tek yerde**:
`guidance/frames.{hpp,py}`. Stream rate ATTITUDE/LOCAL_POSITION ≥50Hz. Setpoint timeout → güdüm aktifken sürekli
≥10Hz yayın; durdurunca moddan çık. Tek yazıcı: yalnız `mission_fsm`'in `active_service`'i setpoint yazar.

**mission_link (§9):** UDP 5005 (aircraft_vision, latest-wins, gösterim); TCP 5006 (lock_valid, kamikaze_result ↑ /
operator_cmd, server_data, config ↓; length-prefixed MessagePack + 1Hz heartbeat). TCP kopar → onboard otonom devam.

**Algı (§10):** AR0234 1920×1200 82° 50fps, merkez (960,600). ROI %70→640×640→geri 1920×1200. YOLOv11s TRT FP16
(her 5 kare) + Kalman([px,py,vx,vy,ax,ay]) + Hungarian(Cost=1−IoU, IoU≥0.3).

**Güdüm (§11):** LOCKING'de kaba(GPS+PN, N=4, 10Hz)→hassas(piksel PID 50Hz; Kp=0.042/Ki=0.0008/Kd=0.025; φ±45/θ±30;
throttle W≈2m). Histerezis 480/520m + bbox-taze. Rate limit Δφ=20°/s, LPF α=0.3.

**FSM (§12):** IDLE→TAKEOFF→CRUISE→LOCKING→KAMIKAZE→RTL→LAND (+MANUAL RC override). active_service tahkimi.
Kamikaze alt-FSM: Intikal(100m,PurePursuit)→Dalış(−45°,TECS,28-30m/s)→QR(50m↓,perspektif+dual decode)→PullUp(R45m,2.7G).

**HSS (§13):** APF (k_att 0.5-1.0, k_rep 5-20, d₀=r+25m, 10Hz) + yerel-min(v<2 & |F|<0.5→pertürbasyon→3 fail→Dubins R_min).

**Sunucu (§15):** ServerClock 1Hz midpoint offset; telemetri governor ≤2Hz (>2Hz→400/err3); aralık doğrulama
(dikilme[-90,90],yonelme[0,360],yatis[-90,90])→clamp/iptal (-0.2/sn önle).

**Failsafe (§18):** ArduPilot native (RC 5s/batt %20/GPS/geofence) + mission_fsm degraded + watchdog + RC override üstün.
mission_link/Wi-Fi kopması uçuşu durdurmaz.

**Kırmızı çizgiler:** rosbridge/C# ROS2 binding yok; DDS ağa sızmaz; tek yazıcı invaryantı; ENU↔NED tek yerde;
QoS merkezî; WPF reposu yeniden yazılmaz; kritik döngü bloklanmaz; mod/faz flapping yok (histerezis); hardcoded sihirli sayı yok.

**Sahiplik (§24):** Sen=msgs+mission_link+mission_fsm+bringup+hss+kamikaze+lock+target_selector+mock_server;
Emircan=perception; Kenan=sim/güdüm-tuning; Hüseyin=WPF GCS.

---

## KARARLAR

- **[K-01] ROS sürümü = ROS2 Humble.** SAD C1 + prompt §1 mutlak kısıt olarak sabitler. KESIN_PLAN §12'deki
  Noetic/Humble çatalı Humble lehine kapandı (container, Xavier NX). Gerekçe videoda "Noetic EOL" ile sahiplenilir.
- **[K-02] Gazebo Faz -1 kapsamı dışı.** Kabul Kapısı -1 (boş SITL takeoff) Gazebo gerektirmez — saf ArduPilot
  SITL headless uçar. gz/ros_gz köprüsü (SAD §25 açık nokta #1) sanal kamera gerektiğinde (Faz 3) netleştirilecek.
  Dev imajı SITL+MAVROS'a odaklı tutuldu ki kapı hızlı ve sağlam yeşile dönsün.
- **[K-03] Faz -1 smoke test aracı = ArduCopter.** Kapı metni "GUIDED; arm; takeoff" copter idiyomuyla birebir ve
  headless'ta en güvenilir. Yarışma aracı sabit-kanat (plane); ArduPlane SITL Faz 1 bringup'ta (sitl.yaml) kurulacak
  (waf ccache ile ucuz). Faz -1 amacı: araç değil **toolchain** doğrulaması.

---

## FAZ CHECKLIST

- [x] **Faz -1 — Geliştirme ortamı** (dev container + SITL) — ✅ **KABUL KAPISI -1 GEÇİLDİ**
  - [x] Repo iskeleti + git init
  - [x] docker/Dockerfile.dev (ROS2 Humble + ArduPilot SITL + MAVROS + python deps)
  - [x] docker/Dockerfile.jetson-humble (⚠️ ON-DEVICE, test edilemez)
  - [x] docker/compose.dev.yaml + Makefile + scripts
  - [x] Dev imajı build (gokdogan-dev:latest, 5.16GB)
  - [x] **Kabul Kapısı -1:** ros2 humble + colcon 0.20.1 + sim_vehicle.py --help ✅ + SITL GUIDED/arm/takeoff → 9.21m ✅
- [ ] Faz 0 — Bootstrap & kontratları dondur (gokdogan_msgs, mission_link şeması, qos, frames)
- [ ] Faz 1 — MAVROS bringup + boş graph + SITL
- [ ] Faz 2 — mission_link + Mock GCS
- [ ] Faz 3 — Algı (dev modda)
- [ ] Faz 4 — Güdüm & hedef seçimi
- [ ] Faz 5 — Kamikaze + HSS
- [ ] Faz 6 — Mock server + video + tam döngü
- [ ] Faz 7 — Senaryo runner + 8 KTR senaryosu
- [ ] Faz 8 — Failsafe & gözlemlenebilirlik
- [ ] Faz 9 — WPF entegrasyonu

## GEÇİLEN KABUL KAPILARI

- **Kabul Kapısı -1** (2026-07-01): Dev container build oldu; container içinde `ros2` (Humble),
  `colcon` (0.20.1), `sim_vehicle.py --help` (ArduPilot SITL), MAVROS paketi mevcut; boş ArduCopter
  SITL aracı headless GUIDED moda geçip arm oldu ve NAV_TAKEOFF ile 9.21 m'ye çıktı. Doğrulama:
  `make verify-env` + `make verify-sitl` (scripts/verify_env.sh, scripts/sitl_smoke.sh, scripts/smoke_takeoff.py).

## AÇIK SORUNLAR

- SAD §25: Gazebo Classic 11 vs gz+ros_gz (Faz 3'te netleşir) · mission_link UDP fast-path gerçekten gerekli mi
  (Faz 2 entegrasyon testinde ölçülür) · video overlay senkron (GCS-side vs onboard-bake, Faz 5/9).
