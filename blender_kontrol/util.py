# -*- coding: utf-8 -*-
"""Secim, undo, menu ve mesh yardimcilari."""
from __future__ import absolute_import, division, print_function

import functools
import math

import maya.cmds as cmds
import maya.api.OpenMaya as om

from .compat import QtCore, QtWidgets, _exec_menu, _main_window
from .core import _warn, run_after_op


COMP_TYPE = {'vertex': 'polymeshVertex', 'edge': 'polymeshEdge', 'face': 'polymeshFace'}
COMP_MASK = {'vertex': 'vertex', 'edge': 'edge', 'face': 'facet'}
COMP_SUFFIX = {'vertex': '.vtx[*]', 'edge': '.e[*]', 'face': '.f[*]'}
COMP_FILTER = {'vertex': 31, 'edge': 32, 'face': 34}


def _fn_name(fn):
    """functools.partial / lambda dahil her cagrilabilir icin okunur ad."""
    return getattr(fn, '__name__', None) or getattr(getattr(fn, 'func', None), '__name__', None) or 'op'


def undoable(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        cmds.undoInfo(openChunk=True, chunkName='blender_' + _fn_name(fn))
        try:
            result = fn(*args, **kwargs)
            run_after_op()
            return result
        except Exception as exc:
            _warn('%s: %s' % (_fn_name(fn), exc))
        finally:
            cmds.undoInfo(closeChunk=True)
    return wrapper


def _sel():
    return cmds.ls(sl=True, long=True) or []


def _objs():
    return cmds.ls(sl=True, objectsOnly=True, long=True, type='transform') or []


def _shape_type(obj):
    shapes = cmds.listRelatives(obj, shapes=True, noIntermediate=True, fullPath=True) or []
    return cmds.nodeType(shapes[0]) if shapes else None


def _comps(kind):
    return cmds.filterExpand(_sel(), selectionMask=COMP_FILTER[kind], expand=False) or []


def popup(title, items):
    """items: (etiket, fonksiyon) listesi; None = ayirici."""
    menu = QtWidgets.QMenu(_main_window())
    if title:
        head = menu.addAction(title)
        head.setEnabled(False)
        menu.addSeparator()
    for item in items:
        if item is None:
            menu.addSeparator()
            continue
        action = menu.addAction(item[0])
        action.triggered.connect(functools.partial(_deferred, undoable(item[1])))
    _exec_menu(menu)


def _deferred(fn, *_):
    QtCore.QTimer.singleShot(0, fn)


# ---------------------------------------------------------------- modelleme
def _face_normal(faces):
    total = om.MVector()
    for face in cmds.ls(faces, flatten=True):
        obj, idx = face.split('.f[')
        sl = om.MSelectionList()
        sl.add(obj)
        fn = om.MFnMesh(sl.getDagPath(0))
        total += fn.getPolygonNormal(int(idx.rstrip(']')), om.MSpace.kWorld)
    return total.normal() if total.length() > 1e-6 else None


def _matrix_list(m):
    return [m[i] for i in range(16)]


def _visible_meshes():
    meshes = cmds.listRelatives(cmds.ls(type='mesh', visible=True, noIntermediate=True, long=True) or [],
                                parent=True, fullPath=True) or []
    return list(set(meshes))


def _last_view_panel():
    panel = cmds.getPanel(underPointer=True)
    if panel and cmds.getPanel(typeOf=panel) == 'modelPanel':
        return panel
    panel = cmds.getPanel(withFocus=True)
    if panel and cmds.getPanel(typeOf=panel) == 'modelPanel':
        return panel
    visible = cmds.getPanel(visiblePanels=True) or []
    models = [p for p in visible if cmds.getPanel(typeOf=p) == 'modelPanel']
    return models[0] if models else None


COMP_NAME = {'vertex': 'vtx', 'edge': 'e', 'face': 'f'}


def _comp(transform, kind, idx):
    return '%s.%s[%d]' % (transform, COMP_NAME[kind], idx)


def _convert(comps, kind):
    flag = {'vertex': 'toVertex', 'edge': 'toEdge', 'face': 'toFace'}[kind]
    kwargs = {flag: True}
    if kind == 'face':
        kwargs['internal'] = True
    return cmds.polyListComponentConversion(comps, **kwargs) or []


# ---------------------------------------------------------------- tikla-sec (loop, ring, yol, linked)
def _click_panel():
    ctx, panel = _context()
    return panel if ctx == 'view' else None


class _NoUndo(object):
    """Blender'da imlec hareketi undo'ya girmez."""

    def __enter__(self):
        self.state = cmds.undoInfo(q=True, stateWithoutFlush=True)
        cmds.undoInfo(stateWithoutFlush=False)

    def __exit__(self, *exc):
        cmds.undoInfo(stateWithoutFlush=self.state)


def _axes_euler(x, y, z):
    m = om.MMatrix([x.x, x.y, x.z, 0, y.x, y.y, y.z, 0, z.x, z.y, z.z, 0, 0, 0, 0, 1])
    e = om.MTransformationMatrix(m).rotation(asQuaternion=False)
    return (math.degrees(e.x), math.degrees(e.y), math.degrees(e.z))


# ---------------------------------------------------------------- yardimcilar: mesh API, aralik secimi
def _mesh_fn(obj):
    dag = om.MSelectionList().add(obj).getDagPath(0)
    try:
        dag.extendToShape()
    except Exception:
        pass
    return om.MFnMesh(dag), dag


def _ranges(obj, kind, ids):
    """[3,4,5,9] -> ['obj.f[3:5]', 'obj.f[9]']"""
    name = COMP_NAME[kind]
    out, ids = [], sorted(set(ids))
    i = 0
    while i < len(ids):
        j = i
        while j + 1 < len(ids) and ids[j + 1] == ids[j] + 1:
            j += 1
        out.append('%s.%s[%d]' % (obj, name, ids[i]) if i == j else '%s.%s[%d:%d]' % (obj, name, ids[i], ids[j]))
        i = j + 1
    return out


def _selected_ids(kind):
    """{obje: [id, ...]} secili bilesenler (tur donusturulmeden)."""
    out = {}
    for c in cmds.ls(cmds.filterExpand(_sel(), selectionMask=COMP_FILTER[kind]) or [], flatten=True, long=True):
        obj = c.split('.')[0]
        out.setdefault(obj, []).append(int(c.split('[')[-1].rstrip(']')))
    return out


def _context():
    panel = cmds.getPanel(underPointer=True)
    if panel:
        kind = cmds.getPanel(typeOf=panel)
        if kind == 'modelPanel':
            return 'view', panel
        if kind == 'outlinerPanel':
            return 'outliner', panel
        if kind == 'scriptedPanel':
            sub = cmds.scriptedPanel(panel, q=True, type=True)
            if sub == 'polyTexturePlacementPanel':
                return 'uv', panel
            if sub in ('graphEditor', 'dopeSheetPanel'):
                return 'graph', panel
    return 'other', panel
