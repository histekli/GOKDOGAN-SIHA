cmake_minimum_required(VERSION 3.8)
project(gokdogan_guidance)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

# C++ header-only kütüphane (frames.hpp)
install(DIRECTORY include/ DESTINATION include)
ament_export_include_directories(include)

# Python modülü (frames.py + gelecekte güdüm)
ament_python_install_package(${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  set(ament_cmake_uncrustify_FOUND TRUE)
  set(ament_cmake_pep257_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()

  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_frames_cpp test/test_frames.cpp)
  if(TARGET test_frames_cpp)
    target_include_directories(test_frames_cpp PRIVATE include)
  endif()

  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_frames_py test/test_frames.py)
endif()

ament_package()
