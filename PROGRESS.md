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
- **[K-04] MAVROS launch'ta `name='mavros'` VERİLMEZ.** Launch Node'da `name='mavros'` zorlamak, MAVROS'un
  `command` eklentisi servislerini (`/mavros/cmd/arming`, `/mavros/cmd/takeoff`) keşfedilemez yapıyordu
  (`sys_status` servisleri — set_mode/set_stream_rate — çalışırken). name kaldırılınca command servisleri geldi.
  (Faz 1'de günlerce süren teşhisin kök nedeni #1.)
- **[K-05] Arm+takeoff BİRLEŞİK ve gecikmesiz gönderilir.** ArduCopter GUIDED'da arm sonrası ~1s içinde takeoff
  gelmezse otomatik disarm ediyor. mission_fsm, arm ve takeoff'u tek worker adımında art arda yürütür
  (`arm_takeoff` komutu). Ayrıca EKF/GPS için arm öncesi settle (prearm_settle_s). (Kök neden #2.)
- **[K-06] MAVROS servis çağrıları ayrı context + senkron worker thread'de.** LifecycleNode+MultiThreadedExecutor
  bağlamında `wait_for_service`/keşif güvenilmezdi; MAVROS komutları ayrı rclpy Context'li yardımcı node'da,
  tek worker thread'de senkron (diag ile doğrulanmış düz-node deseni) yürütülür. Kontrol timer'ı bloklanmaz.
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
- [x] **Faz 0 — Bootstrap & kontratları DONDUR** — ✅ **KABUL KAPISI 0 GEÇİLDİ**
  - [x] gokdogan_msgs: 13 msg + 2 srv + 1 action (BBox/Track/Tracks/Detections/LockEvent/Target/
        MissionMode/MissionCommand/Opponent/Opponents/Hss/HssList/AircraftState; SetMissionMode/ArmDisarm; ExecuteKamikaze)
  - [x] gokdogan_common: merkezî QoS (qos.hpp + qos.py, 7 profil) + C++/Python parite testleri
  - [x] gokdogan_guidance: frames (ENU↔NED, hpp + py) + round-trip identity testleri
  - [x] contracts/: mission_link.schema.json (JSON Schema) + mission_link.md + 19 doğrulama testi (WPF FlightState map)
  - [x] pre-commit (black/flake8/clang-format) + .flake8 + pyproject + .clang-format; CI güncellendi
  - [x] **Kabul Kapısı 0:** colcon build (3 paket) ✅ · colcon test 52/52 ✅ · şema 19/19 ✅ · frames round-trip ✅
- [x] **Faz 1 — MAVROS bringup + boş graph + SITL** — ✅ **KABUL KAPISI 1 GEÇİLDİ**
  - [x] gokdogan_bringup: competition.launch.py (mode:=sitl|hardware) + config/{sitl,hardware}.yaml + CycloneDDS config
  - [x] gokdogan_mission_fsm: lifecycle node (IDLE), SetMissionMode srv, /mission/mode, tek-yazıcı active_service,
        MAVROS set_mode/arming/takeoff (fsm_core 7 unit test)
  - [x] gokdogan_mavlink_iface: /aircraft/state derleyici (MAVROS→AircraftState)
  - [x] bringup launch_test (SITL'siz smoke) + run_sitl_stack.sh (tam SITL otonom kalkış)
  - [x] **Kabul Kapısı 1:** SITL otonom kalkış → rel_alt 14.996m, FSM IDLE→TAKEOFF→CRUISE ✅; 63 test yeşil
- [x] **Faz 2 — mission_link + Mock GCS** — ✅ **KABUL KAPISI 2 GEÇİLDİ**
  - [x] gokdogan_mission_link: UDP 5005 (aircraft_vision↑) + TCP 5006 (kontrol) köprü; heartbeat, reconnect,
        seq/ts, MessagePack length-prefix; protocol.py (bozuk/partial frame dayanıklı)
  - [x] mission_fsm: /mission/command (operatör) girişi → DFA geçişi (START_LOCK/ABORT/KAMIKAZE/SET_MODE)
  - [x] tools/mock_gcs.py: referans GCS (WPF taklidi) — TCP/UDP, exp-backoff reconnect, komut/relay
  - [x] Testler: protocol unit (framing/corrupt/partial/1000-paket) + entegrasyon (çift-yön + TCP kopma/reconnect)
  - [x] **Kabul Kapısı 2:** SITL→CRUISE→mock_gcs START_LOCK→FSM LOCKING; 141 aircraft_vision paketi (0 gap/0 bad);
        72 test yeşil
- [x] **Faz 3 — Algı (dev modda)** — ✅ **KABUL KAPISI 3 GEÇİLDİ**
  - [x] gokdogan_perception: kamera abstraction (synthetic/video/gazebo/⚠️usb) + inference (mock renk-blob /
        ⚠️onnx / ⚠️tensorrt) + ROI %70→640→geri; perception_node
  - [x] gokdogan_tracking: Kalman [px,py,vx,vy,ax,ay] + Hungarian (Cost=1−IoU, IoU≥0.3) + track yönetimi + node
  - [x] gokdogan_lock_validator: **5 kural** (merkez/boyut/içerme/yerde-reddi/otonom) + zaman penceresi
        (5s/4s/200ms) + last_locked_id; node
  - [x] Testler: 5 kuralın HER biri + zaman penceresi + last_locked_id + tracking + **sentetik pipeline entegrasyon**
  - [x] **Kabul Kapısı 3:** sentetik hedef→tespit→takip→doğru lock_event (pure-Python + ROS grafiği); 92 test yeşil
- [x] **Faz 4 — Güdüm & hedef seçimi (iki-faz cascade)** — ✅ **KABUL KAPISI 4 GEÇİLDİ**
  - [x] gokdogan_target_selector: S=0.40·mesafe+0.30·açı+0.20·geçmiş−0.10·risk + lead-angle + node
  - [x] gokdogan_guidance: geo (WGS84 flat-earth→NED) + controllers (PID anti-windup, PN divide-guard,
        rate-limit/LPF, faz-FSM histerezis 480/520) + guidance_node (iki-faz cascade, TEK-YAZICI gate)
  - [x] Testler: geo/selector/controllers + precise kapalı-döngü (kilit <30s) + faz-flapping assert
  - [x] **Kabul Kapısı 4:** SITL kaba faz — copter rakibe otonom yaklaştı (356m→0m intercept),
        guidance tek-yazıcı setpoint yazdı; precise+kilit pure-python <30s; 115 test yeşil
- [x] **Faz 5 — Kamikaze + HSS** — ✅ **KABUL KAPISI 5 GEÇİLDİ**
  - [x] gokdogan_hss: APF (kenar-uzaklığı tabanlı itici, c→0'da patlar) + Dubins yerel-min yedeği; hss_node
        (tek-yazıcı); mission_fsm tahkim (CRUISE'da HSS→SVC_HSS)
  - [x] gokdogan_kamikaze: kamikaze_fsm (Intikal/Dalış/QR/PullUp + min-alt güvenlik pull-up, G≤3 clamp,
        2 deneme) + qr.py (CLAHE+adaptive+perspektif+dual decode) + kamikaze_node (ExecuteKamikaze action)
  - [x] Testler: APF 5 senaryo **0 ihlal** + Dubins; kamikaze FSM guard'ları; QR eğik plaka decode
  - [x] **Kabul Kapısı 5:** SITL HSS kaçınma — copter HSS'i ihlal etmeden hedefe (min_clearance=5.5m>0,
        active_service=SVC_HSS tahkim); kamikaze FSM+QR birim-test; 134 test yeşil
- [x] **Faz 6 — Mock server + video + tam döngü** — ✅ **KABUL KAPISI 6 GEÇİLDİ**
  - [x] tools/mock_server.py: yarışma API emülatörü (giriş/sunucusaati/telemetri_gonder/kilitlenme/
        kamikaze/qr/hss + DEV /_stats); saf `ServerCore` (governor ≤2Hz→400/err3, aralık→400/err4,
        sentetik rakip/HSS/QR) + stdlib http.server (harici bağımlılık YOK)
  - [x] tools/mock_gcs.py: `GameServerClient` (ServerClock midpoint offset + monotonik; TelemetryHzMeter
        ≤2Hz governor; aralık CLAMP; 401→re-login, 5xx→backoff) + kilit/kamikaze POST + QR/HSS GET →
        onboard `server_data` relay (KTR alan adları → dondurulmuş şema $defs)
  - [x] gokdogan_video_streamer: saf pipeline builder (hw nvv4l2h264enc / dev x264enc→RTSP factory) +
        video_streamer_node (GstRtspServer varsa STREAMING, yoksa retry+DEGRADED, ASLA çökmez) +
        launch `enable_video` + sitl/hardware config; Dockerfile.dev'e GStreamer+gi bağımlılıkları
  - [x] Testler: mock_server/GameServerClient 18 (governor/aralık/offset/clamp/olay/relay) + video
        pipeline 8; run_full_loop_demo.sh + Makefile (run-full-loop-demo, mock-server, tools-test)
  - [x] **Kabul Kapısı 6:** SITL→CRUISE → mock_gcs ≤2Hz telemetri (80 paket/40s, 0 rate-reject) +
        ServerClock 80 senkron + rakip/HSS relay + /lock/event→lock_valid→kilit POST (3) +
        aralık-dışı telemetri REDDEDİLDİ (400/err4); 142 colcon + 19 şema + 18 tools test yeşil
- [x] **Faz 7 — Senaryo runner + 8 KTR senaryosu** — ✅ **KABUL KAPISI 7 GEÇİLDİ**
  - [x] sim/scenario_runner.py: YAML spec loader + **saf kabul-değerlendirici** (lte/lt/gte/gt/eq/in/
        between) + 8 senaryo simülatörü. HSS = **gerçek** `gokdogan_hss.apf` (LPF vground modeli →
        yerel-min kaçış), kamikaze = **gerçek** `gokdogan_kamikaze.kamikaze_fsm`; diğerleri fiziğe
        dayalı kinematik. `--all` + JSON rapor.
  - [x] sim/scenarios/*.yaml (8): otonom kalkış-iniş (hız<12) · waypoint (cross-track<5m) · çoklu-İHA
        kilit (<30s) · HSS (0 ihlal) · kamikaze (G≤3, QR, ≤2s) · tam müsabaka (skor>800) ·
        haberleşme kaybı (10s→RTL) · batarya (<%20→RTL). Her biri `live_target` ile canlı SITL eşli.
  - [x] sim/test_scenario_runner.py (25): değerlendirici geçen+kalan girdi (kriterler kof değil),
        spec loader, 8 senaryo pass + **bozunca düşme** testleri (overspeed/uzak-hedef/düşük-skor/
        eşik-altı-failsafe/dev-HSS)
  - [x] scripts/run_scenarios.sh + Makefile (run-scenarios, sim-test → make test'e dahil)
  - [x] **Kabul Kapısı 7:** `make run-scenarios` → **8/8 senaryo** kabul kriterini geçti (deterministik);
        HSS+kamikaze gerçek çekirdek. 142 colcon + 19 şema + 18 tools + **25 sim** test yeşil
- [x] **Faz 8 — Failsafe & gözlemlenebilirlik & sertleştirme** — ✅ **KABUL KAPISI 8 GEÇİLDİ**
  - [x] mission_fsm/failsafe_core.py: **saf** FailsafeMonitor — SAD §18 tüm tetikler (RC 5s→LAND/
        GCS 10s→RTL/GPS glitch→LAND/batt%20→RTL/geofence→RTL/watchdog→RTL) + öncelik + debounce +
        latch; RC override→MANUAL üstün; **İ2: mission_link kaybı ≠ failsafe** (otonom devam);
        batarya 0/raporlanmadı → yanlış-tetik yok
  - [x] gokdogan_common: watchdog.py (node heartbeat/stale + grace) + structured_log.py (JSON olay +
        TimeBase sys↔server↔ros offset) — saf, merkezî
  - [x] mission_link/metrics.py: LinkStats (seq-kayıp %, tek-yön gecikme, dup/reorder) →
        mission_link_node `/health/mission_link` 1Hz yayın (SAD §22)
  - [x] mission_fsm_node entegrasyon: failsafe timer (5Hz) + watchdog (aircraft_state liveness) +
        RC-override algısı (mavros mode) + injectable /failsafe/{gcs,rc,gps,geofence}_ok → RTL/LAND/
        MANUAL + MAVROS set_mode + yapısal JSONLOG + `/health/status` yayını
  - [x] config failsafe eşikleri (sitl+hardware) + ArduPilot native FS param notu (⚠️ on-device) +
        scripts/record_bag.sh (rosbag2 -a) + Makefile (run-failsafe-demo, record)
  - [x] Testler: failsafe 16 (her tetik/öncelik/debounce/latch/İ2/RC-override) + watchdog 5 +
        structured_log 4 + LinkStats 6 = 31 birim
  - [x] **Kabul Kapısı 8:** SITL → CRUISE → GCS-loss <10s **debounce (yanlış RTL yok)** →
        aircraft_state_node öldür → **watchdog(3s) → mission_fsm RTL** (gerçek MAVROS RTL) +
        /health/status stale=['aircraft_state'] + yapısal JSON failsafe log; 175 colcon + 62
        (şema/tools/sim) test yeşil
- [x] **Faz 9 — WPF (GCS) entegrasyonu** — ✅ **KABUL KAPISI 9 (mission_link seam) GEÇİLDİ**
  - [x] WPF reposu entegre: `TEKNOFEST-GOKDOGAN/` (SAD §21 sibling; -main soneki temizlendi, cruft yok)
  - [x] `GOKDOGANIHA.Core/Services/MissionLink/`: **MsgPack** (bağımlılıksız codec) + MissionLinkProtocol
        (dondurulmuş şema, FlightState vision map) + **MissionLinkClient : IFlightStateSource** (UDP 5005
        vision + TCP 5006 kontrol, reconnect/heartbeat, lock_valid/kamikaze_result olayları) + TcpFramer +
        **MissionLinkServerBridge** (onboard-otoriter kilit/kamikaze → ServerClock damgalı sunucu POST) +
        MissionLinkOptions
  - [x] `Services/Mavlink/`: MavlinkFlightStateSource : IFlightStateSource (RF→FlightState uçuş alanları;
        decode enjekte edilir — ⚠️ ON-DEVICE MAVLink NuGet) + saf MavlinkFields.ApplyTo + MavlinkOptions
  - [x] App.xaml.cs wiring: MissionLinkClient + Bridge composition; C# KilitlenmeDenetim/KamikazeFsm
        link-up guard ile AYNA'ya alındı (çift-POST önlendi, SAD §14)
  - [x] Yeni cross-platform test projesi `GOKDOGANIHA.MissionLink.Tests` (net10.0): **19 test** —
        MsgPack round-trip + **çapraz-dil decode (Python protocol.py byte'ları)** + FlightState map +
        TcpFramer + Bridge POST + MAVLink map
  - [x] **Kabul Kapısı 9:** `dotnet build` Core temiz + 19/19 test yeşil; **çift-yön çapraz-dil doğrulama**
        (Python→C# decode + C#→Python decode **dondurulmuş şemaya GEÇERLİ**); **canlı çapraz-süreç**
        (Python UDP aircraft_vision → C# MissionLinkClient soketi → FlightState: locked/bbox/team doğru).
        ⚠️ Tam WPF UI uçtan-uca (harita/video/overlay) **Windows/.NET 10** gerektirir — saha/Hüseyin doğrular.

- [~] **Gazebo kamera-in-the-loop (ertelenen görsel-servo)** — **Adım 1 GEÇTİ** (devam ediyor)
  - **Karar [K-07]: Gazebo Classic 11** (gz Fortress değil) — SAD §25 açık nokta #1 kapandı.
    Gerekçe: ArduPilot+kamera+plane en olgun/dokümante Classic'te; KTR §8.3 birebir Classic; EOL 2026
    tek-sefer yarışma için sorunsuz; `gazebo_ros_camera`→`sensor_msgs/Image` en kısa yol. **Rakip:**
    önce basit hareketli model (actor), sonra ArduPilot SITL instance.
  - [x] Dockerfile.dev: `ros-humble-gazebo-ros-pkgs` + `xvfb` + `llvmpipe` → **headless yazılım render
        (GPU ZORUNLU DEĞİL)**; ArduPilot build cache korunarak yeni katman
  - [x] sim/gazebo/worlds/gokdogan_test.world: kamera (82° FOV, gazebo_ros_camera) + uçan **kırmızı
        rakip** (actor trajectory, ROI merkezinde)
  - [x] perception `_on_image`: **cv_bridge yoksa numpy fallback** (rgb8→bgr, taşınabilir — imaj rebuild'siz)
  - [x] scripts/run_gazebo_smoke.sh + `make run-gazebo-smoke`
  - [x] **Adım 1 doğrulandı:** gzserver headless (llvmpipe) render → `/gokdogan_camera/image_raw` **6.4Hz**
        → perception (source=gazebo, mock renk-blob) → **kırmızı rakip TESPİT** edildi.
        *(Not: `set -u` aktifken `source .../gazebo/setup.sh` script'i sessizce çökertiyordu → tüm
        source'lar `set +u` altına alındı.)*
  - [x] **Adım 2:** rakip plane-şekilli (kırmızı, gövde+kanat+kuyruk) + **QR yer-hedefi** (zeminde
        2×2m QR "teknofest2025" + 4 yanı 45° engel, qr_ground_target) · rqt için `make shell` X11 forward
  - [x] **Adım 3:** best.pt → ONNX export (izole venv; sınıf `iha`, çıktı [1,5,8400]) + **OnnxDetector**
        implemente (YOLOv8/v11 decode + NMS + ROI geri-ölçek) + perception conf/iou param. **Sonuç:**
        gerçek YOLO Gazebo rakibini **tespit ediyor** (conf=0.12). **Domain-gap:** gerçek-eğitimli model
        primitife ~0.19 güven → sim'de eşik düşük (0.12), gerçek/on-device'de 0.35. Gerçekçi mesh (Adım 4
        Talon) güveni artırır. 175 colcon test yeşil (regression yok).
  - [x] **Adım 4a:** ardupilot_gazebo (khancyr) **gazebo11'de derlendi** (libArduPilotPlugin.so) →
        **kenetleme ÇALIŞIYOR:** Gazebo(iris+ArduPilotPlugin) ↔ ArduCopter SITL (`-f gazebo-iris`) ↔
        MAVROS ↔ mission_fsm. `make run-gazebo-sitl`: araç **Gazebo fiziğinde otonom kalktı** (rel_alt
        14.97m, FSM TAKEOFF→CRUISE), kendi kanıtlanmış stack'imizle. Makefile: `gazebo-plugin` (bir-kez
        derle) + `run-gazebo-sitl`.
    - **Karar [K-08] KRİTİK gotcha:** gzserver, ölü `models.gazebosim.org` online DB'sini fetch'te
      ASILIYOR → ArduPilotPlugin yüklenmez, 9002 (FDM) açılmaz, SITL "Waiting for connection"'da takılır.
      Çözüm: **`GAZEBO_MODEL_DATABASE_URI=""`** (tüm gazebo-SITL scriptlerinde şart). Prearm: gerçek-zaman
      (speedup 1) → EKF/GPS settle ~18s.
  - [x] **Adım 4b:** **sabit-kanat kenetleme + kamera ÇALIŞIYOR.** `gokdogan_zephyr` (SwiftGust zephyr
        airframe'ini include eden **düz-SDF** wrapper + ArduPilotPlugin; xacro/ZED bağımlılığı YOK →
        Classic 11 parse eder). ArduPlane `-f gazebo-zephyr` ile kenetlendi: **GPS_FIX=6 (RTK)**, plugin
        9002 bind. Burun kamerası → `/gokdogan_camera/image_raw` (görsel-servo altyapısı). Dünya:
        `sim/gazebo/worlds/gokdogan_plane.world`. GUI: `WORLD=.../gokdogan_plane.world make gazebo-gui`.
    - **Not:** SwiftGust zephyr **demo** modeli xacro kullanıyor → Classic parse edemiyor; base airframe
      (7 LiftDrag, IMU, GPS) düz-SDF → onu include edip plugin'i düz-SDF ELLE ekledim (çalıştı).
  - [~] **Adım 4c:** Baylands indirildi (PX4-SITL_gazebo-classic; world + arazi + **spherical_coordinates**
        GPS orijini). Plane dünyasına GPS orijini eklendi (home=(0,0) sorunu çözüldü). Birleşik sahneye
        entegrasyon bekliyor.
  - [x] **Adım 4d-1 (pivot):** zephyr aero uçurulamadı (mu=1+ref fizik+40m/s wrench fırlatmada bile
        takla; kare-yakalama ile görsel teşhis). Görsel-servo platformu → **gokdogan_iris_cam**
        (iris + burun kamerası). **Copter tam stack ile Gazebo'da uçuyor** (TAKEOFF_ACK→CRUISE 14.97m).
        Arm fix: kamera linkine gerçekçi atalet (minik kütle ODE titreşimi→"Accels inconsistent") +
        `sim/gazebo/config/gazebo_sitl.param` (SIM-only ARMING_CHECK=0). Uçan kameradan dünya
        görüntüsü doğrulandı (rakip+QR karede).
  - [x] **Adım 4d-2 (TALON):** `gokdogan_talon` — ArduPilot SITL_Models **mini_talon_vtail** portu
        (SDF 1.9→1.6, 36 degrees-pose→radyan, 6 LiftDrag gz→Classic birebir, V-tail kanal haritası
        ch0=aileronlar/ch1+ch3=ruddervator/ch2=motor, gz-only sistemler temizlendi, navsat kaldırıldı,
        burun kamerası eklendi; `_port_talon.py` scripti). **Classic'te parse + plugin 9002 bind +
        kamera + ArduPlane HEARTBEAT (V-tail param dosyasıyla) ✅.** Uçuş (hand-launch) sonraki adım.
  - [x] **Adım 4d-3 (GÖRSEL-SERVO MILESTONE):** kameralı copter **tam stack ile uçtu**
        (MAVROS→fsm TAKEOFF_ACK→CRUISE 14.97m, gorsel_servo dünyası) ve kamerasının kareleri
        **OnnxDetector'dan 0.27–0.43 güvenle tespit** üretti (rakip 28m). **Kritik düzeltme:**
        cv_bridge bgr8 + RGB-eğitimli YOLO → OnnxDetector'a BGR→RGB eklendi (GERÇEK kamerada da
        gerekliydi!). Canlı döngüde topic-echo ölçümü llvmpipe CPU doygunluğunda seyrek yayını
        kaçırıyor → GPU makinede gerçek-zamanlı akar. Demo: `make run-gorsel-servo` (GZ_HW=1 ile GUI).
  - [ ] **Kalan (sim — GUI/GPU ile devam):** Talon hand-launch uçuş tuning'i (kenetleme ✅; headless
        tek-atış denemesinde arm reddedildi — `TALON=1 GZ_HW=1 make run-plane-handlaunch` ile GUI'de
        izleyerek: arm moduna FBWA dene, TOSS_* parametreleriyle fırlatma yönü/gücü ayarla) ·
        rakip Talon SITL (-I1) · LOCKING görsel-servo kapalı döngü (guidance precise; llvmpipe CPU
        doygunluğu nedeniyle GPU makinede) · Baylands saha GUI doğrulaması.

## GEÇİLEN KABUL KAPILARI

- **Kabul Kapısı -1** (2026-07-01): Dev container build oldu; container içinde `ros2` (Humble),
  `colcon` (0.20.1), `sim_vehicle.py --help` (ArduPilot SITL), MAVROS paketi mevcut; boş ArduCopter
  SITL aracı headless GUIDED moda geçip arm oldu ve NAV_TAKEOFF ile 9.21 m'ye çıktı. Doğrulama:
  `make verify-env` + `make verify-sitl` (scripts/verify_env.sh, scripts/sitl_smoke.sh, scripts/smoke_takeoff.py).
- **Kabul Kapısı 0** (2026-07-01): Kontratlar DONDURULDU. `colcon build` 3 paket (gokdogan_msgs/common/guidance)
  yeşil; `colcon test` 52 test / 0 hata / 0 başarısızlık (C++ gtest QoS+frames parite, Python QoS golden +
  18 frames param); mission_link JSON Schema 19/19 geçti (geçerli örnekler valide, bozuklar reddedildi,
  WPF FlightState eşleme alanları mevcut). Doğrulama: `make ws-build` + `make test`.
  ⚠️ **Bu noktadan sonra kontratlar (msgs + mission_link şeması) değişiklik için onay gerektirir.**
- **Kabul Kapısı 1** (2026-07-01): SITL otonom kalkış — operatör TAKEOFF → araç ~15m'ye çıktı, FSM IDLE→TAKEOFF→CRUISE
  (2x tekrarlanabilir). Doğrulama: `make run-sitl-stack`.
- **Kabul Kapısı 2** (2026-07-01): mission_link çift-yön + kopma dayanıklılığı. SITL→CRUISE→mock_gcs START_LOCK→
  FSM LOCKING; mock_gcs 141 aircraft_vision paketi aldı (0 seq-gap, 0 bad-frame). protocol 1000-paket loss/disorder
  testi çökmesiz. Doğrulama: `make run-mission-link-demo` + `make test`.
- **Kabul Kapısı 3** (2026-07-01): Algı pipeline. 5 kilit kuralının her biri + zaman penceresi (5s/4s/200ms) +
  last_locked_id ayrı ayrı test edildi. Sentetik hedef→mock tespit→Kalman/Hungarian takip→kilit denetimi
  uçtan uca doğru lock_event üretti (pure-Python entegrasyon testi + ROS grafiği demo). TensorRT/ONNX/USB
  kamera ⚠️ ON-DEVICE. Doğrulama: `make test` + `make run-perception-demo`.

- **Kabul Kapısı 4** (2026-07-01): Güdüm cascade. target_selector (S skoru + lead-angle) ve guidance
  (PID/PN/faz-FSM) çekirdekleri birim-test edildi. Hassas faz kapalı-döngü (piksel PID → merkezleme → kilit)
  pure-python'da <30s; faz-FSM histerezis bandında flapping yok. SITL kaba faz: copter enjekte edilen rakibe
  otonom yaklaştı (356m→0m), guidance yalnız active_service=GUIDANCE'te setpoint yazdı (tek-yazıcı).
  Precise görsel-servo SITL kapalı-döngüsü kamera sim (⚠️ Gazebo) gerektirir — sim fazına ertelendi.
  Doğrulama: `make test` + `make run-guidance-demo`. **NOT:** colcon bazen launch/config değişiminde bringup'ı
  yeniden kurmuyor → demo öncesi `rm -rf install/gokdogan_bringup && make ws-build` veya temiz build önerilir.

- **Kabul Kapısı 5** (2026-07-01): Kamikaze + HSS. APF (kenar-uzaklığı itici + Dubins) 5 senaryoda **0 ihlal**;
  kamikaze FSM guard'ları (min-alt güvenlik pull-up, G≤3 clamp, 2 deneme) + QR pipeline eğik plaka decode
  birim-test. SITL: mission_fsm CRUISE'da HSS bölgesi olunca yazma hakkını HSS'e verdi (SVC_HSS tahkim);
  copter HSS'i ihlal etmeden (min_clearance=5.5m>0) hedefe ulaştı. Kamikaze dalışı sabit-kanat → sim fazına
  ertelendi. **NOT:** SITL'de speedup 10 kontrol döngüsünü sim-zamanında 10x kabalaştırıp aşıma yol açıyor →
  ince kontrol gerektiren senaryolar (HSS) speedup≤3 ile koşulmalı. Büyük graf keşif temposunu yavaşlatıyor →
  odaklı demolar minimal node kümesiyle. Doğrulama: `make test` + `make run-hss-demo`.

- **Kabul Kapısı 6** (2026-07-03): Tam döngü mock'larla. mock_server (yarışma API emülatörü) + SITL +
  onboard (fsm+mission_link+aircraft_state+video) + mock_gcs uçtan uca: SITL→CRUISE → GameServerClient
  login+ServerClock(80 senkron)+≤2Hz telemetri (80 paket/40s, **0 rate-reject** = governor çalıştı) +
  rakip/HSS relay (80 GET → /server/*). /lock/event enjekte → mission_link lock_valid → GCS →
  mock_server kilitlenme POST (3). Ceza-tetikleyici **aralık-dışı telemetri sunucuca REDDEDİLDİ**
  (400/hata_kodu=4); GameServerClient tarafında aynı veri CLAMP edilir (paket reddi/−0.2 önlenir).
  Doğrulama: `make run-full-loop-demo` + `make test`. **NOT (video):** dev container'da GStreamer/`gi`
  yok → video_streamer DEGRADED'e düşüp retry eder (çökmez, İ2); gerçek RTSP yayını için imaj rebuild
  (`make build`, Dockerfile.dev'e GStreamer+gst-rtsp-server+python3-gi eklendi) gerekir — nvv4l2h264enc
  yolu ⚠️ ON-DEVICE (Jetson NVENC). **NOT (aralık-reddi testi):** paylaşılan sunucuda 2Hz telemetri
  akışı sürerken gelen aralık-dışı POST önce rate-limit'e (err3) takılır → izole err4 doğrulaması için
  test akış durduktan sonra yapılır.

- **Kabul Kapısı 7** (2026-07-03): 8 KTR senaryosu otomatik. scenario_runner YAML senaryolarını
  (rakip/HSS/QR/rüzgâr + kabul kriterleri) deterministik simüle edip metrikleri kabul kriterine
  karşı değerlendirdi → **8/8 GEÇTİ**. HSS senaryosu gerçek APF çekirdeğini sürdü (min_clearance
  8.4m>0, 0 ihlal, hedefe ulaştı — yerel-min LPF vground modeliyle Dubins kaçışı tetiklendi);
  kamikaze gerçek FSM çekirdeğini sürdü (max_g=2.7≤3, QR okundu, min-alt korundu). Değerlendirici
  25 birim-testle doğrulandı — geçen+kalan girdilerle kriterlerin gerçekten ayırt ettiği, ve bir
  parametre bozulunca (overspeed/uzak-hedef/düşük-skor/eşik-altı/dev-HSS) senaryonun BAŞARISIZ
  olduğu. Doğrulama: `make run-scenarios` + `make test`. **NOT:** görsel-servo kilit (kamera-in-the-
  loop) ve sabit-kanat kamikaze dalışı Gazebo/plane gerektirir → analitik çekirdek koşuldu, canlı
  SITL fidelity her senaryonun `live_target` make hedefiyle (run-sitl-stack/guidance/hss/full-loop).
  Batarya/haberleşme failsafe canlı tetikleri **Faz 8** (ArduPilot native FS_BATT/FS_GCS) ile eşlenecek.

- **Kabul Kapısı 8** (2026-07-03): Failsafe & gözlemlenebilirlik. Saf failsafe_core (SAD §18 tüm
  tetikler + öncelik + debounce + latch) 16 birim-testle doğrulandı; İ2 kırmızı çizgisi test edildi
  (mission_link/Wi-Fi kaybı failsafe tetiklemez). watchdog + yapısal JSON log + LinkStats (seq-kayıp
  %/gecikme) saf + testli. SITL uçtan uca: CRUISE'da GCS-telemetri kaybı <10s **debounce** ile RTL
  tetiklemedi (yanlış-tetik yok); aircraft_state_node öldürülünce **watchdog** 3s'de bayatı algıladı →
  mission_fsm degraded **RTL**'ye geçti (gerçek MAVROS RTL modu) + `/health/status` stale listesini +
  yapısal JSON failsafe kaydını üretti. Katman-1 (ArduPilot native FS_THR/FS_GCS/BATT/FENCE) ⚠️
  ON-DEVICE — config'te parametre notu, saha ekibi Mission Planner ile ayarlar. Doğrulama:
  `make run-failsafe-demo` + `make test` + `make record`.

- **Kabul Kapısı 9** (2026-07-03): WPF GCS entegrasyonu — mission_link dikişi. Hüseyin'in WPF reposu
  (`TEKNOFEST-GOKDOGAN/`) workspace'e alındı. Diller-arası tek sınır C# tarafında yazıldı:
  bağımlılıksız MsgPack codec + MissionLinkClient (IFlightStateSource) + ServerBridge (onboard kilit/
  kamikaze → sunucu POST). **Dondurulmuş kontrat (Faz 0) çift-yön kanıtlandı:** onboard Python
  `protocol.py`'nin ürettiği gerçek MessagePack byte'ları C#'ta birebir çözüldü (19 birim-test, gömülü
  referans) ve C#'ın ürettiği operator_cmd/server_data Python'da çözülüp JSON Schema'ya GEÇERLİ bulundu.
  **Canlı çapraz-süreç:** Python UDP:5005'ten aircraft_vision → çalışan C# MissionLinkClient soketi →
  FlightState görüntü alanları (bbox/kilit/takım) doğru yazıldı. .NET 10.0.301 SDK ile `dotnet build`
  (Core, net10.0 cross-platform) + `dotnet test` Linux'ta koşuldu. **NOT:** WPF UI (net10.0-windows —
  harita/PFD/LibVLCSharp RTSP+overlay/MP4 kayıt) ve RF MAVLink decoder (NuGet) **Windows + donanım**
  gerektirir → SAD §24 gereği Hüseyin/saha ekibi doğrular; C# tel-protokolü kontratı burada donanımsız
  kilitlendi. Doğrulama: `dotnet test src/GOKDOGANIHA.MissionLink.Tests`.

- **Sim Adım 4d-4 — TALON GÖMÜLME/KİLİT KÖK NEDENİ ÇÖZÜLDÜ** (2026-07-05): Talon'un yarı gömülü
  donması, EOF spam'ı ve ARM başarısızlığı tek kök nedene indi: **Gazebo Classic ODE, gövde (1.8kg) ile
  minik-ataletli kontrol yüzeyi linkleri (0.01kg/~1e-6) aynı modelde olunca modeli dünya origin'ine
  kilitliyor** (include spawn pozu bile uygulanmıyor). gz-sim'in DART fiziği bunu tolere ettiğinden
  orijinal modelde görünmüyordu — SDF 1.9→1.6 portunun kendisi doğruydu. Teşhis: parça-parça bisect
  (yalın gövde ✅ / +tekerlek ✅ / +motor ✅ / +aileron ❌ / +ruddervator ❌), sonra üç aday düzeltme
  (limit/atalet/joint-pose) tek koşuda → yalnız atalet düzeltmesi işledi. Fix: 4 kontrol yüzeyi
  0.05kg/1e-4'e çıkarıldı (model.sdf'e not düşüldü). Sonuç: ARM ✅ + yerden hızlanma ✅ + havalanma
  (max 8.7m, thr %31→78, gspd 12+) ✅ — kalan iş TECS/gaz salınımı tuning'i (uçuşu sürdürme).
  Temizlik (aynı gün): px4_gazebo_classic + SITL_Models + swiftgust klonları (2.7GB) ve zephyr çıkmazı
  silindi (mini_talon_vtail.param → sim/gazebo/config/'e taşındı), handlaunch Talon-varsayılan oldu,
  gorsel-servo/handlaunch scriptlerine adımlı ilerleme + fail-fast + TAKEOFF retry + canlı telemetri
  eklendi, `.gitignore`'daki `models/` kalıbı `/models/` yapıldı (sim modellerimizi yanlışlıkla
  gizliyordu), crash dump/eeprom/log artıkları silinip ignore'landı.

- **Sim Adım 4d-5 — GUI kasması: GPU aslında konteynere hiç verilmiyormuş** (2026-07-06): `GZ_HW=1`
  yalnız `LIBGL_ALWAYS_SOFTWARE`'i kapatıyordu ama docker'a `--device /dev/dri` verilmediği için Mesa
  GPU'ya ulaşamayıp sessizce yazılım render'a düşüyordu — kasmanın kökü bu. Fix: Makefile'a `GPU_DEV`
  (host'ta /dev/dri varsa `--device /dev/dri`) eklendi (X11 kullanan tüm hedefler), script'lere
  "GZ_HW=1 ama /dev/dri yok" uyarısı + dünya hazır olunca **gerçek-zaman faktörü (RTF)** çıktısı
  eklendi (headless referans: 0.99). Ek: gölgeler kapatıldı (gorsel_servo + saha), iris_cam'deki ölü
  `gimbal_small_2d` include'u kaldırıldı (silinen klondaydı — "Unable to find uri" hatası).
  Kullanıcının tek seferlik "MAVROS 90s bağlanamadı" hatası fail-fast'in doğru çalışması; yazılım
  render altında SITL↔plugin el sıkışma çakılmasıydı, GPU ile kaybolması beklenir.
  **Devamı (aynı gün):** `--device /dev/dri` tek başına yetmedi — imaj ENV'inde gömülü
  `LIBGL_ALWAYS_SOFTWARE=1` script'lerde GZ_HW=1 iken unset edilmiyordu; cihaz görünür + GL yazılıma
  zorlanmış çelişkisi gzclient'ta "Unable to create the rendering window" verdi. Fix: iki script de
  GZ_HW=1'de `unset LIBGL_ALWAYS_SOFTWARE GALLIUM_DRIVER QT_QPA_PLATFORM`. Doğrulama (kullanıcının
  Wayland/XWayland oturumunda, konteynerden): glxinfo renderer **RENOIR (radeonsi)** + GUI tam koşu:
  pencere hatası 0, MAVROS 3s, TAKEOFF kabul, HAVADA ✅.

- **Sim Adım 4d-6 — Saha dünyası Talon'a çevrildi + uçuş-dinamiği teşhisi** (2026-07-07):
  gokdogan_saha.world artık iris yerine gokdogan_talon içeriyor (rakip yörüngesi + QR + pad, Talon'un
  +x fırlatma yönüne göre yeniden konumlandı); `make run-saha` hedefi eklendi; kamera izleme talimatı
  (rqt_image_view /gokdogan_camera/image_raw) script'e yazıldı. **Teşhisler:** (1) Baylands arazi meshi
  orijinde uçağı içine gömüyor — izole testte düz zeminde wrench-toss 8.7m verirken saha'da 0.3m + motor
  %0 (arazi teması kuvveti emiyor); düz zemin + hava-spawn'da motor %57-72 spool + hava hızı 18 m/s
  doğrulandı → gömülme kesin. Headless Baylands (llvmpipe) çok yavaş yüklendiğinden orijin zemin
  yüksekliği ölçülemedi; spawn yeri GPU doğrulamasına bırakıldı. (2) **Asıl darboğaz: Talon hiçbir
  dünyada uçuşu SÜRDÜREMİYOR** — motor gazı açılıyor (%60-97), yer hızı 12-21 m/s'e çıkıyor ama hava
  hızı düşük/düzensiz (<10) kalıp irtifa tutmuyor (max 0.6-8.7m sonra savrulup düşüyor). Kök: V-tail
  aero/kontrol otoritesi + TECS/kalkış tuning'i + muhtemel CG/thrust dengesizliği. Bu, ayrı bir
  odaklı çalışma (SİM PROMPT'u — docs/PROMPT_SIM.md) olarak devredildi.

## AÇIK SORUNLAR

- SAD §25: Gazebo Classic 11 vs gz+ros_gz (Faz 3'te netleşir) · mission_link UDP fast-path gerçekten gerekli mi
  (Faz 2 entegrasyon testinde ölçülür) · video overlay senkron (GCS-side vs onboard-bake, Faz 5/9).
