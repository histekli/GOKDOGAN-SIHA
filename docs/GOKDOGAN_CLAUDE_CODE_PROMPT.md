# GÖKDOĞAN — CLAUDE CODE MASTER BUILD PROMPT

> Bu dosya Claude Code'a verilecek **operasyonel inşa talimatıdır.** Amaç: TEKNOFEST Savaşan İHA 2026 yazılımını sıfırdan, mimariye **birebir** uygun, hatasız ve test-edilebilir biçimde inşa etmek.
> **Tek doğruluk kaynağı mimari dosyasıdır:** `docs/GOKDOGAN_YAZILIM_MIMARISI.md` (SAD). Bu prompt = nasıl inşa edileceği; SAD = ne inşa edileceği.
> Dil: kod/identifier/commit/dosya adı **İngilizce**; açıklama Türkçe olabilir.

---

## 0. SANA ROLÜN (Claude Code)

Sen bu projenin **baş yazılım mühendisisin.** Görevin: aşağıdaki fazları **sırayla**, her birini **test edip doğrulayarak** tamamlamak. Başarı ölçütü kod satırı değil, **KTR puanını kazandıracak çalışan sistem**: otonom kilitlenme (500p), kamikaze (300p), otonom uçuş+iniş (150p), HSS kaçınma (ceza önler), telemetri (ceza önler), video (50p).

**Çalışma anlaşması (HER FAZDA UYGULA):**
1. **Fazlı + kapılı:** Bir faz, "Kabul Kapısı" (acceptance gate) geçilmeden sonrakine **geçme**. Kapıyı geçtiğinde dur, kısa rapor ver, kullanıcıdan onay bekle.
2. **Test-güdümlü:** Her node/modül için kodla birlikte test yaz. Build + test + lint **yeşil** olmadan ilerleme.
3. **SITL-önce, x86'da:** Jetson/TensorRT/gerçek kamera/Pixhawk'a **erişimin yok.** Her şey önce **x86 + ArduPilot SITL + mock'lar** ile koşmalı ve doğrulanmalı. Donanım-özel yollar (TensorRT, CSI/UVC kamera, UART) `mode:=hardware` flag'i arkasında, **stub/abstraction** ile; bunları "⚠️ ON-DEVICE DOĞRULAMA GEREKİR" diye işaretle, kendin test etme.
4. **İnkremental commit:** Her anlamlı adımda küçük, açıklayıcı commit (`feat(perception): ...`). Asla tek dev commit.
5. **İlerleme defteri:** Repo kökünde `PROGRESS.md` tut — faz checklist'i, geçilen kapılar, açık sorunlar, kararlar. Her faz sonunda güncelle.
6. **Yıkıcı işlemden önce sor:** `git push --force`, dosya silme, şema değişikliği gibi geri-dönüşsüz adımlarda onay iste.
7. **Belirsizlikte SAD'a bak, sonra sor:** Bir detay SAD'da varsa oradan al; çelişki/eksik varsa **uydurma**, kullanıcıya net soru sor.
8. **Kendi hatanı düzelt:** Build/test hatası alırsan logu oku, kök nedeni bul, düzelt, tekrar çalıştır. Hatayı görmezden gelme/atlama.

---

## 1. OKU VE İÇSELLEŞTİR (BAŞLAMADAN ÖNCE)

1. `docs/GOKDOGAN_YAZILIM_MIMARISI.md` (SAD) — **baştan sona oku.** Node grafiği (§5), QoS matrisi (§6), mesaj tanımları (§7), MAVROS/ENU-NED (§8), `mission_link` (§9), algı (§10), güdüm (§11), FSM (§12), HSS (§13), GCS (§14), sunucu (§15), video (§16), failsafe (§18), sim (§20), repo (§21), sahiplik (§24). Bu senin spec'in.
2. Varsa `docs/KESIN_PLAN_v4.md` — öncelik, kabul kriterleri, KTR uyumu.
3. Mevcut C# WPF reposu (Hüseyin): `https://github.com/huseyingenc-eem/TEKNOFEST-GOKDOGAN` — **SADECE OKU** (Faz 9'a kadar dokunma). Entegrasyon dikiş yerlerini anla: `Core/Models/FlightState.cs` (alanlar: `Latitude/Longitude/Altitude/Roll/Pitch/Heading/GroundSpeed/Airspeed/BatteryPercent/Mode/IsArmed/IsAutonomous/IsLocked/TargetTeamNumber/TargetCenterX/TargetCenterY/TargetWidth/TargetHeight`), `Abstractions/IFlightStateSource.cs`, `Abstractions/IFlightCommandSink.cs`, `Services/Api/GameServerClient.cs`. **`mission_link` şemasını bu alanlara birebir oturacak şekilde tasarla** (Faz 0).

