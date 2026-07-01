cmake_minimum_required(VERSION 3.8)
project(gokdogan_msgs)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  # msg (SAD §7)
  msg/BBox.msg
  msg/Track.msg
  msg/Tracks.msg
  msg/Detections.msg
  msg/LockEvent.msg
  msg/Target.msg
  msg/MissionMode.msg
  msg/MissionCommand.msg
  msg/Opponent.msg
  msg/Opponents.msg
  msg/Hss.msg
  msg/HssList.msg
  msg/AircraftState.msg
  # srv
  srv/SetMissionMode.srv
  srv/ArmDisarm.srv
  # action
  action/ExecuteKamikaze.action
  DEPENDENCIES builtin_interfaces std_msgs
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # Pedantik linter'ları atla (tescilli kod, el yazımı stil): copyright/cpplint/uncrustify.
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  set(ament_cmake_uncrustify_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
