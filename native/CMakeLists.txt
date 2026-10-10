cmake_minimum_required(VERSION 3.20)
project(ALICETfInspector LANGUAGES CXX)
find_package(O2 CONFIG REQUIRED)
add_executable(alice-tf-inspect tf_inspect.cxx)
target_compile_features(alice-tf-inspect PRIVATE cxx_std_20)
target_link_libraries(alice-tf-inspect PRIVATE O2::TFReaderDD O2::Headers O2::Framework)
add_executable(alice-pv-inventory-workflow pv_inventory.cxx)
target_compile_features(alice-pv-inventory-workflow PRIVATE cxx_std_20)
target_link_libraries(alice-pv-inventory-workflow PRIVATE O2::GlobalTrackingWorkflowHelpers
  O2::GlobalTrackingWorkflowReaders O2::DataFormatsGlobalTracking O2::DetectorsRaw
  O2::Framework O2::FrameworkFoundation O2::CommonUtils O2::ReconstructionDataFormats)
