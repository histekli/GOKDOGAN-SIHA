# Kilit denetimi olayı — canlı ilerleme + geçerlilik. /lock/event. SAD §7/§12.
bool valid                              # true = 5s pencerede ≥4s kural sağlandı
int32 target_id                         # kilitlenen hedefin takip ID'si
BBox box                                # kilit anındaki dörtgen
float32[2] center                       # [cx, cy] piksel merkezi
float32 progress_s                      # 0..4 s canlı ilerleme (GCS aynası)
builtin_interfaces/Time lock_end_time   # geçerli kilidin bitiş zamanı (ServerClock damgası GCS'te)
