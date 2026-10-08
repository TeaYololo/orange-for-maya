# -*- coding: utf-8 -*-
"""Maya icin Blender tarzi kontroller.

Tuslar fiziksel konumdan (scan code) okunur, yani Turkce Q klavyede de
Blender'daki gibi calisir. Maya'nin kendi kisayollarina dokunulmaz;
bu modul kapatilinca her sey Maya varsayilanina doner.

    import blender_kontrol; blender_kontrol.install()    # ac
    blender_kontrol.uninstall()                          # kapat
    blender_kontrol.show_help()                          # kisayol listesi
"""
from __future__ import absolute_import, division, print_function

import functools
import math
import re
import sys

import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMayaUI as omui
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui2

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:  # Maya 2024 ve oncesi
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

Qt = QtCore.Qt
QEvent = QtCore.QEvent

EV_KEY_PRESS = QEvent.Type.KeyPress
EV_KEY_RELEASE = QEvent.Type.KeyRelease
EV_SHORTCUT = QEvent.Type.ShortcutOverride
EV_MPRESS = QEvent.Type.MouseButtonPress
EV_MRELEASE = QEvent.Type.MouseButtonRelease
EV_MMOVE = QEvent.Type.MouseMove
EV_MDBL = QEvent.Type.MouseButtonDblClick
EV_WHEEL = QEvent.Type.Wheel
KEY_EVENTS = (EV_SHORTCUT, EV_KEY_PRESS, EV_KEY_RELEASE)
MOUSE_EVENTS = (EV_MPRESS, EV_MRELEASE, EV_MMOVE, EV_MDBL, EV_WHEEL)

LMB = Qt.MouseButton.LeftButton
MMB = Qt.MouseButton.MiddleButton
RMB = Qt.MouseButton.RightButton
NOBTN = Qt.MouseButton.NoButton
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
ALT = Qt.KeyboardModifier.AltModifier
KEYPAD = Qt.KeyboardModifier.KeypadModifier
NOMOD = Qt.KeyboardModifier.NoModifier

# Windows scan code -> tus adi (klavye dilinden bagimsiz)
SCAN = {
    0x10: 'q', 0x11: 'w', 0x12: 'e', 0x13: 'r', 0x14: 't', 0x15: 'y', 0x16: 'u',
    0x17: 'i', 0x18: 'o', 0x19: 'p', 0x1E: 'a', 0x1F: 's', 0x20: 'd', 0x21: 'f',
    0x22: 'g', 0x23: 'h', 0x24: 'j', 0x25: 'k', 0x26: 'l', 0x2C: 'z', 0x2D: 'x',
    0x2E: 'c', 0x2F: 'v', 0x30: 'b', 0x31: 'n', 0x32: 'm',
    0x02: '1', 0x03: '2', 0x04: '3', 0x05: '4', 0x06: '5', 0x07: '6', 0x08: '7',
    0x09: '8', 0x0A: '9', 0x0B: '0', 0x29: 'grave', 0x0F: 'tab',
}
NUMPAD_SCAN = {
    0x52: '0', 0x4F: '1', 0x50: '2', 0x51: '3', 0x4B: '4', 0x4C: '5', 0x4D: '6',
    0x47: '7', 0x48: '8', 0x49: '9', 0x53: '.', 0x4E: '+', 0x4A: '-', 0x37: '*',
    0x35: '/',
}
QT_KEYS = {
    int(Qt.Key.Key_Delete): 'delete', int(Qt.Key.Key_Home): 'home',
    int(Qt.Key.Key_Space): 'space', int(Qt.Key.Key_Left): 'left',
    int(Qt.Key.Key_Right): 'right', int(Qt.Key.Key_Up): 'up',
    int(Qt.Key.Key_Down): 'down', int(Qt.Key.Key_F1): 'f1',
    int(Qt.Key.Key_F12): 'f12', int(Qt.Key.Key_Tab): 'tab', int(Qt.Key.Key_F2): 'f2',
    int(Qt.Key.Key_F3): 'f3', int(Qt.Key.Key_F9): 'f9',
}
for _c in range(26):
    QT_KEYS.setdefault(int(Qt.Key.Key_A) + _c, chr(ord('a') + _c))

COMP_TYPE = {'vertex': 'polymeshVertex', 'edge': 'polymeshEdge', 'face': 'polymeshFace'}
COMP_MASK = {'vertex': 'vertex', 'edge': 'edge', 'face': 'facet'}
COMP_SUFFIX = {'vertex': '.vtx[*]', 'edge': '.e[*]', 'face': '.f[*]'}
COMP_FILTER = {'vertex': 31, 'edge': 32, 'face': 34}

_state = {'comp': 'vertex', 'auto_ortho': set()}


# ---------------------------------------------------------------- yardimcilar
def _main_window():
    return wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)


def _msg(text):
    try:
        cmds.inViewMessage(assistMessage=text, position='topCenter', fade=True,
                           fadeStayTime=900, fadeOutTime=300)
    except Exception:
        print('[Blender] ' + text)


def _tip(text):
    """Farenin yaninda canli deger kutusu (headsUpMessage Turkce karakter gosteremiyor)."""
    QtWidgets.QToolTip.showText(QtGui.QCursor.pos() + QtCore.QPoint(20, 20), text)


def _warn(text):
    cmds.warning('[Blender] ' + text)


def undoable(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        cmds.undoInfo(openChunk=True, chunkName='blender_' + fn.__name__)
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            _warn('%s: %s' % (fn.__name__, exc))
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


def _exec_menu(menu):
    pos = QtGui.QCursor.pos()
    if hasattr(menu, 'exec'):
        getattr(menu, 'exec')(pos)
    else:
        menu.exec_(pos)


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


# ---------------------------------------------------------------- edit modu
def in_edit():
    return bool(cmds.selectMode(q=True, component=True) or cmds.ls(hilite=True))


def current_comp():
    ocm = not cmds.selectMode(q=True, component=True)
    for kind, flag in COMP_TYPE.items():
        try:
            if cmds.selectType(q=True, objectComponent=ocm, **{flag: True}):
                return kind
        except Exception:
            pass
    return _state['comp']


def enter_edit(kind=None):
    kind = kind or _state['comp']
    objs = cmds.ls(hilite=True, long=True) or _objs()
    objs = [o for o in objs if _shape_type(o) in ('mesh', 'nurbsCurve', 'nurbsSurface')]
    if not objs:
        _msg('Önce bir obje seç (sol tık)')
        return
    _state['comp'] = kind
    mask = COMP_MASK[kind]
    if _shape_type(objs[0]) != 'mesh':
        mask = 'controlVertex'
    keep = _sel() if in_edit() else []
    cmds.select(objs, replace=True)
    if not mel.eval('exists "doMenuComponentSelectionExt"'):
        mel.eval('source "dagMenuProc.mel"')  # Maya bunu ilk sag tik menusunde yukluyor
    mel.eval('doMenuComponentSelectionExt("%s", "%s", 0);' % (objs[0], mask))
    cmds.hilite(objs, replace=True)
    keep = cmds.filterExpand(keep, selectionMask=COMP_FILTER[kind]) if keep else None
    if keep:
        cmds.select(keep, replace=True)
    _msg('Edit modu: %s' % {'vertex': 'Köşe (1)', 'edge': 'Kenar (2)', 'face': 'Yüz (3)'}[kind])


def exit_edit():
    objs = cmds.ls(hilite=True, long=True) or cmds.ls(sl=True, objectsOnly=True, long=True) or []
    cmds.selectMode(object=True)
    if objs:
        cmds.hilite(objs, unHilite=True)
        objs = cmds.ls([cmds.listRelatives(o, parent=True, fullPath=True)[0]
                        if cmds.nodeType(o) != 'transform' else o for o in objs], long=True)
        cmds.select(objs, replace=True)
    _msg('Obje modu')


def toggle_edit():
    if in_edit():
        exit_edit()
    else:
        enter_edit()


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


# ---------------------------------------------------------------- silme
def delete_objects():
    objs = _objs()
    if objs:
        cmds.delete(objs)
        _msg('%d obje silindi' % len(objs))


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
    popup('Sil', [('&Köşeler', delete_verts), ('&Kenarlar', delete_edges),
                  ('&Yüzler', delete_faces), None, ('&Erit (Dissolve)', dissolve)])


# ---------------------------------------------------------------- objeler
def duplicate():
    if in_edit():
        if _comps('face'):
            mel.eval('DuplicateFace')
            start_modal('move')
        else:
            _msg('Kopyalamak için yüz seç (3)')
        return
    objs = _objs()
    if not objs:
        return
    new = cmds.duplicate(objs, returnRootsOnly=True)
    cmds.select(new, replace=True)
    start_modal('move')


def instance():
    objs = _objs()
    if objs:
        new = [cmds.instance(o)[0] for o in objs]
        cmds.select(new, replace=True)
        start_modal('move')


def join():
    meshes = [o for o in _objs() if _shape_type(o) == 'mesh']
    if len(meshes) < 2:
        _msg('Birleştirmek için en az 2 mesh seç')
        return
    active = meshes[-1].split('|')[-1]
    parent = cmds.listRelatives(meshes[-1], parent=True, fullPath=True)
    result = cmds.polyUnite(meshes, constructionHistory=True, mergeUVSets=1)[0]
    cmds.delete(result, constructionHistory=True)
    for obj in meshes:
        if cmds.objExists(obj) and not cmds.listRelatives(obj, children=True):
            cmds.delete(obj)
    if parent:
        result = cmds.parent(result, parent[0])[0]
    result = cmds.rename(result, active)
    cmds.select(result, replace=True)


def parent_to_active():
    objs = _objs()
    if len(objs) < 2:
        _msg('Önce çocukları, en son ebeveyni seç')
        return
    cmds.parent(objs[:-1], objs[-1])


def clear_parent():
    objs = _objs()
    if objs:
        cmds.parent(objs, world=True)


def _reset(attr, value):
    for obj in _objs():
        for axis in 'XYZ':
            plug = '%s.%s%s' % (obj, attr, axis)
            if cmds.getAttr(plug, settable=True):
                cmds.setAttr(plug, value)


def reset_location():
    _reset('translate', 0)


def reset_rotation():
    _reset('rotate', 0)


def reset_scale():
    _reset('scale', 1)


def apply_menu():
    def freeze(t, r, s):
        objs = _objs()
        if objs:
            cmds.makeIdentity(objs, apply=True, translate=t, rotate=r, scale=s, normal=0)
    popup('Uygula (Freeze)', [
        ('&Konum', lambda: freeze(True, False, False)),
        ('&Döndürme', lambda: freeze(False, True, False)),
        ('Ö&lçek', lambda: freeze(False, False, True)),
        ('Döndürme && Ölçek', lambda: freeze(False, True, True)),
        ('&Hepsi', lambda: freeze(True, True, True)),
        None,
        ('Geçmişi temizle (Delete History)', lambda: cmds.delete(_objs(), constructionHistory=True)),
    ])


def snap_menu():
    def to_origin():
        for obj in _objs():
            pivot = cmds.xform(obj, q=True, worldSpace=True, rotatePivot=True)
            cmds.move(-pivot[0], -pivot[1], -pivot[2], obj, relative=True, worldSpace=True)

    def to_grid():
        for obj in _objs():
            pos = cmds.xform(obj, q=True, worldSpace=True, rotatePivot=True)
            cmds.move(*[round(p) - p for p in pos] + [obj], relative=True, worldSpace=True)

    popup('Hizala (Snap)', [
        ('Seçimi &orijine taşı', to_origin),
        ('Seçimi &grid\'e yapıştır', to_grid),
        ('&Pivotu ortala', lambda: cmds.xform(_objs(), centerPivots=True)),
    ])


def hide_selected():
    if in_edit():
        if _sel():
            hide_components()
    elif _objs():
        cmds.hide(_objs())


def hide_unselected():
    if in_edit():
        hide_components(unselected=True)
    else:
        mel.eval('HideUnselectedObjects')


def _event_global_pos(ev):
    if hasattr(ev, 'globalPosition'):
        return ev.globalPosition().toPoint()
    return ev.globalPos()


def _is_startup_cam(node):
    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    return any(cmds.nodeType(s) == 'camera' and cmds.camera(s, q=True, startupCamera=True)
               for s in shapes)


def unhide_all():
    shown = 0
    for node in cmds.ls(type='transform', long=True) or []:
        if not cmds.getAttr(node + '.visibility') and not _is_startup_cam(node):
            try:
                cmds.setAttr(node + '.visibility', True)
                shown += 1
            except Exception:
                pass
    try:
        mel.eval('ShowAllComponents')
    except Exception:
        pass
    _msg('%d obje gösterildi' % shown)


def add_menu():
    def add(fn):
        def run():
            if in_edit():
                exit_edit()
            result = fn()
            if result:
                node = result[0] if isinstance(result, (list, tuple)) else result
                if cmds.nodeType(node) != 'transform':
                    node = (cmds.listRelatives(node, parent=True) or [node])[0]
                p = cursor_pos()
                cmds.xform(node, worldSpace=True, translation=(p.x, p.y, p.z))   # Blender: 3D imlece
                cmds.select(node, replace=True)
        return run
    popup('Ekle', [
        ('&Küp', add(cmds.polyCube)),
        ('&Düzlem (Plane)', add(cmds.polyPlane)),
        ('&Küre (UV Sphere)', add(cmds.polySphere)),
        ('&Silindir', add(cmds.polyCylinder)),
        ('K&oni', add(cmds.polyCone)),
        ('&Torus', add(cmds.polyTorus)),
        None,
        ('Çember (eğri)', add(cmds.circle)),
        ('Eğri çiz (CV Curve)', lambda: mel.eval('CVCurveTool')),
        None,
        ('Boş obje (Empty / Locator)', add(cmds.spaceLocator)),
        ('Boş grup', add(lambda: cmds.group(empty=True, name='Empty'))),
        None,
        ('&Kamera', add(cmds.camera)),
        ('Işık: Nokta (Point)', add(cmds.pointLight)),
        ('Işık: Güneş (Directional)', add(cmds.directionalLight)),
        ('Işık: Spot', add(cmds.spotLight)),
        ('Işık: Alan (Area)', add(lambda: cmds.shadingNode('areaLight', asLight=True))),
    ])


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


def extrude():
    if not in_edit():
        _msg('Extrude için Tab ile edit moduna gir')
        return
    kind = current_comp()
    if kind == 'face' and _comps('face'):
        faces = _comps('face')
        normal = _face_normal(faces)
        nodes = cmds.polyExtrudeFacet(faces, keepFacesTogether=True)
        start_modal('attr_axis', nodes=nodes, attr='localTranslateZ', axis=normal)
    elif kind == 'edge' and _comps('edge'):
        cmds.polyExtrudeEdge(_comps('edge'), keepFacesTogether=True)
        start_modal('move', keep_undo=True)
    elif kind == 'vertex' and _comps('vertex'):
        cmds.polyExtrudeVertex(_comps('vertex'))
    else:
        _msg('Önce bir şey seç')


def inset_or_key():
    if not in_edit():
        insert_key()
        return
    faces = _comps('face')
    if not faces:
        _msg('Inset için yüz seç (3)')
        return
    nodes = cmds.polyExtrudeFacet(faces, keepFacesTogether=True, offset=0)
    start_modal('attr_dist', nodes=nodes, attr='offset')


def bevel():
    if not in_edit():
        return
    comps = _comps('edge') or _comps('face') or _comps('vertex')
    if not comps:
        _msg('Bevel için kenar seç (2)')
        return
    nodes = cmds.polyBevel3(comps, offsetAsFraction=False, offset=0.0, segments=1,
                            mitering=0, chamfer=True)
    start_modal('attr_dist', nodes=nodes, attr='offset', wheel_attr='segments')


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
        _msg('Doldurmak için kenar ya da köşe seç')


def connect_verts():
    if _comps('vertex'):
        cmds.polyConnectComponents(_comps('vertex'))


def merge_menu():
    def by_distance():
        verts = cmds.polyListComponentConversion(_sel(), toVertex=True)
        if verts:
            before = cmds.polyEvaluate(verts[0].split('.')[0], vertex=True)
            cmds.polyMergeVertex(verts, distance=0.001)
            after = cmds.polyEvaluate(cmds.ls(sl=True, objectsOnly=True)[0], vertex=True)
            _msg('%d köşe silindi' % (before - after))
    popup('Birleştir (Merge)', [
        ('&Merkezde', lambda: mel.eval('MergeToCenter')),
        ('Mesafeye &göre', by_distance),
    ])


def separate_menu():
    popup('Ayır', [
        ('&Seçimi ayır', lambda: mel.eval('ExtractFace')),
        ('&Gevşek parçalara göre', lambda: cmds.polySeparate(cmds.ls(hilite=True) or _objs())),
    ])


def recalc_normals():
    targets = _comps('face') or cmds.ls(hilite=True) or _objs()
    if targets:
        cmds.polyNormal(targets, normalMode=2, userNormalMode=0)


def flip_normals():
    targets = _comps('face') or cmds.ls(hilite=True) or _objs()
    if targets:
        cmds.polyNormal(targets, normalMode=0, userNormalMode=0)


def subdiv_level(level):
    objs = cmds.ls(hilite=True, long=True) or _objs()
    for obj in objs:
        for shape in cmds.listRelatives(obj, shapes=True, type='mesh', fullPath=True) or []:
            cmds.setAttr(shape + '.displaySmoothMesh', 2 if level else 0)
            if level:
                cmds.setAttr(shape + '.smoothLevel', level)
    _msg('Yumuşak önizleme: %s' % (level or 'kapalı'))


def toggle_soft_select():
    state = not cmds.softSelect(q=True, softSelectEnabled=True)
    cmds.softSelect(edit=True, softSelectEnabled=state)
    _msg('Proportional (Soft Select): %s' % ('açık  -  yarıçap: B + sürükle' if state else 'kapalı'))


# ---------------------------------------------------------------- animasyon
def insert_key():
    objs = _objs()
    if objs:
        cmds.setKeyframe(objs, attribute=['translate', 'rotate', 'scale'])
        _msg('Keyframe eklendi (kare %d)' % cmds.currentTime(q=True))


def clear_key():
    objs = _objs()
    if objs:
        t = cmds.currentTime(q=True)
        cmds.cutKey(objs, time=(t, t), clear=True)
        _msg('Keyframe silindi')


def play_toggle():
    cmds.play(state=not cmds.play(q=True, state=True))


def frame_step(step):
    cmds.currentTime(cmds.currentTime(q=True) + step)


def frame_jump(end):
    t = cmds.playbackOptions(q=True, maxTime=True) if end else cmds.playbackOptions(q=True, minTime=True)
    cmds.currentTime(t)


def key_jump(forward):
    t = cmds.findKeyframe(timeSlider=True, which='next' if forward else 'previous')
    cmds.currentTime(t)


# ---------------------------------------------------------------- gorunum
def _cam(panel):
    cam = cmds.modelPanel(panel, q=True, camera=True)
    if cmds.nodeType(cam) == 'camera':
        cam = cmds.listRelatives(cam, parent=True, fullPath=True)[0]
    return cam


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


def toggle_ortho(panel):
    cam = _cam(panel)
    _state['auto_ortho'].discard(cam)
    ortho = not cmds.camera(_cam_shape(cam), q=True, orthographic=True)
    _set_ortho(cam, ortho)
    _msg('Ortografik' if ortho else 'Perspektif')


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
        _msg('Sahnede kamera yok (Shift+A > Kamera)')
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
        _msg('Önce bir kamera seç')
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
        cmds.dolly(cam, distance=coi * 0.2 * direction)


def toggle_isolate(panel):
    state = cmds.isolateSelect(panel, q=True, state=True)
    mel.eval('enableIsolateSelect "%s" %d;' % (panel, 0 if state else 1))
    _msg('Local view: %s' % ('kapalı' if state else 'açık'))


def view_menu(panel):
    popup('Görünüm', [
        ('Ö&n (Numpad 1)', lambda: view_axis(panel, 'front')),
        ('&Arka (Ctrl+Numpad 1)', lambda: view_axis(panel, 'back')),
        ('&Sağ (Numpad 3)', lambda: view_axis(panel, 'rightSide')),
        ('So&l (Ctrl+Numpad 3)', lambda: view_axis(panel, 'leftSide')),
        ('Ü&st (Numpad 7)', lambda: view_axis(panel, 'top')),
        ('Al&t (Ctrl+Numpad 7)', lambda: view_axis(panel, 'bottom')),
        None,
        ('&Kamera (Numpad 0)', lambda: camera_view(panel)),
        ('Seçime &odaklan (Numpad .)', lambda: frame_selected(panel)),
        ('&Hepsini göster (Home)', lambda: frame_all(panel)),
        ('&Persp / Ortho (Numpad 5)', lambda: toggle_ortho(panel)),
        ('&Local view (Numpad /)', lambda: toggle_isolate(panel)),
        ('Kamerayı görünüme hizala (Ctrl+Alt+Numpad 0)', lambda: align_camera_to_view(panel)),
    ])


def _editor(panel):
    return cmds.modelPanel(panel, q=True, modelEditor=True)


def shading_menu(panel):
    ed = _editor(panel)

    def mode(appearance, textures):
        cmds.modelEditor(ed, edit=True, displayAppearance=appearance, displayTextures=textures)

    popup('Görüntü (Shading)', [
        ('&Wireframe', lambda: mode('wireframe', False)),
        ('&Solid', lambda: mode('smoothShaded', False)),
        ('&Material (doku)', lambda: mode('smoothShaded', True)),
        None,
        ('&X-Ray aç/kapa (Alt+Z)', lambda: toggle_xray(panel)),
        ('Wireframe üstte aç/kapa', lambda: cmds.modelEditor(
            ed, edit=True, wireframeOnShaded=not cmds.modelEditor(ed, q=True, wireframeOnShaded=True))),
    ])


def toggle_wireframe(panel):
    ed = _editor(panel)
    wire = cmds.modelEditor(ed, q=True, displayAppearance=True) == 'wireframe'
    cmds.modelEditor(ed, edit=True, displayAppearance='smoothShaded' if wire else 'wireframe')


def toggle_xray(panel):
    ed = _editor(panel)
    cmds.modelEditor(ed, edit=True, xray=not cmds.modelEditor(ed, q=True, xray=True))


def maximize_panel(panel):
    mel.eval('panePop')


# ---------------------------------------------------------------- modal G/R/S
class HintBar(object):
    """Blender'in alttaki durum cubugu gibi: viewport'un altinda kisayol ipucu."""

    def __init__(self):
        self.label = QtWidgets.QLabel()
        self.label.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint |
                                  Qt.WindowType.WindowTransparentForInput | Qt.WindowType.NoDropShadowWindowHint)
        self.label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setStyleSheet(
            'QLabel { background: rgba(28, 28, 28, 230); color: #dddddd; padding: 6px 10px;'
            ' border-top: 2px solid #e8a33d; font-size: 12px; }')

    def show(self, widget, html):
        self.label.setText(html)
        width = max(200, widget.width() - 16)
        self.label.setFixedWidth(width)
        self.label.adjustSize()
        pos = widget.mapToGlobal(QtCore.QPoint(8, widget.height() - self.label.height() - 8))
        self.label.move(pos)
        if not self.label.isVisible():
            self.label.show()

    def hide(self):
        self.label.hide()


