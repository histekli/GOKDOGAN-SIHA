# Kendi uçağımızın birleşik durumu (MAVROS'tan derlenmiş). /aircraft/state (20Hz). SAD §7/§8.
std_msgs/Header header
float64 lat
float64 lon
float32 alt              # irtifa (m)
float32 roll            # rad (ENU)
float32 pitch           # rad
float32 yaw             # rad (ENU: Doğu'dan CCW)
float32 vground         # yer hızı (m/s)
float32 vair            # hava hızı (m/s)
float32 batt            # batarya yüzdesi [0..100]
string mode             # ArduPilot uçuş modu (GUIDED/AUTO/RTL/...)
bool armed
bool is_autonomous      # otonom mod aktif mi (kilit denetimi şartı)
