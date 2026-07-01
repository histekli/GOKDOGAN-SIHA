# GÖKDOĞAN — Savaşan İHA 2026 Yazılımı

TEKNOFEST Savaşan İHA 2026 (Takım ID 759667) onboard otonomi + GCS entegrasyon yazılımı.

- **Tek doğruluk kaynağı (mimari):** [docs/GOKDOGAN_YAZILIM_MIMARISI.md](docs/GOKDOGAN_YAZILIM_MIMARISI.md) (SAD v1.0)
- **İnşa talimatı:** [docs/GOKDOGAN_CLAUDE_CODE_PROMPT.md](docs/GOKDOGAN_CLAUDE_CODE_PROMPT.md)
- **Plan:** [docs/GOKDOGAN_KESIN_PLAN_v4.md](docs/GOKDOGAN_KESIN_PLAN_v4.md)
- **İlerleme defteri:** [PROGRESS.md](PROGRESS.md)

## Mimari özet

- **Onboard:** Jetson Xavier NX · Docker · **ROS2 Humble** + MAVROS → Pixhawk (UART).
  Kritik döngü (algı→güdüm→MAVROS) uçakta ve izole; Wi-Fi/GCS koparsa uçuş kontrolü kopmaz.
- **GCS:** .NET 10 / C# / WPF (ayrı repo: `huseyingenc-eem/TEKNOFEST-GOKDOGAN`).
- **Diller arası tek sınır:** `mission_link` (UDP akış + TCP kontrol, MessagePack). rosbridge / C# ROS2 binding YOK.
- **Sunucu I/O:** GCS'te HttpClient, tek yetkili IP, telemetri ≤2Hz.

## Repo yapısı

```
docker/            Dev (x86 SITL) + üretim (Jetson) imajları, compose
gokdogan-onboard/  colcon workspace (ROS2 paketleri) — src/ Faz 0'da doldurulur
sim/               SITL / Gazebo / scenario_runner / mock_server (Faz 6-7)
contracts/         mission_link MessagePack şeması (Faz 0'da dondurulur)
scripts/           dev/CI yardımcı betikleri
docs/              SAD + plan + bu prompt
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
