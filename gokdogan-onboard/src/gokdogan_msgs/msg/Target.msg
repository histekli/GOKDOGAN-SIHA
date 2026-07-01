# Seçilen rakip (target_selector çıktısı). /target/selected (2Hz). SAD §7/§11.
int32 takim_no          # rakip takım numarası
float64 lat             # güncel enlem
float64 lon             # güncel boylam
float32 alt             # irtifa (m)
float32 lead_lat        # lead-angle tahmini kesişim enlemi
float32 lead_lon        # lead-angle tahmini kesişim boylamı
float32 score           # S = 0.40·P_mesafe+0.30·P_açı+0.20·P_geçmiş−0.10·P_risk