**Mutlak kısıtlar (KTR/SAD — değiştirilemez):**
- ROS2 **Humble** (container, Xavier NX) + **MAVROS** köprü. Kontrol döngüsü onboard.
- GCS: .NET 10 / C# / WPF (mevcut repo). Sunucu I/O **C#'ta HttpClient**, tek yetkili IP, telemetri **≤2Hz**.
- Kamera **AR0234, 1920×1200, 82° FOV, 50fps**, merkez (960,600).
- Kilit kuralları, kamikaze 100m/45°/30m/28-30m/s/R45m/2.7G, APF+Dubins, hedef skor 0.40/0.30/0.20/0.10 — SAD §7,§11,§12,§13.

---

## 2. KIRMIZI ÇİZGİLER (ASLA İHLAL ETME)

1. **rosbridge / C# ROS2 binding KULLANMA.** Diller arası tek sınır `mission_link` (UDP+TCP, MessagePack). ROS2 ve WPF birbirinin stack'ini bilmez.
2. **DDS ağa sızmasın.** `ROS_LOCALHOST_ONLY=1`, CycloneDDS yalnız `lo`. Yarışma ağında keşif denenmez.
3. **Tek yazıcı invaryantı.** Pixhawk'a setpoint yazma hakkı yalnız `mission_fsm`'in belirlediği `active_service`'te. Hiçbir node bu kuralı atlamaz.
4. **ENU↔NED tek yerde.** Tüm dönüşüm `gokdogan_guidance/frames.{hpp,py}`'de. Başka hiçbir yerde elle yaw/koordinat çevirme YOK. (Klasik kontrol-bozan hata.)
5. **QoS merkezî.** Tüm profiller `gokdogan_qos`'ta tanımlı; publisher/subscriber **aynı** profili kullanır (uyumsuzluk Humble'da sessiz kopma yapar).
6. **WPF reposunu yeniden yazma.** Mevcut, kaliteli ve entegrasyon-hazır. Faz 9'da sadece 2 adapter + eksikler eklenir.
7. **Kritik döngüyü bloklama.** Görsel işlem (YOLO/Kalman) kontrol timer'ını (50/10Hz) asla geciktirmez (ayrı callback group / thread).
8. **Mod-flapping / faz-flapping YOK.** Kaba↔hassas geçişte histerezis (480/520m), durum makinelerinde guard.
9. **Setpoint timeout farkındalığı.** ArduPilot, setpoint akışı kesilirse GUIDED'dan çıkar/failsafe yapar → güdüm aktifken **sürekli** (≥10Hz) setpoint yayınla, durdurman gerekirse moddan çık.
10. **Hardcoded sihirli sayı YOK.** Tüm eşik/kazanç ROS2 param (YAML) veya C# settings'ten. Değerler SAD'dan.

---

## 3. FAZ -1 — GELİŞTİRME ORTAMI (önce bunu kur ve doğrula)

**Hedef:** x86'da ROS2 Humble + ArduPilot SITL + Gazebo + colcon çalışan, tekrarlanabilir bir dev/CI ortamı. Sen bunun **içinde** geliştirip test edeceksin.

**Yap:**
- `docker/Dockerfile.dev` — Ubuntu 22.04 + ROS2 Humble (desktop) + ArduPilot SITL + ardupilot_gazebo + colcon + python deps (msgpack, numpy, scipy, opencv-python, pyzbar, onnxruntime, pymavlink). Gazebo: `gz` (Harmonic) + `ros_gz` (Humble-doğal); Classic 11 alternatifini not düş.
- `docker/Dockerfile.jetson-humble` — **üretim** imajı (jetson-containers `dustynv/ros:humble-*` tabanlı + CUDA/TensorRT). Bunu **yazacaksın ama test edemezsin** → "⚠️ ON-DEVICE" işaretle.
- `docker/compose.dev.yaml` — dev container + SITL servisi.
- `.devcontainer/` (opsiyonel, VS Code).
- `Makefile` / `scripts/`: `make build`, `make test`, `make lint`, `make sitl`, `make run-sitl-stack`.

