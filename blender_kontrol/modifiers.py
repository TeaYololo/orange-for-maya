# -*- coding: utf-8 -*-
"""Blender modifier'larinin Maya karsiliklari ve modifier paneli.

Blender'da edit modu taban mesh'i duzenler, modifier'lar ustte canli hesaplanir. Maya'da her modelleme islemi
gecmis zincirinin sonuna eklenir; bir mirror / subdiv dugumunden sonra yapilan duzenleme onlarin ciktisina
uygulanir. Bu yuzden modifier'lar duzenlemeye uygun Maya yollariyla kurulur:

    Subdivision   Smooth Mesh Preview (topolojiye dokunmaz, kafes duzenlenir). Uygula: polySmooth.
    Mirror        taban mesh'in canli instance'i, obje uzayinda -1 olcek (offsetParentMatrix ile tabana kilitli,
                  viewport'ta secilemez). Uygula: polyMirrorFace (obje merkezi, dikis kaynakli).
    Array         N canli instance, obje uzayinda sabit aralik. Uygula: birlestir (polyUnite), donusum korunur.
    Bevel, Solidify, Triangulate, Weld: gecmis dugumu (Maya'nin yerel yolu); ac / kapa (nodeState), ayarla,
                  sil. Bu dugumlerden sonra yapilan duzenleme onlarin ciktisina uygulanir.

Siralama degistirme bilincli olarak yok: dugumlerin bilesen listeleri topoloji indekslerine bagli; tasimak
modeli bozabilir.
"""
from __future__ import absolute_import, division, print_function

import functools
import math

import maya.cmds as cmds
import maya.api.OpenMaya as om

from .compat import Qt, QtCore, QtGui, QtWidgets, _main_window
from .core import _msg, _warn
from .i18n import _t
from .util import _mesh_fn, _objs, _ranges, _shape_type, undoable
from .editmode import exit_edit, in_edit

ATTR = 'orangeModifier'      # instance transform'u ya da gecmis dugumu: tur ('mirror:x', 'array', 'bevel' ...)
BASE_ATTR = 'orangeBase'     # instance -> taban obje (message baglantisi)
AXES = 'xyz'
HISTORY_KINDS = ('bevel', 'solidify', 'triangulate', 'weld')


# ---------------------------------------------------------------- yardimcilar
def active_mesh():
    """Duzenlenen ya da en son secilen mesh transform'u (instance modifier secilmisse tabani)."""
    objs = cmds.ls(hilite=True, long=True) or _objs()
    for obj in reversed(objs):
        base = base_of(obj)
        if base:
            return base
        if _shape_type(obj) == 'mesh':
            return obj
    return None


def base_of(obj):
    """Instance modifier transform'u ise taban objesi."""
    if not cmds.attributeQuery(BASE_ATTR, node=obj, exists=True):
        return None
    src = cmds.listConnections(obj + '.' + BASE_ATTR, source=True, destination=False) or []
    return cmds.ls(src[0], long=True)[0] if src else None


def _mark(node, kind):
    if not cmds.attributeQuery(ATTR, node=node, exists=True):
        cmds.addAttr(node, longName=ATTR, dataType='string')
    cmds.setAttr(node + '.' + ATTR, kind, type='string')


def kind_of(node):
    if cmds.attributeQuery(ATTR, node=node, exists=True):
        return cmds.getAttr(node + '.' + ATTR) or ''
    return ''


def instance_modifiers(base):
    """[(transform, tur)] tabana bagli instance modifier'lar (olusturma sirasinda)."""
    out = []
    for dst in cmds.listConnections(base + '.message', source=False, destination=True, plugs=True) or []:
        node, _, attr = dst.partition('.')
        if attr == BASE_ATTR:
            node = cmds.ls(node, long=True)[0]
            out.append((node, kind_of(node)))
    return out


def history_modifiers(base):
    """[(dugum, tur)] Orange'in ekledigi gecmis dugumleri."""
    out = []
    for node in cmds.listHistory(base, pruneDagObjects=True) or []:
        k = kind_of(node)
        if k in HISTORY_KINDS:
            out.append((node, k))
    return list(reversed(out))    # olusturma sirasi


def _shape(base):
    return (cmds.listRelatives(base, shapes=True, type='mesh', noIntermediate=True, fullPath=True) or [None])[0]


