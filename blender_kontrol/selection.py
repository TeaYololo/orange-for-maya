# -*- coding: utf-8 -*-
"""Secim komutlari: loop, ring, yol, benzerini sec, ayna, secim araclari."""
from __future__ import absolute_import, division, print_function

import functools
import math

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om

from .compat import QtGui
from .core import _msg, _state
from .i18n import _t
from .util import (COMP_SUFFIX, _click_panel, _comp, _last_view_panel, _mesh_fn, _objs, _ranges, _selected_ids,
    _shape_type, popup)
from .picking import Picker, _hops, _mesh_graph
from .editmode import current_comp, in_edit, select_mode
from .view import subdiv_level


# ---------------------------------------------------------------- secim
def select_all():
    if in_edit():
        suffix = COMP_SUFFIX[current_comp()]
        cmds.select([o + suffix for o in cmds.ls(hilite=True, long=True)], replace=True)
    else:
        mel.eval('SelectAll')


def deselect_all():
    cmds.select(clear=True)


def invert_selection():
    mel.eval('InvertSelection')


def select_linked():
    mel.eval('ConvertSelectionToShell')


def grow_selection():
    mel.eval('GrowPolygonSelectionRegion')


def shrink_selection():
    mel.eval('ShrinkPolygonSelectionRegion')


def select_loop(pos, ring=False, add=False):
    """Alt+tik: loop, Ctrl+Alt+tik: ring. Shift ile ekler."""
    panel = _click_panel()
    if not panel or not in_edit():
        return False
    kind = current_comp()
    picker = Picker(panel)
    r = picker.edge(pos)
    if not r:
        return False
    mesh, edge, _ = r
    obj = mesh['transform']
    it = om.MItMeshEdge(mesh['poly'])
    it.setIndex(edge)
    border = it.numConnectedFaces() == 1
    if kind == 'face':
        # yuz loop'u = kenar halkasina komsu yuzler
        edges = cmds.polySelect(obj, edgeRing=edge, noSelection=True) or []
        if ring:
            edges = cmds.polySelect(obj, edgeLoop=edge, noSelection=True) or []
        comps = cmds.polyListComponentConversion([_comp(obj, 'edge', e) for e in edges], toFace=True)
    else:
        flag = 'edgeRing' if ring else ('edgeBorder' if border else 'edgeLoop')   # sinirda: tum sinir
        edges = cmds.polySelect(obj, noSelection=True, **{flag: edge}) or []
        comps = [_comp(obj, 'edge', e) for e in edges]
        if kind == 'vertex':
            comps = cmds.polyListComponentConversion(comps, toVertex=True)
    if add and set(cmds.ls(comps, flatten=True)) <= set(cmds.ls(sl=True, flatten=True)):
        cmds.select(comps, deselect=True)   # Shift+Alt+tik: zaten seciliyse cikar (toggle)
        return True
    cmds.select(comps, add=add, replace=not add)
    return True


def select_path(pos):
    """Ctrl+tik: son secilenden tiklanan yere en kisa yol."""
    panel = _click_panel()
    if not panel or not in_edit():
        return False
    kind = current_comp()
    picker = Picker(panel)
    r = picker.component(pos, kind)
    if not r:
        return False
    mesh, idx = r
    obj = mesh['transform']
    target = _comp(obj, kind, idx)
    ordered = [c for c in (cmds.ls(orderedSelection=True, flatten=True) or [])
               if c.split('.')[0].split('|')[-1] == obj.split('|')[-1]]
    if not ordered:
        cmds.select(target, add=True)
        return True
    last_id = int(ordered[-1].split('[')[-1].rstrip(']'))
    # Maya'nin polySelect -shortest*Path bayraklari 2027'de hata veriyor; yolu kendimiz buluyoruz
    graph = _mesh_graph(mesh['fn'], mesh['poly'].fullPathName())
    if kind == 'face':
        comps = [_comp(obj, 'face', f) for f in graph.face_path(last_id, idx)]
    elif kind == 'edge':
        edges = graph.vertex_path(graph.edge_verts[last_id], graph.edge_verts[idx])[1]
        comps = [_comp(obj, 'edge', e) for e in edges + [idx]]
    else:
        verts = graph.vertex_path([last_id], [idx])[0]
        comps = [_comp(obj, 'vertex', v) for v in verts]
    cmds.select(comps, add=True)
    cmds.select(target, add=True)  # son secilen = tiklanan (siradaki yol icin)
    return True


