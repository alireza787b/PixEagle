#!/usr/bin/env bash
# Prospective native component build only. No PX4 daemon, simulator or hardware action.
set -euo pipefail
test ! -e /build/CMakeCache.txt
test -f /source/test/fuzztest/CMakeLists.txt
cmake -S /source -B /build -G Ninja \
  -DCONFIG=px4_sitl_test -DCMAKE_BUILD_TYPE=Debug \
  -DANTLR_BUILD_CPP_TESTS=OFF \
  '-DTESTFILTER=^functional-FlightTaskTransition$' \
  "-DPX4_GIT_SUBMODULES=${PX4_GIT_SUBMODULES:?Locked submodules are required}" \
  -DFETCHCONTENT_FULLY_DISCONNECTED=ON -DFETCHCONTENT_UPDATES_DISCONNECTED=ON \
  '-DFETCHCONTENT_SOURCE_DIR_ABSEIL-CPP=/deps/abseil-cpp' \
  -DFETCHCONTENT_SOURCE_DIR_RE2=/deps/re2 \
  -DFETCHCONTENT_SOURCE_DIR_GOOGLETEST=/deps/googletest \
  -DFETCHCONTENT_SOURCE_DIR_ANTLR_CPP=/deps/antlr_cpp
cmake --build /build --target functional-FlightTaskTransition -j2
GTEST_OUTPUT=xml:/build/native-tests.xml \
TRANSITION_CHARACTERIZATION=/build/native-characterization.csv \
  ctest --test-dir /build --no-tests=error --output-on-failure \
  -R '^functional-FlightTaskTransition$'
