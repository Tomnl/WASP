cmake_minimum_required(VERSION 2.8.9)

project(WASP)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "http://www.example.com/Slicer/Extensions/WASP")
set(EXTENSION_CATEGORY "Segmentation")
set(EXTENSION_CONTRIBUTORS "Thomas lawson (MRC Harwell)")
set(EXTENSION_DESCRIPTION "Watershed Annotation and Segmentation Plugin.

Performs a series of watershed filters on a 3D image. 

The user can then select individual segmentations using fiducials to make a new label map.

A model of the label map is generated as well.
")
set(EXTENSION_ICONURL "http://www.example.com/Slicer/Extensions/WASP.png")
set(EXTENSION_SCREENSHOTURLS "http://www.example.com/Slicer/Extensions/WASP/Screenshots/1.png")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(WASP)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_CPACK})
