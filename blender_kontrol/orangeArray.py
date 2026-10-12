# -*- coding: utf-8 -*-
"""Live local-space Array DG node for Maya's Python plug-in API (API 1.0)."""
from __future__ import absolute_import

import maya.OpenMaya as om
import maya.OpenMayaMPx as ompx
import math
import os
import time


TYPE_NAME = 'orangeArray'
TYPE_ID = om.MTypeId(0x0013B2A1)


def _edge_vertices(mesh_fn, edge_id):
    util = om.MScriptUtil()
    util.createFromList([0, 0], 2)
    ptr = util.asInt2Ptr()
    mesh_fn.getEdgeVertices(edge_id, ptr)
    return (om.MScriptUtil.getInt2ArrayItem(ptr, 0, 0),
            om.MScriptUtil.getInt2ArrayItem(ptr, 0, 1))


class OrangeArrayNode(ompx.MPxNode):
    input_mesh = om.MObject()
    output_mesh = om.MObject()
    count_attr = om.MObject()
    relative_x = om.MObject()
    relative_y = om.MObject()
    relative_z = om.MObject()
    constant_x = om.MObject()
    constant_y = om.MObject()
    constant_z = om.MObject()
    use_object_offset = om.MObject()
    object_world_matrix = om.MObject()
    base_inverse_matrix = om.MObject()
    merge_copies = om.MObject()
    merge_distance = om.MObject()

    @staticmethod
    def creator():
        return ompx.asMPxPtr(OrangeArrayNode())

    @staticmethod
    def initialize():
        typed = om.MFnTypedAttribute()
        OrangeArrayNode.input_mesh = typed.create('inputMesh', 'im', om.MFnData.kMesh)
        typed.setStorable(True)
        typed.setReadable(False)
        typed.setWritable(True)
        typed.setKeyable(False)
        OrangeArrayNode.addAttribute(OrangeArrayNode.input_mesh)

        OrangeArrayNode.output_mesh = typed.create('outputMesh', 'om', om.MFnData.kMesh)
        typed.setStorable(False)
        typed.setReadable(True)
        typed.setWritable(False)
        typed.setKeyable(False)
        OrangeArrayNode.addAttribute(OrangeArrayNode.output_mesh)

        numeric = om.MFnNumericAttribute()
        OrangeArrayNode.count_attr = numeric.create('count', 'cnt', om.MFnNumericData.kInt, 2)
        numeric.setMin(1)
        numeric.setKeyable(True)
        OrangeArrayNode.addAttribute(OrangeArrayNode.count_attr)

        for name, short_name, default, member in (
                ('relativeX', 'rx', 1.0, 'relative_x'), ('relativeY', 'ry', 0.0, 'relative_y'),
                ('relativeZ', 'rz', 0.0, 'relative_z'), ('constantX', 'cx', 0.0, 'constant_x'),
                ('constantY', 'cy', 0.0, 'constant_y'), ('constantZ', 'cz', 0.0, 'constant_z')):
            attr = numeric.create(name, short_name, om.MFnNumericData.kDouble, default)
            numeric.setKeyable(True)
            OrangeArrayNode.addAttribute(attr)
            setattr(OrangeArrayNode, member, attr)

        OrangeArrayNode.use_object_offset = numeric.create('useObjectOffset', 'uoo',
                                                           om.MFnNumericData.kBoolean, False)
        numeric.setKeyable(True)
        OrangeArrayNode.addAttribute(OrangeArrayNode.use_object_offset)
        matrix_attr = om.MFnMatrixAttribute()
        OrangeArrayNode.object_world_matrix = matrix_attr.create('objectWorldMatrix', 'owm')
        matrix_attr.setStorable(False)
        OrangeArrayNode.addAttribute(OrangeArrayNode.object_world_matrix)
        OrangeArrayNode.base_inverse_matrix = matrix_attr.create('baseInverseMatrix', 'bim')
        matrix_attr.setStorable(False)
        OrangeArrayNode.addAttribute(OrangeArrayNode.base_inverse_matrix)
        OrangeArrayNode.merge_copies = numeric.create('mergeCopies', 'mc', om.MFnNumericData.kBoolean, False)
        numeric.setKeyable(True)
        OrangeArrayNode.addAttribute(OrangeArrayNode.merge_copies)
        OrangeArrayNode.merge_distance = numeric.create('mergeDistance', 'md', om.MFnNumericData.kDouble, 0.001)
        numeric.setMin(0.0)
        numeric.setKeyable(True)
        OrangeArrayNode.addAttribute(OrangeArrayNode.merge_distance)

        for source in (OrangeArrayNode.input_mesh, OrangeArrayNode.count_attr,
                       OrangeArrayNode.relative_x, OrangeArrayNode.relative_y, OrangeArrayNode.relative_z,
                       OrangeArrayNode.constant_x, OrangeArrayNode.constant_y, OrangeArrayNode.constant_z,
                       OrangeArrayNode.use_object_offset, OrangeArrayNode.object_world_matrix,
                       OrangeArrayNode.base_inverse_matrix):
            OrangeArrayNode.attributeAffects(source, OrangeArrayNode.output_mesh)
        OrangeArrayNode.attributeAffects(OrangeArrayNode.merge_copies, OrangeArrayNode.output_mesh)
        OrangeArrayNode.attributeAffects(OrangeArrayNode.merge_distance, OrangeArrayNode.output_mesh)

    def compute(self, plug, data):
        if plug != self.output_mesh:
            return om.kUnknownParameter
        profile = bool(os.environ.get('ORANGE_ARRAY_PROFILE'))
        profile_started = time.perf_counter() if profile else 0.0
        profile_last = profile_started

        def mark_profile(stage):
            nonlocal profile_last
            if profile:
                now = time.perf_counter()
                print('[orangeArray profile] %s %.3f ms (total %.3f ms)' % (
                    stage, (now - profile_last) * 1000.0, (now - profile_started) * 1000.0))
                profile_last = now

        source_obj = data.inputValue(self.input_mesh).asMesh()
        node_state = om.MFnDependencyNode(self.thisMObject()).findPlug('nodeState')
        if data.inputValue(node_state).asShort() == 1:
            data.outputValue(self.output_mesh).setMObject(source_obj)
            data.setClean(plug)
            return
        output_data = om.MFnMeshData().create()
        if source_obj.isNull():
            data.outputValue(self.output_mesh).setMObject(output_data)
            data.setClean(plug)
            return

        source_fn = om.MFnMesh(source_obj)
        mark_profile('read input')
        source_points = om.MPointArray()
        source_fn.getPoints(source_points, om.MSpace.kObject)
        counts = om.MIntArray()
        connects = om.MIntArray()
        source_fn.getVertices(counts, connects)
        vertex_count = source_points.length()
        count = max(1, min(10000, data.inputValue(self.count_attr).asInt()))
        if source_points.length():
            mins = [min(getattr(source_points[i], axis) for i in range(source_points.length()))
                    for axis in ('x', 'y', 'z')]
            maxs = [max(getattr(source_points[i], axis) for i in range(source_points.length()))
                    for axis in ('x', 'y', 'z')]
            extent = tuple(maxs[i] - mins[i] for i in range(3))
        else:
            extent = (0.0, 0.0, 0.0)
        relative = (data.inputValue(self.relative_x).asDouble(), data.inputValue(self.relative_y).asDouble(),
                    data.inputValue(self.relative_z).asDouble())
        constant = (data.inputValue(self.constant_x).asDouble(), data.inputValue(self.constant_y).asDouble(),
                    data.inputValue(self.constant_z).asDouble())
        step = [extent[i] * relative[i] + constant[i] for i in range(3)]

        # Blender-style Object Offset: transform the next copy by the offset object's
        # world-space relation to the source object's local space. Relative/constant
        # translation remains composable with that matrix.
        object_offset = om.MMatrix()
        if data.inputValue(self.use_object_offset).asBool():
            object_world = data.inputValue(self.object_world_matrix).asMatrix()
            base_inverse = data.inputValue(self.base_inverse_matrix).asMatrix()
            object_offset = object_world * base_inverse
        step_transform = om.MTransformationMatrix()
        step_transform.setTranslation(om.MVector(*step), om.MSpace.kTransform)
        step_matrix = step_transform.asMatrix() * object_offset

        merge = data.inputValue(self.merge_copies).asBool()
        merge_distance = max(0.0, data.inputValue(self.merge_distance).asDouble())
        merge_enabled = merge and merge_distance > 0.0
        merge_distance_sq = merge_distance * merge_distance
        points, polygon_counts, polygon_connects = om.MPointArray(), om.MIntArray(), om.MIntArray()
        vertex_map = []
        source_face_count = counts.length()
        # face_map: kopya*F + yuz -> cikti yuz indeksi (-1: birlesme sonucu cokmus, atlandi).
        # keep_fv: her kaynak yuz-kosesi (kopya sirasiyla) ciktida kaldi mi; None = hepsi kaldi.
        face_map = []
        keep_fv = [] if merge_enabled else None
        cells = {}
        copy_matrix = om.MMatrix()
        for copy_index in range(count):
            for index in range(source_points.length()):
                point = source_points[index] * copy_matrix
                if merge_enabled:
                    cell = (int(math.floor(point.x / merge_distance)),
                            int(math.floor(point.y / merge_distance)),
                            int(math.floor(point.z / merge_distance)))
                    found = None
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            for dz in (-1, 0, 1):
                                for candidate in cells.get((cell[0] + dx, cell[1] + dy, cell[2] + dz), ()):
                                    delta = point - points[candidate]
                                    if delta * delta <= merge_distance_sq:
                                        found = candidate
                                        break
                                if found is not None:
                                    break
                            if found is not None:
                                break
                    if found is None:
                        found = points.length()
                        points.append(point)
                        cells.setdefault(cell, []).append(found)
                    vertex_map.append(found)
                else:
                    vertex_map.append(points.length())
                    points.append(point)
            vertex_offset = copy_index * vertex_count
            if not merge_enabled:
                face_offset = copy_index * source_face_count
                for index in range(source_face_count):
                    polygon_counts.append(counts[index])
                    face_map.append(face_offset + index)
                for index in range(connects.length()):
                    polygon_connects.append(vertex_map[connects[index] + vertex_offset])
            else:
                # Birlesme mesafesi bir kenardan uzunsa bir yuz ayni koseyi iki kez gosterebilir;
                # MFnMesh.create bunu reddeder. Ardisik tekrarlari at, 3 koseden az kalan ya da
                # hala tekrarlayan (papyon) yuzleri tamamen atla.
                cursor = 0
                for index in range(source_face_count):
                    n = counts[index]
                    ids = [vertex_map[connects[cursor + k] + vertex_offset] for k in range(n)]
                    kept = [k for k in range(n) if ids[k] != ids[(k + 1) % n]]
                    kept_ids = [ids[k] for k in kept]
                    if len(kept_ids) < 3 or len(set(kept_ids)) != len(kept_ids):
                        kept = []
                    kept_set = set(kept)
                    keep_fv.extend(k in kept_set for k in range(n))
                    if kept:
                        face_map.append(polygon_counts.length())
                        polygon_counts.append(len(kept))
                        for vertex_id in kept_ids:
                            polygon_connects.append(vertex_id)
                    else:
                        face_map.append(-1)
                    cursor += n
            copy_matrix = copy_matrix * step_matrix

        mark_profile('build topology arrays')
        if not polygon_counts.length():
            # Butun yuzler birlesmeyle coktu: MFnMesh.create yuzsuz mesh'i reddeder, bos mesh dondur.
            data.outputValue(self.output_mesh).setMObject(output_data)
            data.setClean(plug)
            return
        output_fn = om.MFnMesh()
        output_fn.create(points.length(), polygon_counts.length(), points, polygon_counts, polygon_connects, output_data)
        mark_profile('create output mesh')

        # Kenar numaralari MFnMesh.create'in uretimine baglidir ve duzenlenmis bir mesh'te kaynak
        # numaralariyla ortusmez; bu yuzden birlesme kapaliyken de kose cifti -> kenar esleme kurulur.
        source_edge_count = source_fn.numEdges()
        output_edge_ids = {}
        for edge_id in range(output_fn.numEdges()):
            a, b = _edge_vertices(output_fn, edge_id)
            output_edge_ids[(a, b) if a < b else (b, a)] = edge_id
        source_edges = [_edge_vertices(source_fn, edge_id) for edge_id in range(source_edge_count)]
        edge_map = [-1] * (count * source_edge_count)
        for copy_index in range(count):
            vertex_offset = copy_index * vertex_count
            for edge_id, (a, b) in enumerate(source_edges):
                a, b = vertex_map[vertex_offset + a], vertex_map[vertex_offset + b]
                if a != b:
                    edge_map[copy_index * source_edge_count + edge_id] = output_edge_ids.get((a, b) if a < b else (b, a), -1)

        # Yuz-kosesi verileri (UV, renk, normal) kopya sirasiyla kaynak yuz-kosesi dizisini izler;
        # atlanan yuz-koseleri bu maskeyle elenir.
        fv_total = connects.length()

        def face_vertex_kept(copy_index, fv_index):
            return keep_fv is None or keep_fv[copy_index * fv_total + fv_index]

        # Keep secondary UV sets on mesh data (the regular createUVSetWithName API only works on DAG shapes).
        # Keep every Maya UV set and face-vertex assignment for each generated copy.
        try:
            uv_sets = []
            source_fn.getUVSetNames(uv_sets)
            for set_index, uv_set in enumerate(uv_sets):
                if set_index:
                    output_fn.createUVSetDataMeshWithName(uv_set)
                us, vs, uv_counts, uv_ids = om.MFloatArray(), om.MFloatArray(), om.MIntArray(), om.MIntArray()
                source_fn.getUVs(us, vs, uv_set)
                source_fn.getAssignedUVs(uv_counts, uv_ids, uv_set)
                if not us.length():
                    continue
                all_u, all_v, all_counts, all_ids = om.MFloatArray(), om.MFloatArray(), om.MIntArray(), om.MIntArray()
                for copy_index in range(count):
                    for index in range(us.length()):
                        all_u.append(us[index])
                        all_v.append(vs[index])
                    uv_offset = copy_index * us.length()
                    face_offset = copy_index * source_face_count
                    id_cursor = 0
                    fv_cursor = 0
                    for index in range(uv_counts.length()):
                        n = uv_counts[index]
                        if face_map[face_offset + index] >= 0:
                            kept = 0
                            for k in range(n):
                                if face_vertex_kept(copy_index, fv_cursor + k):
                                    all_ids.append(uv_ids[id_cursor + k] + uv_offset)
                                    kept += 1
                            all_counts.append(kept)
                        id_cursor += n
                        fv_cursor += counts[index]
                output_fn.setUVs(all_u, all_v, uv_set)
                output_fn.assignUVs(all_counts, all_ids, uv_set)
        except RuntimeError:
            # A malformed/unsupported custom UV set does not invalidate the mesh result.
            pass
        mark_profile('copy UV sets')

        # Maya color sets and hard/split normals are face-vertex data, so duplicate their assignments
        # alongside topology instead of leaving only the first copy shaded correctly.
        color_stage = 'list sets'
        try:
            color_sets = []
            source_fn.getColorSetNames(color_sets)
            for color_set in color_sets:
                color_stage = 'read %s' % color_set
                source_colors = om.MColorArray()
                source_fn.getFaceVertexColors(source_colors, color_set)
                if not source_colors.length():
                    continue
                colors = om.MColorArray()
                filter_colors = keep_fv is not None and source_colors.length() == fv_total
                for copy_index in range(count):
                    for color_index in range(source_colors.length()):
                        if not filter_colors or keep_fv[copy_index * fv_total + color_index]:
                            colors.append(source_colors[color_index])
                color_stage = 'create %s' % color_set
                output_fn.createColorSetWithNameDataMesh(
                    color_set, source_fn.isColorClamped(color_set), source_fn.getColorRepresentation(color_set))
                color_stage = 'set colors %s' % color_set
                color_ids = om.MIntArray()
                for color_index in range(colors.length()):
                    color_ids.append(color_index)
                output_fn.setSomeColors(color_ids, colors, color_set)
                color_stage = 'assign %s' % color_set
                output_fn.assignColors(color_ids, color_set)
        except RuntimeError as exc:
            om.MGlobal.displayWarning('orangeArray color-set copy skipped at %s: %s' % (color_stage, exc))
        mark_profile('copy color sets')

        try:
            normal_counts, normal_ids = om.MIntArray(), om.MIntArray()
            source_fn.getNormalIds(normal_counts, normal_ids)
            source_normal_data = om.MFloatVectorArray()
            source_fn.getNormals(source_normal_data, om.MSpace.kObject)
            # MFnMesh.create already creates the correct flat face normals. Detect actual within-face
            # normal variation by comparing values, because Maya may assign separate IDs to equal normals.
            needs_custom_normals = False
            normal_index = 0
            for face_index in range(normal_counts.length()):
                first = source_normal_data[normal_ids[normal_index]] if normal_counts[face_index] else None
                for local_index in range(normal_counts[face_index]):
                    if local_index:
                        normal = source_normal_data[normal_ids[normal_index]]
                        if (abs(normal.x - first.x) > 1e-5 or abs(normal.y - first.y) > 1e-5
                                or abs(normal.z - first.z) > 1e-5):
                            needs_custom_normals = True
                    normal_index += 1
            if needs_custom_normals:
                normals, normal_face_ids, normal_vertex_ids = om.MVectorArray(), om.MIntArray(), om.MIntArray()
                normal_transform = om.MMatrix()
                for copy_index in range(count):
                    normal_matrix = normal_transform.inverse().transpose()
                    orientation = -1.0 if normal_transform.det3x3() < 0.0 else 1.0
                    vertex_offset = copy_index * vertex_count
                    face_offset = copy_index * source_face_count
                    connect_offset = 0
                    for face_index in range(source_face_count):
                        output_face = face_map[face_offset + face_index]
                        for local_index in range(counts[face_index]):
                            fv_index = connect_offset + local_index
                            if output_face < 0 or not face_vertex_kept(copy_index, fv_index):
                                continue
                            normal = source_normal_data[normal_ids[fv_index]]
                            transformed = om.MVector(normal.x, normal.y, normal.z) * normal_matrix
                            transformed *= orientation
                            transformed.normalize()
                            normals.append(transformed)
                            normal_face_ids.append(output_face)
                            normal_vertex_ids.append(vertex_map[vertex_offset + connects[fv_index]])
                        connect_offset += counts[face_index]
                    normal_transform = normal_transform * step_matrix
                output_fn.setFaceVertexNormals(normals, normal_face_ids, normal_vertex_ids, om.MSpace.kObject)
        except RuntimeError:
            # Maya can reject custom normals on malformed meshes; topology remains available.
            pass
        mark_profile('copy normals')

        # Shading-engine membership travels as geometry-data object groups. Copy them after
        # setting UVs, colors and normals so mesh-data edits cannot discard the memberships.
        data_stage = 'copy object groups'
        try:
            source_geometry = om.MFnGeometryData(source_obj)
            output_geometry = om.MFnGeometryData(output_data)
            if source_geometry.objectGroupCount() > 0:
                output_geometry.copyObjectGroups(source_obj)
            for group_index in range(source_geometry.objectGroupCount()):
                group_id = source_geometry.objectGroup(group_index)
                component_type = source_geometry.objectGroupType(group_id)
                source_component = source_geometry.objectGroupComponent(group_id)
                if source_component.isNull():
                    continue
                source_indexed = om.MFnSingleIndexedComponent(source_component)
                source_elements = om.MIntArray()
                source_indexed.getElements(source_elements)
                if component_type == om.MFn.kMeshPolygonComponent:
                    stride = source_face_count
                elif component_type == om.MFn.kMeshEdgeComponent:
                    stride = source_edge_count
                elif component_type == om.MFn.kMeshVertComponent:
                    stride = vertex_count
                else:
                    continue
                output_indexed = om.MFnSingleIndexedComponent()
                output_component = output_indexed.create(component_type)
                assigned = set()
                for copy_index in range(count):
                    for element_index in range(source_elements.length()):
                        source_element = source_elements[element_index]
                        if source_element < 0 or source_element >= stride:
                            continue
                        if component_type == om.MFn.kMeshPolygonComponent:
                            value = face_map[copy_index * stride + source_element]
                        elif component_type == om.MFn.kMeshEdgeComponent:
                            value = edge_map[copy_index * stride + source_element]
                        else:
                            value = vertex_map[copy_index * stride + source_element]
                        if value >= 0 and value not in assigned:
                            output_indexed.addElement(value)
                            assigned.add(value)
                output_geometry.setObjectGroupComponent(group_id, output_component)

            # Coalesce edge smoothing on seam edges which became one edge after welding.
            data_stage = 'copy edge smoothness'
            source_smooth = [bool(source_fn.isEdgeSmooth(edge_id)) for edge_id in range(source_edge_count)]
            edge_smooth = {}
            for copy_index in range(count):
                for edge_id in range(source_edge_count):
                    mapped = edge_map[copy_index * source_edge_count + edge_id]
                    if mapped >= 0:
                        value = source_smooth[edge_id]
                        edge_smooth[mapped] = edge_smooth.get(mapped, True) and value
            if edge_smooth:
                edge_ids, edge_values = om.MIntArray(), om.MIntArray()
                for edge_id, smooth in sorted(edge_smooth.items()):
                    edge_ids.append(edge_id)
                    edge_values.append(1 if smooth else 0)
                output_fn.setEdgeSmoothings(edge_ids, edge_values)
                output_fn.cleanupEdgeSmoothing()

        except RuntimeError as exc:
            om.MGlobal.displayWarning('orangeArray mesh metadata skipped at %s: %s' % (data_stage, exc))

        data.outputValue(self.output_mesh).setMObject(output_data)
        data.setClean(plug)
        mark_profile('finish')

    def passThroughToOne(self, plug):
        if plug == self.output_mesh:
            return om.MPlug(self.thisMObject(), self.input_mesh)
        return om.MPlug()


def initializePlugin(plugin_object):
    plugin = ompx.MFnPlugin(plugin_object, 'Orange', '0.9.0', 'Any')
    plugin.registerNode(TYPE_NAME, TYPE_ID, OrangeArrayNode.creator, OrangeArrayNode.initialize,
                        ompx.MPxNode.kDependNode)


def uninitializePlugin(plugin_object):
    ompx.MFnPlugin(plugin_object).deregisterNode(TYPE_ID)
