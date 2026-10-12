#include <maya/MFnDependencyNode.h>
#include <maya/MFnGeometryData.h>
#include <maya/MFnMesh.h>
#include <maya/MFnMeshData.h>
#include <maya/MFnSingleIndexedComponent.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MFnMatrixAttribute.h>
#include <maya/MFnPlugin.h>
#include <maya/MFnTypedAttribute.h>
#include <maya/MGlobal.h>
#include <maya/MIntArray.h>
#include <maya/MMatrix.h>
#include <maya/MTransformationMatrix.h>
#include <maya/MObject.h>
#include <maya/MPointArray.h>
#include <maya/MPxNode.h>
#include <maya/MStatus.h>
#include <maya/MStringArray.h>
#include <maya/MVector.h>
#include <maya/MVectorArray.h>
#include <maya/MFloatArray.h>
#include <maya/MFloatVectorArray.h>
#include <maya/MColorArray.h>
#include <maya/MUintArray.h>
#include <maya/MDoubleArray.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <cmath>
#include <map>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {
const char* kTypeName = "orangeArray";
const MTypeId kTypeId(0x0013B2A1);

uint64_t edgeKey(int a, int b) {
    const uint32_t lo = static_cast<uint32_t>(std::min(a, b));
    const uint32_t hi = static_cast<uint32_t>(std::max(a, b));
    return (static_cast<uint64_t>(lo) << 32) | hi;
}

struct CellKey {
    int64_t x, y, z;
    bool operator==(const CellKey& other) const { return x == other.x && y == other.y && z == other.z; }
};
struct CellHash {
    size_t operator()(const CellKey& c) const {
        size_t h = std::hash<int64_t>()(c.x);
        h ^= std::hash<int64_t>()(c.y) + 0x9e3779b9 + (h << 6) + (h >> 2);
        h ^= std::hash<int64_t>()(c.z) + 0x9e3779b9 + (h << 6) + (h >> 2);
        return h;
    }
};
int64_t cellCoord(double value, double cellSize) {
    const double q = std::floor(value / cellSize);
    const double limit = 9.0e15;
    return static_cast<int64_t>(std::max(-limit, std::min(limit, q)));
}

class OrangeArrayNode final : public MPxNode {
public:
    static MObject inputMesh;
    static MObject outputMesh;
    static MObject count;
    static MObject relativeX;
    static MObject relativeY;
    static MObject relativeZ;
    static MObject constantX;
    static MObject constantY;
    static MObject constantZ;
    static MObject useObjectOffset;
    static MObject objectWorldMatrix;
    static MObject baseInverseMatrix;
    static MObject mergeCopies;
    static MObject mergeDistance;

    static void* creator() { return new OrangeArrayNode(); }

