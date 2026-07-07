# GÖKDOĞAN — dev/CI Makefile (her şey dev container içinde koşar; host'ta ROS2 yok)
.DEFAULT_GOAL := help
SHELL := /bin/bash

IMAGE      ?= gokdogan-dev:latest
DOCKERFILE ?= docker/Dockerfile.dev
WS         ?= /workspace/gokdogan-onboard

# Host'ta çalışan interaktif olmayan container run (loopback ağ, repo mount)
DRUN = docker run --rm --network host -v $(PWD):/workspace -w /workspace $(IMAGE)
# İnteraktif + X11 forward (rqt_image_view/rviz/gazebo gibi GUI araçları çalışsın)
# GPU_DEV: host'ta /dev/dri varsa konteynere ver — yoksa GZ_HW=1 bile sessizce yazılım render'a düşer!
GPU_DEV := $(shell test -d /dev/dri && echo --device /dev/dri)
X11 = -e DISPLAY=$$DISPLAY -e QT_X11_NO_MITSHM=1 -v /tmp/.X11-unix:/tmp/.X11-unix $(GPU_DEV)
DRUN_IT = docker run --rm -it --network host $(X11) -v $(PWD):/workspace -w /workspace $(IMAGE)

.PHONY: help build shell verify-env verify-sitl sitl run-sitl-stack ws-build test schema-test tools-test sim-test lint clean run-full-loop-demo mock-server run-scenarios run-failsafe-demo record run-gazebo-smoke

help: ## Bu yardımı göster
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

build: ## Dev imajını kur (ROS2 Humble + ArduPilot SITL + MAVROS)
	DOCKER_BUILDKIT=1 docker build -f $(DOCKERFILE) -t $(IMAGE) .

shell: ## Dev container içine interaktif gir (X11 forward — rqt/rviz/gazebo GUI çalışır)
	-xhost +local:docker >/dev/null 2>&1 || true
	$(DRUN_IT) bash

verify-env: ## Kabul Kapısı -1 (a): ros2/colcon/sim_vehicle.py sürümleri
	$(DRUN) bash scripts/verify_env.sh

verify-sitl: ## Kabul Kapısı -1 (b): boş SITL aracı GUIDED → arm → takeoff
	$(DRUN) bash scripts/sitl_smoke.sh

sitl: ## Etkileşimli SITL başlat (ArduCopter, MAVProxy konsolu)
	$(DRUN_IT) bash -c "sim_vehicle.py -v ArduCopter --console"

run-sitl-stack: ## SITL + onboard graph (MAVROS+FSM) → otonom kalkış (Kabul Kapısı 1)
	$(DRUN) bash scripts/run_sitl_stack.sh

run-mission-link-demo: ## SITL + mission_link + mock_gcs → START_LOCK→LOCKING (Kabul Kapısı 2)
	$(DRUN) bash scripts/run_mission_link_demo.sh

run-perception-demo: ## perception(synthetic)→tracking→lock_validator → geçerli kilit (Kabul Kapısı 3)
	$(DRUN) bash scripts/run_perception_demo.sh

run-guidance-demo: ## SITL + target_selector + guidance → rakibe kaba-faz yaklaşım (Kabul Kapısı 4)
	$(DRUN) bash scripts/run_guidance_demo.sh

run-hss-demo: ## SITL + hss (APF) → HSS bölgesini ihlal etmeden hedefe (Kabul Kapısı 5)
	$(DRUN) bash scripts/run_hss_demo.sh

run-full-loop-demo: ## mock_server + SITL + onboard + mock_gcs → tam döngü (Kabul Kapısı 6)
	$(DRUN) bash scripts/run_full_loop_demo.sh

mock-server: ## mock yarışma sunucusunu çalıştır (dev API emülatörü)
	$(DRUN_IT) bash -c "python3 tools/mock_server.py $(ARGS)"

run-scenarios: ## 8 KTR senaryosunu scenario_runner ile koş (Kabul Kapısı 7)
	$(DRUN) bash scripts/run_scenarios.sh

run-failsafe-demo: ## SITL failsafe: debounce + node-crash→watchdog→RTL (Kabul Kapısı 8)
	$(DRUN) bash scripts/run_failsafe_demo.sh

run-gazebo-smoke: ## Gazebo Adım 1: headless kamera + kırmızı rakip → perception tespiti
	$(DRUN) bash scripts/run_gazebo_smoke.sh

gazebo-plugin: ## Adım 4: ardupilot_gazebo plugin'ini derle (bir kez; sim/gazebo/ardupilot_gazebo gerekir)
	$(DRUN) bash -c "set +u; source /opt/ros/humble/setup.bash; source /usr/share/gazebo/setup.sh 2>/dev/null; \
	  cd /workspace/sim/gazebo/ardupilot_gazebo && rm -rf build && mkdir build && cd build && cmake .. >/dev/null && make -j2 && echo 'PLUGIN DERLENDİ'"

run-gazebo-sitl: ## Adım 4a: Gazebo↔SITL↔MAVROS↔mission_fsm → araç Gazebo fiziğinde otonom kalkar
	$(DRUN) bash scripts/run_gazebo_sitl.sh

