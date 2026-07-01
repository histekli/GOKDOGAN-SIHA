# GÖKDOĞAN — Savaşan İHA 2026 · KESİN PLAN (v4 — nihai KTR ile uyumlu)

> **v1–v3'ün yerine geçer.** Nihai, teslim edilmiş KTR'ye (Takım ID 759667) **birebir** uyumlu hâle getirildi.
> Bir önceki sürümde benim hatalı/eksik bilgiyle verdiğim 6 tavsiye KTR'ye göre düzeltildi (bkz §0).
> **Kapsam: SADECE YAZILIM** (gövde/mekanik/aviyonik bizde değil). Yazılım ekibi 5 kişi.
> Etiket: `[R]` = KTR'de yazan taahhüt · `[Ö]` = benim önerim (KTR'de yok)

---

## 0. KTR UYUMU ve v3 → v4 DÜZELTMELERİ

| Konu | v3 (yanlış/eksik) | v4 (KTR'ye uygun) | KTR kaynağı |
|---|---|---|---|
| HSS | teğet+Dubins+A* | **APF + Dubins yerel-min yedeği** | Böl. 5 (APF SEÇİLDİ, A*/RRT elendi) |
| Pixhawk köprüsü | pymavlink, MAVROS yok | **MAVROS** (ROS köprü) | Şekil 4.1.14 |
| GCS↔uçak | sadece bridge, MAVLink yok | **GCS doğrudan MAVLink + HttpClient + Wi-Fi UDP veri linki** | 6.2, 6.4 |
| Kamera | 78°/1920×1080 | **AR0234, 1920×1200, 82° FOV, 50fps, USB3**, merkez (960,600) | 1.2, 3.3.2.4, 4.1.5.1 |
| Video overlay/kayıt | Jetson'da bake | **GCS'te RTSP'ye çiz + H.264 MP4 kaydet** | 6.5, 6.6 |
| Parametre etiketleri | birçoğu `[Ö]` | KTR'dekiler `[R]` | 4.1.5, 4.2, 5 |
| ROS sürümü | Humble | **Noetic** (KTR) — *Humble seçilirse tek delta, bkz §4* | 8.3 |

---

## 1. OTORİTE MATRİSİ (her satırda tek karar verici)

| Sorumluluk | OTORİTE | Diğer taraf |
|---|---|---|
| Algı (YOLO + Kalman/IoU → bbox) | **Uçak** | GCS bbox'ı overlay gösterir |
| Güdüm: kaba (GPS+PN) → hassas (görüntü+PID) | **Uçak** | — |
| Kilit denetimi (5 kural, 4s) | **Uçak** | GCS C# `KilitlenmeDenetim` → ayna/display |
| Kamikaze FSM + QR okuma | **Uçak** | GCS faz gösterir |
| HSS kaçınma (APF + Dubins) | **Uçak** | GCS HSS daireleri + rota çizer |
| Hedef seçim skoru (S formülü) | **Uçak** | GCS adayları + operatör override |
| Görev FSM / MAVROS tek-yazıcı | **Uçak** | GCS yüksek-seviye komut önerir |
| Pixhawk MAVLink (otonomi) | **Uçak** (MAVROS) | — |
| Pixhawk MAVLink (telemetri/komut) | **GCS** (RFD868x, doğrudan) | Mission Planner (safety, ops.) |
| **Sunucu I/O** (telemetri/kilit/kamikaze/QR/HSS) | **GCS** (C# HttpClient, tek yetkili IP) | Uçak paket içeriğini üretir |
| Sunucu saati senkron | **GCS** | Uçağa relay |
| Telemetri ≤2Hz | **GCS** | — |
| Video overlay (#FF0000+saat) + kayıt | **GCS** (RTSP'ye) | Uçak ham RTSP gönderir |
| Uyarılar/monitorlar/UI | **GCS** | — |
| Sim/test orkestrasyonu (DEV) | dev araç/CLI | — |

---

## 2. FİNAL MİMARİ (KTR ile uyumlu)

```
┌────────────── HAVA ARACI: Jetson Xavier NX · ROS (Noetic*) + MAVROS ──────────────┐
│  Kamera(AR0234,1920×1200,82°,USB3) ─► perception(YOLOv11s+TRT, Kalman+IoU)          │
│        │                                    │                                       │
│        │                          ┌─────────┴───────────┐                           │
│   GStreamer(RTSP, ham)        lock_validator        target_selector                 │
│        │                          guidance(kaba GPS+PN → hassas görüntü+PID)         │
│        │                          kamikaze(FSM+QR) · hss(APF+Dubins)                 │
│        │                                    │                                       │
│        │                            mission_fsm ─► MAVROS ──(Telem1/UART)──► Pixhawk │ Cube
│        │                                                                             │ Orange+
│   mission_link (Wi-Fi UDP): ▲ bbox/kilit/kamikaze/FSM/aday  ▼ rakip/HSS/QR/komut     │
└────────┼────────────────────────────────────┼──────────────────────────────────────┘
         │ RTSP (Wi-Fi: Rocket5AC↔PowerBeam5AC)│ Wi-Fi UDP
         │                                     │
 Pixhawk─┼─RF(RFD868x, MAVLink)────► YER KONTROL BİLGİSAYARI (Windows)                  
         ▼                                     ▼
┌─────────────────────────────── WPF GCS (.NET 10, C#) ──────────────────────────────┐
│  Kaynak 1: MAVLink lib (RFD868x) → FlightState (uçuş telemetrisi)                    │
│  Kaynak 2: mission_link client (Wi-Fi UDP) → FlightState (bbox/kilit/kamikaze)       │
│  GameServerClient (HttpClient, tek yetkili IP) ←─ Ethernet ─► Yarışma Sunucusu       │
│  VideoPanel (LibVLCSharp): RTSP oynat + #FF0000 dörtgen + sunucu saati overlay + KAYIT│
│  Harita(GMap.NET)+marker · HUD/PFD · sidebar panelleri · renk-kodlu uyarılar         │
└─────────────────────────────────────────────────────────────────────────────────────┘
 (* ROS sürümü §4'te; Humble seçilirse tek değişiklik)
```

**KTR'ye dayanak:** Onboard ROS+MAVROS otonomi (Şekil 4.1.14) · GCS direkt MAVLink + HttpClient (6.4) · Jetson verisi Wi-Fi UDP (6.2) · RTSP→GCS kayıt (6.6) · iki ayrı RF/Wi-Fi hattı + RC = SPOF yok (6.3).

---

## 3. VERİ AKIŞI (dört hat, hepsi KTR'de)

1. **MAVLink/RF (RFD868x):** Pixhawk ↔ GCS — uçuş telemetrisi (GCS okur) + operatör mod/RTL komutları. *(Ham MAVLink, oynama yok — 6.1.)*
2. **MAVLink/UART (Telem1):** Pixhawk ↔ Jetson (MAVROS) — otonomi kontrol döngüsü (tek yazıcı: mission_fsm).
3. **Wi-Fi UDP (mission_link):** Jetson ↔ GCS — ▲ bbox + kilit-geçerli olayı + kamikaze QR metni + FSM state + adaylar; ▼ rakip telemetrisi + HSS + QR koordinatı + sunucu saati + yüksek-seviye operatör komutları (hedef seç / başla / iptal).
4. **RTSP (Wi-Fi):** Jetson kamera → GCS (oynat + overlay + kayıt).
5. **HTTP (Ethernet):** GCS ↔ yarışma sunucusu (HttpClient) — telemetri POST (≤2Hz, FlightState'ten; bbox/flag mission_link'ten gelmiş), kilit POST (uçak olayı tetikler, ServerClock damgalar), kamikaze POST, QR/HSS/saat GET → mission_link ile uçağa relay.

---

## 4. ROS SÜRÜMÜ — TEK AÇIK ÇATAL

- **KTR:** ROS **Noetic** + MAVROS + Gazebo **Classic 11** (8.3, Şekil 4.1.14).
- **Önerim: Noetic'i koru.** Xavier NX native Ubuntu 20.04 = Noetic native (**container yok**); Noetic+MAVROS+Gazebo Classic = en dökümante ArduPilot+görüntü yığını; KTR ile birebir; deadline için en düşük risk.
- **Humble seçilirse (senin önceki tercihin):** tek delta = ROS1→ROS2 + Xavier'da **container** + MAVROS2. Her şey aynı kalır. Sapmayı "Noetic EOL" diye videoda sahiplen. Bu durumda §2'deki "Noetic*" → Humble.
- **Karar bekleniyor.** v4 geri kalanı her iki sürümde de geçerli (sadece paket/launch sözdizimi değişir).

---

## 5. MEVCUT WPF GCS — ENTEGRASYON (huseyingenc-eem/TEKNOFEST-GOKDOGAN)

**Mimari hazır:** `FlightState` çoklu kaynağın yazdığı observable aggregate; `IFlightStateSource`/`IFlightCommandSink` portları mevcut (OCP). Entegrasyon bu portlara takılıyor:

- **Kaynak 1 — `MavlinkFlightStateSource`** (KTR + repo roadmap'i): RFD868x MAVLink → FlightState uçuş alanları (lat/lon/alt/attitude/batt/mod/armed). *(Roadmap'te planlı, yazılacak.)*
- **Kaynak 2 — `MissionLinkSource`** (YENİ, ince): Wi-Fi UDP'den Jetson verisi → FlightState görüntü alanları (`TargetCenterX/Y/Width/Height`, `IsLocked`, lock-event, kamikaze sonucu, adaylar). *(FlightState bu alanlara zaten sahip.)*
- **`GameServerClient` (KALIR, KTR 6.4):** FlightState'ten telemetri paketi → ≤2Hz POST (`TelemetryHzMeter`); lock-event → `KilitlenmeBilgisiGonder`; kamikaze sonucu → `KamikazeBilgisiGonder`; QR/HSS GET → mission_link ile uçağa.
- **`KilitlenmeDenetim` (C#) → DEMOTE:** artık uçak karar verir; C# uçaktan gelen ilerlemeyi gösterir (ayna).
- **`KamikazeFsm` (C#) → DEMOTE:** uçak icra eder; C# faz gösterir.
- **Video (KTR 6.6):** VideoPanel RTSP oynat + #FF0000 dörtgen (bbox mission_link'ten) + sunucu saati overlay → **H.264 MP4 kayıt** (LibVLCSharp + recorder). Kayıt = kamera akışı + bu iki overlay (tüm ekran değil).
- **EKLENECEK:** LibVLCSharp gerçek RTSP, MavlinkFlightStateSource, MissionLinkSource, video kayıt+FTP, ayar persistence, AlertToastHost, hedef aday paneli + override.

> `target_selector` ve `KilitlenmeDenetim` mantığı **uçakta** (Python). C# `AutonomyOptions` ağırlıkları (0.4/0.3/0.2/0.1) config olarak mission_link ile uçağa push edilir.

---

## 6. ONBOARD ROS PAKET YAPISI + mission_link KONTRATI

```
onboard_ws/src/
  perception/      # YOLOv11s(TRT) + Kalman/IoU/Hungarian takip + lock_validator   [EMİRCAN+SEN]
  guidance/        # kaba(GPS+PN) → hassas(görüntü+PID) cascade                     [KENAN/SEN]
  target_selector/ # S = 0.40·P_mesafe+0.30·P_açı+0.20·P_geçmiş−0.10·P_risk + lead-angle [SEN]
  kamikaze/        # FSM + QR (OpenCV/pyzbar)                                        [SEN]
  hss/             # APF + Dubins yerel-min yedeği                                   [SEN]
  mission_fsm/     # DFA orkestrator; MAVROS setpoint tek-yazıcı                     [SEN]
  mission_link/    # Wi-Fi UDP ↔ GCS (yukarı bbox/kilit/kamikaze; aşağı rakip/HSS/QR/komut) [SEN]
  bringup/         # launch + MAVROS config (stream rate, ENU↔NED) + Gazebo         [SEN]
```
**mission_link mesaj şeması (dondur, gün 1-2):**
- ▲ Up: `aircraft_vision`{bbox[x,y,w,h], lock_state, lock_valid, target_id, ts}, `kamikaze_result`{text, ts}, `fsm_state`, `candidates[]`.
- ▼ Down: `server_data`{rakipler[], hss[], qr, sunucu_saati}, `operator_cmd`{type, params}, `config`{autonomy_weights}.

**Sunucu paketleri (C# tarafı, KTR 6.2/6.4 + şartname):** giriş, sunucusaati, telemetri_gonder (≤2Hz; aralık: dikilme[-90,90], yonelme[0,360], yatis[-90,90]), kilitlenme_bilgisi, kamikaze_bilgisi, qr_koordinati, hss_koordinatlari.

---

## 7. ONBOARD MODÜL SPEC'LERİ (KTR'ye göre)

**perception [R]:** Kamera AR0234, 1920×1200, 82° FOV, 50fps, USB3, merkez (960,600). YOLOv11s→ONNX→**TensorRT FP16**; ROI merkez %70 → 640×640 → koordinat geri 1920×1200. **Takip: Kalman+IoU** — durum `[px,py,vx,vy,ax,ay]`, ölçüm `[px,py]`; YOLO her 5 karede; Hungarian `Cost=1−IoU`, IoU≥0.3 ID korunur. Metrik: mAP@50≥0.89, P≥0.87, R≥0.83, FPS≥25, gecikme≤80ms. Dataset 7.500 pozitif + 1.000+ negatif, %70/20/10, augment (rotation/blur/rain-fog/mosaic).

**target_selector [R]:** `S = 0.40·P_mesafe + 0.30·P_açı + 0.20·P_geçmiş − 0.10·P_risk`. flat-Earth WGS-84→NED; `zaman_farki` ile güncellik/tahmin; lead-angle `P_int = P_rakip + v_rakip·t_int`. **İki faz:** d<500m'e kadar **kaba (GPS+PN)**, sonra **hassas (görüntü+PID)** — manuel işaretleme olmadan otomatik geçiş.

**lock_validator [R]:** merkez (yatay≤W/2, dikey≤H/2); ekran ≥%5 → **%6 eşik**; `IoU(bbox_hedef,bbox_kilit)≥0.9`; 5s pencerede ≥4s, 200ms tolerans (baş/bitişte yok); `last_locked_id` ardışık yasak; yerdeki hedef reddi; otonom-mod şart. Paket {ID, bbox, merkez, bitiş-zamanı, geçerlilik} ≤2s.

**guidance [R]:** PID — piksel hatası → açı, merkez (960,600), roll φ_cmd±45° (Kp=0.042/Ki=0.0008/Kd=0.025), pitch θ_cmd±30°, yaw↔roll couple; throttle `d=W·f/W_piksel` (W≈2m, W_piksel≈1100, ~50m). PN `a_c=N·V_c·λ̇`, **N=4**. Cascade PN~10Hz → PID~50Hz. Rate limit Δφ_max=20°/s, LPF α=0.3.

**kamikaze [R]:** Faz1 intikal (100m AGL, Pure Pursuit, upwind, <20m & ≥100m→Faz2); Faz2 dalış (pitch −45°, airspeed hedef 28 / tavan 30 m/s, TECS); Faz3 QR (50m altı başlar, ~30m en iyi; grayscale→CLAHE→adaptive threshold→4 köşe→perspektif→OpenCV QRCodeDetector→Pyzbar; geçerlilik); Faz4 pull-up (28 m/s, R=45m, **n=2.7G**, 3G limit, min güvenli irtifa). QR 2×2m, plaka 45°/3m. Paket ≤2s.

**hss [R] — APF + Dubins:** `U_att=½k_att·d²` (k_att 0.5–1.0); `U_rep=½k_rep(1/d−1/d₀)²` (k_rep 5–20); **d₀=r_HSS+25m**; F_toplam → waypoint setpoint, **10Hz**. Yerel-min: hız<2m/s & |F|<0.5N → 100ms pertürbasyon → 3 başarısız sonra **Dubins** (R_min). HSS GET 5s'de bir, aktivasyonda 1Hz. Kabul: %80→95→100, **0 ihlal saniyesi**.

**mission_fsm:** DFA; `IDLE→TAKEOFF→CRUISE/SEARCH→LOCKING→KAMIKAZE→RTL/LAND` + `MANUAL_OVERRIDE`. MAVROS setpoint tek yazıcı; lock/kamikaze **başlama onayı operatörden** (GCS, KTR 1.1).

---

## 8. SİM + TEST (KTR 8.3)

- **Stack [R]:** ArduPilot SITL + **Gazebo Classic 11** + **ROS Noetic** + **"Baylands"** haritası, sanal rakipler + QR. Çoklu-araç SITL.
- **mock_server (DEV):** yarışma API emülatörü — C# GameServerClient + onboard'ı donanımsız test eder.
- **8 senaryo [R]** (her biri gerçek uçuşta ≥5 tekrar; MAVLink/ROS/Gazebo loglarından grafik):

| Senaryo | Kabul |
|---|---|
| Otonom kalkış-iniş | pist içi, hız <12 m/s |
| Waypoint takibi | cross-track <5m |
| Çoklu İHA kilitlenme | doğru hedef **<30s** |
| HSS kaçınma (APF) | yerel-minsiz **%100, 0 ihlal sn** |
| Kamikaze tam | QR + 30m'de pull-up |
| Tam müsabaka (15dk) | **toplam >800** |
| Haberleşme kaybı | 10s sonra LAND |
| Batarya failsafe | %20 → RTL |

---

## 9. GÖREV DAĞILIMI

| Kişi | Sahiplik |
|---|---|
| **Sen** | mission_link kontratı, onboard iskelet (mission_fsm + MAVROS bringup + QoS), hss(APF+Dubins), kamikaze+QR, lock_validator, target_selector, mock_server, entegrasyon |
| **Emircan** | perception (YOLOv11s eğitim, ONNX/TensorRT, Kalman+IoU, lock_validator beraber), metrik harness |
| **Hüseyin** | WPF GCS: MavlinkFlightStateSource + MissionLinkSource (FlightState'e yaz), LibVLCSharp RTSP + overlay + **MP4 kayıt+FTP**, hedef aday paneli, persistence, toast |
| **Kenan** | sim (SITL/Gazebo Classic 11/Baylands/çoklu-araç), güdüm tuning (PN+PID), ArduPilot param, donanım arayüz sözleşmesi, HITL |

---

## 10. ZAMAN PLANI (sim-first)

**Hafta 0 [Sen]:** mission_link + sunucu paket şemaları dondur · ROS (Noetic native / Humble container) ortamı · onboard stub'lar + mission_fsm + MAVROS bringup · mock_server · SITL+Gazebo Classic 11 (tek+3 araç, Baylands) · GCS'te MissionLinkSource iskeleti. ✅ Boş ama çalışan sistem.

**Faz 1 — Otonom uçuş + sunucu:** SITL AUTO kalkış/waypoint/iniş · C# GameServerClient ≤2Hz+saat (mock) · GCS MavlinkFlightStateSource → harita+HUD.

**Faz 2 — Kilitlenme (500p):** perception(eğitim+Kalman/IoU)+lock_validator · güdüm kaba(GPS+PN)→hassas(görüntü+PID) · entegrasyon: bbox→denetim→lock-event→mission_link→GCS POST · target_selector. ✅ <30s, paket≤2s.

**Faz 3 — Kamikaze (300p):** FSM+QR+dalış+pull-up; QR→mission_link→GCS POST. ✅ G≤3, ≤2s.

**Faz 4 — HSS:** APF+Dubins; HSS GET→mission_link→uçak. ✅ 0 ihlal sn.

**Faz 5 — Video + GCS cila:** LibVLCSharp RTSP + overlay + MP4 kayıt + FTP; persistence+toast+aday paneli.

**Faz 6 — Donanım entegrasyon + uçuşlar:** MAVROS↔Pixhawk, HITL, kademeli gerçek uçuş, failsafe'ler (RC 5s→LAND/RTL, GCS 10s→LAND, GPS glitch→LAND, batt %20→RTL, geofence).

---

## 11. İLK HAFTA — Senin base TODO'n

1. mission_link UDP şeması + sunucu paket şeması — **dondur**.
2. ROS ortamı: Noetic native (Xavier 20.04) **veya** Humble container — §4 kararına göre.
3. MAVROS bringup: SITL'e bağlan, state oku, setpoint yaz (mission_fsm tek yazıcı).
4. mission_fsm DFA + perception/guidance/lock/kamikaze/hss node stub'ları.
5. mission_link node (UDP) + GCS tarafı `MissionLinkSource` iskeleti (mock akış).
6. mock_server (yarışma API) — C# GameServerClient testi için.
7. sim: SITL + Gazebo Classic 11 + Baylands + 3 araç + scenario_runner.
8. tests çatısı + ilk birim testler (lock kuralları, ≤2Hz, aralık).

Bitince: Emircan perception'a, Hüseyin GCS kaynaklarına + eksiklere, Kenan sim/güdüme paralel başlar.

---

## 12. KALAN TEK KARAR

**ROS Noetic (KTR, önerim) mi, Humble (container) mı?** (§4). Bunu söyle; gerisi her iki sürümde de hazır.
