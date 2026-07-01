# Operatör komutu (GCS→onboard, mission_link üzerinden). /mission/command. SAD §7/§12.
uint8 START_LOCK=0
uint8 ABORT=1
uint8 SELECT_TARGET=2
uint8 START_KAMIKAZE=3
uint8 SET_MODE=4

uint8 type
int32 target_id         # SELECT_TARGET / START_KAMIKAZE için hedef ID
string mode             # SET_MODE için (GUIDED/AUTO/RTL/LOITER/LAND)
string params_json      # ek parametreler (serbest form JSON)
