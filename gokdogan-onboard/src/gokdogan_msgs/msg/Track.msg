# Kalman takip çıktısı. Durum [px,py,vx,vy,ax,ay]. SAD §7/§10.
int32 id                # kalıcı takip ID (Hungarian, IoU≥0.3)
BBox box                # güncel/öngörülen dörtgen
float32 vx              # piksel/s
float32 vy              # piksel/s
float32 age             # takibin yaşı (s)
bool predicted          # true = bu kare YOLO'suz sadece Kalman öngörüsü
