# -*- coding: utf-8 -*-
"""Edit modu mesh islemleri (extrude, bevel, merge, split, normal, UV menusu ...)."""
from __future__ import absolute_import, division, print_function

import math

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om

from .core import _filter, _msg, _warn
from .i18n import _t
from .util import (COMP_SUFFIX, _comps, _deferred, _face_normal, _mesh_fn, _objs, _ranges, _sel, _shape_type,
    popup, undoable)
from .ui import pie
from .editmode import current_comp, enter_edit, exit_edit, in_edit, select_mode
from .cursor import cursor_pos
from .anim import insert_key
from .modal import _with_chunk, start_modal
from .valuemodal import _start_value_modal
from .slide import edge_slide


# ---------------------------------------------------------------- silme
def delete_objects():
    objs = _objs()
    if objs:
        cmds.delete(objs)
        _msg(_t('%d obje silindi') % len(objs))


def delete_verts():
    faces = cmds.polyListComponentConversion(_comps('vertex'), toFace=True)
    if faces:
        cmds.delete(faces)


def delete_edges():
    faces = cmds.polyListComponentConversion(_comps('edge'), toFace=True)
    if faces:
        cmds.delete(faces)


def delete_faces():
    faces = cmds.polyListComponentConversion(_sel(), toFace=True, internal=True)
    if faces:
        cmds.delete(faces)


def dissolve():
    kind = current_comp()
    if kind == 'vertex' and _comps('vertex'):
        cmds.polyDelVertex(_comps('vertex'))
    elif kind == 'edge' and _comps('edge'):
        cmds.polyDelEdge(_comps('edge'), cleanVertices=True)
    elif _comps('face'):
        edges = cmds.polyListComponentConversion(_comps('face'), toEdge=True, internal=True)
        if edges:
            cmds.polyDelEdge(edges, cleanVertices=True)


def delete_by_mode():
    if not in_edit():
        delete_objects()
        return
    {'vertex': delete_verts, 'edge': delete_edges, 'face': delete_faces}[current_comp()]()


def delete_menu():
    if not in_edit():
        undoable(delete_objects)()
        return
    popup(_t('Sil'), [(_t('&Köşeler'), delete_verts), (_t('&Kenarlar'), delete_edges),
                  (_t('&Yüzler'), delete_faces), None, (_t('&Erit (Dissolve)'), dissolve),
                  (_t('&Sınırlı erit (Limited Dissolve)'), lambda: limited_dissolve()),
                  (_t('Kenar &halkaları (Edge Loops)'), lambda: delete_edge_loops()),
                  (_t('&Collapse'), lambda: collapse())])


def extrude_faces(together=True, attr='localTranslateZ'):
    faces = _comps('face')
    if not faces:
        _msg(_t('Extrude için yüz seç (3)'))
        return
    normal = _face_normal(faces) or om.MVector(0, 1, 0)
    nodes = cmds.polyExtrudeFacet(faces, keepFacesTogether=together)
    start_modal('attr_axis', nodes=nodes, attr=attr, axis=normal)


def extrude_along_normals():
    """Alt+E > Along Normals: her kose kendi normali boyunca (polyExtrudeFacet.thickness)."""
    extrude_faces(together=True, attr='thickness')


def extrude_individual():
    """Alt+E > Individual Faces."""
    extrude_faces(together=False)


def extrude_edges():
    edges = _comps('edge')
    if not edges:
        _msg(_t('Extrude için kenar seç (2)'))
        return
    cmds.polyExtrudeEdge(edges, keepFacesTogether=True)
    start_modal('move', keep_undo=True)


def extrude_vertices():
    """Kose extrude kapali: Blender'daki gibi tel kenar Maya mesh'inde olamaz,
    Maya'nin kose extrude'u da ust uste kose / sifir alanli yuz birakiyordu."""
    _msg(_t('Köşe extrude yok: kenar (2) ya da yüz (3) seçip E kullan'))


def extrude():
    if not in_edit():
        _msg(_t('Extrude için Tab ile edit moduna gir'))
        return
    kind = current_comp()
    if kind == 'face' and _comps('face'):
        extrude_faces()
    elif kind == 'edge' and _comps('edge'):
        extrude_edges()
    elif kind == 'vertex' and _comps('vertex'):
        extrude_vertices()
    else:
        _msg(_t('Önce bir şey seç'))


def extrude_menu():
    """Alt+E: Blender extrude menusu."""
    if not in_edit():
        _msg(_t('Extrude için Tab ile edit moduna gir'))
        return
    popup(_t('Extrude (Alt+E)'), [
        (_t('&Yüzleri extrude (E)'), lambda: _with_chunk(extrude_faces)()),
        (_t('&Normaller boyunca (Along Normals)'), lambda: _with_chunk(extrude_along_normals)()),
        (_t('&Tek tek yüzler (Individual)'), lambda: _with_chunk(extrude_individual)()),
        None,
        (_t('&Kenarları extrude'), lambda: _with_chunk(extrude_edges)()),
    ])


