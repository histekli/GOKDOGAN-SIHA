// GÖKDOĞAN — ENU↔NED çerçeve dönüşümleri (C++). SAD §8.
//
// KIRMIZI ÇİZGİ (prompt §2.4): ENU↔NED dönüşümü TEK YERDE. Başka hiçbir yerde elle
// yaw/koordinat çevirme YOK. Python karşılığı frames.py ile birebir (round-trip test).
//
// Pozisyon/hız: ENU (E,N,U) ↔ NED (N,E,D).  Açı: yaw_enu = π/2 − heading_ned.
#ifndef GOKDOGAN_GUIDANCE_FRAMES_HPP_
#define GOKDOGAN_GUIDANCE_FRAMES_HPP_

#include <array>
#include <cmath>

namespace gokdogan_guidance
{

constexpr double kPi = 3.14159265358979323846;
constexpr double kTwoPi = 2.0 * kPi;
constexpr double kHalfPi = 0.5 * kPi;

using Vec3 = std::array<double, 3>;

// Açıyı (−π, π] aralığına sar.
inline double wrap_to_pi(double angle)
{
  double a = std::fmod(angle + kPi, kTwoPi);
  if (a <= 0.0) {
    a += kTwoPi;
  }
  return a - kPi;
}

// Açıyı [0, 2π) aralığına sar (heading konvansiyonu).
inline double wrap_to_2pi(double angle)
{
  double a = std::fmod(angle, kTwoPi);
  if (a < 0.0) {
    a += kTwoPi;
  }
  return a;
}

// ENU → NED. (E,N,U) → (N,E,−U). Self-inverse.
inline Vec3 enu_to_ned(double east, double north, double up)
{
  return Vec3{north, east, -up};
}

// NED → ENU. (N,E,D) → (E,N,−D). Self-inverse.
inline Vec3 ned_to_enu(double north, double east, double down)
{
  return Vec3{east, north, -down};
}

// ENU hız → NED hız (pozisyonla aynı eksen dönüşümü).
inline Vec3 enu_vel_to_ned(double ve, double vn, double vu)
{
  return enu_to_ned(ve, vn, vu);
}

// NED hız → ENU hız.
inline Vec3 ned_vel_to_enu(double vn, double ve, double vd)
{
  return ned_to_enu(vn, ve, vd);
}

// NED heading (Kuzey'den CW) → ENU yaw (Doğu'dan CCW). (−π, π].
inline double yaw_enu_from_heading_ned(double heading_ned)
{
  return wrap_to_pi(kHalfPi - heading_ned);
}

// ENU yaw (Doğu'dan CCW) → NED heading (Kuzey'den CW). [0, 2π).
inline double heading_ned_from_yaw_enu(double yaw_enu)
{
  return wrap_to_2pi(kHalfPi - yaw_enu);
}

}  // namespace gokdogan_guidance

#endif  // GOKDOGAN_GUIDANCE_FRAMES_HPP_