_hint_bar = []


def hint_bar():
    if not _hint_bar:
        _hint_bar.append(HintBar())
    return _hint_bar[0]


TRANSFORMS = ('move', 'rotate', 'scale', 'trackball')


class Modal(object):
    """Blender'daki G/R/S/E/I/Ctrl+B gibi fareyle calisan islemler."""

    TITLES = {
        'move': 'TAŞI',
        'rotate': 'DÖNDÜR',
        'trackball': 'SERBEST DÖNDÜR',
        'scale': 'ÖLÇEKLE',
        'attr_axis': 'EXTRUDE',
        'attr_dist': 'AYARLA',
    }

    def __init__(self, kind, panel, nodes=None, attr=None, axis=None, wheel_attr=None,
                 keep_undo=False):
        self.kind = kind
        self.panel = panel
        self.nodes = nodes or []
        self.attr = attr
        self.fixed_axis = axis
        self.wheel_attr = wheel_attr
        self.constraint = None      # (eksen, 'global' | 'local', duzlem_mi)
        self.numeric = ''
        self.applied = None
        self.prev_angle = None
        self.total_angle = 0.0
        self.track = []             # serbest dondurme adimlari (geri almak icin)
        self.auto_start = None      # orta tusla otomatik eksen
        self.timer = None
        self.chunk_open = keep_undo
        self.dirty = keep_undo      # geri alinacak bir sey var mi (bos undo onceki islemi siler)
        self.last_value = ''

    # -- kurulum
    def start(self):
        self.sel = _sel()
        if not self.sel and not self.nodes:
            _msg('Önce bir şey seç')
            return False
        self.edit = in_edit()
        self.view = omui2.M3dView.getM3dViewFromModelPanel(self.panel)
        self.widget = wrapInstance(int(self.view.widget()), QtWidgets.QWidget)
        cam = om.MFnCamera(self.view.getCamera())
        self.view_dir = cam.viewDirection(om.MSpace.kWorld).normal()
        self.right_dir = cam.rightDirection(om.MSpace.kWorld).normal()
        self.up_dir = cam.upDirection(om.MSpace.kWorld).normal()
        self.center = self._center()
        self.local_axes = self._local_axes()
        self.buckets = self._soft_buckets() if self.kind in TRANSFORMS else None
        self.raw_last = QtGui.QCursor.pos()
        self.eff = QtCore.QPointF(self.raw_last)
        self.start_pos = QtCore.QPointF(self.eff)
        self.pivot_2d = self._to_screen(self.center)
        if self.kind in TRANSFORMS:
            self._reset_applied()
        if not self.chunk_open:
            cmds.undoInfo(openChunk=True, chunkName='blender_modal')
            self.chunk_open = True
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(15)
        self.update(force=True)
        return True

    def _center(self):
        if self.kind in ('attr_axis', 'attr_dist') or self.edit:
            verts = cmds.polyListComponentConversion(self.sel, toVertex=True) or self.sel
            pts = cmds.xform(verts, q=True, worldSpace=True, translation=True) or [0, 0, 0]
        else:
            pts = []
            for obj in cmds.ls(self.sel, type='transform', long=True) or self.sel:
                pts += cmds.xform(obj, q=True, worldSpace=True, rotatePivot=True)
        n = max(1, len(pts) // 3)
        return om.MPoint(sum(pts[0::3]) / n, sum(pts[1::3]) / n, sum(pts[2::3]) / n)

    def _local_axes(self):
        objs = cmds.ls(hilite=True, long=True) or cmds.ls(self.sel, objectsOnly=True, long=True) or []
        unit = [om.MVector(1, 0, 0), om.MVector(0, 1, 0), om.MVector(0, 0, 1)]
        if not objs:
            return unit
        obj = objs[0]
        if cmds.nodeType(obj) != 'transform':
            obj = (cmds.listRelatives(obj, parent=True, fullPath=True) or [obj])[0]
        try:
            m = cmds.xform(obj, q=True, worldSpace=True, matrix=True)
        except Exception:
            return unit
        return [om.MVector(m[0], m[1], m[2]).normal(), om.MVector(m[4], m[5], m[6]).normal(),
                om.MVector(m[8], m[9], m[10]).normal()]

    def _soft_buckets(self):
        """Soft select acikken koseleri agirliklarina gore grupla.

        Maya'nin move/rotate/scale komutlari soft select'i uygulamiyor; her
        agirlik grubunu kendi oraninda donusturerek Blender'daki proportional
        editing'i taklit ediyoruz.
        """
        if not (self.edit and cmds.softSelect(q=True, softSelectEnabled=True)):
            return None
        suffix = {om.MFn.kMeshVertComponent: 'vtx', om.MFn.kMeshEdgeComponent: 'e',
                  om.MFn.kMeshPolygonComponent: 'f', om.MFn.kCurveCVComponent: 'cv'}
        groups = {}
        sel = om.MGlobal.getRichSelection().getSelection()
        for i in range(sel.length()):
            try:
                dag, comp = sel.getComponent(i)
            except Exception:
                continue
            if comp.isNull() or comp.apiType() not in suffix:
                continue
            fn = om.MFnSingleIndexedComponent(comp)
            path = dag.fullPathName()
            name = suffix[comp.apiType()]
            for k, idx in enumerate(fn.getElements()):
                w = fn.weight(k).influence if fn.hasWeights else 1.0
                if w < 1e-3:
                    continue
                groups.setdefault(round(w * 32) / 32.0, []).append('%s.%s[%d]' % (path, name, idx))
        return [(comps, w) for w, comps in sorted(groups.items())] or None

    def _targets(self):
        return self.buckets or [(self.sel, 1.0)]

    def _do_move(self, d):
        self.dirty = True
        for comps, w in self._targets():
            cmds.move(d.x * w, d.y * w, d.z * w, comps, relative=True, worldSpace=True)

    def _do_scale(self, old, new):
        self.dirty = True
        for comps, w in self._targets():
            f = (1.0 + (new - 1.0) * w) / (1.0 + (old - 1.0) * w)
            if abs(f - 1.0) > 1e-9:
                cmds.scale(*self._scale_vector(f) + [comps], **self._scale_kwargs())

    def _reset_applied(self):
        self.applied = {'move': om.MVector(), 'rotate': 0.0, 'scale': 1.0,
                        'trackball': None}[self.kind]
        self.prev_angle = None
        self.total_angle = 0.0
        self.track = []
        self.tb_last = QtCore.QPointF(self.eff) if hasattr(self, 'eff') else None

    # -- ekran / dunya donusumleri
    def _port(self, global_pos):
        local = self.widget.mapFromGlobal(QtCore.QPointF(global_pos))
        sx = self.view.portWidth() / float(max(1, self.widget.width()))
        sy = self.view.portHeight() / float(max(1, self.widget.height()))
        return local.x() * sx, self.view.portHeight() - local.y() * sy

    def _to_screen(self, point):
        res = self.view.worldToView(point)
        return float(res[0]), float(res[1])

    def _ray(self, global_pos):
        x, y = self._port(global_pos)
        near, far = om.MPoint(), om.MPoint()
        self.view.viewToWorld(int(round(x)), int(round(y)), near, far)
        return near, om.MVector(far - near).normal()

    def _plane_hit(self, global_pos, normal):
        origin, direction = self._ray(global_pos)
        denom = direction * normal
        if abs(denom) < 1e-8:
            return None
        t = (om.MVector(self.center - origin) * normal) / denom
        return origin + direction * t

    def _axis_vector(self):
        if self.fixed_axis is not None:
            return self.fixed_axis
        if self.constraint is None:
            return None
        axis, space, _plane = self.constraint
        idx = 'xyz'.index(axis)
        if space == 'local':
            return om.MVector(self.local_axes[idx])
        return om.MVector(*[1.0 if i == idx else 0.0 for i in range(3)])

    def _plane(self):
        return bool(self.constraint and self.constraint[2])

    def _pixels_per_unit(self):
        a = self._to_screen(self.center)
        b = self._to_screen(self.center + self.right_dir)
        return max(1e-3, math.hypot(b[0] - a[0], b[1] - a[1]))

    def _number(self):
        expr = self.numeric.replace(',', '.')
        if not expr or not re.match(r'^[0-9.+\-*/() ]+$', expr):
            return None
        try:
            return float(eval(expr, {'__builtins__': {}}, {}))
        except Exception:
            return None

    @staticmethod
    def _mods():
        return QtWidgets.QApplication.keyboardModifiers()

    def _ctrl(self):
        return bool(self._mods() & CTRL)

    @staticmethod
    def _grid_step():
        try:
            return cmds.grid(q=True, spacing=True) / max(1, cmds.grid(q=True, divisions=True))
        except Exception:
            return 1.0

    # -- hesaplama
    def _move_value(self, pos):
        axis = self._axis_vector()
        plane = self._plane()
        num = self._number()
        if num is not None:
            if axis is None:
                return om.MVector(num, 0, 0)
            if plane:
                others = [om.MVector(*[1.0 if i == j else 0.0 for i in range(3)])
                          for j in range(3) if j != 'xyz'.index(self.constraint[0])]
                if self.constraint[1] == 'local':
                    others = [self.local_axes[j] for j in range(3) if j != 'xyz'.index(self.constraint[0])]
                return (others[0] + others[1]) * num
            return axis * num
        if axis is None:
            normal = self.view_dir
        elif plane:
            normal = axis if abs(axis * self.view_dir) > 0.05 else self.view_dir
        else:
            normal = axis ^ (self.view_dir ^ axis)
            normal = normal.normal() if normal.length() > 1e-6 else self.view_dir
        a = self._plane_hit(self.start_pos, normal)
        b = self._plane_hit(pos, normal)
        if a is None or b is None:
            return None
        delta = om.MVector(b - a)
        if axis is not None and not plane:
            amount = delta * axis
            if self._ctrl():
                step = self._grid_step()
                amount = round(amount / step) * step
            return axis * amount
        if plane:
            delta = delta - axis * (delta * axis)
        if self._ctrl():
            step = self._grid_step()
            delta = om.MVector(*[round(v / step) * step for v in (delta.x, delta.y, delta.z)])
        return delta

    def _rotate_value(self, pos):
        """Eksen etrafinda uygulanacak isaretli aci (radyan)."""
        num = self._number()
        if num is not None:
            return math.radians(num)
        return self._mouse_angle(pos) * self._rotation_axis()[1]

    def _mouse_angle(self, pos):
        x, y = self._port(pos)
        angle = math.atan2(y - self.pivot_2d[1], x - self.pivot_2d[0])
        if self.prev_angle is None:
            sx, sy = self._port(self.start_pos)
            self.prev_angle = math.atan2(sy - self.pivot_2d[1], sx - self.pivot_2d[0])
        diff = (angle - self.prev_angle + math.pi) % (2 * math.pi) - math.pi
        self.prev_angle = angle
        self.total_angle += diff
        value = self.total_angle
        if self._ctrl():
            value = math.radians(round(math.degrees(value) / 5.0) * 5.0)
        return value

    def _rotation_axis(self):
        to_viewer = -self.view_dir
        axis = self._axis_vector()
        if axis is None:
            return to_viewer, 1.0
        return axis, (1.0 if axis * to_viewer >= 0 else -1.0)

    def _scale_value(self, pos):
        num = self._number()
        if num is not None:
            return num if abs(num) > 1e-4 else 1e-4
        sx, sy = self._port(self.start_pos)
        x, y = self._port(pos)
        d0 = max(1.0, math.hypot(sx - self.pivot_2d[0], sy - self.pivot_2d[1]))
        value = math.hypot(x - self.pivot_2d[0], y - self.pivot_2d[1]) / d0
        if self._ctrl():
            value = round(value * 10) / 10.0
        return max(0.001, value)

    def _dist_value(self, pos):
        num = self._number()
        if num is not None:
            return max(0.0, num)
        sx, sy = self._port(self.start_pos)
        x, y = self._port(pos)
        d0 = math.hypot(sx - self.pivot_2d[0], sy - self.pivot_2d[1])
        d1 = math.hypot(x - self.pivot_2d[0], y - self.pivot_2d[1])
        value = abs(d1 - d0) / self._pixels_per_unit()
        if self._ctrl():
            value = round(value * 10) / 10.0
        return value

    # -- uygulama
    def _scale_vector(self, factor):
        if self.constraint is None:
            return [factor] * 3
        idx = 'xyz'.index(self.constraint[0])
        if self._plane():
            return [1.0 if i == idx else factor for i in range(3)]
        return [factor if i == idx else 1.0 for i in range(3)]

    def _scale_kwargs(self):
        kwargs = {'relative': True, 'pivot': (self.center.x, self.center.y, self.center.z)}
        if self.edit:
            if self.constraint and self.constraint[1] == 'local':
                kwargs['objectSpace'] = True
            else:
                kwargs['worldSpace'] = True
        return kwargs

    def _rotate_about(self, axis, angle):
        if abs(angle) < 1e-9:
            return
        self.dirty = True
        for comps, w in self._targets():
            euler = om.MQuaternion(angle * w, axis).asEulerRotation()
            cmds.rotate(math.degrees(euler.x), math.degrees(euler.y), math.degrees(euler.z),
                        comps, relative=True, worldSpace=True,
                        pivot=(self.center.x, self.center.y, self.center.z))

    def _update_eff(self):
        """Shift basiliyken fare 10 kat yavas etki eder (hassas mod)."""
        raw = QtGui.QCursor.pos()
        d = raw - self.raw_last
        self.raw_last = raw
        factor = 0.1 if (self._mods() & SHIFT) else 1.0
        self.eff = QtCore.QPointF(self.eff.x() + d.x() * factor, self.eff.y() + d.y() * factor)
        return d.x() != 0 or d.y() != 0

    def _auto_constraint(self):
        """Orta tusla surukleyince fareye en uygun ekseni sec."""
        dx = self.eff.x() - self.auto_start.x()
        dy = -(self.eff.y() - self.auto_start.y())
        length = math.hypot(dx, dy)
        if length < 12:
            return
        space = self.constraint[1] if self.constraint else 'global'
        best, best_score = None, -1.0
        for i, axis in enumerate('xyz'):
            vec = self.local_axes[i] if space == 'local' else om.MVector(*[1.0 if j == i else 0.0 for j in range(3)])
            a = self._to_screen(self.center)
            b = self._to_screen(self.center + vec)
            sx, sy = b[0] - a[0], b[1] - a[1]
            slen = math.hypot(sx, sy)
            if slen < 1e-6:
                continue
            if self.kind == 'move':
                score = abs(sx * dx + sy * dy) / (slen * length)
            else:  # dondurmede ekrana en dik eksen
                score = 1.0 - slen / max(1e-6, self._pixels_per_unit())
            if score > best_score:
                best, best_score = axis, score
        if best and (not self.constraint or self.constraint[0] != best or self.constraint[2]):
            self._revert()
            self.constraint = (best, space, False)

    def update(self, force=False):
        moved = self._update_eff()
        if not force and not moved:
            return
        pos = self.eff
        try:
            if self.auto_start is not None and self.kind in TRANSFORMS:
                self._auto_constraint()
            if self.kind == 'move':
                value = self._move_value(pos)
                if value is None:
                    return
                d = value - self.applied
                if d.length() > 1e-9:
                    self._do_move(d)
                    self.applied = value
                self.last_value = 'D: %.3f  %.3f  %.3f' % (value.x, value.y, value.z)
            elif self.kind == 'rotate':
                value = self._rotate_value(pos)
                self._rotate_about(self._rotation_axis()[0], value - self.applied)
                self.applied = value
                self.last_value = '%.1f°' % math.degrees(value)
            elif self.kind == 'trackball':
                dx = pos.x() - self.tb_last.x()
                dy = -(pos.y() - self.tb_last.y())
                self.tb_last = QtCore.QPointF(pos)
                for axis, angle in ((self.up_dir, dx * 0.01), (self.right_dir, -dy * 0.01)):
                    if abs(angle) > 1e-9:
                        self._rotate_about(axis, angle)
                        self.track.append((axis, angle))
                self.last_value = ''
            elif self.kind == 'scale':
                value = self._scale_value(pos)
                if abs(value - self.applied) > 1e-9:
                    self._do_scale(self.applied, value)
                    self.applied = value
                self.last_value = '%.3f' % value
            elif self.kind == 'attr_axis':
                value = self._move_value(pos)
                if value is None:
                    return
                amount = value * self.fixed_axis
                for node in self.nodes:
                    cmds.setAttr('%s.%s' % (node, self.attr), amount)
                self.last_value = '%.3f' % amount
            elif self.kind == 'attr_dist':
                value = self._dist_value(pos)
                for node in self.nodes:
                    cmds.setAttr('%s.%s' % (node, self.attr), value)
                self.last_value = '%.3f' % value
            self._show()
        except Exception as exc:
            _warn('modal: %s' % exc)
            self.finish(False)

    def _revert(self):
        """Eksen/mod degisince o ana kadar yapilani geri al."""
        if self.kind == 'rotate':
            self._rotate_about(self._rotation_axis()[0], -self.applied)
        elif self.kind == 'trackball':
            for axis, angle in reversed(self.track):
                self._rotate_about(axis, -angle)
        elif self.kind == 'scale' and abs(self.applied - 1.0) > 1e-9:
            self._do_scale(self.applied, 1.0)
        elif self.kind == 'move' and self.applied.length() > 1e-9:
            self._do_move(-self.applied)
        self._reset_applied()

    # -- ipucu
    def _show(self):
        title = self.TITLES[self.kind]
        if self.constraint:
            axis, space, plane = self.constraint
            what = ('%s hariç düzlem' if plane else '%s ekseni') % axis.upper()
            title += '  ·  %s (%s)' % (what, 'lokal' if space == 'local' else 'global')
        value = self.last_value
        if self.numeric:
            value = '[ %s ]   %s' % (self.numeric, value)
        if self._mods() & SHIFT:
            title += '  ·  hassas'
        keys = []
        if self.kind in TRANSFORMS:
            keys += ['<b>X Y Z</b> eksen (2. kez: lokal)', '<b>Shift+X</b> düzlem',
                     '<b>Orta tuş</b> otomatik eksen', '<b>Shift</b> hassas', '<b>Ctrl</b> adımlı',
                     '<b>G R S</b> değiştir']
            if self.kind == 'move' and self.edit:
                keys.append('<b>G G</b> kaydır (slide)')
            if self.kind == 'rotate':
                keys.append('<b>R R</b> serbest')
            if cmds.softSelect(q=True, softSelectEnabled=True):
                keys.append('<b>Tekerlek</b> proportional alanı')
        else:
            keys += ['<b>Ctrl</b> adımlı']
        if self.wheel_attr:
            keys.append('<b>Tekerlek</b> segment')
        keys += ['<b>Sayı</b> yaz', '<b>Sol tık/Enter</b> onay', '<b>Sağ tık/Esc</b> iptal']
        html = ('<span style="color:#e8a33d; font-weight:bold">%s</span>'
                '&nbsp;&nbsp;&nbsp;<span style="color:#ffffff">%s</span><br>%s'
                % (title, value, '&nbsp;&nbsp;·&nbsp;&nbsp;'.join(keys)))
        try:
            hint_bar().show(self.widget, html)
        except Exception:
            _tip('%s  %s' % (title, value))

    # -- olaylar
    def _switch(self, name):
        target = {'g': 'move', 'r': 'rotate', 's': 'scale'}[name]
        if target == self.kind:
            if name == 'g' and self.edit:
                self.finish(False)
                try:
                    mel.eval('SlideEdgeTool')
                    _msg('Kaydır (Slide): kenarı sürükle')
                except Exception as exc:
                    _warn(str(exc))
                return
            if name == 'r':
                self._revert()
                self.kind = 'trackball'
                self._reset_applied()
                self.update(force=True)
            return
        self._revert()
        self.kind = target
        self.numeric = ''
        self.start_pos = QtCore.QPointF(self.eff)
        self.pivot_2d = self._to_screen(self.center)
        self._reset_applied()
        self.update(force=True)

    def _set_constraint(self, axis, plane):
        self._revert()
        c = self.constraint
        if c is None or c[0] != axis or c[2] != plane:
            self.constraint = (axis, 'global', plane)
        elif c[1] == 'global':
            self.constraint = (axis, 'local', plane)
        else:
            self.constraint = None
        self.update(force=True)

    def _wheel(self, up):
        if self.wheel_attr:
            for node in self.nodes:
                plug = '%s.%s' % (node, self.wheel_attr)
                cmds.setAttr(plug, max(1, cmds.getAttr(plug) + (1 if up else -1)))
            self.last_value = 'Segment: %d' % cmds.getAttr('%s.%s' % (self.nodes[0], self.wheel_attr))
            self._show()
        elif self.kind in TRANSFORMS and cmds.softSelect(q=True, softSelectEnabled=True):
            self._revert()
            dist = cmds.softSelect(q=True, softSelectDistance=True)
            cmds.softSelect(edit=True, softSelectDistance=dist * (1.15 if up else 1 / 1.15))
            self.buckets = self._soft_buckets()
            self.last_value = 'Proportional alan: %.2f' % cmds.softSelect(q=True, softSelectDistance=True)
            self.update(force=True)

    def key(self, ev, etype):
        if etype == EV_SHORTCUT:
            ev.accept()
            return True
        key = int(ev.key())
        if etype == EV_KEY_RELEASE:
            if key == int(Qt.Key.Key_Shift):
                self._show()
            return True
        if etype != EV_KEY_PRESS:
            return True
        name = SCAN.get(ev.nativeScanCode() & 0xFF)
        text = ev.text()
        if key in (int(Qt.Key.Key_Return), int(Qt.Key.Key_Enter), int(Qt.Key.Key_Space)):
            self.finish(True)
        elif key == int(Qt.Key.Key_Escape):
            self.finish(False)
        elif key == int(Qt.Key.Key_Shift):
            self._show()
        elif name in ('x', 'y', 'z') and self.kind in TRANSFORMS and self.kind != 'trackball':
            self._set_constraint(name, bool(ev.modifiers() & SHIFT))
        elif name in ('g', 'r', 's') and self.kind in TRANSFORMS and not ev.isAutoRepeat():
            self._switch(name)
        elif key in (int(Qt.Key.Key_PageUp), int(Qt.Key.Key_PageDown)):
            self._wheel(key == int(Qt.Key.Key_PageUp))
        elif key == int(Qt.Key.Key_Backspace):
            self.numeric = '' if ev.modifiers() & CTRL else self.numeric[:-1]
            self._revert_for_numeric()
        elif text and text in '0123456789.,+-*/()':
            self.numeric += text
            self._revert_for_numeric()
        return True

    def _revert_for_numeric(self):
        if self.kind == 'trackball':
            return
        self.update(force=True)

    def mouse(self, ev, etype):
        if etype == EV_MPRESS:
            if ev.button() == LMB:
                self.finish(True)
            elif ev.button() == RMB:
                self.finish(False)
            elif ev.button() == MMB and self.kind in TRANSFORMS and self.kind != 'trackball':
                self.auto_start = QtCore.QPointF(self.eff)
        elif etype == EV_MRELEASE and ev.button() == MMB:
            self.auto_start = None
            self._show()
        elif etype == EV_WHEEL:
            self._wheel(ev.angleDelta().y() > 0)
        return etype != EV_MMOVE

    def finish(self, ok):
        if self.timer:
            self.timer.stop()
            self.timer = None
        try:
            hint_bar().hide()
        except Exception:
            pass
        QtWidgets.QToolTip.hideText()
        _current_filter_set_modal(None)
        if self.chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.chunk_open = False
            if not ok and self.dirty:
                cmds.undo()
        cmds.refresh()


def _abort_modal(*_):
    """Suren G/R/S, loop cut vb. islemi geri alma yapmadan kapat (sahne degistiyse undo tehlikeli)."""
    filt = _filter()
    modal = filt.modal if filt else None
    if modal is None:
        return
    if getattr(modal, 'timer', None):
        modal.timer.stop()
        modal.timer = None
    for holder in (_overlay, _hint_bar):
        for w in holder:
            try:
                w.hide()
            except Exception:
                pass
    QtWidgets.QToolTip.hideText()
    filt.modal = None
    if getattr(modal, 'chunk_open', False):
        try:
            cmds.undoInfo(closeChunk=True)
        except Exception:
            pass
        modal.chunk_open = False


def _on_app_state(state):
    """Maya arka plana gecerse (Alt+Tab) suren islemi o anki haliyle onayla, yuzen pencereleri gizle."""
    if state == Qt.ApplicationState.ApplicationActive:
        return
    filt = _filter()
    if filt and filt.modal:
        try:
            filt.modal.finish(True)
        except Exception:
            _abort_modal()


def start_modal(kind, panel=None, keep_undo=False, **kwargs):
    panel = panel or _last_view_panel()
    if not panel:
        return
    modal = Modal(kind, panel, keep_undo=keep_undo, **kwargs)
    if kind in ('attr_axis', 'attr_dist'):
        modal.chunk_open = True  # olusturma da ayni undo adiminda
        modal.dirty = True
    _current_filter_set_modal(modal)
    if not modal.start():
        _current_filter_set_modal(None)


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


def grab():
    start_modal('move')


def rotate():
    start_modal('rotate')


def scale():
    start_modal('scale')


def _with_chunk(fn):
    """Extrude/inset/bevel: olusturma + modal tek undo adimi olsun."""
    def run():
        cmds.undoInfo(openChunk=True, chunkName='blender_' + fn.__name__)
        filt = _filter()
        try:
            fn()
        except Exception as exc:
            _warn('%s: %s' % (fn.__name__, exc))
        if not (filt and filt.modal):
            cmds.undoInfo(closeChunk=True)
    return run


# ---------------------------------------------------------------- imlec altindaki bilesen
class Picker(object):
    """Fare altindaki mesh/yuz/kenar/koseyi bulur (secimi degistirmeden)."""

    def __init__(self, panel, meshes=None):
        self.view = omui2.M3dView.getM3dViewFromModelPanel(panel)
        self.widget = wrapInstance(int(self.view.widget()), QtWidgets.QWidget)
        self.meshes = []
        for obj in meshes or cmds.ls(hilite=True, long=True) or _objs():
            for shape in cmds.listRelatives(obj, shapes=True, type='mesh', noIntermediate=True,
                                            fullPath=True) or []:
                self.add_mesh(obj, shape)

    def add_mesh(self, transform, shape):
        sel = om.MSelectionList()
        sel.add(shape)
        dag = sel.getDagPath(0)
        self.meshes.append({'transform': transform, 'fn': om.MFnMesh(dag), 'poly': dag,
                            'matrix': dag.inclusiveMatrix(), 'inverse': dag.inclusiveMatrixInverse()})

    def port(self, global_pos):
        local = self.widget.mapFromGlobal(QtCore.QPointF(global_pos))
        sx = self.view.portWidth() / float(max(1, self.widget.width()))
        sy = self.view.portHeight() / float(max(1, self.widget.height()))
        return local.x() * sx, self.view.portHeight() - local.y() * sy

    def screen(self, point):
        res = self.view.worldToView(point)
        return float(res[0]), float(res[1])

    def hit(self, global_pos):
        """En yakin yuz: (mesh_bilgisi, yuz_id, dunya_noktasi) veya None."""
        x, y = self.port(global_pos)
        near, far = om.MPoint(), om.MPoint()
        self.view.viewToWorld(int(round(x)), int(round(y)), near, far)
        best = None
        for mesh in self.meshes:
            o = near * mesh['inverse']
            d = om.MVector(far - near) * mesh['inverse']
            res = mesh['fn'].closestIntersection(om.MFloatPoint(o), om.MFloatVector(d.normal()),
                                                 om.MSpace.kObject, 1e9, False)
            if res is None or res[2] < 0:
                continue
            world = om.MPoint(res[0]) * mesh['matrix']
            dist = world.distanceTo(near)
            if best is None or dist < best[3]:
                best = (mesh, res[2], world, dist)
        return best[:3] if best else None

    def _world(self, mesh, vid):
        return mesh['fn'].getPoint(vid, om.MSpace.kObject) * mesh['matrix']

    def _face_edges(self, mesh, face):
        it = om.MItMeshPolygon(mesh['poly'])
        it.setIndex(face)
        return list(it.getEdges()), list(it.getVertices())

    def edge(self, global_pos):
        """Fareye en yakin kenar: (mesh, kenar_id, t) ; t = kenar uzerindeki konum 0..1."""
        h = self.hit(global_pos)
        if not h:
            return None
        mesh, face, _ = h
        px, py = self.port(global_pos)
        best = None
        for e in self._face_edges(mesh, face)[0]:
            v0, v1 = mesh['fn'].getEdgeVertices(e)
            a = self.screen(self._world(mesh, v0))
            b = self.screen(self._world(mesh, v1))
            dist, t = _seg_dist(px, py, a, b)
            if best is None or dist < best[0]:
                best = (dist, e, t)
        return (mesh, best[1], best[2]) if best else None

    def vertex(self, global_pos):
        h = self.hit(global_pos)
        if not h:
            return None
        mesh, face, _ = h
        px, py = self.port(global_pos)
        best = None
        for v in self._face_edges(mesh, face)[1]:
            sx, sy = self.screen(self._world(mesh, v))
            d = math.hypot(sx - px, sy - py)
            if best is None or d < best[0]:
                best = (d, v)
        return (mesh, best[1]) if best else None

    def component(self, global_pos, kind):
        """'mesh.vtx[3]' gibi isim ve (mesh, id)."""
        if kind == 'vertex':
            r = self.vertex(global_pos)
        elif kind == 'edge':
            r = self.edge(global_pos)
        else:
            h = self.hit(global_pos)
            r = (h[0], h[1]) if h else None
        if not r:
            return None
        return r[0], r[1]


def _seg_dist(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 < 1e-9 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / length2))
    cx, cy = a[0] + dx * t, a[1] + dy * t
    return math.hypot(px - cx, py - cy), t


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
    if kind == 'face':
        # yuz loop'u = kenar halkasina komsu yuzler
        edges = cmds.polySelect(obj, edgeRing=edge, noSelection=True) or []
        if ring:
            edges = cmds.polySelect(obj, edgeLoop=edge, noSelection=True) or []
        comps = cmds.polyListComponentConversion([_comp(obj, 'edge', e) for e in edges], toFace=True)
    else:
        flag = 'edgeRing' if ring else 'edgeLoop'
        if ring and kind == 'vertex':
            flag = 'edgeRing'
        edges = cmds.polySelect(obj, noSelection=True, **{flag: edge}) or []
        comps = [_comp(obj, 'edge', e) for e in edges]
        if kind == 'vertex':
            comps = cmds.polyListComponentConversion(comps, toVertex=True)
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
    graph = MeshGraph(mesh['fn'])
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