def _toggle_attr(attr):
    def run(node):
        plug = '%s.%s' % (node, attr)
        cmds.setAttr(plug, not cmds.getAttr(plug))
    return run


def _cycle_attr(attr, values):
    def run(node):
        plug = '%s.%s' % (node, attr)
        cur = cmds.getAttr(plug)
        nxt = values[(values.index(cur) + 1) % len(values)] if cur in values else values[0]
        cmds.setAttr(plug, nxt)
        _msg(_t('%s: %s') % (attr, nxt))
    return run


def inset_or_key():
    if not in_edit():
        insert_key()
        return
    faces = _comps('face')
    if not faces:
        _msg(_t('Inset için yüz seç (3)'))
        return
    nodes = cmds.polyExtrudeFacet(faces, keepFacesTogether=True, offset=0)
    start_modal('attr_dist', nodes=nodes, attr='offset',
                keys={'i': _toggle_attr('keepFacesTogether')},
                key_hints=[_t('<b>I</b> tek tek (individual)')])


BEVEL_KEYS = {'p': _cycle_attr('depth', [1.0, 0.5, 0.0, -0.5, -1.0]),
              'm': _cycle_attr('mitering', [0, 1, 2, 3, 4]),
              'c': _toggle_attr('chamfer')}
BEVEL_HINTS = ['<b>P</b> profil', '<b>M</b> köşe birleşimi (miter)', '<b>C</b> chamfer']


def _bevel_comps(comps):
    nodes = cmds.polyBevel3(comps, offsetAsFraction=False, offset=0.0, segments=1,
                            mitering=0, chamfer=True)
    start_modal('attr_dist', nodes=nodes, attr='offset', wheel_attr='segments',
                keys=BEVEL_KEYS, key_hints=BEVEL_HINTS)


def bevel():
    if not in_edit():
        return
    comps = _comps('edge') or _comps('face') or _comps('vertex')
    if not comps:
        _msg(_t('Bevel için kenar seç (2)'))
        return
    _bevel_comps(comps)


def bevel_vertices():
    """Shift+Ctrl+B: kose bevel."""
    if not in_edit():
        return
    verts = _comps('vertex') or cmds.polyListComponentConversion(_sel(), toVertex=True)
    if not verts:
        _msg(_t('Köşe bevel için köşe seç (1)'))
        return
    _bevel_comps(verts)


def knife():
    mel.eval('MultiCutTool')


def fill():
    if _comps('edge'):
        try:
            cmds.polyBridgeEdge(_comps('edge'), divisions=0)
        except Exception:
            cmds.polyCloseBorder(_comps('edge'))
        return
    verts = cmds.ls(orderedSelection=True, flatten=True) or []
    verts = [v for v in verts if '.vtx[' in v]
    if len(verts) == 2:
        cmds.polyConnectComponents(verts)
    elif len(verts) >= 3:
        obj = verts[0].split('.')[0]
        ids = [int(v.split('[')[1].rstrip(']')) for v in verts]
        cmds.polyAppendVertex(obj, append=ids)
    else:
        _msg(_t('Doldurmak için kenar ya da köşe seç'))


def connect_verts():
    if _comps('vertex'):
        cmds.polyConnectComponents(_comps('vertex'))


def fill_beauty():
    """Alt+F: sinir kenarlarini kapat ve ucgenle (Blender 'Fill')."""
    edges = _comps('edge') or cmds.polyListComponentConversion(_comps('vertex'), toEdge=True, internal=True)
    if not edges:
        _msg(_t('Doldurmak için sınır kenarları seç'))
        return
    obj = cmds.ls(edges[0].split('.')[0], long=True)[0]
    before = cmds.polyEvaluate(obj, face=True)
    cmds.polyCloseBorder(edges)
    after = cmds.polyEvaluate(obj, face=True)
    if after > before:
        new_faces = '%s.f[%d:%d]' % (obj, before, after - 1)
        cmds.polyTriangulate(new_faces)
        cmds.select(new_faces, replace=True)


def _merge_to(point):
    """Secili koseleri tek koseye indirip o noktaya tasi."""
    verts = cmds.polyListComponentConversion(_sel(), toVertex=True)
    if not verts or point is None:
        return
    cmds.move(point.x, point.y, point.z, verts, absolute=True, worldSpace=True)
    cmds.polyMergeVertex(verts, distance=0.0001)


def _ordered_vertex_point(first):
    ordered = [c for c in (cmds.ls(orderedSelection=True, flatten=True) or []) if '.vtx[' in c]
    if not ordered:
        return None
    v = ordered[0] if first else ordered[-1]
    return om.MPoint(*cmds.xform(v, q=True, worldSpace=True, translation=True))


