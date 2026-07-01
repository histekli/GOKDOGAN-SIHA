cmake_minimum_required(VERSION 3.8)
project(gokdogan_common)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclcpp REQUIRED)

# C++ header-only kütüphane (qos.hpp)
install(DIRECTORY include/ DESTINATION include)
ament_export_include_directories(include)
ament_export_dependencies(rclcpp)

# Python modülü (qos.py)
ament_python_install_package(${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  set(ament_cmake_uncrustify_FOUND TRUE)
  set(ament_cmake_pep257_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()

  # C++ QoS parite testi
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_qos_cpp test/test_qos.cpp)
  if(TARGET test_qos_cpp)
    target_include_directories(test_qos_cpp PRIVATE include)
    ament_target_dependencies(test_qos_cpp rclcpp)
  endif()

  # Python QoS golden testi
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_qos_py test/test_qos.py)
endif()

ament_package()
