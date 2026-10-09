# -*- coding: utf-8 -*-
"""Obje modu islemleri (ekle, kopyala, ebeveyn, layer, origin, yeniden adlandir ...)."""
from __future__ import absolute_import, division, print_function

import functools

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om

from .compat import QtCore, QtGui, QtWidgets, _main_window
from .core import _msg
from .i18n import _t
from .util import _comps, _last_view_panel, _mesh_fn, _objs, _sel, _shape_type, _visible_meshes, popup, undoable
from .ui import _PopupLine
from .picking import Picker
from .editmode import current_comp, enter_edit, exit_edit, in_edit
from .cursor import cursor_pos
from .modal import start_modal
from .selection import select_linked
from .mesh import add_into_mesh, hide_components, shrink_fatten


# ---------------------------------------------------------------- objeler
def duplicate():
    if in_edit():
        if _comps('face'):
            mel.eval('DuplicateFace')
            start_modal('move')
        else:
            _msg(_t('Kopyalamak için yüz seç (3)'))
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
        _msg(_t('Birleştirmek için en az 2 mesh seç'))
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
        _msg(_t('Önce çocukları, en son ebeveyni seç'))
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
    popup(_t('Uygula (Freeze)'), [
        (_t('&Konum'), lambda: freeze(True, False, False)),
        (_t('&Döndürme'), lambda: freeze(False, True, False)),
        (_t('Ö&lçek'), lambda: freeze(False, False, True)),
        (_t('Döndürme && Ölçek'), lambda: freeze(False, True, True)),
        (_t('&Hepsi'), lambda: freeze(True, True, True)),
        None,
        (_t("&Modifier'ları uygula (Apply Modifiers)"), lambda: _apply_modifiers()),
        (_t('Geçmişi temizle (Delete History / Visual Geometry to Mesh)'),
         lambda: cmds.delete(_objs(), constructionHistory=True)),
        (_t("&Instance'ları gerçek yap (Make Instances Real)"), lambda: mel.eval('convertInstanceToObject')),
    ])


def _apply_modifiers():
    from .modifiers import apply_all_selected   # dongusel import: cagri aninda
    apply_all_selected()


def collection_menu():
    """M (obje modu): Blender 'Move to Collection' karsiligi olarak display layer."""
    objs = _objs()
    if not objs:
        _msg(_t('Önce bir obje seç'))
        return

    def new_layer():
        box = _PopupLine('layer1', lambda name: cmds.createDisplayLayer(objs, name=name, noRecurse=True))
        box.move(QtGui.QCursor.pos() - QtCore.QPoint(130, 15))
        box.show()
        box.setFocus()

    def assign(layer):
        cmds.editDisplayLayerMembers(layer, objs, noRecurse=True)
        _msg(_t('%d obje → %s') % (len(objs), layer))

    layers = [l for l in (cmds.ls(type='displayLayer') or []) if l != 'defaultLayer']
    items = [(_t('&Yeni layer...'), new_layer), None]
    items += [(layer, functools.partial(assign, layer)) for layer in layers]
    if layers:
        items.append(None)
    items.append((_t('Layer\'dan çıkar (defaultLayer)'), lambda: assign('defaultLayer')))
    popup(_t('Layer\'a taşı (Move to Collection)'), items)


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
    _msg(_t('%d obje gösterildi') % shown)


def add_menu():
    mesh_fns = (cmds.polyCube, cmds.polyPlane, cmds.polySphere, cmds.polyCylinder, cmds.polyCone, cmds.polyTorus)

    def add(fn):
        def run():
            if in_edit() and fn in mesh_fns and add_into_mesh(fn):
                return   # Blender: edit modunda Shift+A ayni objeye ekler
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
    popup(_t('Ekle'), [
        (_t('&Küp'), add(cmds.polyCube)),
        (_t('&Düzlem (Plane)'), add(cmds.polyPlane)),
        (_t('&Küre (UV Sphere)'), add(cmds.polySphere)),
        (_t('&Silindir'), add(cmds.polyCylinder)),
        (_t('K&oni'), add(cmds.polyCone)),
        (_t('&Torus'), add(cmds.polyTorus)),
        None,
        (_t('Çember (eğri)'), add(cmds.circle)),
        (_t('Eğri çiz (CV Curve)'), lambda: mel.eval('CVCurveTool')),
        None,
        (_t('Boş obje (Empty / Locator)'), add(cmds.spaceLocator)),
        (_t('Boş grup'), add(lambda: cmds.group(empty=True, name='Empty'))),
        None,
        (_t('&Kamera'), add(cmds.camera)),
        (_t('Işık: Nokta (Point)'), add(cmds.pointLight)),
        (_t('Işık: Güneş (Directional)'), add(cmds.directionalLight)),
        (_t('Işık: Spot'), add(cmds.spotLight)),
        (_t('Işık: Alan (Area)'), add(lambda: cmds.shadingNode('areaLight', asLight=True))),
    ])


