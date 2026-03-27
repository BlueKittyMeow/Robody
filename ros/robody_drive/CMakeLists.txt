cmake_minimum_required(VERSION 2.8.3)
project(robody_drive)

find_package(catkin REQUIRED COMPONENTS
  rospy
  geometry_msgs
  std_msgs
  nav_msgs
)

catkin_package()

catkin_install_python(PROGRAMS
  scripts/mecanum_drive_node.py
  scripts/mecanum.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(DIRECTORY launch/
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/launch
)
