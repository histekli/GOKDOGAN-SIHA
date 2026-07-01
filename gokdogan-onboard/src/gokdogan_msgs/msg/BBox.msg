# Sınırlayıcı dörtgen — 1920x1200 kamera uzayında (merkez 960,600). SAD §7/§10.
float32 x                        # sol-üst köşe x (piksel)
float32 y                        # sol-üst köşe y (piksel)
float32 w                        # genişlik (piksel)
float32 h                        # yükseklik (piksel)
float32 score                    # tespit güveni [0..1]
int32 track_id                   # ilişkili takip ID'si (-1 = yok)
builtin_interfaces/Time stamp    # kaynak frame zaman damgası