# ---------------------------------------------------------------- subdivision (smooth mesh preview)
def subdivision_level(base):
    shape = _shape(base)
    if not shape or cmds.getAttr(shape + '.displaySmoothMesh') == 0:
        return 0
    return cmds.getAttr(shape + '.smoothLevel')


def set_subdivision(base, level, render=None):
    shape = _shape(base)
    if not shape:
        return
    cmds.setAttr(shape + '.displaySmoothMesh', 2 if level else 0)
    if level:
        cmds.setAttr(shape + '.smoothLevel', level)
    if render is not None:
        cmds.setAttr(shape + '.useSmoothPreviewForRender', bool(render))
        if render:
            cmds.setAttr(shape + '.renderSmoothLevel', int(render))


def apply_subdivision(base):
    level = subdivision_level(base)
    if not level:
        return False
    set_subdivision(base, 0)
    cmds.polySmooth(base, divisions=level, keepBorder=False)
    return True


# ---------------------------------------------------------------- instance modifier'lar (mirror, array)
def _instance(base, kind, local_matrix):
    inst = cmds.instance(base, name=base.split('|')[-1] + '_' + kind.replace(':', '_'))[0]
    parent = cmds.listRelatives(base, parent=True, fullPath=True)
    current = cmds.listRelatives(inst, parent=True, fullPath=True)
    if parent and (not current or current[0] != parent[0]):
        inst = cmds.parent(inst, parent[0], relative=True)[0]
    elif not parent and current:
        inst = cmds.parent(inst, world=True, relative=True)[0]
    inst = cmds.ls(inst, long=True)[0]
    cmds.xform(inst, objectSpace=True, matrix=local_matrix)
    cmds.connectAttr(base + '.matrix', inst + '.offsetParentMatrix', force=True)
    cmds.addAttr(inst, longName=BASE_ATTR, attributeType='message')
    cmds.connectAttr(base + '.message', inst + '.' + BASE_ATTR, force=True)
    _mark(inst, kind)
    cmds.setAttr(inst + '.overrideEnabled', 1)
    cmds.setAttr(inst + '.overrideDisplayType', 2)     # reference: viewport'ta secilemez
    for attr in ('t', 'r', 's'):                       # yanlislikla tasinip aynayi bozmasin
        for ax in 'xyz':
            cmds.setAttr('%s.%s%s' % (inst, attr, ax), lock=True)
    return inst


def add_mirror(base, axis='x'):
    m = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    m[AXES.index(axis) * 5] = -1
    for inst, k in instance_modifiers(base):
        if k == 'mirror:' + axis:
            return inst
    return _instance(base, 'mirror:' + axis, m)


def add_array(base, count=3, axis='x', gap=0.0):
    """count kopya (taban dahil); aralik = sinir kutusu boyu + gap (Blender 'Relative Offset' 1 gibi)."""
    remove_array(base)
    fn, _dag = _mesh_fn(base)
    box = fn.boundingBox
    size = (box.width, box.height, box.depth)[AXES.index(axis)]
    step = size + gap
    out = []
    for i in range(1, max(2, count)):
        m = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        m[12 + AXES.index(axis)] = step * i
        out.append(_instance(base, 'array', m))
    return out


def remove_array(base):
    for inst, k in instance_modifiers(base):
        if k == 'array':
            cmds.delete(inst)


def remove_instance(inst):
    if cmds.objExists(inst):
        cmds.delete(inst)


def apply_mirror(base, inst, threshold=None):
    axis = kind_of(inst).partition(':')[2] or 'x'
    cmds.delete(inst)
    fn, _dag = _mesh_fn(base)
    box = fn.boundingBox
    threshold = threshold if threshold is not None else max(1e-4, max(box.width, box.height, box.depth) * 1e-3)
    cmds.polyMirrorFace(base, worldSpace=False, axis=AXES.index(axis), axisDirection=1, mirrorAxis=1,
                        mergeMode=1, mergeThresholdType=1, mergeThreshold=threshold)


