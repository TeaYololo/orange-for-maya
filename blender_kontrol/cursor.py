# -*- coding: utf-8 -*-
"""3D imlec ve Shift+S hizalama pie."""
from __future__ import absolute_import, division, print_function

import maya.cmds as cmds
import maya.api.OpenMaya as om

from .settings import setting
from .i18n import _t
from .util import _NoUndo, _axes_euler, _click_panel, _objs, _sel
from .ui import pie
from .picking import Picker
from .editmode import in_edit


# ---------------------------------------------------------------- 3D imlec
CURSOR = 'blenderCursor'


CURSOR_RING = 'blenderCursorRing'
CURSOR_COLORS = ((1.0, 0.2, 0.2), (1.0, 1.0, 1.0))   # Blender imleci: kirmizi / beyaz halka


def _color_shape(shape, rgb):
    cmds.setAttr(shape + '.overrideEnabled', 1)
    cmds.setAttr(shape + '.overrideRGBColors', 1)
    cmds.setAttr(shape + '.overrideColorRGB', *rgb)


def _build_cursor(position=None, rotation=None):
    """Imlec: kucuk carpi (locator) + iki halka (kirmizi XZ, beyaz XY). Undo'ya girmez, Outliner'da gizli,
    secime girerse _deselect_cursor cikarir."""
    with _NoUndo():
        sel = cmds.ls(sl=True)
        node = cmds.spaceLocator(name=CURSOR)[0]
        loc = cmds.listRelatives(node, shapes=True, fullPath=True)[0]
        cmds.setAttr(loc + '.localScale', 0.12, 0.12, 0.12)
        _color_shape(loc, (0.05, 0.05, 0.05))
        for i, (normal, rgb) in enumerate((((0, 1, 0), CURSOR_COLORS[0]), ((0, 0, 1), CURSOR_COLORS[1]))):
            circ = cmds.circle(normal=normal, radius=0.22 + 0.03 * i, sections=24, constructionHistory=False)[0]
            shape = cmds.listRelatives(circ, shapes=True, fullPath=True)[0]
            shape = cmds.parent(shape, node, shape=True, relative=True)[0]
            cmds.delete(circ)
            shape = cmds.rename(shape, '%s%d' % (CURSOR_RING, i))
            _color_shape(shape, rgb)
        for attr in ('sx', 'sy', 'sz'):
            cmds.setAttr('%s.%s' % (node, attr), lock=True, keyable=False)
        cmds.setAttr(node + '.hiddenInOutliner', True)
        if position is not None:
            cmds.xform(node, worldSpace=True, translation=position)
        if rotation is not None:
            cmds.xform(node, worldSpace=True, rotation=rotation)
        if sel:
            cmds.select(sel, replace=True)
        else:
            cmds.select(clear=True)
    return node


def _style_cursor(node):
    """Eski surumun imlecini (siyah reference locator) yeni gorunume cevir."""
    if cmds.listRelatives(node, shapes=True, type='nurbsCurve'):
        return
    pos = cmds.xform(node, q=True, worldSpace=True, translation=True)
    with _NoUndo():
        cmds.delete(node)
    _build_cursor(position=pos)


def _deselect_cursor(*_):
    """SelectionChanged: imlec secime girmesin (Blender'da imlec secilemez)."""
    try:
        sel = cmds.ls(sl=True, objectsOnly=True) or []
        if any(s.split('|')[-1].startswith(CURSOR) for s in sel):
            with _NoUndo():
                cmds.select([n for n in cmds.ls(CURSOR, dag=True) or []], deselect=True)
    except Exception:
        pass


def cursor_node(create=True):
    if cmds.objExists(CURSOR):
        _style_cursor(CURSOR)
        return CURSOR
    if not create:
        return None
    return _build_cursor()


def cursor_pos():
    node = cursor_node(create=False)
    if not node:
        return om.MPoint(0, 0, 0)
    return om.MPoint(*cmds.xform(node, q=True, worldSpace=True, translation=True))


def set_cursor(point, rotation=None):
    with _NoUndo():
        node = cursor_node()
        cmds.xform(node, worldSpace=True, translation=(point.x, point.y, point.z))
        if rotation is not None:
            cmds.xform(node, worldSpace=True, rotation=rotation)


