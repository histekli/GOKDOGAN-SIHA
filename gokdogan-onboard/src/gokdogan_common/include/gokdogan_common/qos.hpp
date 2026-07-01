// GÖKDOĞAN — Merkezî QoS profilleri (C++). SAD §6.
//
// KIRMIZI ÇİZGİ (prompt §2.5): Tüm publisher/subscriber AYNI adlandırılmış profili
// kullanır. Humble'da pub/sub QoS uyumsuzluğu SESSİZ bağlantı kopması yapar.
// Python karşılığı: gokdogan_common/qos.py (birebir aynı değerler — test/test_qos ile doğrulanır).
#ifndef GOKDOGAN_COMMON_QOS_HPP_
#define GOKDOGAN_COMMON_QOS_HPP_

#include "rclcpp/qos.hpp"

namespace gokdogan_common
{

// Yüksek-hız akış: en taze kazanır (BEST_EFFORT, depth=1, VOLATILE).
// /camera/image, /perception/tracks, /perception/selected_bbox,
// /mavros/setpoint_raw/attitude, /aircraft/state
inline rclcpp::QoS sensor_stream()
{
  rclcpp::QoS q(rclcpp::KeepLast(1));
  q.best_effort();
  q.durability_volatile();
  return q;
}

// YOLO tespitleri: güvenilir, kısa geçmiş (RELIABLE, depth=5, VOLATILE).
// /perception/detections
inline rclcpp::QoS detections()
{
  rclcpp::QoS q(rclcpp::KeepLast(5));
  q.reliable();
  q.durability_volatile();
  return q;
}

// Seçilen hedef: geç-katılan abone son değeri görmeli (RELIABLE, depth=10, TRANSIENT_LOCAL).
// /target/selected
inline rclcpp::QoS target_selected()
{
  rclcpp::QoS q(rclcpp::KeepLast(10));
  q.reliable();
  q.transient_local();
  return q;
}

// Kilit olayı: güvenilir olay (RELIABLE, depth=20, VOLATILE).
// /lock/event
inline rclcpp::QoS lock_event()
{
  rclcpp::QoS q(rclcpp::KeepLast(20));
  q.reliable();
  q.durability_volatile();
  return q;
}

// Görev modu: geç-katılan son değeri görmeli (RELIABLE, depth=10, TRANSIENT_LOCAL).
// /mission/mode
inline rclcpp::QoS mission_mode()
{
  rclcpp::QoS q(rclcpp::KeepLast(10));
  q.reliable();
  q.transient_local();
  return q;
}

// Operatör komutu: güvenilir olay (RELIABLE, depth=10, VOLATILE).
// /mission/command
inline rclcpp::QoS mission_command()
{
  rclcpp::QoS q(rclcpp::KeepLast(10));
  q.reliable();
  q.durability_volatile();
  return q;
}

// Sunucu verisi (rakip/HSS): geç-katılan son değeri görmeli (RELIABLE, depth=5, TRANSIENT_LOCAL).
// /server/opponents, /server/hss
inline rclcpp::QoS server_data()
{
  rclcpp::QoS q(rclcpp::KeepLast(5));
  q.reliable();
  q.transient_local();
  return q;
}

}  // namespace gokdogan_common

#endif  // GOKDOGAN_COMMON_QOS_HPP_