class MeshGraph(object):
    """En kisa yol icin mesh komsuluk grafigi (Dijkstra)."""

    def __init__(self, fn):
        self.fn = fn
        pts = fn.getPoints(om.MSpace.kObject)
        self.pts = pts
        n_edges = fn.numEdges
        self.edge_verts = [fn.getEdgeVertices(e) for e in range(n_edges)]
        self.vadj = [[] for _ in range(fn.numVertices)]
        for e, (a, b) in enumerate(self.edge_verts):
            d = pts[a].distanceTo(pts[b])
            self.vadj[a].append((b, e, d))
            self.vadj[b].append((a, e, d))
        self._fadj = None

    @staticmethod
    def _dijkstra(sources, targets, neighbors):
        import heapq
        targets = set(targets)
        dist = {s: 0.0 for s in sources}
        prev = {}
        heap = [(0.0, s) for s in sources]
        heapq.heapify(heap)
        while heap:
            d, node = heapq.heappop(heap)
            if node in targets:
                path, links = [node], []
                while node in prev:
                    node, link = prev[node]
                    path.append(node)
                    links.append(link)
                return path[::-1], links[::-1]
            if d > dist.get(node, 1e30):
                continue
            for other, link, w in neighbors(node):
                nd = d + w
                if nd < dist.get(other, 1e30):
                    dist[other] = nd
                    prev[other] = (node, link)
                    heapq.heappush(heap, (nd, other))
        return [], []

    def vertex_path(self, sources, targets):
        """(kose_listesi, kenar_listesi)"""
        return self._dijkstra(list(sources), list(targets), lambda v: self.vadj[v])

    def face_path(self, a, b):
        if self._fadj is None:
            centers = []
            edge_faces = {}
            for f in range(self.fn.numPolygons):
                verts = self.fn.getPolygonVertices(f)
                c = om.MVector()
                for v in verts:
                    c += om.MVector(self.pts[v])
                centers.append(c / len(verts))
                for i in range(len(verts)):
                    key = tuple(sorted((verts[i], verts[(i + 1) % len(verts)])))
                    edge_faces.setdefault(key, []).append(f)
            self._fadj = [[] for _ in range(self.fn.numPolygons)]
            for faces in edge_faces.values():
                for f in faces:
                    for g in faces:
                        if f != g:
                            self._fadj[f].append((g, None, (centers[f] - centers[g]).length()))
        return self._dijkstra([a], [b], lambda f: self._fadj[f])[0]

    def shell(self, face):
        """Bagli tum yuzler (L / Ctrl+L)."""
        self.face_path(face, -1)  # komsulugu kur
        seen, stack = {face}, [face]
        while stack:
            f = stack.pop()
            for g, _, _ in self._fadj[f]:
                if g not in seen:
                    seen.add(g)
                    stack.append(g)
        return sorted(seen)


