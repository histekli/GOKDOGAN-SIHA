// ENU↔NED dönüşüm testleri (C++). SAD §8. frames.py ile PARİTE.
#include <gtest/gtest.h>
#include "gokdogan_guidance/frames.hpp"

using namespace gokdogan_guidance;

namespace
{
bool ang_close(double a, double b, double tol = 1e-9)
{
  return std::abs(wrap_to_pi(a - b)) < tol;
}
}  // namespace

TEST(Frames, PositionRoundtripIdentity)
{
  const double e = 100.0, n = -50.0, u = -7.0;
  auto ned = enu_to_ned(e, n, u);
  auto enu = ned_to_enu(ned[0], ned[1], ned[2]);
  EXPECT_DOUBLE_EQ(enu[0], e);
  EXPECT_DOUBLE_EQ(enu[1], n);
  EXPECT_DOUBLE_EQ(enu[2], u);
}

TEST(Frames, EnuToNedKnown)
{
  auto ned = enu_to_ned(1.0, 2.0, 3.0);
  EXPECT_DOUBLE_EQ(ned[0], 2.0);
  EXPECT_DOUBLE_EQ(ned[1], 1.0);
  EXPECT_DOUBLE_EQ(ned[2], -3.0);
}

TEST(Frames, YawFromHeadingKnown)
{
  EXPECT_TRUE(ang_close(yaw_enu_from_heading_ned(0.0), kHalfPi));            // Kuzey
  EXPECT_TRUE(ang_close(yaw_enu_from_heading_ned(kHalfPi), 0.0));           // Doğu
  EXPECT_TRUE(ang_close(yaw_enu_from_heading_ned(kPi), -kHalfPi));          // Güney
}

TEST(Frames, YawHeadingRoundtrip)
{
  for (double h : {0.0, 0.3, 1.0, kHalfPi, 3.0, kPi, 4.5, 6.0}) {
    double yaw = yaw_enu_from_heading_ned(h);
    double back = heading_ned_from_yaw_enu(yaw);
    EXPECT_TRUE(ang_close(back, h)) << "heading=" << h;
  }
}