**Kabul Kapısı -1:** Dev container build oluyor; içinde `ros2 --version` (Humble), `colcon version`, `sim_vehicle.py --help` (ArduPilot SITL) çalışıyor; boş SITL aracı kalkıp uçabiliyor (`mode GUIDED; arm; takeoff`).

> Eğer ortam kurulamıyorsa (ağ/erişim), **DUR** ve kullanıcıya hangi bağımlılığın gerektiğini bildir.

---

## 4. FAZLI İNŞA PLANI

Her faz: **Amaç → Teslimat (dosyalar) → Notlar → Hata yönetimi → Testler → Kabul Kapısı → DUR/RAPOR.**

### FAZ 0 — Bootstrap & Kontratları DONDUR (en kritik)
**Amaç:** Workspace + tüm mesaj/şema kontratları; herkesin stub'a karşı paralel başlayabilmesi.
**Teslimat:**
- colcon workspace: `gokdogan-onboard/src/...` (SAD §21 yapısı).
- `gokdogan_msgs` paketi: **tüm** `.msg/.srv/.action` (SAD §7) — `BBox, Track, Tracks, Detections, LockEvent, Target, MissionMode, MissionCommand, Opponents, HssList, AircraftState`; srv `SetMissionMode, ArmDisarm`; action `ExecuteKamikaze`.
- `contracts/mission_link.md` + `contracts/mission_link.schema.json` — **MessagePack** şeması (dil-bağımsız). UDP `aircraft_vision` + TCP `lock_valid, kamikaze_result, operator_cmd, server_data, config`. Her mesaj: `type, seq, ts` + gövde. **vision alanları WPF `FlightState`'e birebir map** (TargetCenterX/Y/Width/Height, IsLocked, ...).
- `gokdogan_common/qos.hpp` + `qos.py` — merkezî QoS profilleri (SAD §6).
- `gokdogan_guidance/frames.hpp` + `frames.py` — ENU↔NED tek dönüşüm (yaw dahil) + birim testleri.
- Repo iskeleti: `README.md`, `PROGRESS.md`, `.gitignore`, `pre-commit` (clang-format/black/flake8), `.github/workflows/ci.yml` (colcon build+test on x86).
**Hata yönetimi:** schema validation (JSON Schema) testi; QoS profil tutarlılık testi.
**Testler:** `colcon build --packages-select gokdogan_msgs gokdogan_common gokdogan_guidance` yeşil; frames round-trip testi (ENU→NED→ENU = identity).
**Kabul Kapısı 0:** Mesajlar derleniyor, şema valide, frames testi geçiyor. → **DUR/RAPOR.** *(Kontratlar bu noktadan sonra dondurulur; değişiklik için onay gerekir.)*