def select_linked_under_cursor(deselect=False):
    """L: imlecin altindaki parcayi sec (Shift+L: cikar)."""
    panel = _last_view_panel()
    if not panel or not in_edit():
        return
    picker = Picker(panel)
    h = picker.hit(QtGui.QCursor.pos())
    if not h:
        _msg('İmleç bir mesh üzerinde değil')
        return
    mesh, face, _ = h
    obj = mesh['transform']
    faces = MeshGraph(mesh['fn']).shell(face)
    comps = [_comp(obj, 'face', f) for f in faces]
    kind = current_comp()
    if kind != 'face':
        comps = cmds.polyListComponentConversion(comps, **{'toVertex' if kind == 'vertex' else 'toEdge': True})
    if deselect:
        cmds.select(comps, deselect=True)
    else:
        cmds.select(comps, add=True)


# ---------------------------------------------------------------- loop cut (Ctrl+R)
def _edge_ring_pairs(mesh, edge):
    """Kenar halkasini dortgenler uzerinden yuru.

    Donus: ([(kose_a, kose_b), ...], kapali_mi). Tum ciftler ayni yone bakar
    (a'lar halkanin bir tarafinda), boylece t oranindaki noktalar kesim cizgisini verir.
    """
    fn = mesh['fn']
    it_edge = om.MItMeshEdge(mesh['poly'])
    it_poly = om.MItMeshPolygon(mesh['poly'])

    def faces_of(e):
        it_edge.setIndex(e)
        return list(it_edge.getConnectedFaces())

    def step(face, a, b):
        """Dortgende (a,b) kenarinin karsisindaki kenar: (a'ya komsu, b'ye komsu, kenar_id)."""
        verts = list(fn.getPolygonVertices(face))
        if len(verts) != 4 or a not in verts or b not in verts:
            return None
        i, j = verts.index(a), verts.index(b)
        na = verts[(i - 1) % 4] if verts[(i + 1) % 4] == b else verts[(i + 1) % 4]
        nb = verts[(j - 1) % 4] if verts[(j + 1) % 4] == a else verts[(j + 1) % 4]
        it_poly.setIndex(face)
        for e in it_poly.getEdges():
            if set(fn.getEdgeVertices(e)) == {na, nb}:
                return na, nb, e
        return None

    def walk(face):
        out, cur, e, prev = [], (v0, v1), edge, None
        while face is not None and len(out) < 100000:
            res = step(face, cur[0], cur[1])
            if not res:
                return out, False
            na, nb, ne = res
            if ne == edge:
                return out, True
            out.append((na, nb))
            cur, prev = (na, nb), face
            nxt = [f for f in faces_of(ne) if f != prev]
            face, e = (nxt[0] if nxt else None), ne
        return out, False

    v0, v1 = fn.getEdgeVertices(edge)
    faces = faces_of(edge)
    fwd, closed = walk(faces[0]) if faces else ([], False)
    back = []
    if not closed and len(faces) > 1:
        back, _ = walk(faces[1])
    return list(reversed(back)) + [(v0, v1)] + fwd, closed


class PreviewOverlay(QtWidgets.QWidget):
    """Viewport'un ustunde seffaf katman; loop cut onizleme cizgileri (geometriye dokunmaz)."""

    def __init__(self):
        super(PreviewOverlay, self).__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint |
                                             Qt.WindowType.WindowTransparentForInput |
                                             Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.lines = []

    def show_lines(self, picker, lines):
        widget = picker.widget
        sx = widget.width() / float(max(1, picker.view.portWidth()))
        sy = widget.height() / float(max(1, picker.view.portHeight()))
        h = picker.view.portHeight()
        self.lines = [[QtCore.QPointF(x * sx, (h - y) * sy) for x, y in line] for line in lines]
        self.setGeometry(QtCore.QRect(widget.mapToGlobal(QtCore.QPoint(0, 0)), widget.size()))
        if not self.isVisible():
            self.show()
        self.update()

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 215, 0), 2))
        for line in self.lines:
            painter.drawPolyline(QtGui.QPolygonF(line))
        painter.end()


_overlay = []


def preview_overlay():
    if not _overlay:
        _overlay.append(PreviewOverlay())
    return _overlay[0]


