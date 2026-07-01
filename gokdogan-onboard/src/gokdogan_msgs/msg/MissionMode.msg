# Görev FSM durumu + tek-yazıcı tahkimi. /mission/mode (olay+1Hz). SAD §7/§12.
# state değerleri (DFA):
uint8 IDLE=0
uint8 TAKEOFF=1
uint8 CRUISE=2
uint8 LOCKING=3
uint8 KAMIKAZE=4
uint8 RTL=5
uint8 LAND=6
uint8 MANUAL=7

# active_service değerleri (setpoint yazma hakkı sahibi — tek yazıcı invaryantı):
uint8 SVC_NONE=0
uint8 SVC_GUIDANCE=1
uint8 SVC_KAMIKAZE=2
uint8 SVC_HSS=3
uint8 SVC_MISSION_FSM=4     # takeoff/land/RTL doğrudan FSM

uint8 state
uint8 active_service
string detail