    static MStatus initialize() {
        MStatus status;
        MFnTypedAttribute typed;
        inputMesh = typed.create("inputMesh", "im", MFnData::kMesh, MObject::kNullObj, &status);
        CHECK_MSTATUS_AND_RETURN_IT(status);
        typed.setStorable(true);
        typed.setReadable(false);
        typed.setWritable(true);
        CHECK_MSTATUS_AND_RETURN_IT(addAttribute(inputMesh));

        outputMesh = typed.create("outputMesh", "om", MFnData::kMesh, MObject::kNullObj, &status);
        CHECK_MSTATUS_AND_RETURN_IT(status);
        typed.setStorable(false);
        typed.setReadable(true);
        typed.setWritable(false);
        CHECK_MSTATUS_AND_RETURN_IT(addAttribute(outputMesh));

        MFnNumericAttribute numeric;
        count = numeric.create("count", "cnt", MFnNumericData::kInt, 2, &status);
        CHECK_MSTATUS_AND_RETURN_IT(status);
        numeric.setMin(1);
        numeric.setKeyable(true);
        CHECK_MSTATUS_AND_RETURN_IT(addAttribute(count));

        struct NumberAttr { const char* name; const char* shortName; double defaultValue; MObject* object; };
        NumberAttr attrs[] = {
            {"relativeX", "rx", 1.0, &relativeX}, {"relativeY", "ry", 0.0, &relativeY},
            {"relativeZ", "rz", 0.0, &relativeZ}, {"constantX", "cx", 0.0, &constantX},
            {"constantY", "cy", 0.0, &constantY}, {"constantZ", "cz", 0.0, &constantZ}
        };
        for (auto& attr : attrs) {
            *attr.object = numeric.create(attr.name, attr.shortName, MFnNumericData::kDouble,
                                          attr.defaultValue, &status);
            CHECK_MSTATUS_AND_RETURN_IT(status);
            numeric.setKeyable(true);
            CHECK_MSTATUS_AND_RETURN_IT(addAttribute(*attr.object));
        }

        useObjectOffset = numeric.create("useObjectOffset", "uoo", MFnNumericData::kBoolean, false, &status);
        CHECK_MSTATUS_AND_RETURN_IT(status);
        numeric.setKeyable(true);
        CHECK_MSTATUS_AND_RETURN_IT(addAttribute(useObjectOffset));
        MFnMatrixAttribute matrix;
        objectWorldMatrix = matrix.create("objectWorldMatrix", "owm", MFnMatrixAttribute::kDouble, &status);
        CHECK_MSTATUS_AND_RETURN_IT(status);
        matrix.setStorable(false);
        CHECK_MSTATUS_AND_RETURN_IT(addAttribute(objectWorldMatrix));
        baseInverseMatrix = matrix.create("baseInverseMatrix", "bim", MFnMatrixAttribute::kDouble, &status);
        CHECK_MSTATUS_AND_RETURN_IT(status);
        matrix.setStorable(false);
        CHECK_MSTATUS_AND_RETURN_IT(addAttribute(baseInverseMatrix));
        mergeCopies = numeric.create("mergeCopies", "mc", MFnNumericData::kBoolean, false, &status);
        CHECK_MSTATUS_AND_RETURN_IT(status);
        numeric.setKeyable(true);
        CHECK_MSTATUS_AND_RETURN_IT(addAttribute(mergeCopies));
        mergeDistance = numeric.create("mergeDistance", "md", MFnNumericData::kDouble, 0.001, &status);
        CHECK_MSTATUS_AND_RETURN_IT(status);
        numeric.setMin(0.0);
        numeric.setKeyable(true);
        CHECK_MSTATUS_AND_RETURN_IT(addAttribute(mergeDistance));

        for (const MObject& source : {inputMesh, count, relativeX, relativeY, relativeZ,
                                      constantX, constantY, constantZ, useObjectOffset,
                                      objectWorldMatrix, baseInverseMatrix, mergeCopies, mergeDistance}) {
            CHECK_MSTATUS_AND_RETURN_IT(attributeAffects(source, outputMesh));
        }
        return MS::kSuccess;
    }

