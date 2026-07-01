# GÖKDOĞAN — dev/CI Makefile (her şey dev container içinde koşar; host'ta ROS2 yok)
.DEFAULT_GOAL := help
SHELL := /bin/bash

IMAGE      ?= gokdogan-dev:latest
DOCKERFILE ?= docker/Dockerfile.dev
WS         ?= /workspace/gokdogan-onboard

# Host'ta çalışan interaktif olmayan container run (loopback ağ, repo mount)
DRUN = docker run --rm --network host -v $(PWD):/workspace -w /workspace $(IMAGE)
DRUN_IT = docker run --rm -it --network host -v $(PWD):/workspace -w /workspace $(IMAGE)

.PHONY: help build shell verify-env verify-sitl sitl run-sitl-stack ws-build test schema-test lint clean

help: ## Bu yardımı göster
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

build: ## Dev imajını kur (ROS2 Humble + ArduPilot SITL + MAVROS)
	DOCKER_BUILDKIT=1 docker build -f $(DOCKERFILE) -t $(IMAGE) .

shell: ## Dev container içine interaktif gir
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

mock-gcs: ## mock GCS'i çalıştır (referans yer istasyonu — onboard'a bağlanır)
	$(DRUN_IT) bash -c "source /opt/ros/humble/setup.bash; source gokdogan-onboard/install/setup.bash; python3 tools/mock_gcs.py $(ARGS)"

ws-build: ## colcon workspace derle (Faz 0+ paketleri geldiğinde)
	$(DRUN) bash -c "source /opt/ros/humble/setup.bash && cd $(WS) && colcon build --symlink-install"

test: ## colcon test (Faz 0+) + mission_link şema testi
	$(DRUN) bash -c "set +u; source /opt/ros/humble/setup.bash; set -u; cd $(WS) && colcon test && colcon test-result --all"
	$(MAKE) schema-test

schema-test: ## mission_link JSON Schema doğrulaması (contracts/)
	$(DRUN) bash -c "python3 -m pytest -q contracts/test_mission_link_schema.py"

lint: ## flake8 + black --check (Faz 0+ python)
	$(DRUN) bash -c "cd /workspace && black --check . 2>/dev/null; flake8 --max-line-length=120 . 2>/dev/null || true"

clean: ## colcon build/install/log temizle
	rm -rf gokdogan-onboard/build gokdogan-onboard/install gokdogan-onboard/log