def select_linked_under_cursor(deselect=False):
    """L: imlecin altindaki parcayi sec (Shift+L: cikar)."""
    panel = _last_view_panel()
    if not panel or not in_edit():
        return
    picker = Picker(panel)
    h = picker.hit(QtGui.QCursor.pos())
    if not h:
        _msg(_t('İmleç bir mesh üzerinde değil'))
        return
    mesh, face, _ = h
    obj = mesh['transform']
    faces = _mesh_graph(mesh['fn'], mesh['poly'].fullPathName()).shell(face)
    comps = [_comp(obj, 'face', f) for f in faces]
    kind = current_comp()
    if kind != 'face':
        comps = cmds.polyListComponentConversion(comps, **{'toVertex' if kind == 'vertex' else 'toEdge': True})
    if deselect:
        cmds.select(comps, deselect=True)
    else:
        cmds.select(comps, add=True)


def ctrl_number(level):
    """Ctrl+1/2/3: edit modunda genisleterek secim modu, obje modunda yumusak onizleme (Blender)."""
    if in_edit() and level in (1, 2, 3):
        select_mode(('vertex', 'edge', 'face')[level - 1], expand=True)
    else:
        subdiv_level(level)


# ---------------------------------------------------------------- Shift+G benzerini sec / grupla sec
SIMILAR_MODES = {
    'face': [('Normal', 'normal'), ('Alan (Area)', 'area'), ('Kenar sayısı (Polygon Sides)', 'sides'),
             ('Materyal', 'material'), ('Eş düzlemli (Coplanar)', 'coplanar')],
    'edge': [('Uzunluk (Length)', 'length'), ('Yön (Direction)', 'direction'),
             ('Komşu yüz sayısı (Faces around)', 'faces'), ('Sertlik (Sharpness)', 'sharp'), ('Crease', 'crease')],
    'vertex': [('Normal', 'normal'), ('Komşu yüz sayısı (Amount of Faces)', 'faces'),
               ('Bağlı kenar sayısı (Connecting Edges)', 'edges')],
}


def _similar_props(fn, dag, kind, mode):
    """Her bilesen icin karsilastirilacak deger listesi."""
    n = {'vertex': fn.numVertices, 'edge': fn.numEdges, 'face': fn.numPolygons}[kind]
    if kind == 'face':
        if mode in ('normal', 'coplanar'):
            normals = [fn.getPolygonNormal(i, om.MSpace.kWorld) for i in range(n)]
            if mode == 'normal':
                return normals
            it = om.MItMeshPolygon(dag)
            centers = []
            while not it.isDone():
                centers.append(om.MVector(it.center(om.MSpace.kWorld)))
                it.next()
            return [(normals[i], normals[i] * centers[i]) for i in range(n)]
        if mode == 'area':
            it = om.MItMeshPolygon(dag)
            out = []
            while not it.isDone():
                out.append(it.getArea(om.MSpace.kWorld))
                it.next()
            return out
        if mode == 'sides':
            return [fn.polygonVertexCount(i) for i in range(n)]
        if mode == 'material':
            try:
                shaders, ids = fn.getConnectedShaders(dag.instanceNumber())
                return [shaders[i].__str__() if i >= 0 else '' for i in ids]
            except Exception:
                return [''] * n
    if kind == 'edge':
        if mode in ('length', 'direction'):
            out = []
            for e in range(n):
                a, b = fn.getEdgeVertices(e)
                d = om.MVector(fn.getPoint(b, om.MSpace.kWorld) - fn.getPoint(a, om.MSpace.kWorld))
                out.append(d.length() if mode == 'length' else (d.normal() if d.length() > 1e-12 else d))
            return out
        if mode == 'faces':
            it = om.MItMeshEdge(dag)
            out = []
            while not it.isDone():
                out.append(it.numConnectedFaces())
                it.next()
            return out
        if mode == 'sharp':
            return [fn.isEdgeSmooth(e) for e in range(n)]
        if mode == 'crease':
            values = [0.0] * n
            try:
                ids, vals = fn.getCreaseEdges()
                for i, v in zip(ids, vals):
                    values[i] = round(v, 4)
            except Exception:
                pass
            return values
    if kind == 'vertex':
        if mode == 'normal':
            return [fn.getVertexNormal(v, True, om.MSpace.kWorld) for v in range(n)]
        it = om.MItMeshVertex(dag)
        out = []
        while not it.isDone():
            out.append(it.numConnectedFaces() if mode == 'faces' else it.numConnectedEdges())
            it.next()
        return out
    return [None] * n


