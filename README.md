# GÖKDOĞAN — Savaşan İHA 2026 Yazılımı

TEKNOFEST Savaşan İHA 2026 (Takım ID 759667) onboard otonomi + GCS entegrasyon yazılımı.

> **Durum:** Planlı tüm fazlar (−1 … 9) tamamlandı · ~256 test yeşil · x86 SITL'de uçtan uca çalışıyor.
> Kalanlar donanım/model/WPF-arayüz/uçuş (⚠️ ON-DEVICE) — bkz. [EL KİTABI §3](docs/EL_KITABI.md).

- 📘 **KULLANIM & DURUM — EL KİTABI:** [docs/EL_KITABI.md](docs/EL_KITABI.md) ← *buradan başla*
- **Tek doğruluk kaynağı (mimari):** [docs/GOKDOGAN_YAZILIM_MIMARISI.md](docs/GOKDOGAN_YAZILIM_MIMARISI.md) (SAD)
- **İnşa talimatı:** [docs/GOKDOGAN_CLAUDE_CODE_PROMPT.md](docs/GOKDOGAN_CLAUDE_CODE_PROMPT.md)
- **Plan:** [docs/GOKDOGAN_KESIN_PLAN_v4.md](docs/GOKDOGAN_KESIN_PLAN_v4.md)
- **İlerleme defteri:** [PROGRESS.md](PROGRESS.md)

## Hızlı başlangıç

```bash
make build && make verify-sitl     # kur + doğrula (tek seferlik)
make test                          # tüm testler (colcon + şema + tools + sim)
make run-full-loop-demo            # mock_server + SITL + onboard + GCS → tam görev döngüsü
make help                          # tüm komutlar
```
Fazların demo komutları ve "nasıl kullanılır" için → [EL KİTABI §5-6](docs/EL_KITABI.md).

## Mimari özet

- **Onboard:** Jetson Xavier NX · Docker · **ROS2 Humble** + MAVROS → Pixhawk (UART).
  Kritik döngü (algı→güdüm→MAVROS) uçakta ve izole; Wi-Fi/GCS koparsa uçuş kontrolü kopmaz.
- **GCS:** .NET 10 / C# / WPF (ayrı repo: `huseyingenc-eem/TEKNOFEST-GOKDOGAN`).
- **Diller arası tek sınır:** `mission_link` (UDP akış + TCP kontrol, MessagePack). rosbridge / C# ROS2 binding YOK.
- **Sunucu I/O:** GCS'te HttpClient, tek yetkili IP, telemetri ≤2Hz.

## Repo yapısı

```
docker/            Dev (x86 SITL) + üretim (Jetson ⚠️) imajları, compose
gokdogan-onboard/  colcon workspace — 14 ROS2 paketi (msgs/common/guidance/perception/
                   tracking/lock_validator/target_selector/kamikaze/hss/mission_fsm/
                   mission_link/mavlink_iface/video_streamer/bringup)
contracts/         mission_link MessagePack şeması (DONDU) + JSON Schema testleri
tools/             mock_server.py · mock_gcs.py · synthetic_qr.py
sim/               scenario_runner.py + scenarios/*.yaml (8 KTR senaryosu)
scripts/           run_*_demo.sh (Kabul Kapısı demoları) + probe/verify/smoke
TEKNOFEST-GOKDOGAN/ WPF GCS reposu (C#/.NET 10) — mission_link C# dikişi (Faz 9)
docs/              EL_KITABI + SAD + KESIN_PLAN + PROMPT
```

## Geliştirme ortamı (Faz -1)

Her şey **x86 + ArduPilot SITL + mock'lar** üzerinde koşar. Jetson/TensorRT/gerçek kamera/Pixhawk
yolları `mode:=hardware` arkasında stub'lanır ve **⚠️ ON-DEVICE DOĞRULAMA GEREKİR** olarak işaretlenir.

```bash
make build            # docker/Dockerfile.dev imajını kurar (ROS2 Humble + ArduPilot SITL + MAVROS)
make verify-env       # container içinde ros2 --version, colcon version, sim_vehicle.py --help
make verify-sitl      # boş SITL aracını kaldırır: GUIDED → arm → takeoff (Kabul Kapısı -1)
make shell            # dev container içine interaktif gir
```

> ROS sürümü kararı: SAD/prompt **ROS2 Humble**'ı mutlak kısıt (C1) olarak sabitler → Humble.