### FAZ 1 — MAVROS bringup + boş graph + SITL
**Amaç:** Otonomi iskeletinin SITL'e bağlanması; mission_fsm IDLE; manuel komutla arm/takeoff.
**Teslimat:**
- `gokdogan_bringup`: `competition.launch.py` (`mode:=sitl|hardware`), `config/sitl.yaml` + `config/hardware.yaml`, MAVROS launch include.
- `gokdogan_mission_fsm`: **lifecycle node**, `IDLE` state, `SetMissionMode` srv, `/mission/mode` publish. MAVROS `set_mode/arming` çağrıları. **Tek yazıcı** iskeleti.
- `gokdogan_mavlink_iface` (gerekirse ince sarmalayıcı) — `/aircraft/state` publish (MAVROS topic'lerinden derlenmiş).
**Notlar:** SITL: MAVROS `fcu_url:=udp://:14555@`. Stream rate'leri artır (ATTITUDE/LOCAL_POSITION ≥50Hz).
**Hata yönetimi:** MAVROS bağlantı kaybı → FSM degraded/IDLE; mode reddi → retry + log; arming check fail → IDLE'da kal.
**Testler:** integration test (pytest + launch_testing): SITL kalkar, MAVROS connected, FSM IDLE→TAKEOFF, takeoff doğrulanır.
**Kabul Kapısı 1:** `make run-sitl-stack` ile araç otonom kalkıp belirli irtifaya çıkıyor. → **DUR/RAPOR.**

### FAZ 2 — mission_link + Mock GCS
**Amaç:** Diller arası sınırın çalışması; WPF olmadan onboard'ı test etmek.
**Teslimat:**
- `gokdogan_mission_link` (rclpy): UDP(5005) akış + TCP(5006) kontrol köprüsü; ROS2 topic ↔ soket. Heartbeat, reconnect (exp backoff), seq/ts, MessagePack çerçeveleme (TCP length-prefixed).
- `tools/mock_gcs.py` — **referans GCS:** TCP/UDP bağlanır, `operator_cmd` gönderir, `aircraft_vision`/`fsm_state` alır, `server_data` relay eder. WPF'in yapacağını birebir taklit eder (Faz 9 referansı).
**Hata yönetimi (kapsamlı):** TCP kopma→onboard otonom devam + GCS reconnect; UDP loss→latest-wins, stale flag; **partial/bozuk frame**→drop+log, çökme yok; şema-versiyon uyumsuzluğu→reddet+log; heartbeat timeout→link-lost event.
**Testler:** mock_gcs START_LOCK→FSM geçişi; onboard fsm_state→mock_gcs alır; TCP kopar→onboard devam eder (kanıtla); 1000 paket UDP loss/disorder altında çökme yok.
**Kabul Kapısı 2:** Tam çift-yön akış + kopma dayanıklılığı. → **DUR/RAPOR.**

### FAZ 3 — Algı (dev modda)
**Amaç:** Görüntü→tespit→takip→kilit-denetimi; tüm kilit kuralları.
**Teslimat:**
- `gokdogan_perception`: kamera **abstraction** — `source:=gazebo|video|synthetic|usb`. Dev: `tools/synthetic_target.py` (bilinen ground-truth bbox'lı hareketli İHA sprite'ları) + Gazebo kamera + video dosyası. **Inference abstraction:** `backend:=tensorrt|onnxruntime|mock`. Dev: ONNX Runtime CPU veya deterministik mock; **TensorRT yolu yazılır ama ⚠️ ON-DEVICE.** ROI %70→640×640→geri 1920×1200.
- `gokdogan_tracking`: Kalman ([px,py,vx,vy,ax,ay]) + Hungarian (Cost=1−IoU, IoU≥0.3 ID) + YOLO-her-5-kare. `/perception/tracks`, `/perception/selected_bbox`.
- `gokdogan_lock_validator`: **5 kural + ek** (SAD §7): merkez (yatay≤W/2, dikey≤H/2), %6 boyut, %90 IoU, 5s/4s pencere + 200ms tolerans (baş/bitiş hariç), last_locked_id, yerdeki hedef reddi, otonom-mod şartı. `/lock/event` (valid + canlı progress).
**Hata yönetimi (kapsamlı):** kamera frame yok/disconnect→reconnect+IDLE'a sinyal; inference timeout→frame atla; boş tespit→track predict-only; engine eksik/uyumsuz (hardware)→açık hata, çökme yok; pencere sınırı/tolerans edge-case'leri (unit test); track loss→ID koru N kare sonra düş.
**Testler:** **5 kuralın her biri için ayrı unit test** (sentetik bbox dizileri); sentetik hedef→tespit→takip→lock_event; ID-switch metriği; lock-valid oranı.
**Kabul Kapısı 3:** Sentetik senaryoda doğru lock_event; 5 kural testleri yeşil. → **DUR/RAPOR.**

### FAZ 4 — Güdüm & Hedef Seçimi (iki-faz)
**Amaç:** Kaba(GPS+PN)→hassas(görüntü+PID) cascade; SITL'de scripted hedefe kilit.
**Teslimat:**
- `gokdogan_target_selector`: `S=0.40·P_mesafe+0.30·P_açı+0.20·P_geçmiş−0.10·P_risk`; flat-Earth WGS-84→NED; lead-angle kesişim; `zaman_farki` ile tahmin.
- `gokdogan_guidance`: PID (piksel→açı, merkez 960,600, Kp=0.042/Ki=0.0008/Kd=0.025, φ±45/θ±30, throttle pinhole W≈2m→~50m) + PN (a_c=N·V_c·λ̇, N=4) cascade (PID 50Hz / PN 10Hz). Rate limit Δφ=20°/s, LPF α=0.3. **frames.hpp ile ENU setpoint.** Faz geçişi histerezisli (480/520m + bbox-taze).
**Hata yönetimi:** PN'de V_c≈0 (divide-by-zero)→guard; PID windup→anti-windup clamp; setpoint saturation→clamp+log; hedef kaybı (mid-lock)→hassas→kaba'ya geri / hold; bbox stale→precise'a girme.
**Testler:** SITL + scripted hareketli hedef → araç takip eder, lock olur; time-to-lock, miss distance ölç; faz-geçiş flapping yok (assert).
**Kabul Kapısı 4:** SITL'de scripted hedefe **<30s** otonom kilit, 0 yanlış-pozitif paket. → **DUR/RAPOR.**

### FAZ 5 — Kamikaze + HSS
**Amaç:** Kamikaze alt-FSM + APF kaçınma.
**Teslimat:**
- `gokdogan_kamikaze`: `ExecuteKamikaze` action; faz FSM (Intikal 100m/Pure Pursuit → Dalış −45°/TECS/28-30m/s → QR 50m↓ → PullUp R45m/2.7G/min-alt). QR: `tools/synthetic_qr.py` (eğik plakalı sentetik kareler) + grayscale→CLAHE→adaptive threshold→4 köşe→`cv2.warpPerspective`→`QRCodeDetector`→pyzbar dual decode.
- `gokdogan_hss`: APF (k_att 0.5-1.0, k_rep 5-20, d₀=r+25m, 10Hz) + yerel-min (v<2m/s & |F|<0.5N→100ms pertürbasyon→3 fail→Dubins R_min).
**Hata yönetimi:** QR bulunamadı→min-alt'ta pull-up (her halükarda); pull-up G aşımı→guard/clamp; min-alt güvenlik (kesin); 2-deneme limiti; APF yerel-min→Dubins fallback; çakışan kuvvetler; aktivasyon mid-flight→taze liste.
**Testler:** SITL kamikaze (dalış açısı tutma, QR okuma, pull-up G≤3, paket≤2s); HSS 5 konfig → **0 ihlal saniyesi**, yerel-min yok.
**Kabul Kapısı 5:** Kamikaze + HSS SITL senaryoları geçiyor. → **DUR/RAPOR.**

### FAZ 6 — Mock Server + Video + Tam Döngü
**Amaç:** Sunucu döngüsünü (mock ile) ve video'yu uçtan uca bağlamak.
**Teslimat:**
- `tools/mock_server.py` — yarışma API'si birebir emülatörü (giriş, sunucusaati, telemetri_gonder **≤2Hz/>2Hz→400 err3**, kilitlenme_bilgisi, kamikaze_bilgisi, qr_koordinati, hss_koordinatlari). Sentetik rakip/HSS/QR. **Aralık doğrulama** (aralık-dışı→reddet) — GCS'in doğru davrandığını test eder.
- `mock_gcs.py` genişlet: mock_server'a HttpClient gibi davranır (telemetri POST ≤2Hz, kilit/kamikaze POST, QR/HSS GET) + onboard relay. *(Gerçek HttpClient C#'ta — Faz 9.)*
- `gokdogan_video_streamer`: GStreamer `tee→nvv4l2h264enc→RTSP` (hardware) / dev'de `videotestsrc`/Gazebo→x264enc→RTSP. Ham kamera (overlay GCS'te).
**Hata yönetimi:** sunucu 4xx/5xx→retry/backoff, 401→re-login; >2Hz→governor engeller; timeout→kuyruk+skip; RTSP başlatılamadı→retry+placeholder.
**Testler:** uçtan uca SITL: telemetri mock_server'a ≤2Hz akıyor, lock_event→kilit POST, ceza-tetikleyici aralık-dışı veri reddediliyor (-0.2/sn yok); RTSP akışı oynatılabiliyor.
**Kabul Kapısı 6:** Tam görev döngüsü mock'larla çalışıyor. → **DUR/RAPOR.**

