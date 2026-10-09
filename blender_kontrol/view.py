# -*- coding: utf-8 -*-
"""Gorunum, kamera, shading ve panel komutlari."""
from __future__ import absolute_import, division, print_function

import math

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om

from .core import _msg, _state, _warn
from .i18n import _t
from .util import _matrix_list, _objs, _visible_meshes
from .ui import pie
from .picking import Picker
from .cursor import cursor_node, set_cursor


def subdiv_level(level):
    objs = cmds.ls(hilite=True, long=True) or _objs()
    for obj in objs:
        for shape in cmds.listRelatives(obj, shapes=True, type='mesh', fullPath=True) or []:
            cmds.setAttr(shape + '.displaySmoothMesh', 2 if level else 0)
            if level:
                cmds.setAttr(shape + '.smoothLevel', level)
    _msg(_t('Yumuşak önizleme: %s') % (level or _t('kapalı')))


# ---------------------------------------------------------------- gorunum
def _cam(panel):
    """Panelin kamerasi (transform, tam yol: _scene_cameras ile karsilastirilabilir)."""
    cam = cmds.modelPanel(panel, q=True, camera=True)
    if cmds.nodeType(cam) == 'camera':
        cam = cmds.listRelatives(cam, parent=True, fullPath=True)[0]
    return (cmds.ls(cam, long=True) or [cam])[0]


def _cam_shape(cam):
    return (cmds.listRelatives(cam, shapes=True, type='camera', fullPath=True) or [cam])[0]


def _set_ortho(cam, ortho):
    shape = _cam_shape(cam)
    if ortho == cmds.camera(shape, q=True, orthographic=True):
        return
    if ortho:
        coi = cmds.camera(shape, q=True, centerOfInterest=True)
        hfov = cmds.camera(shape, q=True, horizontalFieldOfView=True)
        cmds.camera(shape, edit=True, orthographic=True,
                    orthographicWidth=2 * coi * math.tan(math.radians(hfov) / 2))
    else:
        cmds.camera(shape, edit=True, orthographic=False)


def _ensure_persp(panel):
    cam = _cam(panel)
    if cmds.camera(_cam_shape(cam), q=True, startupCamera=True) and cam.split('|')[-1] != 'persp':
        cmds.lookThru(panel, 'persp')
        cam = _cam(panel)
    return cam


def view_axis(panel, side):
    cam = _ensure_persp(panel)
    cmds.viewSet(cam, **{side: True})
    _set_ortho(cam, True)
    _state['auto_ortho'].add(cam)


def view_axis_local(panel, side):
    """Shift+Numpad 1/3/7: aktif objenin lokal eksenlerine gore on/sag/ust."""
    objs = _objs() or cmds.ls(hilite=True, long=True)
    if not objs:
        view_axis(panel, side)
        return
    obj = objs[-1]
    cam = _ensure_persp(panel)
    cmds.viewSet(cam, **{side: True})
    shape = _cam_shape(cam)
    obj_rot = om.MTransformationMatrix(om.MMatrix(cmds.xform(obj, q=True, worldSpace=True, matrix=True)))
    obj_rot = obj_rot.rotation(asQuaternion=True).asMatrix()
    cam_rot = om.MTransformationMatrix(om.MMatrix(cmds.xform(cam, q=True, worldSpace=True, matrix=True)))
    cam_rot = cam_rot.rotation(asQuaternion=True).asMatrix()
    rot = cam_rot * obj_rot
    pivot = om.MPoint(*cmds.xform(obj, q=True, worldSpace=True, rotatePivot=True))
    coi = cmds.camera(shape, q=True, centerOfInterest=True)
    z = om.MVector(rot[8], rot[9], rot[10]).normal()   # kamera kendi +Z'sinin tersine bakar
    full = om.MTransformationMatrix(rot)
    full.setTranslation(om.MVector(pivot + z * coi), om.MSpace.kWorld)
    cmds.xform(cam, worldSpace=True, matrix=_matrix_list(full.asMatrix()))
    cmds.camera(shape, edit=True, centerOfInterest=coi)
    _set_ortho(cam, True)
    _state['auto_ortho'].add(cam)


