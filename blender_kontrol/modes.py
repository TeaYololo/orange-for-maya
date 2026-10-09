# -*- coding: utf-8 -*-
"""Sculpt ve boyama modlari, Ctrl+Tab mod pie."""
from __future__ import absolute_import, division, print_function

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om

from .compat import QtGui
from .core import _current_filter_set_modal, _msg
from .i18n import _t
from .util import _last_view_panel, _objs, _shape_type, _visible_meshes
from .ui import pie
from .picking import Picker
from .editmode import current_comp, exit_edit, in_edit, select_mode
from .valuemodal import ValueModal


# ---------------------------------------------------------------- sculpt ve boyama modlari (Ctrl+Tab)
SCULPT_CTX = 'sculptMeshCacheContext'
SCULPT_BRUSHES = {   # Blender tusu -> (Maya runtime komutu, ad)
    'v': ('SetMeshSculptTool', 'Draw (Sculpt)'), 's': ('SetMeshSmoothTool', 'Smooth'),
    'p': ('SetMeshPinchTool', 'Pinch'), 'i': ('SetMeshBulgeTool', 'Inflate (Bulge)'),
    'g': ('SetMeshGrabTool', 'Grab'), 'shift+t': ('SetMeshScrapeTool', 'Scrape'),
    'c': ('SetMeshWaxTool', 'Clay Strips (Wax)'), 'shift+c': ('SetMeshKnifeTool', 'Crease (Knife)'),
    'k': ('SetMeshSmearTool', 'Snake Hook (Smear)'), 'm': ('SetMeshFreezeTool', 'Mask (Freeze)'),
    'shift+f': None, 'f': None,
}
# sculpt modunda gecerli kalan genel tuslar (gorunum, oynatma, F tuslari...)
SCULPT_GLOBAL = frozenset(['tab', 'ctrl+tab', 'space', 'shift+space', 'f1', 'f2', 'f3', 'f9', 'f11', 'f12', 'left', 'right',
                           'up', 'down', 'shift+left', 'shift+right', 'ctrl+shift+z', 'ctrl+comma', 'grave', 'z', 'shift+z',
                           'alt+z', 'n', 't', 'home', 'ctrl+space', 'alt+shift+z', 'ctrl+alt+q', 'ctrl+shift+space', 'q',
                           'ctrl+0', 'ctrl+1', 'ctrl+2', 'ctrl+3', 'ctrl+4', 'ctrl+5', 'ctrl+pgup', 'ctrl+pgdown'])


def _sculpting():
    try:
        return cmds.currentCtx() == SCULPT_CTX
    except Exception:
        return False


def enter_sculpt():
    meshes = [o for o in (cmds.ls(hilite=True, long=True) or _objs()) if _shape_type(o) == 'mesh']
    if not meshes:
        _msg(_t('Sculpt için bir mesh seç'))
        return
    if in_edit():
        exit_edit()
    cmds.select(meshes, replace=True)
    mel.eval('SetMeshSculptTool')
    _msg(_t('Sculpt modu: F yarıçap, Shift+F güç, V S P I G C K M fırçalar, Ctrl+Tab çıkış'))


def exit_sculpt():
    cmds.setToolTo('selectSuperContext')


def sculpt_brush(combo):
    cmd, name = SCULPT_BRUSHES[combo]
    mel.eval(cmd)
    _msg(_t('Fırça: %s') % name)


def sculpt_radius(strength=False):
    """F / Shift+F: firca yaricapi / gucu, fareyle (Blender radial control)."""
    if not _sculpting():
        return
    flag = 'strength' if strength else 'size'
    start = cmds.sculptMeshCacheCtx(SCULPT_CTX, q=True, **{flag: True})
    panel = _last_view_panel()
    if not panel:
        return

    def apply(v):
        cmds.sculptMeshCacheCtx(SCULPT_CTX, edit=True, **{flag: v})
    tool = ValueModal(panel, title='GÜÇ' if strength else 'YARIÇAP', apply_fn=apply,
                      center=om.MPoint(_cursor_world_hint(panel)), start=start, lo=0.01,
                      hi=100.0 if strength else None, scale=(0.25 if strength else max(0.01, start / 150.0)),
                      step=1.0, fmt='%.2f')
    _current_filter_set_modal(tool)
    if not tool.start():
        _current_filter_set_modal(None)


def _cursor_world_hint(panel):
    """Fare altindaki yuzey noktasi (yoksa kamera hedefi): deger modallerinin ekran merkezi icin."""
    try:
        picker = Picker(panel, meshes=_visible_meshes())
        h = picker.hit(QtGui.QCursor.pos())
        if h:
            return h[2]
        fn = om.MFnCamera(picker.view.getCamera())
        return fn.centerOfInterestPoint(om.MSpace.kWorld)
    except Exception:
        return om.MPoint()


def enter_paint(kind):
    meshes = [o for o in (cmds.ls(hilite=True, long=True) or _objs()) if _shape_type(o) == 'mesh']
    if not meshes:
        _msg(_t('Önce bir mesh seç'))
        return
    if in_edit():
        exit_edit()
    cmds.select(meshes, replace=True)
    if kind == 'weight':
        if not any(cmds.ls(cmds.listHistory(m) or [], type='skinCluster') for m in meshes):
            _msg(_t('Ağırlık boyamak için mesh\'in skin\'i olmalı (Skin > Bind Skin)'))
            return
        mel.eval('ArtPaintSkinWeightsTool')
    elif kind == 'vertex':
        mel.eval('PaintVertexColorTool')
    else:
        mel.eval('Art3dPaintTool')


def mode_pie():
    """Ctrl+Tab: Blender mod pie'i (secim modlari + sculpt / boyama)."""
    ctx = cmds.currentCtx()
    now = 'sculpt' if ctx == SCULPT_CTX else (current_comp() if in_edit() else 'object')
    paint = {'artAttrSkinContext': 'weight', 'artAttrColorPerVertexContext': 'vertex', 'art3dPaintContext': 'texture'}

    def to_object():
        if _sculpting() or ctx in paint:
            exit_sculpt()
        if in_edit():
            exit_edit()
    return pie(_t('Mod (Ctrl+Tab)'), [
        (_t('Köşe'), lambda: select_mode('vertex'), now == 'vertex'),
        (_t('Yüz'), lambda: select_mode('face'), now == 'face'),
        (_t('Obje modu'), to_object, now == 'object' and ctx not in paint),
        (_t('Kenar'), lambda: select_mode('edge'), now == 'edge'),
        (_t('Sculpt'), enter_sculpt, now == 'sculpt'),
        (_t('Vertex Paint'), lambda: enter_paint('vertex'), paint.get(ctx) == 'vertex'),
        (_t('Weight Paint'), lambda: enter_paint('weight'), paint.get(ctx) == 'weight'),
        (_t('Texture Paint'), lambda: enter_paint('texture'), paint.get(ctx) == 'texture'),
    ])
