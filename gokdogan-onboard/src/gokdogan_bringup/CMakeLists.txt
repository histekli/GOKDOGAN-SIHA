cmake_minimum_required(VERSION 3.8)
project(gokdogan_bringup)

find_package(ament_cmake REQUIRED)

install(DIRECTORY launch config DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()

  # Entegrasyon smoke testi (SITL'siz): stack ayağa kalkıyor, /mission/mode IDLE,
  # bağlantısız TAKEOFF reddi. Tam SITL kalkış → scripts/run_sitl_stack.sh (make run-sitl-stack).
  find_package(launch_testing_ament_cmake REQUIRED)
  add_launch_test(test/test_bringup_smoke.py TIMEOUT 120)
endif()

ament_package()