def _similar_match(mode, a, b):
    cos_tol = math.cos(math.radians(1.0))
    if mode == 'normal':
        return a * b >= cos_tol
    if mode == 'direction':
        return abs(a * b) >= cos_tol
    if mode == 'coplanar':
        return a[0] * b[0] >= cos_tol and abs(a[1] - b[1]) <= 1e-3 * max(1.0, abs(a[1]))
    if mode in ('area', 'length'):
        return abs(a - b) <= 1e-3 * max(abs(a), abs(b)) + 1e-9
    return a == b


def select_similar(kind, mode):
    """Shift+G (edit modu): secilenlere benzeyenleri secime ekle."""
    added = 0
    for obj, ids in _selected_ids(kind).items():
        fn, dag = _mesh_fn(obj)
        props = _similar_props(fn, dag, kind, mode)
        refs = [props[i] for i in set(ids) if i < len(props)]
        hits = [i for i, p in enumerate(props) if any(_similar_match(mode, p, r) for r in refs)]
        if hits:
            cmds.select(_ranges(obj, kind, hits), add=True)
            added += len(hits)
    if not added:
        _msg(_t('Önce bir şey seç'))


def select_grouped(mode):
    """Shift+G (obje modu): Blender Select Grouped."""
    objs = _objs()
    if not objs:
        _msg(_t('Önce bir obje seç'))
        return
    active = objs[-1]
    result = []
    if mode == 'children':
        result = cmds.listRelatives(objs, allDescendents=True, type='transform', fullPath=True) or []
    elif mode == 'immediate':
        result = cmds.listRelatives(objs, children=True, type='transform', fullPath=True) or []
    elif mode == 'parent':
        result = cmds.listRelatives(objs, parent=True, fullPath=True) or []
    elif mode == 'siblings':
        par = cmds.listRelatives(active, parent=True, fullPath=True)
        result = (cmds.listRelatives(par[0], children=True, type='transform', fullPath=True) if par else
                  cmds.ls(assemblies=True, long=True)) or []
    elif mode == 'type':
        want = _shape_type(active)
        result = [t for t in cmds.ls(type='transform', long=True) if _shape_type(t) == want]
    elif mode == 'layer':
        layer = (cmds.listConnections(active + '.drawOverride', type='displayLayer') or ['defaultLayer'])[0]
        members = cmds.editDisplayLayerMembers(layer, q=True, fullNames=True) or []
        result = cmds.ls(members, type='transform', long=True)
    if result:
        cmds.select(result, add=True)
    else:
        _msg(_t('Eşleşen obje yok'))


def select_similar_menu():
    if not in_edit():
        popup(_t('Grupla seç (Shift+G)'), [
            (_t('&Çocuklar (Children)'), lambda: select_grouped('children')),
            (_t('&Doğrudan çocuklar'), lambda: select_grouped('immediate')),
            (_t('&Ebeveyn (Parent)'), lambda: select_grouped('parent')),
            (_t('&Kardeşler (Siblings)'), lambda: select_grouped('siblings')),
            (_t('&Tür (Type)'), lambda: select_grouped('type')),
            (_t('&Layer (Collection)'), lambda: select_grouped('layer')),
        ])
        return
    kind = current_comp()
    popup(_t('Benzerini seç (Shift+G)'),
          [(_t(label), functools.partial(select_similar, kind, mode)) for label, mode in SIMILAR_MODES[kind]])


def select_mirror():
    """Shift+Ctrl+M: secimin objenin yerel X eksenine gore aynasini sec."""
    kind = current_comp()
    total = 0
    sel_ids = _selected_ids(kind)
    if not sel_ids:
        _msg(_t('Önce bir şey seç'))
        return
    result = []
    for obj, ids in sel_ids.items():
        fn, _dag = _mesh_fn(obj)
        pts = fn.getPoints(om.MSpace.kObject)
        size = max(1e-6, max(abs(c) for p in pts for c in (p.x, p.y, p.z)))
        tol = size * 1e-4
        grid = {}
        for v, p in enumerate(pts):
            grid.setdefault((round(p.x / tol), round(p.y / tol), round(p.z / tol)), v)

        def mirror_vertex(v):
            p = pts[v]
            key = (round(-p.x / tol), round(p.y / tol), round(p.z / tol))
            for dx in (0, -1, 1):
                m = grid.get((key[0] + dx, key[1], key[2]))
                if m is not None:
                    return m
            return None

        if kind == 'vertex':
            out = [mirror_vertex(v) for v in ids]
        elif kind == 'edge':
            lookup = dict((frozenset(fn.getEdgeVertices(e)), e) for e in range(fn.numEdges))
            out = [lookup.get(frozenset(mirror_vertex(v) for v in fn.getEdgeVertices(e))) for e in ids]
        else:
            lookup = dict((frozenset(fn.getPolygonVertices(f)), f) for f in range(fn.numPolygons))
            out = [lookup.get(frozenset(mirror_vertex(v) for v in fn.getPolygonVertices(f))) for f in ids]
        out = [i for i in out if i is not None]
        total += len(out)
        result += _ranges(obj, kind, out)
    if result:
        cmds.select(result, replace=True)
    _msg(_t('Ayna seçimi: %d / %d') % (total, sum(len(v) for v in sel_ids.values())))