run-saha: ## BİRLEŞİK SAHA: Baylands + Talon elle-fırlatma + rakip + QR (GUI: GZ_HW=1 make run-saha)
	-xhost +local:docker >/dev/null 2>&1 || true
	-docker kill gokdogan-hl >/dev/null 2>&1 || true
	docker run --rm -it --name gokdogan-hl --network host -e DISPLAY=$$DISPLAY -e QT_X11_NO_MITSHM=1 \
	  -e GZ_HW -e WATCH_DELAY -e TOSS_VX -e TOSS_VY -e TOSS_VZ $(GPU_DEV) \
	  -e WORLD=/workspace/sim/gazebo/worlds/gokdogan_saha.world \
	  -v /tmp/.X11-unix:/tmp/.X11-unix -v $(PWD):/workspace -w /workspace $(IMAGE) \
	  bash scripts/run_plane_handlaunch.sh

run-plane-handlaunch: ## Talon elle-fırlatma, boş test dünyası (GUI: GZ_HW=1 make run-plane-handlaunch)
	-xhost +local:docker >/dev/null 2>&1 || true
	-docker kill gokdogan-hl >/dev/null 2>&1 || true
	docker run --rm -it --name gokdogan-hl --network host -e DISPLAY=$$DISPLAY -e QT_X11_NO_MITSHM=1 \
	  -e GZ_HW -e WORLD -e WATCH_DELAY -e TOSS_VX -e TOSS_VY -e TOSS_VZ $(GPU_DEV) \
	  -v /tmp/.X11-unix:/tmp/.X11-unix -v $(PWD):/workspace -w /workspace $(IMAGE) \
	  bash scripts/run_plane_handlaunch.sh

gazebo-gui: ## Gazebo'yu GÖRSEL aç (host X11). Talon için: WORLD=/workspace/sim/gazebo/worlds/talon_test.world make gazebo-gui
	-xhost +local:docker >/dev/null 2>&1 || true
	docker run --rm -it --network host \
	  -e DISPLAY=$$DISPLAY -e QT_X11_NO_MITSHM=1 -e WORLD -e GZ_HW $(GPU_DEV) \
	  -v /tmp/.X11-unix:/tmp/.X11-unix -v $(PWD):/workspace -w /workspace $(IMAGE) \
	  bash scripts/run_gazebo_gui.sh

record: ## rosbag2 tüm topic'leri kaydet (SAD §22) — çalışan graph gerektirir. ARGS=süre
	$(DRUN) bash scripts/record_bag.sh $(ARGS)

mock-gcs: ## mock GCS'i çalıştır (referans yer istasyonu — onboard'a bağlanır)
	$(DRUN_IT) bash -c "source /opt/ros/humble/setup.bash; source gokdogan-onboard/install/setup.bash; python3 tools/mock_gcs.py $(ARGS)"

ws-build: ## colcon workspace derle (Faz 0+ paketleri geldiğinde)
	$(DRUN) bash -c "source /opt/ros/humble/setup.bash && cd $(WS) && colcon build --symlink-install"

test: ## colcon test (Faz 0+) + mission_link şema testi + tools (mock_server/gcs)
	$(DRUN) bash -c "set +u; source /opt/ros/humble/setup.bash; set -u; cd $(WS) && colcon test && colcon test-result --all"
	$(MAKE) schema-test
	$(MAKE) tools-test
	$(MAKE) sim-test

schema-test: ## mission_link JSON Schema doğrulaması (contracts/)
	$(DRUN) bash -c "python3 -m pytest -q contracts/test_mission_link_schema.py"

tools-test: ## mock_server + GameServerClient testleri (Faz 6, tools/)
	$(DRUN) bash -c "set +u; source /opt/ros/humble/setup.bash; set -u; python3 -m pytest -q tools/test_mock_server.py"

sim-test: ## senaryo runner testleri (Faz 7, sim/)
	$(DRUN) bash -c "python3 -m pytest -q sim/test_scenario_runner.py"

lint: ## flake8 + black --check (Faz 0+ python)
	$(DRUN) bash -c "cd /workspace && black --check . 2>/dev/null; flake8 --max-line-length=120 . 2>/dev/null || true"

clean: ## colcon build/install/log temizle (container içinde — dosyalar root-sahipli)
	$(DRUN) bash -c "cd $(WS) && rm -rf build install log"

run-gorsel-servo: ## Görsel-servo demo: uçan kameralı copter + rakip + YOLO (GUI: GZ_HW=1)
	-xhost +local:docker >/dev/null 2>&1 || true
	-docker kill gokdogan-gs >/dev/null 2>&1 || true
	docker run --rm -it --name gokdogan-gs --network host -e DISPLAY=$$DISPLAY -e QT_X11_NO_MITSHM=1 \
	  -e GZ_HW -e WORLD -e WATCH_DELAY $(GPU_DEV) \
	  -v /tmp/.X11-unix:/tmp/.X11-unix -v $(PWD):/workspace -w /workspace $(IMAGE) \
	  bash scripts/run_gorsel_servo.sh