def collapse():
    """Blender 'Collapse': her bagli parcayi kendi merkezinde birlestir."""
    edges = _comps('edge') or cmds.polyListComponentConversion(
        _comps('face') or _comps('vertex'), toEdge=True, internal=True)
    if edges:
        cmds.polyCollapseEdge(edges)
    else:
        _msg(_t('Collapse için kenar / yüz seç'))


def merge_menu():
    from .objects import collection_menu  # dongusel import: cagri aninda
    if not in_edit():
        collection_menu()   # Blender: obje modunda M = Move to Collection
        return

    def by_distance():
        verts = cmds.polyListComponentConversion(_sel(), toVertex=True)
        if verts:
            before = cmds.polyEvaluate(verts[0].split('.')[0], vertex=True)
            cmds.polyMergeVertex(verts, distance=0.001)
            after = cmds.polyEvaluate(cmds.ls(sl=True, objectsOnly=True)[0], vertex=True)
            _msg(_t('%d köşe silindi') % (before - after))
    popup(_t('Birleştir (Merge)'), [
        (_t('&Merkezde'), lambda: mel.eval('MergeToCenter')),
        (_t('&İmleçte (At Cursor)'), lambda: _merge_to(cursor_pos())),
        (_t('&Collapse'), collapse),
        (_t('İl&k seçilende (At First)'), lambda: _merge_to(_ordered_vertex_point(True))),
        (_t('&Son seçilende (At Last)'), lambda: _merge_to(_ordered_vertex_point(False))),
        None,
        (_t('Mesafeye &göre'), by_distance),
    ])


def split_selection():
    """Y / Alt+M: secimi mesh icinde ayir ama tasima (Blender Split)."""
    if _comps('face'):
        cmds.polyChipOff(_comps('face'), keepFacesTogether=True, duplicate=False)
    elif _comps('edge') or _comps('vertex'):
        mel.eval('DetachComponent')
    else:
        _msg(_t('Ayırmak için bir şey seç'))


def split_menu():
    popup(_t('Ayır (Split)'), [
        (_t('&Seçim'), split_selection),
        (_t('Yüzleri &kenarlardan ayır'), lambda: cmds.polySplitEdge(
            _comps('edge') or cmds.polyListComponentConversion(_comps('face'), toEdge=True, internal=True))),
        (_t('Yüz && kenarları &köşelerden ayır'), lambda: cmds.polySplitVertex(
            _comps('vertex') or cmds.polyListComponentConversion(_sel(), toVertex=True))),
    ])


def separate_by_material():
    """P > Materyale gore: her shading engine kendi objesi olsun."""
    obj = (cmds.ls(hilite=True, long=True) or _objs() or [None])[0]
    if not obj:
        return
    groups = []
    for se in cmds.ls(type='shadingEngine') or []:
        members = cmds.ls(cmds.sets(se, q=True) or [], long=True)
        faces = [m for m in cmds.ls(cmds.polyListComponentConversion(members, toFace=True) or [], long=True)
                 if m.split('.')[0] == obj]
        if faces:
            groups.append(faces)
    if len(groups) < 2:
        _msg(_t('Bu objede tek materyal var'))
        return
    if in_edit():
        exit_edit()
    for faces in groups[1:]:
        cmds.polyChipOff(faces, keepFacesTogether=True, duplicate=False)
    cmds.polySeparate(obj)


def separate_menu():
    popup(_t('Ayır'), [
        (_t('&Seçimi ayır'), lambda: mel.eval('ExtractFace')),
        (_t('&Materyale göre'), separate_by_material),
        (_t('&Gevşek parçalara göre'), lambda: cmds.polySeparate(cmds.ls(hilite=True) or _objs())),
    ])


def _normal_targets():
    return _comps('face') or cmds.ls(hilite=True) or _objs()


def recalc_normals():
    targets = _normal_targets()
    if targets:
        cmds.polyNormal(targets, normalMode=2, userNormalMode=0)


def recalc_normals_inside():
    targets = _normal_targets()
    if targets:
        cmds.polyNormal(targets, normalMode=2, userNormalMode=0)
        cmds.polyNormal(targets, normalMode=0, userNormalMode=0)


def flip_normals():
    targets = _normal_targets()
    if targets:
        cmds.polyNormal(targets, normalMode=0, userNormalMode=0)


def normals_menu():
    """Alt+N: Blender normals menusu."""
    popup(_t('Normaller (Alt+N)'), [
        (_t('&Çevir (Flip)'), flip_normals),
        (_t('&Dışa doğru hesapla (Shift+N)'), recalc_normals),
        (_t('&İçe doğru hesapla (Shift+Ctrl+N)'), recalc_normals_inside),
        None,
        (_t('Yüzlerden ayarla / kilidi aç (&Set from Faces)'),
         lambda: cmds.polyNormalPerVertex(_normal_targets(), unFreezeNormal=True)),
        (_t('&Ortala (Average)'), lambda: cmds.polyAverageNormal(_normal_targets())),
        (_t('&Yumuşak gölgele (Shade Smooth)'), lambda: shade_smooth()),
        (_t('Dü&z gölgele (Shade Flat)'), lambda: shade_flat()),
    ])


