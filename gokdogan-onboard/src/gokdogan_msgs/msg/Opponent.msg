# Tek rakip telemetrisi (sunucudan, KTR alan adları). SAD §7.
int32 takim_no
float64 enlem           # lat
float64 boylam          # lon
float32 irtifa          # alt (m)
float32 dikilme         # pitch (deg) [-90,90]
float32 yonelme         # heading (deg) [0,360]
float32 yatis           # roll (deg) [-90,90]
float32 hiz             # ground speed (m/s)
float32 zaman_farki     # sunucu ile ölçüm arası gecikme (s) — tahmin/güncellik için