### FAZ 7 — Senaryo Runner + 8 KTR Senaryosu
**Amaç:** KTR'nin 8 görev testini otomatik koşmak.
**Teslimat:**
- `sim/scenario_runner.py` + `sim/scenarios/*.yaml` (rakip sayı/davranış, HSS yerleşim+aktivasyon, QR, rüzgâr).
- 8 senaryo integration testi (SAD §8 / KTR 8.3): otonom kalkış-iniş (hız<12m/s), waypoint (cross-track<5m), çoklu-İHA kilit (<30s), HSS (%100, 0 ihlal), kamikaze tam, tam müsabaka (>800 hedef metrik), haberleşme kaybı (10s→LAND), batarya failsafe (→RTL).
**Testler:** Her senaryo CI'da (veya nightly) koşar; metrikler raporlanır.
**Kabul Kapısı 7:** 8 senaryonun tamamı kabul kriterini geçiyor. → **DUR/RAPOR.**

### FAZ 8 — Failsafe & Gözlemlenebilirlik & Sertleştirme
**Teslimat:** failsafe katmanları (SAD §18: RC 5s, GCS 10s, GPS glitch, batt %20, geofence, HSS, mission_link kopuk→otonom devam), watchdog/heartbeat tüm node'lar, rosbag2 kayıt, yapısal JSON log, tek zaman tabanı (ServerClock offset log), mission_link metrikleri.
**Testler:** her failsafe tetik testi; node-crash→güvenli state; chaos test (rastgele kopma/gecikme).
**Kabul Kapısı 8:** Tüm failsafe testleri geçiyor; sistem degrade durumlarda güvenli. → **DUR/RAPOR.**