    MStatus compute(const MPlug& plug, MDataBlock& data) override {
        if (plug != outputMesh) return MS::kUnknownParameter;
        MStatus status;
        const MObject sourceObject = data.inputValue(inputMesh, &status).asMesh();
        CHECK_MSTATUS_AND_RETURN_IT(status);
        MPlug statePlug = MFnDependencyNode(thisMObject()).findPlug("nodeState", true, &status);
        short nodeState = 0;
        if (status == MS::kSuccess && statePlug.getValue(nodeState) == MS::kSuccess && nodeState == 1) {
            data.outputValue(outputMesh).setMObject(sourceObject);
            data.setClean(plug);
            return MS::kSuccess;
        }
        MFnMeshData outputDataFn;
        MObject outputData = outputDataFn.create(&status);
        CHECK_MSTATUS_AND_RETURN_IT(status);
        if (sourceObject.isNull()) {
            data.outputValue(outputMesh).setMObject(outputData);
            data.setClean(plug);
            return MS::kSuccess;
        }

        MFnMesh source(sourceObject, &status);
        CHECK_MSTATUS_AND_RETURN_IT(status);
        MPointArray sourcePoints;
        CHECK_MSTATUS_AND_RETURN_IT(source.getPoints(sourcePoints, MSpace::kObject));
        MIntArray sourceCounts, sourceConnects;
        CHECK_MSTATUS_AND_RETURN_IT(source.getVertices(sourceCounts, sourceConnects));

        const unsigned int sourceVertexCount = sourcePoints.length();
        const unsigned int sourceFaceCount = sourceCounts.length();
        const unsigned int sourceConnectCount = sourceConnects.length();
        const int copies = std::max(1, std::min(10000, data.inputValue(count).asInt()));
        double minPoint[3] = {0.0, 0.0, 0.0};
        double maxPoint[3] = {0.0, 0.0, 0.0};
        if (sourceVertexCount) {
            minPoint[0] = maxPoint[0] = sourcePoints[0].x;
            minPoint[1] = maxPoint[1] = sourcePoints[0].y;
            minPoint[2] = maxPoint[2] = sourcePoints[0].z;
            for (unsigned int i = 1; i < sourceVertexCount; ++i) {
                for (unsigned int axis = 0; axis < 3; ++axis) {
                    const double value = sourcePoints[i][axis];
                    minPoint[axis] = std::min(minPoint[axis], value);
                    maxPoint[axis] = std::max(maxPoint[axis], value);
                }
            }
        }
        const double relative[3] = {data.inputValue(relativeX).asDouble(),
                                    data.inputValue(relativeY).asDouble(),
                                    data.inputValue(relativeZ).asDouble()};
        const double constant[3] = {data.inputValue(constantX).asDouble(),
                                    data.inputValue(constantY).asDouble(),
                                    data.inputValue(constantZ).asDouble()};
        double step[3];
        for (unsigned int axis = 0; axis < 3; ++axis)
            step[axis] = (maxPoint[axis] - minPoint[axis]) * relative[axis] + constant[axis];

        MMatrix objectOffset;
        if (data.inputValue(useObjectOffset).asBool()) {
            objectOffset = data.inputValue(objectWorldMatrix).asMatrix() *
                           data.inputValue(baseInverseMatrix).asMatrix();
        }
        MTransformationMatrix stepTransform;
        CHECK_MSTATUS_AND_RETURN_IT(stepTransform.setTranslation(
            MVector(step[0], step[1], step[2]), MSpace::kTransform));
        MMatrix stepMatrix = stepTransform.asMatrix() * objectOffset;

        MPointArray points;
        std::vector<int> faceCountsVec, faceConnectsVec;
        faceCountsVec.reserve(static_cast<size_t>(sourceFaceCount) * copies);
        faceConnectsVec.reserve(static_cast<size_t>(sourceConnectCount) * copies);
        std::vector<unsigned int> vertexMap;
        vertexMap.reserve(sourceVertexCount * static_cast<unsigned int>(copies));
        // faceMap: kopya*F + yuz -> cikti yuz indeksi (-1: birlesme sonucu cokmus, atlandi).
        // keepFaceVertex: kaynak yuz-kosesi (kopya sirasiyla) ciktida kaldi mi; birlesme kapaliyken bos = hepsi kaldi.
        std::vector<int> faceMap;
        faceMap.reserve(static_cast<size_t>(sourceFaceCount) * copies);
        std::vector<char> keepFaceVertex;
        const double mergeDistanceValue = std::max(0.0, data.inputValue(mergeDistance).asDouble());
        const bool merge = data.inputValue(mergeCopies).asBool() && mergeDistanceValue > 0.0;
        const double mergeDistanceSq = mergeDistanceValue * mergeDistanceValue;
        if (merge) keepFaceVertex.reserve(static_cast<size_t>(sourceConnectCount) * copies);
        std::unordered_map<CellKey, std::vector<unsigned int>, CellHash> cells;
        std::vector<unsigned int> faceIdsScratch, keptLocal, sortedScratch;
        MMatrix copyMatrix;
        for (int copy = 0; copy < copies; ++copy) {
            const unsigned int faceOffset = static_cast<unsigned int>(copy) * sourceFaceCount;
            const size_t vertexOffset = static_cast<size_t>(copy) * sourceVertexCount;
            for (unsigned int i = 0; i < sourceVertexCount; ++i) {
                const MPoint point = sourcePoints[i] * copyMatrix;
                if (merge) {
                    const CellKey cell = {cellCoord(point.x, mergeDistanceValue),
                                          cellCoord(point.y, mergeDistanceValue),
                                          cellCoord(point.z, mergeDistanceValue)};
                    unsigned int found = static_cast<unsigned int>(points.length());
                    bool matched = false;
                    for (int dx = -1; dx <= 1 && !matched; ++dx)
                        for (int dy = -1; dy <= 1 && !matched; ++dy)
                            for (int dz = -1; dz <= 1 && !matched; ++dz) {
                                const CellKey neighbor = {cell.x + dx, cell.y + dy, cell.z + dz};
                                const auto bucket = cells.find(neighbor);
                                if (bucket == cells.end()) continue;
                                for (unsigned int candidate : bucket->second) {
                                    const MVector delta = point - points[candidate];
                                    if ((delta * delta) <= mergeDistanceSq) {
                                        found = candidate;
                                        matched = true;
                                        break;
                                    }
                                }
                            }
                    if (!matched) {
                        points.append(point);
                        cells[cell].push_back(found);
                    }
                    vertexMap.push_back(found);
                } else {
                    vertexMap.push_back(static_cast<unsigned int>(points.length()));
                    points.append(point);
                }
            }
            if (!merge) {
                for (unsigned int i = 0; i < sourceFaceCount; ++i) {
                    faceCountsVec.push_back(sourceCounts[i]);
                    faceMap.push_back(static_cast<int>(faceOffset + i));
                }
                for (unsigned int i = 0; i < sourceConnectCount; ++i)
                    faceConnectsVec.push_back(static_cast<int>(vertexMap[
                        vertexOffset + static_cast<unsigned int>(sourceConnects[i])]));
            } else {
                // Birlesme mesafesi bir kenardan uzunsa bir yuz ayni koseyi iki kez gosterebilir; MFnMesh::create
                // bunu reddeder. Ardisik tekrarlari at, 3 koseden az kalan ya da hala tekrarlayan (papyon) yuzleri atla.
                unsigned int cursor = 0;
                for (unsigned int face = 0; face < sourceFaceCount; ++face) {
                    const unsigned int n = static_cast<unsigned int>(sourceCounts[face]);
                    faceIdsScratch.resize(n);
                    for (unsigned int k = 0; k < n; ++k)
                        faceIdsScratch[k] = vertexMap[vertexOffset + static_cast<unsigned int>(sourceConnects[cursor + k])];
                    keptLocal.clear();
                    for (unsigned int k = 0; k < n; ++k)
                        if (faceIdsScratch[k] != faceIdsScratch[(k + 1) % n]) keptLocal.push_back(k);
                    bool valid = keptLocal.size() >= 3;
                    if (valid) {
                        sortedScratch.clear();
                        for (unsigned int k : keptLocal) sortedScratch.push_back(faceIdsScratch[k]);
                        std::sort(sortedScratch.begin(), sortedScratch.end());
                        valid = std::adjacent_find(sortedScratch.begin(), sortedScratch.end()) == sortedScratch.end();
                    }
                    if (!valid) keptLocal.clear();
                    size_t keptCursor = 0;
                    for (unsigned int k = 0; k < n; ++k) {
                        const bool kept = keptCursor < keptLocal.size() && keptLocal[keptCursor] == k;
                        if (kept) ++keptCursor;
                        keepFaceVertex.push_back(kept ? 1 : 0);
                    }
                    if (valid) {
                        faceMap.push_back(static_cast<int>(faceCountsVec.size()));
                        faceCountsVec.push_back(static_cast<int>(keptLocal.size()));
                        for (unsigned int k : keptLocal) faceConnectsVec.push_back(static_cast<int>(faceIdsScratch[k]));
                    } else {
                        faceMap.push_back(-1);
                    }
                    cursor += n;
                }
            }
            copyMatrix *= stepMatrix;
        }

        if (faceCountsVec.empty()) {
            // Butun yuzler birlesmeyle coktu: MFnMesh::create yuzsuz mesh'i reddeder, bos mesh dondur.
            data.outputValue(outputMesh).setMObject(outputData);
            data.setClean(plug);
            return MS::kSuccess;
        }
        MIntArray faceCounts, faceConnects;
        faceCounts = MIntArray(faceCountsVec.data(), static_cast<unsigned int>(faceCountsVec.size()));
        if (!faceConnectsVec.empty())
            faceConnects = MIntArray(faceConnectsVec.data(), static_cast<unsigned int>(faceConnectsVec.size()));
        MFnMesh output;
        output.create(static_cast<int>(points.length()), static_cast<int>(faceCounts.length()),
                      points, faceCounts, faceConnects, outputData, &status);
        CHECK_MSTATUS_AND_RETURN_IT(status);

        // Kenar numaralari MFnMesh::create'in uretimine baglidir ve duzenlenmis bir mesh'te kaynak numaralariyla
        // ortusmez; bu yuzden birlesme kapaliyken de kose cifti -> kenar esleme kurulur.
        const unsigned int sourceEdgeCount = static_cast<unsigned int>(source.numEdges());
        std::vector<int> edgeMap(static_cast<size_t>(copies) * sourceEdgeCount, -1);
        {
            std::unordered_map<uint64_t, int> outputEdgeIds;
            outputEdgeIds.reserve(static_cast<size_t>(std::max(0, output.numEdges())));
            for (int edge = 0; edge < output.numEdges(); ++edge) {
                int2 vertices;
                if (output.getEdgeVertices(edge, vertices) == MS::kSuccess)
                    outputEdgeIds[edgeKey(vertices[0], vertices[1])] = edge;
            }
            std::vector<std::pair<int, int>> sourceEdges(sourceEdgeCount, std::make_pair(-1, -1));
            for (unsigned int edge = 0; edge < sourceEdgeCount; ++edge) {
                int2 vertices;
                if (source.getEdgeVertices(static_cast<int>(edge), vertices) == MS::kSuccess)
                    sourceEdges[edge] = std::make_pair(vertices[0], vertices[1]);
            }
            for (int copy = 0; copy < copies; ++copy) {
                const size_t vertexOffset = static_cast<size_t>(copy) * sourceVertexCount;
                const size_t edgeOffset = static_cast<size_t>(copy) * sourceEdgeCount;
                for (unsigned int edge = 0; edge < sourceEdgeCount; ++edge) {
                    if (sourceEdges[edge].first < 0) continue;
                    const int a = static_cast<int>(vertexMap[vertexOffset + static_cast<unsigned int>(sourceEdges[edge].first)]);
                    const int b = static_cast<int>(vertexMap[vertexOffset + static_cast<unsigned int>(sourceEdges[edge].second)]);
                    if (a == b) continue;
                    const auto found = outputEdgeIds.find(edgeKey(a, b));
                    if (found != outputEdgeIds.end()) edgeMap[edgeOffset + edge] = found->second;
                }
            }
        }
        // Yuz-kosesi verileri (UV, renk, normal) kopya sirasiyla kaynak yuz-kosesi dizisini izler;
        // atlanan yuz-koseleri bu maskeyle elenir.
        const auto faceVertexKept = [&](int copy, unsigned int faceVertex) {
            return keepFaceVertex.empty() ||
                   keepFaceVertex[static_cast<size_t>(copy) * sourceConnectCount + faceVertex] != 0;
        };
        // Maya stores per-face shading membership in mesh geometry-data object groups.
        // Preserve the stable group IDs and repeat the assigned component indices per copy.
        MFnGeometryData inputGeometry(sourceObject, &status);
        MObject sourceGeometryObject = sourceObject;
        if (status == MS::kSuccess) {
            MFnGeometryData outputGeometry(outputData, &status);
            if (status == MS::kSuccess && inputGeometry.objectGroupCount() > 0 &&
                outputGeometry.copyObjectGroups(sourceGeometryObject) == MS::kSuccess) {
                for (unsigned int groupIndex = 0; groupIndex < inputGeometry.objectGroupCount(); ++groupIndex) {
                    const unsigned int groupId = inputGeometry.objectGroup(groupIndex, &status);
                    if (status != MS::kSuccess) continue;
                    const MFn::Type componentType = inputGeometry.objectGroupType(groupId, &status);
                    if (status != MS::kSuccess) continue;
                    const MObject sourceComponent = inputGeometry.objectGroupComponent(groupId, &status);
                    if (status != MS::kSuccess || sourceComponent.isNull()) continue;
                    MFnSingleIndexedComponent sourceIndexed(sourceComponent, &status);
                    if (status != MS::kSuccess) continue;
                    MIntArray sourceElements;
                    if (sourceIndexed.getElements(sourceElements) != MS::kSuccess) continue;
                    unsigned int componentStride = 0;
                    if (componentType == MFn::kMeshPolygonComponent) componentStride = sourceFaceCount;
                    else if (componentType == MFn::kMeshEdgeComponent) componentStride = sourceEdgeCount;
                    else if (componentType == MFn::kMeshVertComponent) componentStride = sourceVertexCount;
                    else continue;
                    MFnSingleIndexedComponent outputIndexed;
                    MObject outputComponent = outputIndexed.create(componentType, &status);
                    if (status != MS::kSuccess) continue;
                    std::unordered_map<int, bool> assigned;
                    for (int copy = 0; copy < copies; ++copy) {
                        for (unsigned int element = 0; element < sourceElements.length(); ++element) {
                            const int sourceIndex = sourceElements[element];
                            int value = -1;
                            if (componentType == MFn::kMeshPolygonComponent && sourceIndex >= 0 &&
                                static_cast<unsigned int>(sourceIndex) < sourceFaceCount)
                                value = faceMap[static_cast<size_t>(copy) * sourceFaceCount + sourceIndex];
                            else if (componentType == MFn::kMeshEdgeComponent && sourceIndex >= 0 &&
                                     static_cast<unsigned int>(sourceIndex) < sourceEdgeCount)
                                value = edgeMap[static_cast<size_t>(copy) * sourceEdgeCount + sourceIndex];
                            else if (componentType == MFn::kMeshVertComponent && sourceIndex >= 0 &&
                                     static_cast<unsigned int>(sourceIndex) < sourceVertexCount)
                                value = static_cast<int>(vertexMap[static_cast<size_t>(copy) * sourceVertexCount + sourceIndex]);
                            if (value >= 0 && assigned.emplace(value, true).second)
                                outputIndexed.addElement(value);
                        }
                    }
                    outputGeometry.setObjectGroupComponent(groupId, outputComponent);
                }
            }
        }

        MStringArray uvSets;
        if (source.getUVSetNames(uvSets) == MS::kSuccess) {
            for (unsigned int setIndex = 0; setIndex < uvSets.length(); ++setIndex) {
                const MString setName = uvSets[setIndex];
                MString outputSetName = setName;
                if (setIndex > 0)
                    outputSetName = output.createUVSetDataMeshWithName(setName, &status);
                if (status != MS::kSuccess) continue;
                MFloatArray u, v;
                MIntArray uvCounts, uvIds;
                if (source.getUVs(u, v, &setName) != MS::kSuccess ||
                    source.getAssignedUVs(uvCounts, uvIds, &setName) != MS::kSuccess || u.length() == 0)
                    continue;
                MFloatArray allU, allV;
                MIntArray allCounts, allIds;
                allU.setLength(u.length() * static_cast<unsigned int>(copies));
                allV.setLength(v.length() * static_cast<unsigned int>(copies));
                if (keepFaceVertex.empty()) {
                    allCounts.setLength(uvCounts.length() * static_cast<unsigned int>(copies));
                    allIds.setLength(uvIds.length() * static_cast<unsigned int>(copies));
                }
                for (int copy = 0; copy < copies; ++copy) {
                    const unsigned int uvOffset = static_cast<unsigned int>(copy) * u.length();
                    for (unsigned int i = 0; i < u.length(); ++i) {
                        allU[uvOffset + i] = u[i];
                        allV[uvOffset + i] = v[i];
                    }
                    if (keepFaceVertex.empty()) {
                        const unsigned int faceOffset = static_cast<unsigned int>(copy) * uvCounts.length();
                        const unsigned int idOffset = static_cast<unsigned int>(copy) * uvIds.length();
                        for (unsigned int i = 0; i < uvCounts.length(); ++i) allCounts[faceOffset + i] = uvCounts[i];
                        for (unsigned int i = 0; i < uvIds.length(); ++i) allIds[idOffset + i] = uvIds[i] + uvOffset;
                        continue;
                    }
                    // Birlesme yuz atladiysa UV sayilari ve kimlikleri de atlanan yuz-koselerini elemeli.
                    const size_t faceOffset = static_cast<size_t>(copy) * sourceFaceCount;
                    unsigned int idCursor = 0, faceVertexCursor = 0;
                    for (unsigned int face = 0; face < uvCounts.length(); ++face) {
                        const int n = uvCounts[face];
                        if (face < sourceFaceCount && faceMap[faceOffset + face] >= 0) {
                            int kept = 0;
                            for (int k = 0; k < n; ++k) {
                                if (!faceVertexKept(copy, faceVertexCursor + static_cast<unsigned int>(k))) continue;
                                allIds.append(uvIds[idCursor + static_cast<unsigned int>(k)] + static_cast<int>(uvOffset));
                                ++kept;
                            }
                            allCounts.append(kept);
                        }
                        idCursor += static_cast<unsigned int>(n);
                        if (face < sourceFaceCount) faceVertexCursor += static_cast<unsigned int>(sourceCounts[face]);
                    }
                }
                output.setUVs(allU, allV, &outputSetName);
                output.assignUVs(allCounts, allIds, &outputSetName);
            }
        }

        MStringArray colorSets;
        if (source.getColorSetNames(colorSets) == MS::kSuccess) {
            for (unsigned int setIndex = 0; setIndex < colorSets.length(); ++setIndex) {
                const MString setName = colorSets[setIndex];
                MColorArray sourceColors;
                if (source.getFaceVertexColors(sourceColors, &setName) != MS::kSuccess || sourceColors.length() == 0)
                    continue;
                MColorArray colors;
                MIntArray colorIds;
                const bool filterColors = !keepFaceVertex.empty() && sourceColors.length() == sourceConnectCount;
                if (!filterColors) {
                    const unsigned int colorCount = sourceColors.length() * static_cast<unsigned int>(copies);
                    colors.setLength(colorCount);
                    colorIds.setLength(colorCount);
                }
                for (int copy = 0; copy < copies; ++copy) {
                    const unsigned int offset = static_cast<unsigned int>(copy) * sourceColors.length();
                    for (unsigned int i = 0; i < sourceColors.length(); ++i) {
                        if (filterColors) {
                            if (!faceVertexKept(copy, i)) continue;
                            colorIds.append(static_cast<int>(colors.length()));
                            colors.append(sourceColors[i]);
                            continue;
                        }
                        colors[offset + i] = sourceColors[i];
                        colorIds[offset + i] = static_cast<int>(offset + i);
                    }
                }
                const auto representation = source.getColorRepresentation(setName);
                const bool clamped = source.isColorClamped(setName);
                output.createColorSetWithNameDataMesh(setName, clamped, representation, &status);
                if (status != MS::kSuccess) continue;
                output.setSomeColors(colorIds, colors, &setName, representation);
                output.assignColors(colorIds, &setName);
            }
        }

        MIntArray normalCounts, normalIds;
        if (source.getNormalIds(normalCounts, normalIds) == MS::kSuccess) {
            MFloatVectorArray sourceNormals;
            if (source.getNormals(sourceNormals, MSpace::kObject) == MS::kSuccess) {
                bool customNormals = false;
                unsigned int normalIndex = 0;
                for (unsigned int face = 0; face < normalCounts.length(); ++face) {
                    const MFloatVector first = normalCounts[face] ? sourceNormals[normalIds[normalIndex]] : MFloatVector();
                    for (int local = 0; local < normalCounts[face]; ++local, ++normalIndex) {
                        if (local) {
                            const MFloatVector n = sourceNormals[normalIds[normalIndex]];
                            if (std::abs(n.x - first.x) > 1.0e-5f || std::abs(n.y - first.y) > 1.0e-5f ||
                                std::abs(n.z - first.z) > 1.0e-5f)
                                customNormals = true;
                        }
                    }
                }
                if (customNormals && normalIds.length() == sourceConnectCount) {
                    std::vector<MVector> normalsVec;
                    std::vector<int> faceIdsVec, vertexIdsVec;
                    normalsVec.reserve(static_cast<size_t>(sourceConnectCount) * copies);
                    faceIdsVec.reserve(static_cast<size_t>(sourceConnectCount) * copies);
                    vertexIdsVec.reserve(static_cast<size_t>(sourceConnectCount) * copies);
                    MMatrix normalTransform;
                    for (int copy = 0; copy < copies; ++copy) {
                        const MMatrix normalMatrix = normalTransform.inverse().transpose();
                        const double orientation = normalTransform.det3x3() < 0.0 ? -1.0 : 1.0;
                        const size_t faceOffset = static_cast<size_t>(copy) * sourceFaceCount;
                        const size_t vertexOffset = static_cast<size_t>(copy) * sourceVertexCount;
                        unsigned int cursor = 0;
                        for (unsigned int face = 0; face < sourceFaceCount; ++face) {
                            const int outputFace = faceMap[faceOffset + face];
                            for (int local = 0; local < sourceCounts[face]; ++local, ++cursor) {
                                if (outputFace < 0 || !faceVertexKept(copy, cursor)) continue;
                                const MFloatVector n = sourceNormals[normalIds[cursor]];
                                MVector transformed = MVector(n.x, n.y, n.z) * normalMatrix;
                                transformed *= orientation;
                                transformed.normalize();
                                normalsVec.push_back(transformed);
                                faceIdsVec.push_back(outputFace);
                                vertexIdsVec.push_back(static_cast<int>(vertexMap[
                                    vertexOffset + static_cast<unsigned int>(sourceConnects[cursor])]));
                            }
                        }
                        normalTransform *= stepMatrix;
                    }
                    if (!normalsVec.empty()) {
                        MVectorArray normals(normalsVec.data(), static_cast<unsigned int>(normalsVec.size()));
                        MIntArray faceIds(faceIdsVec.data(), static_cast<unsigned int>(faceIdsVec.size()));
                        MIntArray vertexIds(vertexIdsVec.data(), static_cast<unsigned int>(vertexIdsVec.size()));
                        output.setFaceVertexNormals(normals, faceIds, vertexIds, MSpace::kObject);
                    }
                }
            }
        }

        MIntArray smoothEdgeIds, smoothValues;
        std::vector<bool> sourceSmooth(sourceEdgeCount, false);
        for (unsigned int edge = 0; edge < sourceEdgeCount; ++edge)
            sourceSmooth[edge] = source.isEdgeSmooth(static_cast<int>(edge));
        std::map<int, bool> mergedSmooth;
        for (int copy = 0; copy < copies; ++copy) {
            for (int edge = 0; edge < source.numEdges(); ++edge) {
                const int mapped = edgeMap[static_cast<size_t>(copy) * sourceEdgeCount + edge];
                if (mapped < 0) continue;
                const bool smooth = sourceSmooth[static_cast<unsigned int>(edge)];
                auto inserted = mergedSmooth.emplace(mapped, smooth);
                if (!inserted.second) inserted.first->second = inserted.first->second && smooth;
            }
        }
        for (const auto& item : mergedSmooth) {
            smoothEdgeIds.append(item.first);
            smoothValues.append(item.second ? 1 : 0);
        }
        output.setEdgeSmoothings(smoothEdgeIds, smoothValues);

        data.outputValue(outputMesh).setMObject(outputData);
        data.setClean(plug);
        return MS::kSuccess;
    }