def rename_active():
    objs = _objs() or cmds.ls(sl=True, long=True)
    if not objs:
        _msg(_t('Yeniden adlandırmak için bir obje seç'))
        return
    obj = objs[-1]
    box = _PopupLine(obj.split('|')[-1], lambda name: cmds.rename(obj, name))
    box.move(QtGui.QCursor.pos() - QtCore.QPoint(130, 15))
    box.show()
    box.setFocus()


def alt_s():
    """Alt+S: edit modunda kalinlastir/incelt, obje modunda olcegi sifirla (Blender)."""
    if in_edit():
        shrink_fatten()
    else:
        undoable(reset_scale)()


# ---------------------------------------------------------------- obje: Ctrl+G, Set Origin, Ctrl+P / Alt+P, Ctrl+L, Alt+Q
def new_layer_from_selection():
    """Ctrl+G (obje modu): secimden yeni display layer (Blender New Collection)."""
    objs = _objs()
    if not objs:
        _msg(_t('Önce bir obje seç'))
        return
    if in_edit():
        _msg(_t('Ctrl+G obje modunda çalışır'))
        return
    box = _PopupLine('layer1', lambda name: cmds.createDisplayLayer(objs, name=name, noRecurse=True))
    box.move(QtGui.QCursor.pos() - QtCore.QPoint(130, 15))
    box.show()
    box.setFocus()


