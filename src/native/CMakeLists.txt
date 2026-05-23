cmake_minimum_required(VERSION 3.16)
project(audio_capture LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Static CRT — no Visual C++ redistributable needed
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

add_library(audio_capture SHARED
    audio_capture.cpp
)

target_compile_definitions(audio_capture PRIVATE AUDIO_CAPTURE_EXPORTS)

target_link_libraries(audio_capture PRIVATE ole32)

# Suppress noisy warnings
if(MSVC)
    target_compile_options(audio_capture PRIVATE /W3 /wd4996 /utf-8)
endif()