class LoopCut(object):
    """Blender Ctrl+R: kenarin uzerine gel (kesilecek halka vurgulanir), tekerlek =
    kesim sayisi, sol tik = kes (tek kesimde kaydir), ikinci sol tik = onay.

    Guvenlik: onizleme icin geometri olusturulmaz/silinmez (onceki surum Maya'yi
    cokertti); halka sadece secimle gosterilir, kesim tiklayinca bir kez yapilir.
    """

    def __init__(self, panel):
        self.panel = panel
        self.pairs = []
        self.closed = False
        self.count = 1
        self.node = None
        self.edge = None          # (transform, kenar_id)
        self.ends = None          # kenarin uc noktalari (dunya), kaydirma icin
        self.edges_before = 0
        self.state = 'hover'
        self.timer = None
        self.chunk_open = False
        self.last_pos = None

    def start(self):
        if not in_edit():
            objs = [o for o in _objs() if _shape_type(o) == 'mesh']
            if not objs:
                _msg('Loop cut için bir mesh seç')
                return False
            enter_edit('edge')
        self.picker = Picker(self.panel)
        if not self.picker.meshes:
            return False
        cmds.undoInfo(openChunk=True, chunkName='blender_loopcut')
        self.chunk_open = True
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(30)
        self.update(force=True)
        return True

    def _hover(self, pos):
        r = self.picker.edge(pos)
        if not r:
            return
        mesh, edge, _ = r
        key = (mesh['transform'], edge)
        if key == self.edge:
            return
        self.edge = key
        v0, v1 = mesh['fn'].getEdgeVertices(edge)
        self.ends = (self.picker._world(mesh, v0), self.picker._world(mesh, v1))
        pairs, self.closed = _edge_ring_pairs(mesh, edge)
        self.pairs = [(self.picker._world(mesh, a), self.picker._world(mesh, b)) for a, b in pairs]

    def _draw(self):
        """Blender'daki sari onizleme: kesimlerin nereden gececegini ciz."""
        if self.state != 'hover' or not self.pairs:
            preview_overlay().hide()
            return
        lines = []
        for k in range(1, self.count + 1):
            t = k / float(self.count + 1)
            pts = [self.picker.screen(a + (b - a) * t) for a, b in self.pairs]
            if self.closed:
                pts.append(pts[0])
            lines.append(pts)
        preview_overlay().show_lines(self.picker, lines)

    def _cut(self):
        obj, edge = self.edge
        self.edges_before = cmds.polyEvaluate(obj, edge=True)
        self.verts_before = cmds.polyEvaluate(obj, vertex=True)
        multi = self.count > 1
        # polySplitRing tek kenarla bir sey yapmiyor; halkanin tum kenarlari gerekli
        ring = cmds.polySelect(obj, edgeRing=edge, noSelection=True) or [edge]
        self.node = cmds.polySplitRing([_comp(obj, 'edge', e) for e in ring], constructionHistory=True,
                                       splitType=2 if multi else 1, divisions=self.count,
                                       weight=0.5, smoothingAngle=30, rootEdge=edge)[0]

    def update(self, force=False):
        pos = QtGui.QCursor.pos()
        if not force and pos == self.last_pos:
            return
        self.last_pos = pos
        try:
            if self.state == 'hover':
                self._hover(pos)
                self._draw()
                self._show()
            else:
                a = self.picker.screen(self.ends[0])
                b = self.picker.screen(self.ends[1])
                px, py = self.picker.port(pos)
                t = max(0.0, min(1.0, _seg_dist(px, py, a, b)[1]))
                if Modal._mods() & CTRL:
                    t = round(t * 10) / 10.0
                cmds.setAttr(self.node + '.weight', t)
                self._show('%.2f' % t)
        except Exception as exc:
            _warn('loop cut: %s' % exc)
            self.finish(False)

    def _show(self, value=''):
        if self.state == 'hover':
            title = 'LOOP CUT  ·  %d kesim' % self.count
            keys = ['<b>Kenarın üzerine gel</b> (sarı çizgi = kesim yeri)',
                    '<b>Tekerlek / PageUp</b> kesim sayısı', '<b>Sol tık</b> kes',
                    '<b>Sağ tık/Esc</b> iptal']
        else:
            title = 'KAYDIR  ·  %s' % value
            keys = ['<b>Fare</b> kaydır', '<b>Ctrl</b> adımlı', '<b>Sol tık/Enter</b> onay',
                    '<b>Sağ tık/Esc</b> ortala']
        html = ('<span style="color:#e8a33d; font-weight:bold">%s</span><br>%s'
                % (title, '&nbsp;&nbsp;·&nbsp;&nbsp;'.join(keys)))
        hint_bar().show(self.picker.widget, html)

    def _set_count(self, delta):
        self.count = max(1, min(64, self.count + delta))
        self._draw()
        self._show()

    def _click(self):
        if self.state == 'hover':
            if not self.edge:
                return
            preview_overlay().hide()
            self._cut()
            if self.count > 1:
                self.finish(True)
            else:
                self.state = 'slide'
                self.update(force=True)
        else:
            self.finish(True)

    def key(self, ev, etype):
        if etype == EV_SHORTCUT:
            ev.accept()
            return True
        if etype != EV_KEY_PRESS:
            return True
        key = int(ev.key())
        if key in (int(Qt.Key.Key_Return), int(Qt.Key.Key_Enter), int(Qt.Key.Key_Space)):
            self._click()
        elif key == int(Qt.Key.Key_Escape):
            self._cancel()
        elif key in (int(Qt.Key.Key_PageUp), int(Qt.Key.Key_Plus)):
            self._set_count(1)
        elif key in (int(Qt.Key.Key_PageDown), int(Qt.Key.Key_Minus)):
            self._set_count(-1)
        return True

    def _cancel(self):
        if self.state == 'slide':
            cmds.setAttr(self.node + '.weight', 0.5)
            self.finish(True)
        else:
            self.finish(False)

    def mouse(self, ev, etype):
        if etype == EV_MPRESS:
            if ev.button() == LMB:
                self._click()
            elif ev.button() == RMB:
                self._cancel()
        elif etype == EV_WHEEL and self.state == 'hover':
            self._set_count(1 if ev.angleDelta().y() > 0 else -1)
        return etype != EV_MMOVE

    def finish(self, ok):
        if self.timer:
            self.timer.stop()
            self.timer = None
        try:
            hint_bar().hide()
        except Exception:
            pass
        _current_filter_set_modal(None)
        preview_overlay().hide()
        ok = ok and self.node is not None
        if ok:
            # yeni kenarlari sec (Blender gibi)
            # yeni kenarlardan sadece iki ucu da yeni kose olanlar = yeni loop(lar)
            obj = self.edge[0]
            after = cmds.polyEvaluate(obj, vertex=True)
            if after > self.verts_before:
                new_verts = '%s.vtx[%d:%d]' % (obj, self.verts_before, after - 1)
                loops = cmds.polyListComponentConversion(new_verts, toEdge=True, internal=True)
                cmds.select(loops or new_verts, replace=True)
        if self.chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.chunk_open = False
            # Bos bir undo adimini geri almak bir onceki islemi silerdi
            if not ok and self.node is not None:
                cmds.undo()


def loop_cut():
    panel = _last_view_panel()
    if not panel:
        return
    tool = LoopCut(panel)
    _current_filter_set_modal(tool)
    if not tool.start():
        _current_filter_set_modal(None)


# ---------------------------------------------------------------- 2. asama komutlari
def rip():
    """V: koseleri/kenarlari ayir ve tasi."""
    if not in_edit() or not (_comps('vertex') or _comps('edge')):
        _msg('Rip için köşe ya da kenar seç')
        return
    cmds.undoInfo(openChunk=True, chunkName='blender_rip')
    try:
        mel.eval('DetachComponent')
    except Exception as exc:
        _warn('rip: %s' % exc)
    start_modal('move', keep_undo=True)
    filt = _filter()
    if not (filt and filt.modal):
        cmds.undoInfo(closeChunk=True)


def mirror():
    """Ctrl+M: secilen eksende aynala (X/Y/Z ile degistir, Enter onay)."""
    start_modal('scale')
    filt = _filter()
    m = filt.modal if filt else None
    if isinstance(m, Modal):
        m.constraint = ('x', 'global', False)
        m.numeric = '-1'
        m.TITLES = dict(Modal.TITLES, scale='AYNALA')
        m.update(force=True)


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

    popup('Kenar (Ctrl+E)', [
        ('&Köprü (Bridge)', lambda: cmds.polyBridgeEdge(_comps('edge'), divisions=0)),
        ('&Böl (Subdivide)', lambda: cmds.polySubdivideEdge(_comps('edge'), divisions=1)),
        ('Kenar &kaydır (Slide)', lambda: mel.eval('SlideEdgeTool')),
        ('&Ofset kenar halkası', lambda: mel.eval('OffsetEdgeLoopTool')),
        ('Kenarı &döndür (Rotate)', lambda: cmds.polySpinEdge(_comps('edge'), offset=1)),
        None,
        ('Dikiş işaretle (&Mark Seam / UV kes)', lambda: cmds.polyMapCut(_comps('edge'))),
        ('Dikişi kaldır (Clear Seam / UV dik)', lambda: cmds.polyMapSew(_comps('edge'))),
        ('&Sert yap (Mark Sharp)', lambda: sharp(True)),
        ('Yumuşak yap (Clear Sharp)', lambda: sharp(False)),
        ('&Crease (1)', lambda: crease(1.0)),
        ('Crease kaldır', lambda: crease(0.0)),
        None,
        ('Kenar &loop\'unu sil (Dissolve)', lambda: cmds.polyDelEdge(_comps('edge'), cleanVertices=True)),
    ])


def vertex_menu():
    popup('Köşe (Ctrl+V)', [
        ('&Bağla (Connect, J)', connect_verts),
        ('&Ayır (Rip, V)', rip),
        ('Merkezde &birleştir', lambda: mel.eval('MergeToCenter')),
        ('&Yumuşat (Smooth Vertices)', lambda: cmds.polyAverageVertex(_comps('vertex'), iterations=1)),
        ('&Bevel köşe', lambda: cmds.polyBevel3(_comps('vertex'), offset=0.1, segments=1)),
        ('Dairesel yap (&Circularize)', lambda: cmds.polyCircularize(_sel())),
    ])


def face_menu():
    def shade(smooth):
        targets = _comps('face') or cmds.ls(hilite=True)
        cmds.polySoftEdge(targets, angle=180 if smooth else 0)

    popup('Yüz (Ctrl+F)', [
        ('&Extrude (E)', lambda: _with_chunk(extrude)()),
        ('&Inset (I)', lambda: _with_chunk(inset_or_key)()),
        ('&Poke (merkeze üçgen)', lambda: cmds.polyPoke(_comps('face'))),
        ('Üç&gene çevir (Ctrl+T)', triangulate),
        ('&Dörtgene çevir (Alt+J)', quadrangulate),
        ('&Böl (Subdivide)', lambda: cmds.polySubdivideFacet(_comps('face'), divisions=1)),
        ('Kalınlık ver (&Solidify)', lambda: cmds.polyExtrudeFacet(_comps('face'), keepFacesTogether=True,
                                                                   thickness=0.1)),
        None,
        ('&Kopyala (Duplicate)', lambda: mel.eval('DuplicateFace')),
        ('Ay&ır (Extract)', lambda: mel.eval('ExtractFace')),
        ('Deliği doldur (&Fill Hole)', lambda: mel.eval('FillHole')),
        ('Mesh &aynala (Mirror modifier gibi)...', lambda: _deferred(mesh_mirror_menu)),
        None,
        ('Yumuşak gölgele (Shade Smooth)', lambda: shade(True)),
        ('Düz gölgele (Shade Flat)', lambda: shade(False)),
        ('Normalleri çevir (&Flip)', flip_normals),
    ])


def triangulate():
    targets = _comps('face') or cmds.ls(hilite=True) or _objs()
    if targets:
        cmds.polyTriangulate(targets)


def quadrangulate():
    targets = _comps('face') or cmds.ls(hilite=True) or _objs()
    if targets:
        cmds.polyQuad(targets, angle=30, keepGroupBorder=True, keepTextureBorders=True)


def shade_smooth():
    targets = cmds.ls(hilite=True) or _objs()
    if targets:
        cmds.polySoftEdge(targets, angle=180)
        _msg('Shade Smooth')


def shade_flat():
    targets = cmds.ls(hilite=True) or _objs()
    if targets:
        cmds.polySoftEdge(targets, angle=0)
        _msg('Shade Flat')


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
    popup('Mesh aynala (Mirror modifier gibi, birleştirerek)', [
        ('-X → +X', lambda: run(0, 0)), ('+X → -X', lambda: run(0, 1)),
        ('-Y → +Y', lambda: run(1, 0)), ('+Y → -Y', lambda: run(1, 1)),
        ('-Z → +Z', lambda: run(2, 0)), ('+Z → -Z', lambda: run(2, 1)),
    ])


# ---------------------------------------------------------------- ayarlar (optionVar, Maya kapaninca da kalir)
SETTINGS = {
    'emulate_numpad': ('bk_emulateNumpad', 0),
    'emulate_3button': ('bk_emulate3Button', 0),
    'space_action': ('bk_spaceAction', 'play'),   # play | hotbox | search
    'zoom_to_mouse': ('bk_zoomToMouse', 0),       # Blender: Zoom to Mouse Position
    'orbit_selection': ('bk_orbitSelection', 0),  # Blender: Orbit Around Selection
}


def _apply_camera_settings():
    """Blender'in navigasyon ayarlarini Maya'nin kamera araclarina aktar."""
    try:
        cmds.dollyCtx('dollyContext', edit=True, dollyTowardsCenter=not setting('zoom_to_mouse'))
    except Exception as exc:
        _warn('zoom ayarı uygulanamadı: %s' % exc)
    try:
        cmds.tumbleCtx('tumbleContext', edit=True, objectTumble=bool(setting('orbit_selection')))
    except Exception as exc:
        _warn('orbit ayarı uygulanamadı: %s' % exc)


def setting(name):
    var, default = SETTINGS[name]
    if not cmds.optionVar(exists=var):
        return default
    return cmds.optionVar(q=var)


def set_setting(name, value):
    var, _ = SETTINGS[name]
    if isinstance(value, str):
        cmds.optionVar(stringValue=(var, value))
    else:
        cmds.optionVar(intValue=(var, int(value)))
    if name in ('zoom_to_mouse', 'orbit_selection'):
        _apply_camera_settings()
    # Not: menuyu burada yeniden kurma; kendi callback'i icinde menu silmek Maya'yi cokertebilir


def space_action():
    if setting('space_action') == 'search':
        show_search()
    else:
        play_toggle()


