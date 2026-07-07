#!/usr/bin/env bash
# Kabul Kapısı 7: 8 KTR senaryosunu scenario_runner ile koş (deterministik, hızlı).
#   HSS + kamikaze GERÇEK çekirdekleri sürer; diğerleri fiziğe dayalı kinematik model.
#   Canlı SITL fidelity: her senaryonun 'live_target' make hedefi (run-sitl-stack/hss/guidance/
#   full-loop). Bu gate 8/8 kabul kriterini metrik değerlendirmesiyle doğrular.
set -o pipefail
cd /workspace 2>/dev/null || cd "$(dirname "$0")/.."

echo "=========================================================="
echo " GÖKDOĞAN Kabul Kapısı 7 — 8 KTR Senaryosu"
echo "=========================================================="
python3 sim/scenario_runner.py --all sim/scenarios --report /tmp/scenarios_report.json
RC=$?
echo "----------------------------------------------------------"
if [ "$RC" = "0" ]; then
  echo " Kabul Kapısı 7 GEÇTİ ✅  (rapor: /tmp/scenarios_report.json)"
else
  echo " BAŞARISIZ ❌ (bir veya daha çok senaryo kabul kriterini geçmedi)"
fi
exit $RC