def apply_array(base):
    """Array kopyalarini taban objeyle birlestir; obje donusumu, pivotu, adi ve ebeveyni korunur."""
    insts = [i for i, k in instance_modifiers(base) if k == 'array']
    if not insts:
        return base
    name = base.split('|')[-1]
    parent = cmds.listRelatives(base, parent=True, fullPath=True)
    rp = cmds.xform(base, q=True, objectSpace=True, rotatePivot=True)
    sp = cmds.xform(base, q=True, objectSpace=True, scalePivot=True)
    world = cmds.xform(base, q=True, worldSpace=True, matrix=True)
    if parent:
        base = cmds.parent(base, world=True)[0]
        for inst, _k in instance_modifiers(base):     # kopyalar da tabanin obje uzayinda kalsin
            cmds.parent(inst, world=True, relative=True)
    base = cmds.ls(base, long=True)[0]
    cmds.xform(base, worldSpace=True, matrix=[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
    copies = []
    for inst in instance_modifiers(base):
        if inst[1] != 'array':
            continue
        dup = cmds.duplicate(inst[0])[0]
        for attr in (ATTR, BASE_ATTR):
            if cmds.attributeQuery(attr, node=dup, exists=True):
                cmds.deleteAttr(dup, attribute=attr)
        cmds.setAttr(dup + '.overrideEnabled', 0)
        for attr in ('t', 'r', 's'):
            for ax in 'xyz':
                cmds.setAttr('%s.%s%s' % (dup, attr, ax), lock=False)
        copies.append(dup)
    for inst in insts:
        cmds.delete(inst)
    keep = instance_modifiers(base)      # mirror instance'lari: birlesimden sonra yeniden kur
    keep_kinds = [k for _i, k in keep]
    for inst, _k in keep:
        cmds.delete(inst)
    result = cmds.polyUnite([base] + copies, constructionHistory=True, mergeUVSets=1)[0]
    cmds.delete(result, constructionHistory=True)
    for o in [base] + copies:
        if cmds.objExists(o) and not cmds.listRelatives(o, children=True):
            cmds.delete(o)
    result = cmds.rename(result, name)
    cmds.xform(result, worldSpace=True, matrix=world)
    cmds.xform(result, objectSpace=True, rotatePivot=rp, scalePivot=sp)
    if parent:
        result = cmds.parent(result, parent[0])[0]
    result = cmds.ls(result, long=True)[0]
    for k in keep_kinds:
        if k.startswith('mirror:'):
            add_mirror(result, k.partition(':')[2])
    cmds.select(result, replace=True)
    return result


# ---------------------------------------------------------------- gecmis modifier'lari
def _all_edges_sharper_than(base, angle):
    fn, dag = _mesh_fn(base)
    it = om.MItMeshEdge(dag)
    cos_tol = math.cos(math.radians(angle))
    out = []
    while not it.isDone():
        faces = list(it.getConnectedFaces())
        if len(faces) == 2:
            a = fn.getPolygonNormal(faces[0], om.MSpace.kObject)
            b = fn.getPolygonNormal(faces[1], om.MSpace.kObject)
            if a * b < cos_tol:
                out.append(it.index())
        it.next()
    return out


def add_history_modifier(base, kind, value=None):
    """Tabanin tum mesh'ine gecmis dugumu ekle. Donus: dugum ya da None."""
    if kind == 'bevel':
        edges = _all_edges_sharper_than(base, 30.0)
        if not edges:
            _msg(_t('Bevel: 30°\'den keskin kenar yok'))
            return None
        # Blender Bevel modifier varsayilanlari: 0.1 m, 1 segment, duz pah. chamfer=False Maya'da sekli kesmez,
        # yalnizca destek halkasi ekler (kose yuzleri duzlemsel olmaz); depth=1 cok segmentte yuvarlak profil;
        # subdivideNgons kose n-gon'larini Blender gibi dortgenlere boler.
        node = cmds.polyBevel3(_ranges(base, 'edge', edges), offset=value or 0.1, segments=1, offsetAsFraction=False,
                               mitering=0, chamfer=True, depth=1.0, subdivideNgons=True)[0]
    elif kind == 'solidify':
        node = cmds.polyExtrudeFacet(base + '.f[*]', keepFacesTogether=True, thickness=value or 0.1)[0]
    elif kind == 'triangulate':
        node = cmds.polyTriangulate(base + '.f[*]')[0]
    elif kind == 'weld':
        node = cmds.polyMergeVertex(base + '.vtx[*]', distance=value or 0.001)[0]
    else:
        return None
    _mark(node, kind)
    return node


MAIN_ATTR = {'bevel': 'offset', 'solidify': 'thickness', 'weld': 'distance'}
INT_ATTRS = {'bevel': [('segments', 1, 12)]}      # panelde ek tam sayi ayari: (oznitelik, en az, en cok)


def set_enabled(node, on):
    cmds.setAttr(node + '.nodeState', 0 if on else 1)      # 1 = HasNoEffect


def is_enabled(node):
    return cmds.getAttr(node + '.nodeState') == 0


def remove_history_modifier(node):
    if cmds.objExists(node):
        cmds.delete(node)


# ---------------------------------------------------------------- hepsini uygula (Ctrl+A)
def apply_all(base):
    """Blender 'Apply' (tum modifier'lar): subdiv, array, mirror gercek geometri; gecmis duzlesir."""
    if in_edit():
        exit_edit()
    # Blender'daki yaygin yigin sirasi: Mirror -> Array -> Subdivision (array mirror instance'larini yeniden
    # kurmak zorunda kalmasin; tek adimda temiz geri alinir)
    for inst, k in instance_modifiers(base):
        if k.startswith('mirror:'):
            apply_mirror(base, inst)
    base = apply_array(base)
    apply_subdivision(base)
    cmds.delete(base, constructionHistory=True)
    cmds.select(base, replace=True)
    return base


def apply_all_selected():
    bases = []
    for obj in _objs() or cmds.ls(hilite=True, long=True):
        base = base_of(obj) or (obj if _shape_type(obj) == 'mesh' else None)
        if base and base not in bases:
            bases.append(base)
    if not bases:
        _msg(_t('Önce bir mesh seç'))
        return
    for base in bases:
        apply_all(base)
    _msg(_t('Modifier\'lar uygulandı: %d obje') % len(bases))


# ---------------------------------------------------------------- panel
class ModifierPanel(QtWidgets.QDialog):
    """Blender Properties > Modifiers karsiligi: secili mesh'in modifier'lari."""

    def __init__(self):
        super(ModifierPanel, self).__init__(_main_window(), Qt.WindowType.Tool)
        self.setObjectName('BlenderKontrolModifiers')
        self.setWindowTitle(_t('Orange: modifier\'lar'))
        self.resize(360, 420)
        self.base = None
        self.layout_ = QtWidgets.QVBoxLayout(self)
        self.head = QtWidgets.QLabel()
        self.layout_.addWidget(self.head)
        add = QtWidgets.QHBoxLayout()
        self.add_box = QtWidgets.QComboBox()
        for key, label in self.ADD:
            self.add_box.addItem(_t(label), key)
        add_btn = QtWidgets.QPushButton(_t('Ekle'))
        add_btn.clicked.connect(self._add)
        add.addWidget(self.add_box, 1)
        add.addWidget(add_btn)
        self.layout_.addLayout(add)
        self.body = QtWidgets.QVBoxLayout()
        self.layout_.addLayout(self.body)
        self.layout_.addStretch(1)
        bottom = QtWidgets.QHBoxLayout()
        apply_all_btn = QtWidgets.QPushButton(_t('Hepsini uygula (Ctrl+A)'))
        apply_all_btn.clicked.connect(lambda: self._run(lambda: apply_all(self.base)))
        bottom.addWidget(apply_all_btn)
        self.layout_.addLayout(bottom)
        self.job = cmds.scriptJob(event=['SelectionChanged', self.refresh], killWithScene=False)
        self.refresh()

    ADD = [('subdiv', 'Subdivision Surface (smooth preview)'), ('mirror:x', 'Mirror X'), ('mirror:y', 'Mirror Y'),
           ('mirror:z', 'Mirror Z'), ('array', 'Array (3 kopya, X)'), ('bevel', 'Bevel (30° kenarlar)'),
           ('solidify', 'Solidify (kalınlık)'), ('triangulate', 'Triangulate'), ('weld', 'Weld (mesafeye göre birleştir)')]

    def _run(self, fn):
        if not self.base or not cmds.objExists(self.base):
            return
        try:
            undoable(fn)()
        except Exception as exc:
            _warn(str(exc))
        self.refresh()

    def _add(self):
        key = self.add_box.currentData()
        base = self.base

        def run():
            if key == 'subdiv':
                set_subdivision(base, max(1, subdivision_level(base) or 2))
            elif key.startswith('mirror:'):
                add_mirror(base, key.partition(':')[2])
            elif key == 'array':
                add_array(base, 3, 'x')
            else:
                add_history_modifier(base, key)
            cmds.select(base, replace=True)
        self._run(run)

    def _clear(self):
        while self.body.count():
            item = self.body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _row(self, title, widgets):
        box = QtWidgets.QGroupBox(title)
        lay = QtWidgets.QHBoxLayout(box)
        for w in widgets:
            lay.addWidget(w)
        self.body.addWidget(box)

    def _button(self, text, fn):
        b = QtWidgets.QPushButton(text)
        b.clicked.connect(lambda *_: self._run(fn))
        return b

    def refresh(self, *_):
        try:
            self.base = active_mesh()
        except Exception:
            self.base = None
        self._clear()
        if not self.base:
            self.head.setText(_t('Bir mesh seç'))
            return
        base = self.base
        self.head.setText('<b>%s</b>' % base.split('|')[-1])
        level = subdivision_level(base)
        if level:
            spin = QtWidgets.QSpinBox()
            spin.setRange(1, 4)
            spin.setValue(level)
            spin.setPrefix(_t('seviye '))
            spin.valueChanged.connect(lambda v: self._run(lambda: set_subdivision(base, v)))
            self._row(_t('Subdivision Surface'), [spin, self._button(_t('Uygula'), lambda: apply_subdivision(base)),
                                                  self._button('✕', lambda: set_subdivision(base, 0))])
        for inst, k in instance_modifiers(base):
            if k.startswith('mirror:'):
                self._row(_t('Mirror %s') % k.partition(':')[2].upper(),
                          [self._button(_t('Uygula'), functools.partial(apply_mirror, base, inst)),
                           self._button('✕', functools.partial(remove_instance, inst))])
        arrays = [i for i, k in instance_modifiers(base) if k == 'array']
        if arrays:
            spin = QtWidgets.QSpinBox()
            spin.setRange(2, 100)
            spin.setValue(len(arrays) + 1)
            spin.setPrefix(_t('kopya '))
            spin.valueChanged.connect(lambda v: self._run(lambda: add_array(base, v, 'x')))
            self._row(_t('Array'), [spin, self._button(_t('Uygula'), lambda: apply_array(base)),
                                    self._button('✕', lambda: remove_array(base))])
        for node, k in history_modifiers(base):
            widgets = []
            check = QtWidgets.QCheckBox(_t('açık'))
            check.setChecked(is_enabled(node))
            check.toggled.connect(functools.partial(lambda n, on: self._run(lambda: set_enabled(n, on)), node))
            widgets.append(check)
            attr = MAIN_ATTR.get(k)
            if attr:
                spin = QtWidgets.QDoubleSpinBox()
                spin.setDecimals(4)
                spin.setRange(0.0, 1e6)
                spin.setSingleStep(0.01)
                spin.setValue(cmds.getAttr('%s.%s' % (node, attr)))
                spin.valueChanged.connect(functools.partial(
                    lambda plug, v: self._run(lambda: cmds.setAttr(plug, v)), '%s.%s' % (node, attr)))
                widgets.append(spin)
            for name, low, high in INT_ATTRS.get(k, []):
                ispin = QtWidgets.QSpinBox()
                ispin.setRange(low, high)
                ispin.setValue(cmds.getAttr('%s.%s' % (node, name)))
                ispin.setPrefix(_t('segment ') if name == 'segments' else name + ' ')
                ispin.valueChanged.connect(functools.partial(
                    lambda plug, v: self._run(lambda: cmds.setAttr(plug, v)), '%s.%s' % (node, name)))
                widgets.append(ispin)
            widgets.append(self._button('✕', functools.partial(remove_history_modifier, node)))
            self._row('%s  (%s)' % (k.capitalize(), node), widgets)

    def closeEvent(self, ev):
        try:
            cmds.scriptJob(kill=self.job, force=True)
        except Exception:
            pass
        super(ModifierPanel, self).closeEvent(ev)


def show_panel():
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.objectName() == 'BlenderKontrolModifiers':
            w.close()
            w.deleteLater()
    panel = ModifierPanel()
    panel.move(QtGui.QCursor.pos() + QtCore.QPoint(16, 16))
    panel.show()
    return panel
