# -*- coding: utf-8 -*-
"""F9: son islemi ayarla paneli."""
from __future__ import absolute_import, division, print_function

import maya.cmds as cmds
import maya.mel as mel

from .compat import Qt, QtCore, QtWidgets, _main_window
from .core import _msg, _warn
from .i18n import _t
from .util import undoable
from .objects import move_near_cursor


# Sik gorulen history ozniteliklerinin Turkce adlari (digerleri Maya'nin niceName'i ile; Ingilizce arayuzde
# _t cevirisi yine Maya'nin adina denk gelir). Ham ad ipucunda gorunur.
NICE_NAMES = {
    'keepFacesTogether': 'Yüzleri birlikte tut', 'thickness': 'Kalınlık', 'offset': 'Ofset', 'divisions': 'Bölme sayısı',
    'segments': 'Segment', 'fraction': 'Oran', 'depth': 'Derinlik', 'smoothingAngle': 'Yumuşatma açısı',
    'distance': 'Mesafe', 'taper': 'Daralma', 'twist': 'Burgu', 'width': 'Genişlik', 'height': 'Yükseklik',
    'radius': 'Yarıçap', 'scale': 'Ölçek', 'roundness': 'Yuvarlaklık', 'autoFit': 'Otomatik sığdır',
    'localTranslateX': 'Yerel taşıma X', 'localTranslateY': 'Yerel taşıma Y', 'localTranslateZ': 'Yerel taşıma Z',
    'localRotateX': 'Yerel döndürme X', 'localRotateY': 'Yerel döndürme Y', 'localRotateZ': 'Yerel döndürme Z',
    'localScaleX': 'Yerel ölçek X', 'localScaleY': 'Yerel ölçek Y', 'localScaleZ': 'Yerel ölçek Z',
    'mergeThreshold': 'Birleştirme eşiği', 'subdivisionsAxis': 'Eksen bölmeleri', 'subdivisionsHeight': 'Yükseklik bölmeleri',
}


def nice_name(node, attr):
    """Oznitelik etiketi: bilinen Turkce ad (cevrilir), yoksa Maya'nin okunabilir adi, o da yoksa ham ad."""
    if attr in NICE_NAMES:
        return _t(NICE_NAMES[attr])
    try:
        return cmds.attributeQuery(attr, node=node, niceName=True) or attr
    except Exception:
        return attr


# ---------------------------------------------------------------- F9: son islemi ayarla paneli
class AdjustLastPanel(QtWidgets.QDialog):
    """Blender 'Adjust Last Operation': secili objenin en son history dugumunun sayisal ayarlari."""

    SKIP = {'caching', 'frozen', 'nodeState', 'isHistoricallyInteresting', 'inputComponents', 'useOldPolyArchitecture'}

    def __init__(self, node):
        super(AdjustLastPanel, self).__init__(_main_window(), Qt.WindowType.Tool)
        self.setObjectName('BlenderKontrolAdjustLast')
        self.node = node
        self.setWindowTitle(_t('Son işlem: %s') % node)
        layout = QtWidgets.QVBoxLayout(self)
        head = QtWidgets.QLabel('<b>%s</b>  <span style="color:gray">(%s)</span>' % (node, cmds.nodeType(node)))
        layout.addWidget(head)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)
        self.count = 0
        for attr in self._attrs():
            widget = self._widget(attr)
            if widget is not None:
                label = QtWidgets.QLabel(nice_name(node, attr))
                label.setToolTip(attr)
                widget.setToolTip('%s.%s' % (node, attr))
                form.addRow(label, widget)
                self.count += 1
        if not self.count:
            form.addRow(QtWidgets.QLabel(_t('Ayarlanabilir sayısal değer yok')))
        more = QtWidgets.QPushButton(_t('Attribute Editor\'de aç'))
        more.clicked.connect(lambda: mel.eval('showEditor "%s"' % node))
        layout.addWidget(more)

    def _attrs(self):
        attrs = cmds.listAttr(self.node, keyable=True, scalar=True) or []
        attrs += [a for a in (cmds.listAttr(self.node, scalar=True, settable=True, visible=True) or [])
                  if a not in attrs and a not in self.SKIP and not a.startswith(('ihi', 'message'))]
        out = []
        for a in attrs:
            if '.' in a or a in self.SKIP:
                continue
            try:
                kind = cmds.getAttr('%s.%s' % (self.node, a), type=True)
            except Exception:
                continue
            if kind in ('double', 'float', 'doubleLinear', 'doubleAngle', 'long', 'short', 'byte', 'bool', 'enum'):
                out.append(a)
        return out[:24]

    def _widget(self, attr):
        plug = '%s.%s' % (self.node, attr)
        kind = cmds.getAttr(plug, type=True)
        value = cmds.getAttr(plug)
        if kind == 'bool':
            w = QtWidgets.QCheckBox()
            w.setChecked(bool(value))
            w.toggled.connect(lambda v, p=plug: self._set(p, bool(v)))
        elif kind == 'enum':
            w = QtWidgets.QComboBox()
            names = (cmds.attributeQuery(attr, node=self.node, listEnum=True) or [''])[0].split(':')
            w.addItems([n.split('=')[0] for n in names])
            w.setCurrentIndex(int(value))
            w.currentIndexChanged.connect(lambda v, p=plug: self._set(p, int(v)))
        elif kind in ('long', 'short', 'byte'):
            w = QtWidgets.QSpinBox()
            w.setRange(-1000000, 1000000)
            w.setKeyboardTracking(False)     # her tus vurusunda degil, Enter / odak cikisinda uygula
            w.setValue(int(value))
            w.valueChanged.connect(lambda v, p=plug: self._set(p, int(v)))
        else:
            w = QtWidgets.QDoubleSpinBox()
            w.setDecimals(4)
            w.setRange(-1e7, 1e7)
            w.setSingleStep(0.1)
            w.setKeyboardTracking(False)
            w.setValue(float(value))
            w.valueChanged.connect(lambda v, p=plug: self._set(p, float(v)))
        return w

    def _set(self, plug, value):
        try:
            undoable(lambda: cmds.setAttr(plug, value))()
        except Exception as exc:
            _warn(str(exc))


def adjust_last():
    """F9: son islemin ayarlari (yuzen panel; Maya'da secili objenin en son history dugumu)."""
    objs = cmds.ls(hilite=True, long=True) or cmds.ls(sl=True, objectsOnly=True, long=True)
    if not objs:
        _msg(_t('Önce bir obje seç'))
        return
    history = [n for n in (cmds.listHistory(objs[0], pruneDagObjects=True) or [])
               if cmds.nodeType(n) not in ('groupId', 'groupParts', 'shadingEngine', 'tweak', 'objectSet')]
    if not history:
        _msg(_t('Bu objenin ayarlanacak bir işlemi yok'))
        return
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.objectName() == 'BlenderKontrolAdjustLast':
            w.close()
            w.deleteLater()
    panel = AdjustLastPanel(history[0])
    panel.adjustSize()
    move_near_cursor(panel, QtCore.QPoint(16, 16))
    panel.show()
    return panel