def view_opposite(panel):
    """Numpad 9: bakis yonunu 180 derece cevir."""
    opposite = {'front': 'back', 'back': 'front', 'rightSide': 'leftSide', 'leftSide': 'rightSide',
                'top': 'bottom', 'bottom': 'top'}
    now = _current_view(panel)
    if now in opposite:
        view_axis(panel, opposite[now])
        return
    cam = _ensure_persp(panel)
    cmds.tumble(cam, azimuthAngle=180)


def pan_step(panel, dx, dy):
    """Ctrl+Numpad 2/4/6/8: adim adim kaydir."""
    cam = _cam(panel)
    coi = cmds.camera(_cam_shape(cam), q=True, centerOfInterest=True)
    step = max(0.01, coi * 0.1)
    kwargs = {}
    if dx:
        kwargs['right' if dx > 0 else 'left'] = step
    if dy:
        kwargs['up' if dy > 0 else 'down'] = step
    cmds.track(cam, **kwargs)


def roll_step(panel, degrees):
    """Shift+Numpad 4/6: gorunumu yatir."""
    cmds.roll(_cam(panel), degree=degrees)


def center_view_at(panel, global_pos):
    """Alt+orta tik: fare altindaki noktayi gorunumun (ve orbit'in) merkezi yap."""
    picker = Picker(panel, meshes=_visible_meshes())
    h = picker.hit(global_pos)
    if not h:
        _msg(_t('İmleç bir mesh üzerinde değil'))
        return
    fn = om.MFnCamera(picker.view.getCamera())
    d = h[2] - fn.centerOfInterestPoint(om.MSpace.kWorld)
    cmds.move(d.x, d.y, d.z, _cam(panel), relative=True, worldSpace=True)


def _alt_mmb_action(panel, start, dx, dy):
    """Alt+orta tus: tik = merkeze al, surukle = yone gore eksen gorunumu (Blender Alt+MMB)."""
    try:
        if math.hypot(dx, dy) < 12:
            center_view_at(panel, start)
        elif abs(dx) > abs(dy):
            view_axis(panel, 'rightSide' if dx > 0 else 'leftSide')
        else:
            view_axis(panel, 'top' if dy < 0 else 'bottom')
    except Exception as exc:
        _warn(_t('görünüm: %s') % exc)


def toggle_ortho(panel):
    cam = _cam(panel)
    _state['auto_ortho'].discard(cam)
    ortho = not cmds.camera(_cam_shape(cam), q=True, orthographic=True)
    _set_ortho(cam, ortho)
    _msg(_t('Ortografik') if ortho else _t('Perspektif'))


def leave_auto_ortho(panel):
    try:
        cam = _cam(panel)
    except Exception:
        return
    if cam in _state['auto_ortho']:
        _state['auto_ortho'].discard(cam)
        _set_ortho(cam, False)


def _scene_cameras():
    cams = []
    for shape in cmds.ls(type='camera', long=True) or []:
        if not cmds.camera(shape, q=True, startupCamera=True):
            cams.append(cmds.listRelatives(shape, parent=True, fullPath=True)[0])
    return cams


def camera_view(panel):
    cams = _scene_cameras()
    if not cams:
        _msg(_t('Sahnede kamera yok (Shift+A > Kamera)'))
        return
    if _cam(panel) in cams:
        cmds.lookThru(panel, 'persp')
    else:
        cmds.lookThru(panel, cams[0])


def set_active_camera(panel):
    cams = [o for o in _objs() if o in _scene_cameras()]
    if cams:
        cmds.lookThru(panel, cams[0])


def align_camera_to_view(panel):
    cams = [o for o in _objs() if o in _scene_cameras()] or _scene_cameras()
    view_cam = _cam(panel)
    if not cams or cams[0] == view_cam:
        _msg(_t('Önce bir kamera seç'))
        return
    cmds.xform(cams[0], worldSpace=True, matrix=cmds.xform(view_cam, q=True, worldSpace=True, matrix=True))
    cmds.lookThru(panel, cams[0])


def frame_selected(panel):
    cmds.viewFit(_cam(panel), animate=True)


def frame_all(panel):
    cmds.viewFit(_cam(panel), allObjects=True, animate=True)


def orbit_step(panel, azimuth, elevation):
    cam = _ensure_persp(panel)
    leave_auto_ortho(panel)
    cmds.tumble(cam, azimuthAngle=azimuth, elevationAngle=elevation)


