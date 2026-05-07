cmake_minimum_required(VERSION 3.20)

project(XFAgentBridge VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS Widgets Network HttpServer)

qt_add_executable(XFAgentBridge
    WIN32
    MACOSX_BUNDLE
    src/BridgeSettings.cpp
    src/BridgeSettings.h
    src/HttpServerController.cpp
    src/HttpServerController.h
    src/MainWindow.cpp
    src/MainWindow.h
    src/TaskProcessor.cpp
    src/TaskProcessor.h
    src/TaskReceiver.cpp
    src/TaskReceiver.h
    src/processipc.h
    src/processipc.cpp
    src/main.cpp
)

target_link_libraries(XFAgentBridge
    PRIVATE
        Qt6::Widgets
        Qt6::Network
        Qt6::HttpServer
)

set_target_properties(XFAgentBridge PROPERTIES
    MACOSX_BUNDLE_GUI_IDENTIFIER com.xfagent.bridge
    MACOSX_BUNDLE_BUNDLE_NAME XFAgentBridge
    WIN32_EXECUTABLE TRUE
)

install(TARGETS XFAgentBridge
    BUNDLE DESTINATION .
    RUNTIME DESTINATION bin
)