def toggle_soft_select():
    state = not cmds.softSelect(q=True, softSelectEnabled=True)
    cmds.softSelect(edit=True, softSelectEnabled=state)
    _msg(_t('Proportional (Soft Select): %s') % (_t('açık  -  yarıçap: B + sürükle') if state else _t('kapalı')))


# ---------------------------------------------------------------- 2. asama komutlari
def rip():
    """V: koseleri/kenarlari ayir ve tasi."""
    if not in_edit() or not (_comps('vertex') or _comps('edge')):
        _msg(_t('Rip için köşe ya da kenar seç'))
        return
    cmds.undoInfo(openChunk=True, chunkName='blender_rip')
    try:
        mel.eval('DetachComponent')
    except Exception as exc:
        _warn(_t('rip: %s') % exc)
    start_modal('move', keep_undo=True)
    filt = _filter()
    if not (filt and filt.modal):
        cmds.undoInfo(closeChunk=True)


def hide_components(unselected=False):
    comps = _sel()
    if unselected:
        objs = cmds.ls(hilite=True, long=True)
        kind = current_comp()
        everything = [o + COMP_SUFFIX[kind] for o in objs]
        cmds.select(everything, replace=True)
        cmds.select(comps, deselect=True)
    try:
        mel.eval('toggleVisibilityAndKeepSelection 0')
    except Exception:
        cmds.hide(cmds.ls(sl=True))
    cmds.select(clear=True)


def edge_menu():
    def sharp(on):
        cmds.polySoftEdge(_comps('edge'), angle=0 if on else 180)

    def crease(value):
        cmds.polyCrease(_comps('edge'), value=value)

    popup(_t('Kenar (Ctrl+E)'), [
        (_t('&Köprü (Bridge)'), lambda: cmds.polyBridgeEdge(_comps('edge'), divisions=0)),
        (_t('&Böl (Subdivide)'), lambda: cmds.polySubdivideEdge(_comps('edge'), divisions=1)),
        (_t('Kenar &kaydır (Slide, G G)'), lambda: _deferred(edge_slide)),
        (_t('&Ofset kenar halkası'), lambda: mel.eval('OffsetEdgeLoopTool')),
        (_t('Kenarı &döndür (Rotate)'), lambda: cmds.polySpinEdge(_comps('edge'), offset=1)),
        None,
        (_t('Dikiş işaretle (&Mark Seam / UV kes)'), lambda: cmds.polyMapCut(_comps('edge'))),
        (_t('Dikişi kaldır (Clear Seam / UV dik)'), lambda: cmds.polyMapSew(_comps('edge'))),
        (_t('&Sert yap (Mark Sharp)'), lambda: sharp(True)),
        (_t('Yumuşak yap (Clear Sharp)'), lambda: sharp(False)),
        (_t('&Crease (1)'), lambda: crease(1.0)),
        (_t('Crease kaldır'), lambda: crease(0.0)),
        None,
        (_t('Kenar &loop\'unu sil (Dissolve)'), lambda: cmds.polyDelEdge(_comps('edge'), cleanVertices=True)),
    ])


def vertex_menu():
    popup(_t('Köşe (Ctrl+V)'), [
        (_t('&Bağla (Connect, J)'), connect_verts),
        (_t('&Ayır (Rip, V)'), rip),
        (_t('Merkezde &birleştir'), lambda: mel.eval('MergeToCenter')),
        (_t('&Yumuşat (Smooth Vertices)'), lambda: cmds.polyAverageVertex(_comps('vertex'), iterations=1)),
        (_t('&Bevel köşe'), lambda: cmds.polyBevel3(_comps('vertex'), offset=0.1, segments=1)),
        (_t('Dairesel yap (&Circularize)'), lambda: cmds.polyCircularize(_sel())),
    ])


def face_menu():
    popup(_t('Yüz (Ctrl+F)'), [
        (_t('&Extrude (E)'), lambda: _with_chunk(extrude)()),
        (_t('&Inset (I)'), lambda: _with_chunk(inset_or_key)()),
        (_t('&Poke (merkeze üçgen)'), lambda: cmds.polyPoke(_comps('face'))),
        (_t('Üç&gene çevir (Ctrl+T)'), triangulate),
        (_t('&Dörtgene çevir (Alt+J)'), quadrangulate),
        (_t('&Böl (Subdivide)'), lambda: cmds.polySubdivideFacet(_comps('face'), divisions=1)),
        (_t('Kalınlık ver (&Solidify)'), lambda: cmds.polyExtrudeFacet(_comps('face'), keepFacesTogether=True,
                                                                   thickness=0.1)),
        None,
        (_t('&Kopyala (Duplicate)'), lambda: mel.eval('DuplicateFace')),
        (_t('Ay&ır (Extract)'), lambda: mel.eval('ExtractFace')),
        (_t('Deliği doldur (&Fill Hole)'), lambda: mel.eval('FillHole')),
        (_t('&Grid Fill (dörtgen ızgara)'), grid_fill),
        (_t('Mesh &aynala (Mirror modifier gibi)...'), lambda: _deferred(mesh_mirror_menu)),
        None,
        (_t('Yumuşak gölgele (Shade Smooth)'), shade_smooth),
        (_t('Düz gölgele (Shade Flat)'), shade_flat),
        (_t('Normalleri çevir (&Flip)'), flip_normals),
    ])