def zoom_step(panel, direction):
    cam = _cam(panel)
    shape = _cam_shape(cam)
    if cmds.camera(shape, q=True, orthographic=True):
        width = cmds.camera(shape, q=True, orthographicWidth=True)
        cmds.camera(shape, edit=True, orthographicWidth=width * (0.8 if direction > 0 else 1.25))
    else:
        coi = cmds.camera(shape, q=True, centerOfInterest=True)
        step = coi * 0.2 * direction
        cmds.dolly(cam, distance=step)
        # dolly COI'yi guncellemiyor: guncellemezsek orbit merkezi kayar, yakinlasma hedefe varamaz
        cmds.camera(shape, edit=True, centerOfInterest=max(1e-3, coi - step))


def toggle_isolate(panel):
    state = cmds.isolateSelect(panel, q=True, state=True)
    mel.eval('enableIsolateSelect "%s" %d;' % (panel, 0 if state else 1))
    _msg(_t('Local view: %s') % (_t('kapalı') if state else _t('açık')))


def _editor(panel):
    return cmds.modelPanel(panel, q=True, modelEditor=True)


def toggle_wireframe(panel):
    ed = _editor(panel)
    wire = cmds.modelEditor(ed, q=True, displayAppearance=True) == 'wireframe'
    cmds.modelEditor(ed, edit=True, displayAppearance='smoothShaded' if wire else 'wireframe')


def toggle_xray(panel):
    ed = _editor(panel)
    cmds.modelEditor(ed, edit=True, xray=not cmds.modelEditor(ed, q=True, xray=True))


def maximize_panel(panel):
    mel.eval('panePop')


def cursor_reset_and_frame(panel):
    if cursor_node(create=False):
        set_cursor(om.MPoint(0, 0, 0), (0.0, 0.0, 0.0))
    frame_all(panel)


# ---------------------------------------------------------------- pie'lar
def _current_view(panel):
    """Kamera bir eksene tam bakiyorsa 'front', 'top'... ; sahne kamerasindan bakiliyorsa 'camera'."""
    try:
        cam = _cam(panel)
        if cam in _scene_cameras():
            return 'camera'
        m = cmds.xform(cam, q=True, worldSpace=True, matrix=True)
        look = om.MVector(-m[8], -m[9], -m[10]).normal()   # kamera -Z yonune bakar
    except Exception:
        return None
    for side, axis in (('front', (0, 0, -1)), ('back', (0, 0, 1)), ('rightSide', (-1, 0, 0)),
                       ('leftSide', (1, 0, 0)), ('top', (0, -1, 0)), ('bottom', (0, 1, 0))):
        if look * om.MVector(*axis) > 0.999:
            return side
    return None


def view_pie(panel):
    now = _current_view(panel)
    return pie(_t('Görünüm'), [
        (_t('Sol'), lambda: view_axis(panel, 'leftSide'), now == 'leftSide'),
        (_t('Sağ'), lambda: view_axis(panel, 'rightSide'), now == 'rightSide'),
        (_t('Alt'), lambda: view_axis(panel, 'bottom'), now == 'bottom'),
        (_t('Üst'), lambda: view_axis(panel, 'top'), now == 'top'),
        (_t('Ön'), lambda: view_axis(panel, 'front'), now == 'front'),
        (_t('Arka'), lambda: view_axis(panel, 'back'), now == 'back'),
        (_t('Kamera'), lambda: camera_view(panel), now == 'camera'),
        (_t('Seçime odaklan'), lambda: frame_selected(panel)),
    ])