def _cursor_rotation(picker, hit_mesh=None, face=None):
    """Ayara gore imlec rotasyonu: None (dokunma), gorunume ya da yuzey normaline hizali."""
    mode = setting('cursor_orient')
    cam = om.MFnCamera(picker.view.getCamera())
    right = cam.rightDirection(om.MSpace.kWorld).normal()
    if mode == 'view':
        z = -cam.viewDirection(om.MSpace.kWorld).normal()
        y = cam.upDirection(om.MSpace.kWorld).normal()
        return _axes_euler((y ^ z).normal(), y, z)
    if mode == 'surface' and hit_mesh is not None:
        z = hit_mesh['fn'].getPolygonNormal(face, om.MSpace.kWorld).normal()
        x = right - z * (right * z)
        if x.length() < 1e-6:
            x = cam.upDirection(om.MSpace.kWorld) ^ z
        x = x.normal()
        return _axes_euler(x, (z ^ x).normal(), z)
    return None


def place_cursor(global_pos):
    """Shift+sag tik: imleci fare altindaki yuzeye (yoksa imlec duzlemine) koy."""
    panel = _click_panel()
    if not panel:
        return False
    meshes = cmds.listRelatives(cmds.ls(type='mesh', visible=True, noIntermediate=True, long=True) or [],
                                parent=True, fullPath=True) or []
    picker = Picker(panel, meshes=list(set(meshes)))
    h = picker.hit(global_pos)
    if h:
        set_cursor(h[2], _cursor_rotation(picker, h[0], h[1]))
        return True
    x, y = picker.port(global_pos)
    near, far = om.MPoint(), om.MPoint()
    picker.view.viewToWorld(int(round(x)), int(round(y)), near, far)
    direction = om.MVector(far - near).normal()
    normal = om.MFnCamera(picker.view.getCamera()).viewDirection(om.MSpace.kWorld).normal()
    denom = direction * normal
    if abs(denom) > 1e-8:
        t = (om.MVector(cursor_pos() - near) * normal) / denom
        set_cursor(near + direction * t, _cursor_rotation(picker))
    return True


def _selection_center():
    sel = _sel()
    if not sel:
        return None
    if in_edit():
        verts = cmds.polyListComponentConversion(sel, toVertex=True) or sel
        pts = cmds.xform(verts, q=True, worldSpace=True, translation=True) or []
    else:
        pts = []
        for obj in _objs():
            pts += cmds.xform(obj, q=True, worldSpace=True, rotatePivot=True)
    if not pts:
        return None
    n = len(pts) // 3
    return om.MPoint(sum(pts[0::3]) / n, sum(pts[1::3]) / n, sum(pts[2::3]) / n)


def _active_pivot():
    objs = _objs()
    return om.MPoint(*cmds.xform(objs[-1], q=True, worldSpace=True, rotatePivot=True)) if objs else None


def _move_selection_to(point, each=True):
    if point is None:
        return
    if in_edit():
        c = _selection_center()
        if c:
            d = point - c
            cmds.move(d.x, d.y, d.z, _sel(), relative=True, worldSpace=True)
        return
    for obj in _objs():
        cmds.move(point.x, point.y, point.z, obj, worldSpace=True, rotatePivotRelative=True)


def snap_pie():
    def cursor_to(p):
        if p is not None:
            set_cursor(p)

    def grid(p):
        return om.MPoint(round(p.x), round(p.y), round(p.z))

    def selection_to_grid():
        if in_edit():
            c = _selection_center()
            if c:
                _move_selection_to(grid(c))
            return
        for obj in _objs():
            p = om.MPoint(*cmds.xform(obj, q=True, worldSpace=True, rotatePivot=True))
            g = grid(p)
            cmds.move(g.x, g.y, g.z, obj, worldSpace=True, rotatePivotRelative=True)

    def pivot_to_cursor():
        p = cursor_pos()
        for obj in _objs():
            cmds.xform(obj, worldSpace=True, pivots=(p.x, p.y, p.z))

    return pie(_t('Hizala (Shift+S)'), [
        (_t('İmleç → Seçim'), lambda: cursor_to(_selection_center())),
        (_t('Seçim → İmleç'), lambda: _move_selection_to(cursor_pos())),
        (_t('Seçim → Grid'), selection_to_grid),
        (_t('İmleç → Orijin'), lambda: cursor_to(om.MPoint(0, 0, 0))),
        (_t('İmleç → Grid'), lambda: cursor_to(grid(cursor_pos()))),
        (_t('Seçim → Aktif'), lambda: _move_selection_to(_active_pivot())),
        (_t('İmleç → Aktif'), lambda: cursor_to(_active_pivot())),
        (_t('Pivot → İmleç (origin)'), pivot_to_cursor),
    ])
