// QoS profil tutarlılık testi (C++). SAD §6 golden değerleri — qos.py ile PARİTE kontratı.
// Aynı golden test_qos.py'de; ikisi eşleşmezse C++/Python node'ları sessizce kopar (prompt §2.5).
#include <gtest/gtest.h>
#include "gokdogan_common/qos.hpp"

namespace
{
struct Golden
{
  rmw_qos_reliability_policy_t rel;
  rmw_qos_durability_policy_t dur;
  size_t depth;
};

void check(const rclcpp::QoS & q, const Golden & g, const char * name)
{
  const auto & p = q.get_rmw_qos_profile();
  EXPECT_EQ(p.history, RMW_QOS_POLICY_HISTORY_KEEP_LAST) << name;
  EXPECT_EQ(p.reliability, g.rel) << name;
  EXPECT_EQ(p.durability, g.dur) << name;
  EXPECT_EQ(p.depth, g.depth) << name;
}
}  // namespace

TEST(QoSParity, MatchesSadGolden)
{
  using namespace gokdogan_common;
  check(sensor_stream(),
        {RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT, RMW_QOS_POLICY_DURABILITY_VOLATILE, 1},
        "sensor_stream");
  check(detections(),
        {RMW_QOS_POLICY_RELIABILITY_RELIABLE, RMW_QOS_POLICY_DURABILITY_VOLATILE, 5},
        "detections");
  check(target_selected(),
        {RMW_QOS_POLICY_RELIABILITY_RELIABLE, RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL, 10},
        "target_selected");
  check(lock_event(),
        {RMW_QOS_POLICY_RELIABILITY_RELIABLE, RMW_QOS_POLICY_DURABILITY_VOLATILE, 20},
        "lock_event");
  check(mission_mode(),
        {RMW_QOS_POLICY_RELIABILITY_RELIABLE, RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL, 10},
        "mission_mode");
  check(mission_command(),
        {RMW_QOS_POLICY_RELIABILITY_RELIABLE, RMW_QOS_POLICY_DURABILITY_VOLATILE, 10},
        "mission_command");
  check(server_data(),
        {RMW_QOS_POLICY_RELIABILITY_RELIABLE, RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL, 5},
        "server_data");
}
