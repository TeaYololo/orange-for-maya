# Orange Array native Maya node

`orangeArray.cpp` builds the same `orangeArray` dependency node type and type ID as
`blender_kontrol/orangeArray.py`. The native node bulk-builds mesh point/connectivity arrays and
copies face shading-group assignments, UV sets, face-vertex color sets, split normals and edge
smoothing. Maya must load exactly one implementation of this node type in a session. Maya's
`MFnMesh::setCreaseEdges` and `setCreaseVertices` crash when used on the generated mesh data from
this custom DG compute path (reproduced in Maya 2027 in both C++ and Python API); crease weights are
therefore not copied by this node yet. The rest of Array output remains live and stable with crease-bearing input.

The checked-in `blender_kontrol/orangeArray.mll` is compiled for Maya 2027 on Windows x64. The
loader selects it only in Maya 2027; other supported Maya versions use the Python plug-in. Rebuild
for another Maya release because the MLL ABI and devkit libraries are version-specific.

With Visual Studio C++ tools and the matching Maya devkit installed:

```powershell
# MAYA_LOCATION is a CMake cache variable (an environment variable alone is not read).
cmake -S native/orangeArray -B build/orangeArray -A x64 "-DMAYA_LOCATION=C:/Program Files/Autodesk/Maya2027"
cmake --build build/orangeArray --config Release
Copy-Item build/orangeArray/Release/orangeArray.mll blender_kontrol/orangeArray.mll
```

Without CMake on PATH, Visual Studio's bundled copy works:
`C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe`.

`tools/benchmark_orange_array.py` measures warmed DG reevaluation in mayapy. Set
`ORANGE_ARRAY_FORCE_PYTHON=1` to measure the fallback; these numbers do not represent viewport
interaction or rendering. The Python fallback also duplicates mesh object-group components so
face shading remains consistent on releases without the Maya 2027 Windows native binary.