# ---------------------------------------------------------------- B / W / C secim araclari
SELECT_TOOLS = [('selectSuperContext', 'Kutu seçimi'), ('lassoSelectContext', 'Kement (Lasso)'),
                ('artSelectContext', 'Fırça (Circle / Paint)')]


def _set_select_tool(ctx):
    if ctx == 'artSelectContext':
        mel.eval('ArtPaintSelectTool')
    else:
        cmds.setToolTo(ctx)
    _msg(_t('Seçim aracı: %s') % _t(dict(SELECT_TOOLS)[ctx]))


def box_select_tool():
    """B: kutu secimi (Maya: Shift ekle/cikar, Ctrl cikar, Ctrl+Shift ekle)."""
    cmds.setToolTo('selectSuperContext')
    _msg(_t('Kutu seçimi: sol tuşla sürükle (Ctrl+Shift ekle, Ctrl çıkar)'))


def cycle_select_tool():
    """W: kutu -> kement -> firca."""
    names = [c for c, _ in SELECT_TOOLS]
    cur = cmds.currentCtx()
    nxt = names[(names.index(cur) + 1) % len(names)] if cur in names else names[0]
    _set_select_tool(nxt)


def circle_select_toggle():
    """C: firca ile secim; tekrar C, sag tik ya da Esc ile onceki araca don."""
    if cmds.currentCtx() == 'artSelectContext':
        _end_circle_select()
        return
    _state['circle_prev'] = cmds.currentCtx()
    mel.eval('ArtPaintSelectTool')
    _msg(_t('Fırça ile seç: boya. Bitirmek için C, sağ tık ya da Esc'))


def _end_circle_select():
    prev = _state.pop('circle_prev', None) or 'selectSuperContext'
    try:
        cmds.setToolTo(prev)
    except Exception:
        cmds.setToolTo('selectSuperContext')


# ---------------------------------------------------------------- fill region (Shift+Ctrl+tik)
def select_fill_region(pos):
    """Son secilenle tiklanan arasindaki dikdortgen bolge (Blender Shift+Ctrl+tik). Kose ve yuz modu."""
    panel = _click_panel()
    if not panel or not in_edit():
        return False
    kind = current_comp()
    picker = Picker(panel)
    r = picker.component(pos, 'vertex' if kind == 'edge' else kind)
    if not r:
        return False
    mesh, idx = r
    obj = mesh['transform']
    ordered = [c for c in (cmds.ls(orderedSelection=True, flatten=True, long=True) or [])
               if c.split('.')[0].split('|')[-1] == obj.split('|')[-1]]
    if not ordered:
        return False
    graph = _mesh_graph(mesh['fn'], mesh['poly'].fullPathName())
    last = ordered[-1]
    if kind == 'face':
        a = int(last.split('[')[-1].rstrip(']'))
        graph.face_path(a, a)       # komsulugu kur
        neighbors = lambda f: [g for g, _l, _w in graph._fadj[f]]
    else:
        if '.e[' in last:
            a = graph.edge_verts[int(last.split('[')[-1].rstrip(']'))][0]
        else:
            a = int(last.split('[')[-1].rstrip(']'))
        neighbors = lambda v: [w for w, _e, _d in graph.vadj[v]]
    da, db = _hops(a, neighbors), _hops(idx, neighbors)
    if idx not in da:
        return False
    total = da[idx]
    region = [n for n in da if n in db and da[n] + db[n] == total]
    if kind == 'face':
        cmds.select(_ranges(obj, 'face', region), add=True)
    elif kind == 'vertex':
        cmds.select(_ranges(obj, 'vertex', region), add=True)
    else:
        edges = cmds.polyListComponentConversion(_ranges(obj, 'vertex', region), toEdge=True, internal=True)
        cmds.select(edges, add=True)
    return True