    MPlug passThroughToOne(const MPlug& plug) const override {
        return plug == outputMesh ? MPlug(thisMObject(), inputMesh) : MPlug();
    }
};

MObject OrangeArrayNode::inputMesh;
MObject OrangeArrayNode::outputMesh;
MObject OrangeArrayNode::count;
MObject OrangeArrayNode::relativeX;
MObject OrangeArrayNode::relativeY;
MObject OrangeArrayNode::relativeZ;
MObject OrangeArrayNode::constantX;
MObject OrangeArrayNode::constantY;
MObject OrangeArrayNode::constantZ;
MObject OrangeArrayNode::useObjectOffset;
MObject OrangeArrayNode::objectWorldMatrix;
MObject OrangeArrayNode::baseInverseMatrix;
MObject OrangeArrayNode::mergeCopies;
MObject OrangeArrayNode::mergeDistance;
}  // namespace

MStatus initializePlugin(MObject object) {
    MFnPlugin plugin(object, "Orange", "0.9.0", "Any");
    return plugin.registerNode(kTypeName, kTypeId, OrangeArrayNode::creator, OrangeArrayNode::initialize,
                               MPxNode::kDependNode);
}

MStatus uninitializePlugin(MObject object) {
    MFnPlugin plugin(object);
    return plugin.deregisterNode(kTypeId);
}