# ---------------------------------------------------------------- Grid Fill (Ctrl+F menusu, F3)
def _boundary_loop(edges):
    """Secili kenarlardan kapali sinir halkasi: (obje, [kose sirasi]) ya da (obje, None)."""
    flat = cmds.ls(edges, flatten=True, long=True)
    objs = set(e.split('.')[0] for e in flat)
    if len(objs) != 1:
        return None, None
    obj = objs.pop()
    fn, dag = _mesh_fn(obj)
    it = om.MItMeshEdge(dag)
    adj = {}
    for e in flat:
        eid = int(e.split('[')[-1].rstrip(']'))
        it.setIndex(eid)
        if it.numConnectedFaces() != 1:
            return obj, None          # ic kenar: delik siniri degil
        a, b = fn.getEdgeVertices(eid)
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    if not adj or any(len(v) != 2 for v in adj.values()):
        return obj, None
    start = min(adj)
    loop, prev, cur = [start], None, start
    while True:
        nxt = [v for v in adj[cur] if v != prev]
        if not nxt or nxt[0] == start:
            break
        prev, cur = cur, nxt[0]
        loop.append(cur)
        if len(loop) > len(adj):
            return obj, None
    return obj, (loop if len(loop) == len(adj) else None)


def _coons(bottom, right, top, left):
    """Dort kenar egrisinden (dunya MPoint listeleri) Coons yamasi: grid[i][j], i=0..m, j=0..n.
    bottom[i]=G(i,0), top[i]=G(i,n), left[j]=G(0,j), right[j]=G(m,j)."""
    m, n = len(bottom) - 1, len(left) - 1
    p00, pm0, p0n, pmn = (om.MVector(bottom[0]), om.MVector(bottom[m]), om.MVector(top[0]), om.MVector(top[m]))
    grid = []
    for i in range(m + 1):
        u = i / float(m)
        col = []
        for j in range(n + 1):
            v = j / float(n)
            lc = om.MVector(bottom[i]) * (1 - v) + om.MVector(top[i]) * v
            ld = om.MVector(left[j]) * (1 - u) + om.MVector(right[j]) * u
            b = p00 * ((1 - u) * (1 - v)) + pm0 * (u * (1 - v)) + p0n * ((1 - u) * v) + pmn * (u * v)
            col.append(om.MPoint(lc + ld - b))
        grid.append(col)
    return grid