# ---------------------------------------------------------------- pie menu
class PieMenu(QtWidgets.QWidget):
    """Blender tarzi daire menu. Ogeler Blender sirasiyla: Sol, Sag, Alt, Ust, SolUst, SagUst, SolAlt, SagAlt.

    Oge: (etiket, fonksiyon) ya da (etiket, fonksiyon, aktif_mi). Aktif olan mavi cizilir.

    Tusa basip birak: menu acik kalir, tikla. Tusa basili tut, yone cek, birak: secilir.
    """

    DIRS = [180, 0, 270, 90, 135, 45, 225, 315]
    RADIUS = 125

    def __init__(self, title, items):
        super(PieMenu, self).__init__(_main_window(), Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint |
                                      Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.title = title
        self.items = (list(items) + [None] * 8)[:8]
        self.hover = -1
        self.opened = None
        self.font_ = QtGui.QFont(self.font())
        self.font_.setPointSize(9)
        metrics = QtGui.QFontMetrics(self.font_)
        self.sizes = [None if it is None else QtCore.QSize(metrics.horizontalAdvance(it[0]) + 24, 26)
                      for it in self.items]
        self.resize(2 * (self.RADIUS + 130), 2 * (self.RADIUS + 50))
        self.center = QtCore.QPointF(self.width() / 2.0, self.height() / 2.0)

    def _rect(self, i):
        a = math.radians(self.DIRS[i])
        cx = self.center.x() + math.cos(a) * self.RADIUS
        cy = self.center.y() - math.sin(a) * self.RADIUS * 0.8
        size = self.sizes[i]
        x = cx - size.width() / 2.0
        if self.DIRS[i] in (0, 45, 315):
            x = cx - 20          # sagdakiler sola hizali
        elif self.DIRS[i] in (180, 135, 225):
            x = cx - size.width() + 20
        return QtCore.QRectF(x, cy - size.height() / 2.0, size.width(), size.height())

    def _index_at(self, pos):
        dx = pos.x() - self.center.x()
        dy = self.center.y() - pos.y()
        if math.hypot(dx, dy) < 22:
            return -1
        angle = math.degrees(math.atan2(dy, dx)) % 360
        best, best_d = -1, 999
        for i, it in enumerate(self.items):
            if it is None:
                continue
            d = abs((angle - self.DIRS[i] + 180) % 360 - 180)
            if d < best_d:
                best, best_d = i, d
        return best

    def popup_at(self, global_pos):
        self.move(global_pos - QtCore.QPoint(int(self.center.x()), int(self.center.y())))
        self.opened = QtCore.QElapsedTimer()
        self.opened.start()
        self.show()
        self.activateWindow()
        self.setFocus()

    def _pos(self, ev):
        return ev.position() if hasattr(ev, 'position') else QtCore.QPointF(ev.pos())

    def mouseMoveEvent(self, ev):
        idx = self._index_at(self._pos(ev))
        if idx != self.hover:
            self.hover = idx
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == RMB:
            self.close()
            return
        self.hover = self._index_at(self._pos(ev))
        self._run()

    def keyPressEvent(self, ev):
        if int(ev.key()) == int(Qt.Key.Key_Escape):
            self.close()
        elif int(ev.key()) in (int(Qt.Key.Key_Return), int(Qt.Key.Key_Enter)):
            self._run()

    def keyReleaseEvent(self, ev):
        # basili tutup birakinca (Blender "drag-release") secili ogeyi calistir
        if not ev.isAutoRepeat() and self.opened and self.opened.elapsed() > 250 and self.hover >= 0:
            self._run()

    def _run(self):
        item = self.items[self.hover] if self.hover >= 0 else None
        self.close()
        if item:
            QtCore.QTimer.singleShot(0, undoable(item[1]))

    def paintEvent(self, _ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setFont(self.font_)
        c = self.center
        # merkez halka ve yon gostergesi
        p.setPen(QtGui.QPen(QtGui.QColor(20, 20, 20, 220), 6))
        p.drawEllipse(c, 18, 18)
        p.setPen(QtGui.QPen(QtGui.QColor(110, 110, 110), 2))
        p.drawEllipse(c, 18, 18)
        if self.hover >= 0:
            p.setPen(QtGui.QPen(QtGui.QColor(232, 163, 61), 4))
            start = (self.DIRS[self.hover] - 25) * 16
            p.drawArc(QtCore.QRectF(c.x() - 18, c.y() - 18, 36, 36), int(start), 50 * 16)
        if self.title:
            p.setPen(QtGui.QColor(230, 230, 230))
            p.drawText(QtCore.QRectF(c.x() - 120, c.y() - self.RADIUS * 0.8 - 52, 240, 18),
                       Qt.AlignmentFlag.AlignCenter, self.title)
        for i, it in enumerate(self.items):
            if it is None:
                continue
            r = self._rect(i)
            hot = i == self.hover
            active = len(it) > 2 and bool(it[2])
            if hot:
                fill, text = QtGui.QColor(232, 163, 61), QtGui.QColor(20, 20, 20)
            elif active:
                fill, text = QtGui.QColor(71, 114, 179), QtGui.QColor(255, 255, 255)   # Blender mavisi
            else:
                fill, text = QtGui.QColor(44, 44, 44, 240), QtGui.QColor(225, 225, 225)
            p.setPen(QtGui.QPen(QtGui.QColor(120, 165, 230) if active else QtGui.QColor(15, 15, 15), 1))
            p.setBrush(fill)
            p.drawRoundedRect(r, 5, 5)
            p.setPen(text)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, it[0])
        p.end()


def pie(title, items):
    menu = PieMenu(title, items)
    menu.popup_at(QtGui.QCursor.pos())
    return menu


# ---------------------------------------------------------------- 3D imlec
CURSOR = 'blenderCursor'


class _NoUndo(object):
    """Blender'da imlec hareketi undo'ya girmez."""

    def __enter__(self):
        self.state = cmds.undoInfo(q=True, stateWithoutFlush=True)
        cmds.undoInfo(stateWithoutFlush=False)

    def __exit__(self, *exc):
        cmds.undoInfo(stateWithoutFlush=self.state)


def _style_cursor(node):
    """Reference gorunumu: tiklayinca secilmez (Maya bunu koyu/siyah cizer)."""
    if cmds.getAttr(node + '.overrideEnabled') and cmds.getAttr(node + '.overrideDisplayType') == 2:
        return
    shape = cmds.listRelatives(node, shapes=True)[0]
    with _NoUndo():
        cmds.setAttr(shape + '.localScale', 0.4, 0.4, 0.4)
        cmds.setAttr(node + '.overrideEnabled', 1)
        cmds.setAttr(node + '.overrideRGBColors', 0)
        cmds.setAttr(node + '.overrideDisplayType', 2)
        cmds.setAttr(node + '.hiddenInOutliner', True)


def cursor_node(create=True):
    if cmds.objExists(CURSOR):
        _style_cursor(CURSOR)
        return CURSOR
    if not create:
        return None
    with _NoUndo():
        sel = cmds.ls(sl=True)
        node = cmds.spaceLocator(name=CURSOR)[0]
        for attr in ('rx', 'ry', 'rz', 'sx', 'sy', 'sz'):
            cmds.setAttr('%s.%s' % (node, attr), lock=True, keyable=False)
        if sel:
            cmds.select(sel, replace=True)
        else:
            cmds.select(clear=True)
    _style_cursor(node)
    return node



def cursor_pos():
    node = cursor_node(create=False)
    if not node:
        return om.MPoint(0, 0, 0)
    return om.MPoint(*cmds.xform(node, q=True, worldSpace=True, translation=True))


def set_cursor(point):
    with _NoUndo():
        cmds.xform(cursor_node(), worldSpace=True, translation=(point.x, point.y, point.z))


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
        set_cursor(h[2])
        return True
    x, y = picker.port(global_pos)
    near, far = om.MPoint(), om.MPoint()
    picker.view.viewToWorld(int(round(x)), int(round(y)), near, far)
    direction = om.MVector(far - near).normal()
    normal = om.MFnCamera(picker.view.getCamera()).viewDirection(om.MSpace.kWorld).normal()
    denom = direction * normal
    if abs(denom) > 1e-8:
        t = (om.MVector(cursor_pos() - near) * normal) / denom
        set_cursor(near + direction * t)
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

    return pie('Hizala (Shift+S)', [
        ('İmleç → Seçim', lambda: cursor_to(_selection_center())),
        ('Seçim → İmleç', lambda: _move_selection_to(cursor_pos())),
        ('Seçim → Grid', selection_to_grid),
        ('İmleç → Orijin', lambda: cursor_to(om.MPoint(0, 0, 0))),
        ('İmleç → Grid', lambda: cursor_to(grid(cursor_pos()))),
        ('Seçim → Aktif', lambda: _move_selection_to(_active_pivot())),
        ('İmleç → Aktif', lambda: cursor_to(_active_pivot())),
        ('Pivot → İmleç (origin)', pivot_to_cursor),
    ])


def cursor_reset_and_frame(panel):
    if cursor_node(create=False):
        set_cursor(om.MPoint(0, 0, 0))
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
    return pie('Görünüm', [
        ('Sol', lambda: view_axis(panel, 'leftSide'), now == 'leftSide'),
        ('Sağ', lambda: view_axis(panel, 'rightSide'), now == 'rightSide'),
        ('Alt', lambda: view_axis(panel, 'bottom'), now == 'bottom'),
        ('Üst', lambda: view_axis(panel, 'top'), now == 'top'),
        ('Ön', lambda: view_axis(panel, 'front'), now == 'front'),
        ('Arka', lambda: view_axis(panel, 'back'), now == 'back'),
        ('Kamera', lambda: camera_view(panel), now == 'camera'),
        ('Seçime odaklan', lambda: frame_selected(panel)),
    ])


def shading_pie(panel):
    ed = _editor(panel)

    def mode(appearance, textures):
        cmds.modelEditor(ed, edit=True, displayAppearance=appearance, displayTextures=textures)

    def lights():
        current = cmds.modelEditor(ed, q=True, displayLights=True)
        cmds.modelEditor(ed, edit=True, displayLights='default' if current != 'default' else 'all')

    wire = cmds.modelEditor(ed, q=True, displayAppearance=True) == 'wireframe'
    textures = cmds.modelEditor(ed, q=True, displayTextures=True)
    return pie('Görüntü (Z)', [
        ('Wireframe', lambda: mode('wireframe', False), wire),
        ('X-Ray', lambda: toggle_xray(panel), cmds.modelEditor(ed, q=True, xray=True)),
        ('Solid', lambda: mode('smoothShaded', False), not wire and not textures),
        ('Material (doku)', lambda: mode('smoothShaded', True), not wire and textures),
        ('Wireframe üstte', lambda: cmds.modelEditor(
            ed, edit=True, wireframeOnShaded=not cmds.modelEditor(ed, q=True, wireframeOnShaded=True)),
         cmds.modelEditor(ed, q=True, wireframeOnShaded=True)),
        ('Sahne ışıkları', lights, cmds.modelEditor(ed, q=True, displayLights=True) == 'all'),
        None,
        None,
    ])


def select_mode_pie():
    now = current_comp() if in_edit() else 'object'
    return pie('Seçim modu (Ctrl+Tab)', [
        ('Köşe', lambda: enter_edit('vertex'), now == 'vertex'),
        ('Yüz', lambda: enter_edit('face'), now == 'face'),
        ('Obje modu', lambda: exit_edit() if in_edit() else None, now == 'object'),
        ('Kenar', lambda: enter_edit('edge'), now == 'edge'),
    ])


# ---------------------------------------------------------------- F2 / F3 / F9
class _PopupLine(QtWidgets.QLineEdit):
    def __init__(self, text, on_accept):
        super(_PopupLine, self).__init__(text, _main_window())
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumWidth(260)
        self.setStyleSheet('QLineEdit { padding: 6px; font-size: 13px; border: 2px solid #e8a33d; }')
        self.on_accept = on_accept
        self.returnPressed.connect(self._accept)
        self.selectAll()

    def _accept(self):
        text = self.text().strip()
        self.close()
        if text:
            QtCore.QTimer.singleShot(0, lambda: undoable(self.on_accept)(text))

    def keyPressEvent(self, ev):
        if int(ev.key()) == int(Qt.Key.Key_Escape):
            self.close()
            return
        super(_PopupLine, self).keyPressEvent(ev)


def rename_active():
    objs = _objs() or cmds.ls(sl=True, long=True)
    if not objs:
        _msg('Yeniden adlandırmak için bir obje seç')
        return
    obj = objs[-1]
    box = _PopupLine(obj.split('|')[-1], lambda name: cmds.rename(obj, name))
    box.move(QtGui.QCursor.pos() - QtCore.QPoint(130, 15))
    box.show()
    box.setFocus()


_search_cache = []


def _search_entries():
    if _search_cache:
        return _search_cache
    entries = []
    for combo, title in ACTION_TITLES.items():
        binding = BINDINGS.get(combo)
        if binding:
            entries.append((title, combo.upper(), ('binding', combo)))
    for name in cmds.runTimeCommand(q=True, commandArray=True) or []:
        try:
            ann = cmds.runTimeCommand(name, q=True, annotation=True) or ''
            cat = cmds.runTimeCommand(name, q=True, category=True) or ''
        except Exception:
            continue
        if not cat.startswith('Menu items'):
            continue
        tr = TR_ALIASES.get(name)
        entries.append(('%s  [%s]' % (name, tr) if tr else name, ann, ('runtime', name)))
    # Turkce karsiligi olanlar en ustte gorunsun
    entries.sort(key=lambda e: (e[2][0] != 'binding', '[' not in e[0]))
    _search_cache.extend(entries)
    return entries


class SearchPalette(QtWidgets.QDialog):
    """F3: Blender'daki menu arama. Blender komutlari + Maya menu komutlari."""

    def __init__(self):
        super(SearchPalette, self).__init__(_main_window(), Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(520, 380)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText('Ara... (ör. extrude, bevel, mirror, köprü)')
        self.edit.setStyleSheet('QLineEdit { padding: 6px; font-size: 13px; border: 2px solid #e8a33d; }')
        self.list = QtWidgets.QListWidget()
        layout.addWidget(self.edit)
        layout.addWidget(self.list)
        self.entries = _search_entries()
        self.edit.textChanged.connect(self._filter)
        self.edit.returnPressed.connect(self._run_current)
        self.list.itemActivated.connect(lambda _item: self._run_current())
        self.edit.installEventFilter(self)
        self._filter('')

    def _filter(self, text):
        words = [w for w in text.lower().split() if w]
        self.list.clear()
        shown = 0
        for title, detail, action in self.entries:
            hay = (title + ' ' + detail).lower()
            if all(w in hay for w in words):
                item = QtWidgets.QListWidgetItem('%s    —  %s' % (title, detail) if detail else title)
                item.setData(Qt.ItemDataRole.UserRole, action)
                self.list.addItem(item)
                shown += 1
                if shown >= 200:
                    break
        if self.list.count():
            self.list.setCurrentRow(0)

    def eventFilter(self, obj, ev):
        if ev.type() == EV_KEY_PRESS and int(ev.key()) in (int(Qt.Key.Key_Down), int(Qt.Key.Key_Up)):
            row = self.list.currentRow() + (1 if int(ev.key()) == int(Qt.Key.Key_Down) else -1)
            self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
            return True
        return False

    def _run_current(self):
        item = self.list.currentItem()
        self.close()
        if not item:
            return
        kind, name = item.data(Qt.ItemDataRole.UserRole)
        if kind == 'binding':
            QtCore.QTimer.singleShot(0, functools.partial(_run_binding, BINDINGS[name], _last_view_panel()))
        else:
            QtCore.QTimer.singleShot(0, lambda: mel.eval(name))


def show_search():
    dlg = SearchPalette()
    dlg.move(QtGui.QCursor.pos() - QtCore.QPoint(260, 20))
    dlg.show()
    dlg.edit.setFocus()


def adjust_last():
    """F9: son islemin ayarlari (Maya'da secili objenin en son history dugumu)."""
    objs = cmds.ls(hilite=True, long=True) or cmds.ls(sl=True, objectsOnly=True, long=True)
    if not objs:
        _msg('Önce bir obje seç')
        return
    history = [n for n in (cmds.listHistory(objs[0], pruneDagObjects=True) or [])
               if cmds.nodeType(n) not in ('groupId', 'groupParts', 'shadingEngine')]
    if not history:
        _msg('Bu objenin ayarlanacak bir işlemi yok')
        return
    mel.eval('showEditor "%s"' % history[0])
    _msg('Son işlem: %s  (Attribute Editor\'de değerleri değiştir)' % history[0])


# F3 aramasinda Turkce kelimeyle bulunabilsin diye sik Maya komutlarinin karsiliklari
TR_ALIASES = {
    'BridgeEdge': 'köprü', 'MirrorPolygonGeometry': 'aynala simetri', 'SmoothPolygon': 'yumuşat pürüzsüz subdivision',
    'CombinePolygons': 'birleştir join', 'SeparatePolygon': 'ayır parçala', 'FillHole': 'delik doldur',
    'PolyExtrude': 'extrude çıkart', 'BevelPolygon': 'bevel pah', 'InsertEdgeLoopTool': 'loop cut kenar halkası',
    'MultiCutTool': 'bıçak kes knife', 'MergeVertices': 'birleştir merge köşe', 'DeleteHistory': 'geçmişi sil history',
    'FreezeTransformations': 'uygula apply freeze dondur', 'CenterPivot': 'pivot ortala origin',
    'Triangulate': 'üçgen', 'Quadrangulate': 'dörtgen quad', 'ReversePolygonNormals': 'normal çevir flip',
    'ConformPolygonNormals': 'normal düzelt', 'SoftPolyEdgeElements': 'yumuşak gölgele shade smooth',
    'HardPolyEdgeElements': 'sert gölgele shade flat', 'PolygonBooleanUnion': 'boolean birleşim',
    'PolygonBooleanDifference': 'boolean fark çıkar', 'PolygonBooleanIntersection': 'boolean kesişim',
    'CreatePolygonType': 'yazı metin text', 'UVEditor': 'uv editör', 'HypershadeWindow': 'malzeme shader material',
    'RenderViewWindow': 'render görüntü', 'GraphEditor': 'animasyon eğri graph', 'OutlinerWindow': 'outliner sahne listesi',
    'DuplicateSpecial': 'kopyala özel instance', 'GroupSelected': 'grupla', 'ParentSelected': 'ebeveyn parent',
    'SlideEdgeTool': 'kaydır slide', 'OffsetEdgeLoopTool': 'ofset kenar', 'DetachComponent': 'rip ayır',
    'ExtractFace': 'yüz ayır extract', 'DuplicateFace': 'yüz kopyala', 'PokePolygon': 'poke üçgen merkez',
    'CreaseTool': 'crease kenar sertliği', 'TargetWeldTool': 'kaynak birleştir weld',
    'polyRetopo': 'retopo yeniden topoloji', 'ReduceEditor': 'azalt decimate reduce',
}


ACTION_TITLES = {
    'tab': 'Edit modu aç/kapa', 'g': 'Taşı (Grab)', 'r': 'Döndür (Rotate)', 's': 'Ölçekle (Scale)',
    'e': 'Extrude', 'i': 'Inset / Keyframe ekle', 'ctrl+b': 'Bevel', 'ctrl+r': 'Loop cut',
    'k': 'Bıçak (Knife)', 'f': 'Yüz/kenar doldur (Fill)', 'j': 'Köşeleri bağla (Join)',
    'm': 'Birleştir (Merge)', 'p': 'Ayır (Separate)', 'v': 'Rip', 'ctrl+m': 'Aynala (Mirror)',
    'ctrl+v': 'Köşe menüsü',
    'ctrl+t': 'Üçgene çevir (Triangulate)', 'alt+j': 'Dörtgene çevir (Tris to Quads)',
    'shift+a': 'Ekle (Add)', 'shift+d': 'Kopyala (Duplicate)', 'alt+d': 'Instance',
    'x': 'Sil (Delete)', 'ctrl+j': 'Birleştir (Join objects)', 'ctrl+p': 'Ebeveyn yap (Parent)',
    'alt+p': 'Ebeveyni kaldır', 'ctrl+a': 'Uygula (Apply / Freeze)', 'shift+s': 'Hizala (Snap)',
    'h': 'Gizle', 'alt+h': 'Hepsini göster', 'shift+n': 'Normalleri düzelt', 'alt+n': 'Normalleri çevir',
    'o': 'Proportional editing', 'l': 'Bağlı olanları seç (imleç altı)', 'ctrl+l': 'Bağlı olanları seç',
    'ctrl+i': 'Seçimi ters çevir', 'a': 'Hepsini seç', 'np/': 'Local view', 'np5': 'Persp / Ortho',
    'z': 'Görüntü (shading) pie', 'grave': 'Görünüm pie', 'f12': 'Render', 'f2': 'Yeniden adlandır',
    'f9': 'Son işlemi ayarla', 'ctrl+tab': 'Seçim modu pie', 'shift+r': 'Son işlemi tekrarla',
    'ctrl+e': 'Kenar menüsü (köprü, dikiş, crease, kaydır)', 'ctrl+f': 'Yüz menüsü (poke, solidify, mirror)',
}


# ---------------------------------------------------------------- tus tablosu
V = frozenset(['view'])
VO = frozenset(['view', 'outliner'])
ALL = frozenset(['view', 'outliner', 'other'])
VT = frozenset(['view', 'other'])


def _b(ctx, fn, panel=False, undo=True, raw=False, repeat=False):
    return {'ctx': ctx, 'fn': fn, 'panel': panel, 'undo': undo and not raw, 'repeat': repeat}


BINDINGS = {
    # mod / secim
    'tab': _b(V, toggle_edit),
    '1': _b(V, lambda: enter_edit('vertex')),
    '2': _b(V, lambda: enter_edit('edge')),
    '3': _b(V, lambda: enter_edit('face')),
    'a': _b(VO, select_all),
    'alt+a': _b(VO, deselect_all),
    'ctrl+i': _b(VO, invert_selection),
    'ctrl+l': _b(V, select_linked),
    'w': _b(V, lambda: cmds.setToolTo('selectSuperContext'), undo=False),
    'c': _b(V, lambda: mel.eval('ArtPaintSelectTool'), undo=False),
    # donusum
    'g': _b(V, grab, raw=True),
    'r': _b(V, rotate, raw=True),
    's': _b(V, scale, raw=True),
    'alt+g': _b(V, reset_location),
    'alt+r': _b(V, reset_rotation),
    'alt+s': _b(V, reset_scale),
    'ctrl+a': _b(V, apply_menu, raw=True),
    'shift+s': _b(V, snap_pie, raw=True),
    'o': _b(V, toggle_soft_select),
    # obje
    'x': _b(VO, delete_menu, raw=True),
    'delete': _b(VO, delete_by_mode),
    'shift+d': _b(V, duplicate, raw=True),
    'alt+d': _b(V, instance, raw=True),
    'shift+a': _b(V, add_menu, raw=True),
    'ctrl+j': _b(V, join),
    'ctrl+p': _b(VO, parent_to_active),
    'alt+p': _b(VO, clear_parent),
    'h': _b(VO, hide_selected),
    'shift+h': _b(VO, hide_unselected),
    'alt+h': _b(VO, unhide_all),
    'shift+r': _b(V, lambda: mel.eval('RepeatLast'), undo=False),
    # modelleme
    'e': _b(V, _with_chunk(extrude), raw=True),
    'i': _b(V, _with_chunk(inset_or_key), raw=True),
    'ctrl+b': _b(V, _with_chunk(bevel), raw=True),
    'ctrl+r': _b(V, loop_cut, raw=True),
    'k': _b(V, knife, undo=False),
    'f': _b(V, fill),
    'j': _b(V, connect_verts),
    'l': _b(V, select_linked_under_cursor),
    'shift+l': _b(V, lambda: select_linked_under_cursor(deselect=True)),
    'v': _b(V, rip, raw=True),
    'ctrl+m': _b(V, mirror, raw=True),
    'ctrl+e': _b(V, edge_menu, raw=True),
    'ctrl+v': _b(V, vertex_menu, raw=True),
    'ctrl+f': _b(V, face_menu, raw=True),
    'ctrl+t': _b(V, triangulate),
    'alt+j': _b(V, quadrangulate),
    'm': _b(V, merge_menu, raw=True),
    'p': _b(V, separate_menu, raw=True),
    'shift+n': _b(V, recalc_normals),
    'alt+n': _b(V, flip_normals),
    'ctrl+0': _b(V, lambda: subdiv_level(0)),
    'ctrl+1': _b(V, lambda: subdiv_level(1)),
    'ctrl+2': _b(V, lambda: subdiv_level(2)),
    'ctrl+3': _b(V, lambda: subdiv_level(3)),
    # animasyon
    'alt+i': _b(V, clear_key),
    'space': _b(VT, space_action, undo=False),
    'left': _b(VT, lambda: frame_step(-1), undo=False, repeat=True),
    'right': _b(VT, lambda: frame_step(1), undo=False, repeat=True),
    'shift+left': _b(VT, lambda: frame_jump(False), undo=False),
    'shift+right': _b(VT, lambda: frame_jump(True), undo=False),
    'up': _b(VT, lambda: key_jump(True), undo=False, repeat=True),
    'down': _b(VT, lambda: key_jump(False), undo=False, repeat=True),
    # gorunum
    'np1': _b(V, lambda p: view_axis(p, 'front'), panel=True, undo=False),
    'ctrl+np1': _b(V, lambda p: view_axis(p, 'back'), panel=True, undo=False),
    'np3': _b(V, lambda p: view_axis(p, 'rightSide'), panel=True, undo=False),
    'ctrl+np3': _b(V, lambda p: view_axis(p, 'leftSide'), panel=True, undo=False),
    'np7': _b(V, lambda p: view_axis(p, 'top'), panel=True, undo=False),
    'ctrl+np7': _b(V, lambda p: view_axis(p, 'bottom'), panel=True, undo=False),
    'np5': _b(V, toggle_ortho, panel=True, undo=False),
    'np0': _b(V, camera_view, panel=True, undo=False),
    'ctrl+np0': _b(V, set_active_camera, panel=True, undo=False),
    'ctrl+alt+np0': _b(V, align_camera_to_view, panel=True),
    'np.': _b(V, frame_selected, panel=True, undo=False),
    'home': _b(V, frame_all, panel=True, undo=False),
    'shift+c': _b(V, cursor_reset_and_frame, panel=True, undo=False),
    'np/': _b(V, toggle_isolate, panel=True, undo=False),
    'np2': _b(V, lambda p: orbit_step(p, 0, -15), panel=True, undo=False, repeat=True),
    'np8': _b(V, lambda p: orbit_step(p, 0, 15), panel=True, undo=False, repeat=True),
    'np4': _b(V, lambda p: orbit_step(p, 15, 0), panel=True, undo=False, repeat=True),
    'np6': _b(V, lambda p: orbit_step(p, -15, 0), panel=True, undo=False, repeat=True),
    'np+': _b(V, lambda p: zoom_step(p, 1), panel=True, undo=False, repeat=True),
    'np-': _b(V, lambda p: zoom_step(p, -1), panel=True, undo=False, repeat=True),
    'ctrl+np+': _b(V, grow_selection, repeat=True),
    'ctrl+np-': _b(V, shrink_selection, repeat=True),
    'grave': _b(V, view_pie, panel=True, raw=True),
    'z': _b(V, shading_pie, panel=True, raw=True),
    'ctrl+tab': _b(V, select_mode_pie, raw=True),
    'shift+z': _b(V, toggle_wireframe, panel=True, undo=False),
    'alt+z': _b(V, toggle_xray, panel=True, undo=False),
    'ctrl+space': _b(V, maximize_panel, panel=True, undo=False),
    'n': _b(V, lambda: mel.eval('ToggleChannelsLayers'), undo=False),
    't': _b(V, lambda: mel.eval('ToggleToolbox'), undo=False),
    # genel
    'ctrl+shift+z': _b(ALL, lambda: cmds.redo(), undo=False, repeat=True),
    'f12': _b(ALL, lambda: mel.eval('RenderIntoNewWindow'), undo=False),
    'f1': _b(ALL, lambda: show_help(), undo=False),
    'f2': _b(VO, rename_active, raw=True),
    'f3': _b(ALL, lambda: show_search(), raw=True),
    'f9': _b(V, adjust_last, raw=True),
}


def _key_name(ev):
    sc = ev.nativeScanCode()
    if ev.modifiers() & KEYPAD:
        name = NUMPAD_SCAN.get(sc & 0xFF)
        return ('np' + name) if name else None
    name = QT_KEYS.get(int(ev.key()))
    if name in ('delete', 'home', 'space', 'left', 'right', 'up', 'down', 'f1', 'f2', 'f3', 'f9', 'f12'):
        return name
    if sc and not sc & 0x100:
        name = SCAN.get(sc & 0xFF) or name
    if name and name.isdigit() and setting('emulate_numpad'):
        return 'np' + name   # Blender "Emulate Numpad": ust siradaki rakamlar numpad gibi
    return name


def _combo(ev, name):
    mods = ev.modifiers()
    parts = []
    if mods & CTRL:
        parts.append('ctrl')
    if mods & ALT:
        parts.append('alt')
    if mods & SHIFT:
        parts.append('shift')
    return '+'.join(parts + [name])


def _context():
    panel = cmds.getPanel(underPointer=True)
    if panel:
        kind = cmds.getPanel(typeOf=panel)
        if kind == 'modelPanel':
            return 'view', panel
        if kind == 'outlinerPanel':
            return 'outliner', panel
    return 'other', panel


def _typing():
    w = QtWidgets.QApplication.focusWidget()
    if isinstance(w, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit,
                      QtWidgets.QAbstractSpinBox)):
        return True
    return isinstance(w, QtWidgets.QComboBox) and w.isEditable()


def _run_binding(binding, panel):
    fn = binding['fn']
    call = (lambda: fn(panel)) if binding['panel'] else fn
    if binding['undo']:
        undoable(call)()
        return
    try:
        call()
    except Exception as exc:
        _warn(str(exc))


# ---------------------------------------------------------------- olay filtresi
class BlenderFilter(QtCore.QObject):
    def __init__(self, parent=None):
        super(BlenderFilter, self).__init__(parent)
        self.modal = None
        self.nav = None        # (basilan_tus, Maya'ya giden tus) navigasyon surerken
        self.eat_release = None
        self.sending = False

    def eventFilter(self, obj, ev):
        if self.sending:
            return False
        try:
            t = ev.type()
            if t in KEY_EVENTS:
                return self._key(ev, t)
            if t in MOUSE_EVENTS:
                if not obj.isWidgetType():
                    return False
                return self._mouse(obj, ev, t)
            return False
        except Exception as exc:
            # Hata olursa olayi Maya'ya birak; suren islem varsa guvenle kapat
            self.nav = None
            self.eat_release = None
            if self.modal:
                _abort_modal()
            _warn('beklenmeyen hata (Maya normal çalışmaya devam ediyor): %s' % exc)
            return False

    # -- klavye
    def _key(self, ev, t):
        if self.modal:
            return self.modal.key(ev, t)
        if QtWidgets.QApplication.activePopupWidget() or _typing():
            return False
        name = _key_name(ev)
        if not name:
            return False
        combo = _combo(ev, name)
        if combo == 'space' and setting('space_action') == 'hotbox':
            return False   # Maya'nin hotbox'i calissin
        binding = BINDINGS.get(combo)
        if not binding:
            return False
        ctx, panel = _context()
        if ctx not in binding['ctx']:
            return False
        if t == EV_SHORTCUT:
            ev.accept()
            return True
        if t == EV_KEY_RELEASE:
            return True
        if ev.isAutoRepeat() and not binding['repeat']:
            return True
        if binding['panel'] and ctx != 'view':
            panel = _last_view_panel()
        QtCore.QTimer.singleShot(0, functools.partial(_run_binding, binding, panel))
        return True

    # -- fare
    def _send(self, obj, ev, etype, button, buttons, mods):
        if hasattr(ev, 'position'):
            new = QtGui.QMouseEvent(etype, ev.position(), ev.scenePosition(), ev.globalPosition(),
                                    button, buttons, mods)
        else:
            new = QtGui.QMouseEvent(etype, ev.localPos(), ev.windowPos(), ev.screenPos(),
                                    button, buttons, mods)
        self.sending = True
        try:
            QtWidgets.QApplication.sendEvent(obj, new)
        finally:
            self.sending = False

    def _mouse(self, obj, ev, t):
        if self.modal:
            return self.modal.mouse(ev, t)
        if t == EV_WHEEL or QtWidgets.QApplication.activePopupWidget():
            return False
        if self.nav is not None:
            source, target = self.nav
            if t == EV_MMOVE:
                self._send(obj, ev, t, NOBTN, target, ALT)
                return True
            if t == EV_MRELEASE and ev.button() == source:
                self._send(obj, ev, t, target, NOBTN, ALT)
                self.nav = None
                return True
            return True
        if self.eat_release is not None:
            if t == EV_MRELEASE and ev.button() == self.eat_release:
                self.eat_release = None
            return True
        if t == EV_MDBL and ev.button() == MMB:
            return _context()[0] == 'view'
        if t != EV_MPRESS:
            return False
        button, mods = ev.button(), ev.modifiers()
        emulate = button == LMB and mods & ALT and setting('emulate_3button')
        if button == MMB or emulate:
            ctx, panel = _context()
            if ctx != 'view':
                return False
            if mods & SHIFT:
                target = MMB        # kaydir (pan)
            elif mods & CTRL:
                target = RMB        # zoom
            else:
                target = LMB        # dondur (orbit)
                leave_auto_ortho(panel)
            self.nav = (button, target)
            self._send(obj, ev, t, target, target, ALT)
            return True
        if button == RMB and mods & SHIFT and not mods & (CTRL | ALT) and _context()[0] == 'view':
            try:
                if place_cursor(_event_global_pos(ev)):   # Shift+sag tik: 3D imlec
                    self.eat_release = RMB
                    return True
            except Exception as exc:
                _warn('imlec: %s' % exc)
        if button == LMB and mods & (ALT | CTRL) and in_edit() and _context()[0] == 'view':
            pos = _event_global_pos(ev)
            try:
                if mods & ALT:
                    # Alt+tik loop, Ctrl+Alt+tik ring; Shift ile ekle
                    handled = select_loop(pos, ring=bool(mods & CTRL), add=bool(mods & SHIFT))
                else:
                    handled = select_path(pos)   # Ctrl+tik: en kisa yol
            except Exception as exc:
                _warn('seçim: %s' % exc)
                handled = False
            if handled:
                self.eat_release = LMB
                return True
        return False


# ---------------------------------------------------------------- kurulum
_KEY = '_blender_kontrol_filter'
_JOB_KEY = '_blender_kontrol_cursor_job'


def _filter():
    return getattr(sys.modules['__main__'], _KEY, None)


def _current_filter_set_modal(modal):
    filt = _filter()
    if filt is not None:
        filt.modal = modal


def _kill_old_cursor_job():
    """Bu modulun kurdugu scriptJob'lari temizle (eski surumun tek is numarasi ya da liste)."""
    jobs = getattr(sys.modules['__main__'], _JOB_KEY, None)
    if jobs is None:
        return
    for job in (jobs if isinstance(jobs, (list, tuple)) else [jobs]):
        try:
            cmds.scriptJob(kill=job, force=True)
        except Exception:
            pass
    delattr(sys.modules['__main__'], _JOB_KEY)


def is_installed():
    return _filter() is not None


def install(quiet=False):
    uninstall(quiet=True)
    app = QtWidgets.QApplication.instance()
    filt = BlenderFilter(app)
    app.installEventFilter(filt)
    setattr(sys.modules['__main__'], _KEY, filt)
    try:
        cmds.selectPref(trackSelectionOrder=True)
    except Exception:
        pass
    _kill_old_cursor_job()
    jobs = []
    for event in ('PreFileNewOrOpened', 'SceneOpened', 'NewSceneOpened'):
        try:
            jobs.append(cmds.scriptJob(event=[event, _abort_modal]))
        except Exception:
            pass   # bu Maya surumunde olmayan olay
    setattr(sys.modules['__main__'], _JOB_KEY, jobs)
    try:
        app.applicationStateChanged.connect(_on_app_state)
    except Exception:
        pass
    if cmds.objExists(CURSOR):
        _style_cursor(CURSOR)
    _apply_camera_settings()
    _build_menu()
    if not quiet:
        _msg('Blender kontrolleri AÇIK  -  F1: kısayol listesi')


def uninstall(quiet=False):
    filt = _filter()
    if filt is None:
        return
    app = QtWidgets.QApplication.instance()
    app.removeEventFilter(filt)
    try:
        app.applicationStateChanged.disconnect(_on_app_state)
    except Exception:
        pass
    if filt.modal:
        filt.modal.finish(False)
    filt.deleteLater()
    delattr(sys.modules['__main__'], _KEY)
    _kill_old_cursor_job()
    for holder in (_overlay, _hint_bar):
        for w in holder:
            try:
                w.hide()
            except Exception:
                pass
    _build_menu()
    if not quiet:
        _msg('Blender kontrolleri KAPALI (Maya varsayılanı)')


def reload_module():
    """Diskteki son surumu yukle. Menu callback'inden evalDeferred ile cagrilir
    (menuyu kendi callback'i icinde silmek Maya'yi cokertebilir)."""
    import importlib
    module = importlib.reload(sys.modules[__name__])
    module.install()


def _toggle(*_):
    cmds.evalDeferred(uninstall if is_installed() else install)


def _build_menu():
    name = 'BlenderKontrolMenu'
    if cmds.about(batch=True):
        return
    if cmds.menu(name, exists=True):
        cmds.deleteUI(name)
    menu = cmds.menu(name, label='Blender', parent='MayaWindow', tearOff=True)
    cmds.menuItem(label='Blender kontrolleri', checkBox=is_installed(), command=_toggle, parent=menu)
    cmds.menuItem(label='Kısayol listesi  (F1)', command=lambda *_: show_help(), parent=menu)
    cmds.menuItem(divider=True, dividerLabel='Ayarlar', parent=menu)
    cmds.menuItem(label='Emulate Numpad (üst sıradaki rakamlar = numpad)', parent=menu,
                  checkBox=bool(setting('emulate_numpad')),
                  command=lambda on: set_setting('emulate_numpad', on))
    cmds.menuItem(label='Emulate 3 Button Mouse (Alt + sol tık = orta tuş)', parent=menu,
                  checkBox=bool(setting('emulate_3button')),
                  command=lambda on: set_setting('emulate_3button', on))
    space = cmds.menuItem(label='Space tuşu', subMenu=True, parent=menu)
    cmds.radioMenuItemCollection(parent=space)
    for value, label in (('play', 'Oynat / durdur (Blender)'), ('search', 'Arama (F3 gibi)'),
                         ('hotbox', 'Maya hotbox')):
        cmds.menuItem(label=label, radioButton=setting('space_action') == value, parent=space,
                      command=functools.partial(lambda v, *_: set_setting('space_action', v), value))
    cmds.menuItem(label='Zoom to Mouse Position (tekerlek fareye doğru)', parent=menu,
                  checkBox=bool(setting('zoom_to_mouse')),
                  command=lambda on: set_setting('zoom_to_mouse', on))
    cmds.menuItem(label='Orbit Around Selection (seçimin etrafında dön)', parent=menu,
                  checkBox=bool(setting('orbit_selection')),
                  command=lambda on: set_setting('orbit_selection', on))
    cmds.menuItem(divider=True, parent=menu)
    cmds.menuItem(label='Yeniden yükle (güncelleme sonrası)', parent=menu,
                  command=lambda *_: cmds.evalDeferred(reload_module))


HELP = u"""
<h2>Blender Kontrolleri</h2>
<p>Maya'da artık Blender gibi çalışabilirsin. Üstteki <b>Blender</b> menüsünden açıp kapatabilirsin.
Tuşlar imleç <b>3D görünümün üzerindeyken</b> çalışır.</p>
<h3>Fare</h3>
<table>
<tr><td><b>Orta tuş sürükle</b></td><td>Etrafında dön (orbit)</td></tr>
<tr><td><b>Shift + orta tuş</b></td><td>Kaydır (pan)</td></tr>
<tr><td><b>Ctrl + orta tuş</b> / tekerlek</td><td>Yakınlaş / uzaklaş</td></tr>
<tr><td><b>Sol tık</b></td><td>Seç (Shift: ekle/çıkar, boşluğa sürükle: kutu seçimi)</td></tr>
<tr><td><b>Alt + sol tık</b> (edit modu)</td><td>Loop seç (Shift ile ekle)</td></tr>
<tr><td><b>Ctrl + Alt + sol tık</b></td><td>Ring seç</td></tr>
<tr><td><b>Ctrl + sol tık</b></td><td>En kısa yol (son seçilenden tıklanana)</td></tr>
<tr><td><b>Sağ tık</b></td><td>Maya bağlam menüsü</td></tr>
<tr><td><b>Shift + sağ tık</b></td><td>3D imleci koy (yüzeye ya da imleç düzlemine)</td></tr>
</table>
<h3>Görünüm</h3>
<table>
<tr><td><b>Numpad 1 / 3 / 7</b></td><td>Ön / sağ / üst (Ctrl ile ters taraf)</td></tr>
<tr><td><b>Numpad 5</b></td><td>Perspektif / ortografik</td></tr>
<tr><td><b>Numpad 0</b></td><td>Kameradan bak (Ctrl: seçili kamerayı aktif yap, Ctrl+Alt: kamerayı görünüme hizala)</td></tr>
<tr><td><b>Numpad . </b></td><td>Seçime odaklan</td></tr>
<tr><td><b>Home</b> / Shift+C</td><td>Hepsini göster</td></tr>
<tr><td><b>Numpad 2 4 6 8</b></td><td>Adım adım döndür</td></tr>
<tr><td><b>Numpad + / -</b></td><td>Yakınlaş / uzaklaş</td></tr>
<tr><td><b>Numpad /</b></td><td>Local view (sadece seçili)</td></tr>
<tr><td><b>1'in solundaki tuş (")</b></td><td>Görünüm pie menüsü (numpad yoksa)</td></tr>
<tr><td><b>Z</b> / Shift+Z / Alt+Z</td><td>Görüntü pie menüsü / wireframe / X-ray</td></tr>
<tr><td colspan="2" style="color:gray">Pie menü: tuşa bas-bırak sonra tıkla, ya da basılı tutup yöne çek ve bırak.</td></tr>
<tr><td><b>Ctrl + Space</b></td><td>Paneli büyüt</td></tr>
<tr><td><b>N</b> / <b>T</b></td><td>Channel Box / araç çubuğu</td></tr>
</table>
<h3>Obje modu</h3>
<table>
<tr><td><b>Tab</b></td><td>Edit moduna gir / çık</td></tr>
<tr><td><b>G / R / S</b></td><td>Taşı / döndür / ölçekle. İşlem sırasında:<br>
X/Y/Z eksen (2. kez lokal, 3. kez kapalı) · Shift+X/Y/Z düzlem · orta tuş otomatik eksen ·
Shift hassas · Ctrl adımlı · G/R/S arası geçiş · G G kaydır (edit modu) · R R serbest döndür ·
tekerlek/PageUp proportional alanı · sayı ya da işlem yaz (ör. 2*3)</td></tr>
<tr><td><b>Alt + G / R / S</b></td><td>Konum / döndürme / ölçeği sıfırla</td></tr>
<tr><td><b>Ctrl + A</b></td><td>Uygula (freeze) ve geçmişi temizle</td></tr>
<tr><td><b>Shift + A</b></td><td>Ekle (küp, küre, kamera, ışık...)</td></tr>
<tr><td><b>Shift + D</b> / Alt + D</td><td>Kopyala / instance</td></tr>
<tr><td><b>X</b> / Delete</td><td>Sil</td></tr>
<tr><td><b>A</b> / Alt + A / Ctrl + I</td><td>Hepsini seç / seçimi kaldır / ters çevir</td></tr>
<tr><td><b>H</b> / Shift + H / Alt + H</td><td>Gizle / diğerlerini gizle / hepsini göster</td></tr>
<tr><td><b>Ctrl + J</b></td><td>Birleştir (join)</td></tr>
<tr><td><b>Ctrl + P</b> / Alt + P</td><td>Ebeveyn yap (en son seçilen) / ebeveyni kaldır</td></tr>
<tr><td><b>Shift + S</b></td><td>Hizala pie: imleç/seçim → seçim/imleç/grid/orijin/aktif, pivot → imleç</td></tr>
<tr><td><b>Shift + A</b> (3D imleç)</td><td>Yeni objeler 3D imlecin olduğu yere eklenir (Shift+C: imleci sıfırla)</td></tr>
<tr><td><b>Ctrl + 0..3</b></td><td>Yumuşak önizleme (subdivision) seviyesi</td></tr>
<tr><td><b>O</b></td><td>Proportional editing (soft select)</td></tr>
<tr><td><b>W</b> / <b>C</b></td><td>Seçim aracı / fırça ile seçim</td></tr>
<tr><td><b>Shift + R</b></td><td>Son işlemi tekrarla</td></tr>
</table>
<h3>Edit modu (Tab)</h3>
<table>
<tr><td><b>1 / 2 / 3</b></td><td>Köşe / kenar / yüz</td></tr>
<tr><td><b>E</b></td><td>Extrude</td></tr>
<tr><td><b>I</b></td><td>Inset</td></tr>
<tr><td><b>Ctrl + B</b></td><td>Bevel (tekerlek: segment sayısı)</td></tr>
<tr><td><b>Ctrl + R</b></td><td>Loop cut: kenarın üzerine gel, tekerlek kesim sayısı, tıkla, kaydır, tıkla</td></tr>
<tr><td><b>V</b></td><td>Rip (ayır ve taşı)</td></tr>
<tr><td><b>Ctrl + M</b></td><td>Aynala (X/Y/Z seç, Enter)</td></tr>
<tr><td><b>Ctrl + E / V / F</b></td><td>Kenar / köşe / yüz menüsü (köprü, dikiş, crease, poke, mirror...)</td></tr>
<tr><td><b>Ctrl + T</b> / Alt + J</td><td>Üçgene / dörtgene çevir</td></tr>
<tr><td><b>L</b> / Shift + L</td><td>İmlecin altındaki parçayı seç / çıkar</td></tr>
<tr><td><b>H</b> / Shift + H / Alt + H</td><td>Seçili yüzleri gizle / diğerlerini gizle / göster</td></tr>
<tr><td><b>K</b></td><td>Bıçak (Multi-Cut)</td></tr>
<tr><td><b>F</b> / <b>J</b></td><td>Yüz / kenar doldur, köşeleri bağla</td></tr>
<tr><td><b>M</b></td><td>Birleştir (merkezde / mesafeye göre)</td></tr>
<tr><td><b>P</b></td><td>Ayır</td></tr>
<tr><td><b>X</b></td><td>Sil menüsü (köşe/kenar/yüz/erit)</td></tr>
<tr><td><b>Ctrl + L</b> / Ctrl + Numpad +/-</td><td>Bağlı olanları seç / seçimi büyüt-küçült</td></tr>
<tr><td><b>Shift + N</b> / Alt + N</td><td>Normalleri düzelt / çevir</td></tr>
</table>
<h3>Animasyon ve genel</h3>
<table>
<tr><td><b>I</b> (obje modu) / Alt + I</td><td>Keyframe ekle / sil</td></tr>
<tr><td><b>Space</b></td><td>Oynat / durdur</td></tr>
<tr><td><b>← / →</b></td><td>Bir kare geri / ileri (Shift: başa / sona)</td></tr>
<tr><td><b>↑ / ↓</b></td><td>Sonraki / önceki keyframe</td></tr>
<tr><td><b>Ctrl+Z</b> / Ctrl+Shift+Z</td><td>Geri al / yinele</td></tr>
<tr><td><b>Ctrl+S</b></td><td>Kaydet</td></tr>
<tr><td><b>F12</b></td><td>Render</td></tr>
<tr><td><b>F1</b></td><td>Bu liste</td></tr>
<tr><td><b>F2</b></td><td>Yeniden adlandır</td></tr>
<tr><td><b>F3</b></td><td>Komut ara (Blender ve Maya menü komutları)</td></tr>
<tr><td><b>F9</b></td><td>Son işlemi ayarla (Attribute Editor'de açar)</td></tr>
<tr><td><b>Ctrl + Tab</b></td><td>Seçim modu pie (köşe / kenar / yüz / obje)</td></tr>
<tr><td colspan="2" style="color:gray">Ayarlar (Blender menüsü): Emulate Numpad, Emulate 3 Button Mouse, Space tuşu (oynat / ara / Maya hotbox).</td></tr>
</table>
<p style="color:gray">Blender'dan farkı: Maya'da her işlem "geçmiş" (history) bırakır; işin bitince
Ctrl+A &gt; Geçmişi temizle. Maya'nın kendi menüleri ve Channel Box'ı (sağda) her zaman kullanılabilir.</p>
"""


def show_help():
    name = 'BlenderKontrolHelp'
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.objectName() == name:
            w.close()
            w.deleteLater()
    dlg = QtWidgets.QDialog(_main_window())
    dlg.setObjectName(name)
    dlg.setWindowTitle('Blender kısayolları')
    dlg.resize(620, 760)
    layout = QtWidgets.QVBoxLayout(dlg)
    text = QtWidgets.QTextBrowser()
    text.setHtml(HELP.replace('<table>', '<table cellpadding="3">'))
    layout.addWidget(text)
    dlg.show()