def shading_pie(panel):
    ed = _editor(panel)

    def mode(appearance, textures, rendered=False):
        cmds.modelEditor(ed, edit=True, displayAppearance=appearance, displayTextures=textures,
                         displayLights='all' if rendered else 'default', shadows=rendered)

    def lights():
        current = cmds.modelEditor(ed, q=True, displayLights=True)
        cmds.modelEditor(ed, edit=True, displayLights='default' if current != 'default' else 'all')

    wire = cmds.modelEditor(ed, q=True, displayAppearance=True) == 'wireframe'
    textures = cmds.modelEditor(ed, q=True, displayTextures=True)
    rendered = (not wire and cmds.modelEditor(ed, q=True, displayLights=True) == 'all'
                and cmds.modelEditor(ed, q=True, shadows=True))
    return pie(_t('Görüntü (Z)'), [
        (_t('Wireframe'), lambda: mode('wireframe', False), wire),
        (_t('Rendered (sahne ışıkları + gölge)'), lambda: mode('smoothShaded', True, rendered=True), rendered),
        (_t('Solid'), lambda: mode('smoothShaded', False), not wire and not textures and not rendered),
        (_t('Material (doku)'), lambda: mode('smoothShaded', True), not wire and textures and not rendered),
        (_t('X-Ray'), lambda: toggle_xray(panel), cmds.modelEditor(ed, q=True, xray=True)),
        (_t('Overlay aç/kapa'), lambda: toggle_overlays(panel), ed not in _state.get('overlays', {})),
        (_t('Wireframe üstte'), lambda: cmds.modelEditor(
            ed, edit=True, wireframeOnShaded=not cmds.modelEditor(ed, q=True, wireframeOnShaded=True)),
         cmds.modelEditor(ed, q=True, wireframeOnShaded=True)),
        (_t('Sahne ışıkları'), lights, cmds.modelEditor(ed, q=True, displayLights=True) == 'all'),
    ])


# ---------------------------------------------------------------- Shift+Space arac pie, quad view, overlays
def tool_pie():
    cur = cmds.currentCtx()

    def tool(ctx):
        return lambda: cmds.setToolTo(ctx)
    return pie(_t('Araçlar (Shift+Space)'), [
        (_t('Kutu seçimi'), tool('selectSuperContext'), cur == 'selectSuperContext'),
        (_t('Taşı'), tool('moveSuperContext'), cur == 'moveSuperContext'),
        (_t('Kement (Lasso)'), tool('lassoSelectContext'), cur == 'lassoSelectContext'),
        (_t('Döndür'), tool('RotateSuperContext'), cur == 'RotateSuperContext'),
        (_t('Fırça seçimi'), lambda: mel.eval('ArtPaintSelectTool'), cur == 'artSelectContext'),
        (_t('Ölçekle'), tool('scaleSuperContext'), cur == 'scaleSuperContext'),
        (_t('Bıçak (Multi-Cut)'), lambda: mel.eval('MultiCutTool')),
        (_t('Quad Draw (retopo)'), lambda: mel.eval('dR_quadDrawTool')),
    ])


def toggle_quad_view(panel):
    """Ctrl+Alt+Q: dortlu gorunum <-> tek gorunum."""
    visible = [p for p in (cmds.getPanel(visiblePanels=True) or []) if cmds.getPanel(typeOf=p) == 'modelPanel']
    if len(visible) > 1:
        mel.eval('setNamedPanelLayout "Single Perspective View"')
    else:
        mel.eval('setNamedPanelLayout "Four View"')


OVERLAY_FLAGS = ('grid', 'headsUpDisplay', 'cameras', 'lights', 'locators', 'manipulators', 'joints')


def toggle_overlays(panel):
    """Shift+Alt+Z: grid, HUD, kamera/isik/locator ikonlari ve manipulatorleri birlikte gizle / geri getir."""
    ed = _editor(panel)
    saved = _state.setdefault('overlays', {})
    if ed in saved:
        for flag, value in saved.pop(ed).items():
            cmds.modelEditor(ed, edit=True, **{flag: value})
        _msg(_t('Overlay: açık'))
        return
    saved[ed] = dict((f, cmds.modelEditor(ed, q=True, **{f: True})) for f in OVERLAY_FLAGS)
    for flag in OVERLAY_FLAGS:
        cmds.modelEditor(ed, edit=True, **{flag: False})
    _msg(_t('Overlay: kapalı'))


def cycle_workspace(step):
    """Ctrl+PageUp / PageDown: Maya calisma alanlari (Blender workspace sekmeleri)."""
    names = cmds.workspaceLayoutManager(listLayouts=True) or []
    if not names:
        return
    cur = cmds.workspaceLayoutManager(q=True, current=True)
    nxt = names[(names.index(cur) + step) % len(names)] if cur in names else names[0]
    cmds.workspaceLayoutManager(setCurrent=nxt)
    _msg(_t('Çalışma alanı: %s') % nxt)


def walk_navigation():
    """Shift+`: Blender Walk/Fly; Maya Walk Tool (WASD, fare ile bak)."""
    mel.eval('WalkTool')
    _msg(_t('Walk: WASD hareket, fare ile bak, Esc çıkış'))