### FAZ 9 — WPF (Hüseyin) Entegrasyonu *(repo eklendiğinde)*
**Önkoşul:** Kullanıcı `TEKNOFEST-GOKDOGAN` reposunu workspace'e ekler (submodule/sibling).
**Teslimat:**
- `GOKDOGANIHA.Core/Services/Mavlink/MavlinkFlightStateSource.cs` — RF MAVLink → FlightState (uçuş alanları). `IFlightStateSource` implementasyonu.
- `GOKDOGANIHA.Core/Services/MissionLink/MissionLinkClient.cs` — **dondurulmuş `mission_link` şemasına** (Faz 0) göre UDP+TCP client → FlightState (vision alanları); `operator_cmd`/`config` gönderir. `IFlightCommandSink` → MissionCommand.
- `GameServerClient` canlı yola bağlanır (FlightState'ten paket, ServerClock, ≤2Hz); `KilitlenmeDenetim`/`KamikazeFsm` **ayna**ya alınır.
- Video: VideoPanel RTSP + overlay (#FF0000 + sunucu saati) + **MP4 kayıt+FTP**.
- Eksikler: persistence, AlertToastHost, hedef aday paneli.
**Notlar:** WPF threading — yüksek-hız veri arka plan buffer + mevcut 100ms tick; kritik olay `Dispatcher.Invoke` (SAD §17).
**Hata yönetimi:** mock_gcs ile bire bir aynı kontrat → WPF, onboard'a sorunsuz takılır; bağlantı kopması GCS'te uyarı, onboard etkilenmez.
**Testler:** WPF, çalışan SITL+onboard'a bağlanıp gerçek veriyi gösteriyor; komut gönderiyor; mock_server'a telemetri/kilit POST'luyor.
**Kabul Kapısı 9:** WPF + onboard + SITL + mock_server uçtan uca; tam müsabaka senaryosu GCS'ten izlenip yönetilebiliyor. → **DUR/RAPOR.**

---

## 5. HATA DURUMLARI KATALOĞU (hepsini kodla + kritik olanları test et)

Aşağıdaki her satır için: **savunmacı kod + log + (kritikse) test.** Sistem **çökmemeli**, güvenli duruma geçmeli.

**ROS2/DDS:** QoS uyumsuzluğu (sessiz kopma)→merkezî profil; node crash→watchdog+respawn (launch `respawn=true`) + FSM güvenli state; lifecycle transition fail→retry/abort; intra-process pitfall (mutable mesaj)→const-correct; executor starvation→callback group ayrımı.

**MAVROS/MAVLink:** connection loss→reconnect+IDLE; mode reddi→retry+operatör uyarı; arming fail→sebep logla, IDLE'da kal; **ENU/NED hatası**→frames.hpp tek nokta + test; stream rate düşük→bringup'ta zorla; **setpoint timeout**→güdüm aktifken sürekli yayın, dururken moddan çık; SITL≠gerçek farkları→config.

**Algı:** kamera disconnect/frame yok→reconnect+sinyal; frame drop→latest-wins buffer; TensorRT engine eksik/uyumsuz→açık hata (hardware); inference timeout→atla; boş tespit→Kalman predict-only; ID switch→IoU eşiği+age; track loss→N-kare grace.

**Kilit denetimi:** pencere baş/bitiş edge→test; 200ms tolerans dağılımı→test; hedef yeniden-giriş→last_locked_id; yerdeki hedef→irtifa kontrolü; mod flapping→guard.

**Güdüm:** V_c≈0→divide guard; PID windup→anti-windup; saturation→clamp; hedef kaybı mid-lock→geri-kaba/hold; bbox stale→precise'a girme; faz flapping→histerezis.

**Kamikaze:** QR yok→min-alt pull-up; dalış kararsızlığı→TECS limit; G aşımı→clamp/guard; min-alt→kesin güvenlik; 2-deneme limiti; perspektif başarısız→CLAHE+retry.

**HSS:** yerel-min→pertürbasyon→Dubins; çakışan kuvvet; aktivasyon mid-flight; d→0 (singularity)→clamp.

**mission_link:** TCP kopma→reconnect+otonom devam; UDP loss/disorder→seq+latest-wins; partial/bozuk frame→drop+log; şema versiyon→reddet; heartbeat timeout→link-lost; clock skew→offset.

**Sunucu (mock+gerçek):** 4xx/5xx→backoff retry; 401→re-login; **>2Hz→governor (400/err3 önle)**; **aralık-dışı alan→clamp/iptal (-0.2/sn önle)**; timeout→skip; partition→kuyruk.

**Konteyner/deploy:** GPU yok→açık hata (hardware); device eksik→açık hata; restart mid-mission→state recovery/güvenli IDLE; model/volume eksik→açık hata.

**Eşzamanlılık/zaman:** race→lock/atomic; WPF cross-thread→Dispatcher; buffer over/underflow→bounded queue; ServerClock sync fail→son offset + uyarı; timestamp ordering→monotonik.

---

## 6. KESİTSEL GEREKSİNİMLER

**Kod standartları:** C++17 (perception inference, performans-kritik) / Python (tracking, mission_link, FSM, sim — hız). Her node ayrı paket. clang-format + black + flake8 + ament_lint. Type hints (Python), const-correctness (C++).
**Test:** unit (her algoritma) + integration (launch_testing + SITL) + senaryo (8 KTR). Hedef: kritik mantıkta yüksek kapsam. Her PR'da CI yeşil.
**Loglama:** ROS2 logger (seviyeli) + yapısal JSON (faz/state geçişi, latency, hata). rosbag2 tüm topic.
**Konfig:** ROS2 param YAML (`sitl.yaml`/`hardware.yaml`) — tüm eşik/kazanç. C# settings.json. Sihirli sayı yok.
**Determinizm:** dev'de sentetik kaynaklar tekrarlanabilir (seed'li).
**Dokümantasyon:** her paket `README`; `PROGRESS.md` güncel; mimari değişiklik SAD'a yansıtılır (onayla).

---

## 7. NİHAİ TAMAMLANMA TANIMI (Definition of Done)

- [ ] x86 dev ortamında `make build && make test && make lint` **yeşil**.
- [ ] 8 KTR senaryosu SITL'de kabul kriterlerini geçiyor (Faz 7).
- [ ] Tüm failsafe testleri geçiyor (Faz 8); kopma/crash'te güvenli.
- [ ] WPF + onboard + SITL + mock_server uçtan uca; tam müsabaka GCS'ten yönetiliyor (Faz 9).
- [ ] Donanım-özel yollar (TensorRT, UART, CSI/USB kamera) yazılmış ve **"⚠️ ON-DEVICE DOĞRULAMA"** olarak işaretli (sen test edemezsin; takım sahada doğrular).
- [ ] `mission_link` kontratı dondurulmuş; WPF ve onboard aynı şemaya uyuyor.
- [ ] `PROGRESS.md` tüm fazları/kapıları kayıt altında.

---

## 8. ŞİMDİ BAŞLA

1. `docs/GOKDOGAN_YAZILIM_MIMARISI.md`'yi oku ve özetini `PROGRESS.md`'ye yaz.
2. WPF reposunu (read-only) inceleyip `FlightState` alanlarını çıkar.
3. **Faz -1**'i kur ve doğrula; Kabul Kapısı -1'de **DUR ve RAPOR ver.**
4. Onay gelince Faz 0'a geç.

Her fazda: küçük commit'ler, testler yeşil, kapı geçilince dur. Belirsizlikte SAD'a bak, çelişkide sor. **Uydurma yok, atlama yok, kırmızı çizgi ihlali yok.**