def _world_bbox_center(obj):
    b = cmds.exactWorldBoundingBox(obj)
    return om.MVector((b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0, (b[2] + b[5]) / 2.0)


def _surface_center(obj):
    """Alan agirlikli yuz merkezleri ortalamasi (Origin to Center of Mass, Surface)."""
    fn, dag = _mesh_fn(obj)
    it = om.MItMeshPolygon(dag)
    total, area = om.MVector(), 0.0
    while not it.isDone():
        a = it.getArea(om.MSpace.kWorld)
        total += om.MVector(it.center(om.MSpace.kWorld)) * a
        area += a
        it.next()
    return total / area if area > 1e-12 else _world_bbox_center(obj)


def set_origin(mode):
    objs = _objs()
    if not objs:
        _msg(_t('Önce bir obje seç'))
        return
    for obj in objs:
        piv = om.MVector(*cmds.xform(obj, q=True, worldSpace=True, rotatePivot=True))
        if mode == 'geometry_to_origin':
            c = _world_bbox_center(obj)
            if _shape_type(obj) == 'mesh':
                cmds.move(piv.x - c.x, piv.y - c.y, piv.z - c.z, obj + '.vtx[*]', relative=True, worldSpace=True)
            continue
        if mode == 'origin_to_geometry':
            target = _world_bbox_center(obj)
        elif mode == 'origin_to_cursor':
            target = om.MVector(cursor_pos())
        elif mode == 'origin_to_mass':
            target = _surface_center(obj) if _shape_type(obj) == 'mesh' else _world_bbox_center(obj)
        else:
            continue
        cmds.xform(obj, worldSpace=True, pivots=(target.x, target.y, target.z))


def set_origin_menu():
    popup(_t('Origin ayarla (Set Origin)'), [
        (_t('&Geometriyi origin\'e taşı (Geometry to Origin)'), lambda: set_origin('geometry_to_origin')),
        (_t('&Origin\'i geometriye taşı (Origin to Geometry)'), lambda: set_origin('origin_to_geometry')),
        (_t('Origin\'i 3D &imlece taşı (Origin to 3D Cursor)'), lambda: set_origin('origin_to_cursor')),
        (_t('Origin\'i &kütle merkezine (Center of Mass, Surface)'), lambda: set_origin('origin_to_mass')),
    ])


def parent_menu():
    """Ctrl+P: Blender Set Parent To."""
    objs = _objs()
    if len(objs) < 2:
        _msg(_t('Önce çocukları, en son ebeveyni seç'))
        return
    popup(_t('Ebeveyn yap (Ctrl+P)'), [
        (_t('&Obje (dönüşümü koru)'), lambda: cmds.parent(objs[:-1], objs[-1])),
        (_t('Obje (&ters dönüşüm olmadan)'), lambda: cmds.parent(objs[:-1], objs[-1], relative=True)),
    ])


def clear_parent_menu():
    """Alt+P: Blender Clear Parent."""
    objs = _objs()
    if not objs:
        return
    popup(_t('Ebeveyni kaldır (Alt+P)'), [
        (_t('&Kaldır (yerel dönüşüm kalır, obje yer değiştirebilir)'), lambda: cmds.parent(objs, world=True, relative=True)),
        (_t('Kaldır, dünya &dönüşümünü koru'), lambda: cmds.parent(objs, world=True)),
    ])


def link_menu():
    """Ctrl+L (obje modu): Blender Link / Transfer Data."""
    objs = _objs()
    if len(objs) < 2:
        _msg(_t('Önce hedefleri, en son kaynak (aktif) objeyi seç'))
        return
    active, others = objs[-1], objs[:-1]

    def materials():
        shapes = cmds.listRelatives(active, shapes=True, fullPath=True) or []
        sgs = cmds.listConnections(shapes, type='shadingEngine') or []
        if not sgs:
            _msg(_t('Aktif objenin materyali yok'))
            return
        cmds.sets(others, edit=True, forceElement=sgs[0])

    def uvs():
        for o in others:
            cmds.transferAttributes(active, o, uvs=2, sampleSpace=5)
            cmds.delete(o, constructionHistory=True)

    def layer():
        lay = (cmds.listConnections(active + '.drawOverride', type='displayLayer') or ['defaultLayer'])[0]
        cmds.editDisplayLayerMembers(lay, others, noRecurse=True)

    popup(_t('Bağla / aktar (Ctrl+L)'), [
        (_t('&Materyalleri bağla'), materials),
        (_t('&UV\'leri aktar (aynı topoloji)'), uvs),
        (_t('&Layer\'ı bağla (Link to Collection)'), layer),
    ])


def ctrl_l():
    if in_edit():
        select_linked()
    else:
        link_menu()


def transfer_mode():
    """Alt+Q (edit modu): imlec altindaki objeye gec, ayni bilesen modunda kal."""
    panel = _last_view_panel()
    if not panel or not in_edit():
        return
    picker = Picker(panel, meshes=_visible_meshes())
    h = picker.hit(QtGui.QCursor.pos())
    if not h:
        _msg(_t('İmleç bir mesh üzerinde değil'))
        return
    obj = h[0]['transform']
    if obj in (cmds.ls(hilite=True, long=True) or []):
        return
    kind = current_comp()
    exit_edit()
    cmds.select(obj, replace=True)
    enter_edit(kind)


# ---------------------------------------------------------------- nesne modu Boolean (F3)
def boolean(op):
    """Aktif (en son secilen) hedef, digerleri kesici. op: 1 union, 2 difference, 3 intersection."""
    meshes = [o for o in _objs() if _shape_type(o) == 'mesh']
    if len(meshes) < 2:
        _msg(_t('Boolean için en az 2 mesh seç (en son seçilen hedef)'))
        return
    target, cutters = meshes[-1], meshes[:-1]
    name = target.split('|')[-1]
    result = cmds.polyCBoolOp([target] + cutters, operation=op, constructionHistory=False)[0]
    result = cmds.rename(result, name)
    cmds.select(result, replace=True)


class BatchRenameDialog(QtWidgets.QDialog):
    """Ctrl+F2: secili objeleri toplu yeniden adlandir (bul/degistir, onek, sonek, numara)."""

    def __init__(self):
        super(BatchRenameDialog, self).__init__(_main_window())
        self.setObjectName('BlenderKontrolBatchRename')
        self.setWindowTitle(_t('Toplu yeniden adlandır (Ctrl+F2)'))
        form = QtWidgets.QFormLayout(self)
        self.find = QtWidgets.QLineEdit()
        self.replace = QtWidgets.QLineEdit()
        self.prefix = QtWidgets.QLineEdit()
        self.suffix = QtWidgets.QLineEdit()
        self.base = QtWidgets.QLineEdit()
        self.base.setPlaceholderText(_t('boş: eski adı koru'))
        form.addRow(_t('Bul'), self.find)
        form.addRow(_t('Değiştir'), self.replace)
        form.addRow(_t('Önek'), self.prefix)
        form.addRow(_t('Sonek'), self.suffix)
        form.addRow(_t('Yeni ad + numara'), self.base)
        self.preview = QtWidgets.QLabel()
        self.preview.setStyleSheet('color: gray')
        form.addRow(self.preview)
        ok = QtWidgets.QPushButton(_t('Uygula'))
        ok.clicked.connect(self.apply)
        form.addRow(ok)
        for w in (self.find, self.replace, self.prefix, self.suffix, self.base):
            w.textChanged.connect(self._preview)
        self._preview()

    def new_names(self, objs):
        out = []
        for i, obj in enumerate(objs):
            name = obj.split('|')[-1]
            if self.base.text().strip():
                name = '%s%02d' % (self.base.text().strip(), i + 1)
            if self.find.text():
                name = name.replace(self.find.text(), self.replace.text())
            out.append(self.prefix.text() + name + self.suffix.text())
        return out

    def _preview(self):
        objs = _objs()
        names = self.new_names(objs[:3])
        self.preview.setText((_t('%d obje') % len(objs)) + ('  ·  ' + ', '.join(names) if names else ''))

    def apply(self):
        objs = _objs()
        names = self.new_names(objs)
        chunk = undoable(lambda: [cmds.rename(o, n) for o, n in zip(reversed(objs), reversed(names)) if n])
        chunk()
        self.close()


def batch_rename():
    if not _objs():
        _msg(_t('Önce obje seç'))
        return
    dlg = BatchRenameDialog()
    dlg.move(QtGui.QCursor.pos() - QtCore.QPoint(150, 60))
    dlg.show()
    return dlg