def grid_fill(span=None, offset=0):
    """Blender Grid Fill: secili kapali sinir halkasini dortgen izgarayla doldur.

    Halka 2 * (span + n) koseden olusmali (cift sayi). Yeni yuzler mesh'e birlestirilir (Ctrl+J gibi gecmis
    birlesir). offset: izgaranin kosesinin halkadaki baslangic kaydirmasi (Blender 'Offset')."""
    edges = _comps('edge')
    if not edges:
        _msg(_t('Grid Fill için kapalı bir sınır halkası seç (kenar modu)'))
        return None
    obj, loop = _boundary_loop(edges)
    if not loop:
        _msg(_t('Grid Fill: seçim tek, kapalı bir delik sınırı olmalı'))
        return None
    count = len(loop)
    if count % 2 or count < 6:
        _msg(_t('Grid Fill çift sayıda (en az 6) sınır kenarı ister: %d') % count)
        return None
    half = count // 2
    m = max(1, min(half - 1, span or max(1, count // 4)))
    n = half - m
    loop = loop[offset % count:] + loop[:offset % count]
    fn, dag = _mesh_fn(obj)
    pts = [fn.getPoint(v, om.MSpace.kWorld) for v in loop]
    bottom = pts[0:m + 1]
    right = pts[m:m + n + 1]
    top = list(reversed(pts[m + n:2 * m + n + 1]))
    left = list(reversed(pts[2 * m + n:] + pts[:1]))
    grid = _coons(bottom, right, top, left)
    # sarma yonu: sinir kenari (loop0 -> loop1) mevcut yuzde ayni yonde geciyorsa yeni yuzler ters sarilir
    it = om.MItMeshEdge(dag)
    vit = om.MItMeshVertex(dag)
    vit.setIndex(loop[0])
    eid = [e for e in vit.getConnectedEdges() if set(fn.getEdgeVertices(e)) == {loop[0], loop[1]}]
    flip = False
    if eid:
        it.setIndex(eid[0])
        face = it.getConnectedFaces()[0]
        verts = list(fn.getPolygonVertices(face))
        i0 = verts.index(loop[0])
        flip = verts[(i0 + 1) % len(verts)] == loop[1]
    points = om.MPointArray()
    index = {}
    for i in range(m + 1):
        for j in range(n + 1):
            index[(i, j)] = len(points)
            points.append(grid[i][j])
    counts, connects = om.MIntArray(), om.MIntArray()
    for i in range(m):
        for j in range(n):
            quad = [index[(i, j)], index[(i + 1, j)], index[(i + 1, j + 1)], index[(i, j + 1)]]
            if flip:
                quad.reverse()
            counts.append(4)
            for q in quad:
                connects.append(q)
    patch_fn = om.MFnMesh()
    patch = patch_fn.create(points, counts, connects)
    patch_tr = om.MFnDagNode(patch).fullPathName()
    if cmds.nodeType(patch_tr) != 'transform':
        patch_tr = cmds.listRelatives(patch_tr, parent=True, fullPath=True)[0]
    cmds.sets(patch_tr, edit=True, forceElement='initialShadingGroup')
    name = obj.split('|')[-1]
    parent = cmds.listRelatives(obj, parent=True, fullPath=True)
    before_faces = cmds.polyEvaluate(obj, face=True)
    was_edit = in_edit()
    if was_edit:
        exit_edit()
    size = max(1e-4, max(fn.boundingBox.width, fn.boundingBox.height, fn.boundingBox.depth))
    result = cmds.polyUnite(obj, patch_tr, constructionHistory=True, mergeUVSets=1)[0]
    cmds.polyMergeVertex(result, distance=size * 1e-4)
    cmds.delete(result, constructionHistory=True)
    for o in (obj, patch_tr):
        if cmds.objExists(o) and not cmds.listRelatives(o, children=True):
            cmds.delete(o)
    if parent:
        result = cmds.parent(result, parent[0])[0]
    result = cmds.rename(result, name)
    after_faces = cmds.polyEvaluate(result, face=True)
    cmds.select(result, replace=True)
    enter_edit('face')
    new_faces = '%s.f[%d:%d]' % (result, before_faces, after_faces - 1)
    cmds.select(new_faces, replace=True)
    _msg(_t('Grid Fill: %d x %d') % (m, n))
    return new_faces


def triangulate():
    targets = _comps('face') or cmds.ls(hilite=True) or _objs()
    if targets:
        cmds.polyTriangulate(targets)


def quadrangulate():
    targets = _comps('face') or cmds.ls(hilite=True) or _objs()
    if targets:
        cmds.polyQuad(targets, angle=30, keepGroupBorder=True, keepTextureBorders=True)


def shade_smooth():
    targets = _comps('face') or cmds.ls(hilite=True) or _objs()
    if targets:
        cmds.polySoftEdge(targets, angle=180)
        _msg(_t('Shade Smooth'))


def shade_flat():
    targets = _comps('face') or cmds.ls(hilite=True) or _objs()
    if targets:
        cmds.polySoftEdge(targets, angle=0)
        _msg(_t('Shade Flat'))


def mesh_mirror_menu():
    """Blender'daki Mirror modifier'in Maya karsiligi: geometriyi aynala + birlestir."""
    def run(axis, direction):
        targets = cmds.ls(hilite=True) or _objs()
        if not targets:
            return
        if in_edit():
            exit_edit()
        cmds.polyMirrorFace(targets, worldSpace=False, axis=axis, axisDirection=direction,
                            mergeMode=1, mergeThresholdType=1, mergeThreshold=0.001)
    popup(_t('Mesh aynala (Mirror modifier gibi, birleştirerek)'), [
        (_t('-X → +X'), lambda: run(0, 0)), (_t('+X → -X'), lambda: run(0, 1)),
        (_t('-Y → +Y'), lambda: run(1, 0)), (_t('+Y → -Y'), lambda: run(1, 1)),
        (_t('-Z → +Z'), lambda: run(2, 0)), (_t('+Z → -Z'), lambda: run(2, 1)),
    ])


def _selected_vertex_data():
    """[(obje, kose_id, dunya_noktasi, dunya_normali)] secimden (tur ne olursa olsun)."""
    out = []
    verts = cmds.ls(cmds.polyListComponentConversion(_sel(), toVertex=True) or [], flatten=True, long=True)
    fns = {}
    for v in verts:
        obj, vid = v.split('.vtx[')[0], int(v.split('[')[-1].rstrip(']'))
        if obj not in fns:
            fns[obj] = _mesh_fn(obj)[0]
        fn = fns[obj]
        out.append((obj, vid, om.MVector(fn.getPoint(vid, om.MSpace.kWorld)),
                    fn.getVertexNormal(vid, True, om.MSpace.kWorld)))
    return out


def _set_points(data, positions):
    for (obj, vid, _p, _n), q in zip(data, positions):
        cmds.xform('%s.vtx[%d]' % (obj, vid), worldSpace=True, translation=(q.x, q.y, q.z))


def shrink_fatten():
    """Alt+S (edit modu): koseleri kendi normalleri boyunca it / cek."""
    data = _selected_vertex_data()
    if not data:
        _msg(_t('Önce bir şey seç'))
        return
    center = om.MPoint(sum((d[2] for d in data), om.MVector()) / len(data))
    _start_value_modal(title='KALINLAŞTIR / İNCELT', center=center,
                       apply_fn=lambda v: _set_points(data, [p + n * v for _o, _i, p, n in data]))


def to_sphere():
    """Shift+Alt+S: secimi kureye yaklastir (0..1)."""
    data = _selected_vertex_data()
    if len(data) < 3:
        _msg(_t('Küreye çevirmek için en az 3 köşe seç'))
        return
    c = sum((d[2] for d in data), om.MVector()) / len(data)
    radius = sum((d[2] - c).length() for d in data) / len(data)
    targets = [c + (d[2] - c).normal() * radius if (d[2] - c).length() > 1e-9 else d[2] for d in data]

    def apply(f):
        _set_points(data, [d[2] + (t - d[2]) * f for d, t in zip(data, targets)])
    _start_value_modal(title='KÜREYE ÇEVİR', center=om.MPoint(c), apply_fn=apply, lo=0.0, hi=1.0,
                       scale=1.0 / 250.0, fmt='%.2f')


def crease_edges():
    """Shift+E: kenar crease (0..1; Maya'da negatif yok)."""
    edges = _comps('edge') or cmds.polyListComponentConversion(_comps('face'), toEdge=True) or []
    if not edges:
        _msg(_t('Crease için kenar seç (2)'))
        return
    pts = cmds.xform(cmds.polyListComponentConversion(edges, toVertex=True), q=True, worldSpace=True, translation=True)
    n = max(1, len(pts) // 3)
    center = om.MPoint(sum(pts[0::3]) / n, sum(pts[1::3]) / n, sum(pts[2::3]) / n)
    flat = cmds.ls(edges, flatten=True)
    try:
        before = cmds.polyCrease(flat, q=True, value=True) or [0.0] * len(flat)
    except Exception:
        before = [0.0] * len(flat)
    start = max(before or [0.0])

    def revert():
        for edge, value in zip(flat, before):
            cmds.polyCrease(edge, value=max(0.0, value))
    _start_value_modal(title='CREASE', center=center, start=start, lo=0.0, hi=1.0, scale=1.0 / 250.0, fmt='%.2f',
                       apply_fn=lambda v: cmds.polyCrease(edges, value=v), revert_fn=revert)


# ---------------------------------------------------------------- U (UV), X menusu eklentileri, edit modunda Shift+A
def _uv_targets():
    faces = _comps('face')
    if faces:
        return faces
    objs = cmds.ls(hilite=True, long=True) or _objs()
    return cmds.polyListComponentConversion(objs, toFace=True) if objs else []


def uv_unwrap():
    faces = _uv_targets()
    if not faces:
        return
    try:
        if not cmds.pluginInfo('Unfold3D', q=True, loaded=True):
            cmds.loadPlugin('Unfold3D', quiet=True)
        cmds.u3dUnfold(faces, iterations=1, pack=1, borderintersection=True, triangleflip=True)
    except Exception:
        cmds.unfold(faces)


def uv_menu():
    """U (edit modu): Blender UV Mapping menusu."""
    if not in_edit():
        _msg(_t('UV için Tab ile edit moduna gir'))
        return
    popup(_t('UV (U)'), [
        (_t('&Unwrap (Unfold3D)'), uv_unwrap),
        (_t('&Smart UV Project (otomatik)'), lambda: cmds.polyAutoProjection(_uv_targets(), layoutMethod=1)),
        None,
        (_t('&Küp projeksiyonu'), lambda: cmds.polyAutoProjection(_uv_targets(), planes=6, optimize=0)),
        (_t('S&ilindir projeksiyonu'), lambda: cmds.polyProjection(_uv_targets(), type='Cylindrical')),
        (_t('K&üre projeksiyonu'), lambda: cmds.polyProjection(_uv_targets(), type='Spherical')),
        (_t('&Görünümden projeksiyon'), lambda: cmds.polyProjection(_uv_targets(), type='Planar', mapDirection='c')),
        None,
        (_t('Dikiş işaretle (&Mark Seam)'), lambda: cmds.polyMapCut(_comps('edge'))),
        (_t('Dikişi kaldır (&Clear Seam)'), lambda: cmds.polyMapSew(_comps('edge'))),
        (_t('&Sıfırla (Reset)'), lambda: cmds.polyForceUV(_uv_targets(), unitize=True)),
    ])


def limited_dissolve(angle=5.0):
    """X > Limited Dissolve: secimdeki (yoksa tum) kenarlardan iki yuzu neredeyse ayni duzlemde olanlari erit."""
    objs = cmds.ls(hilite=True, long=True) or _objs()
    edges = cmds.ls(cmds.polyListComponentConversion(_sel(), toEdge=True, internal=bool(_comps('face'))) or [],
                    flatten=True, long=True) if _sel() and in_edit() else []
    if not edges:
        edges = cmds.ls([o + '.e[*]' for o in objs], flatten=True, long=True)
    cos_tol = math.cos(math.radians(angle))
    victims = {}
    fns = {}
    for e in edges:
        obj, eid = e.split('.e[')[0], int(e.split('[')[-1].rstrip(']'))
        if obj not in fns:
            fns[obj] = _mesh_fn(obj)
        fn, dag = fns[obj]
        it = om.MItMeshEdge(dag)
        it.setIndex(eid)
        faces = list(it.getConnectedFaces())
        if len(faces) == 2:
            a = fn.getPolygonNormal(faces[0], om.MSpace.kWorld)
            b = fn.getPolygonNormal(faces[1], om.MSpace.kWorld)
            if a * b >= cos_tol:
                victims.setdefault(obj, []).append(eid)
    count = 0
    for obj, ids in victims.items():
        cmds.polyDelEdge(_ranges(obj, 'edge', ids), cleanVertices=True)
        count += len(ids)
    _msg(_t('%d kenar eritildi') % count)


def delete_edge_loops():
    """X > Edge Loops: secili kenar halkalarini sil, koseleri temizle."""
    edges = _comps('edge')
    if edges:
        cmds.polyDelEdge(edges, cleanVertices=True)
    else:
        _msg(_t('Kenar seç (2)'))


def add_into_mesh(fn):
    """Edit modunda Shift+A: primitifi duzenlenen mesh'e ekle (Blender gibi ayni objeye)."""
    target = [o for o in cmds.ls(hilite=True, long=True) if _shape_type(o) == 'mesh']
    if not target:
        return False
    target = target[0]
    kind = current_comp()
    before = cmds.polyEvaluate(target, face=True)
    name = target.split('|')[-1]
    parent = cmds.listRelatives(target, parent=True, fullPath=True)
    new = fn()
    node = new[0] if isinstance(new, (list, tuple)) else new
    p = cursor_pos()
    cmds.xform(node, worldSpace=True, translation=(p.x, p.y, p.z))
    exit_edit()
    result = cmds.polyUnite(target, node, constructionHistory=True, mergeUVSets=1)[0]
    cmds.delete(result, constructionHistory=True)
    for obj in (target, node):
        if cmds.objExists(obj) and not cmds.listRelatives(obj, children=True):
            cmds.delete(obj)
    if parent:
        result = cmds.parent(result, parent[0])[0]
    result = cmds.rename(result, name)
    cmds.select(result, replace=True)
    enter_edit('face')
    after = cmds.polyEvaluate(result, face=True)
    cmds.select('%s.f[%d:%d]' % (result, before, after - 1), replace=True)
    if kind != 'face':
        select_mode(kind)
    return True


# ---------------------------------------------------------------- proportional: Shift+O falloff, Alt+O bagli
FALLOFFS = [('Yumuşak (Smooth)', '1,0,2,0,1,2'), ('Küre (Sphere)', '1,0,2,0.866,0.5,2,0,1,2'),
            ('Kök (Root)', '1,0,2,0.707,0.5,2,0,1,2'), ('Keskin (Sharp)', '1,0,2,0.25,0.5,2,0,1,2'),
            ('Doğrusal (Linear)', '1,0,1,0,1,1'), ('Sabit (Constant)', '1,0,1,1,0.999,1,0,1,1')]


def falloff_pie():
    cur = cmds.softSelect(q=True, softSelectCurve=True)

    def setter(curve, label):
        def run():
            cmds.softSelect(edit=True, softSelectCurve=curve)
            _msg(_t('Proportional falloff: %s') % _t(label))
        return run
    items = [(_t(label), setter(curve, label), cur == curve) for label, curve in FALLOFFS]
    order = [4, 1, 5, 0, 2, 3]   # pie sirasi: Sol, Sag, Alt, Ust, SolUst, SagUst
    return pie(_t('Proportional falloff (Shift+O)'), [items[i] for i in order])


def toggle_soft_connected():
    """Alt+O: proportional sadece bagli parcalarda (Maya surface) <-> hacim."""
    surface = cmds.softSelect(q=True, softSelectFalloff=True) == 1
    cmds.softSelect(edit=True, softSelectFalloff=0 if surface else 1)
    _msg(_t('Proportional bağlı (connected): %s') % (_t('kapalı') if surface else _t('açık')))
