# -*- coding: utf-8 -*-
"""Ortak arayuz parcalari: ipucu cubugu, onizleme katmani, pie menu, satir kutusu."""
from __future__ import absolute_import, division, print_function

import math
import os
import sys

import maya.cmds as cmds
import maya.api.OpenMaya as om

from .compat import Qt, QtCore, QtGui, QtWidgets, RMB, _main_window
from .core import _warn
from .settings import setting
from .util import _NoUndo, undoable


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


class PreviewOverlay(QtWidgets.QWidget):
    """Viewport'un ustunde seffaf katman; loop cut onizleme cizgileri (geometriye dokunmaz)."""

    def __init__(self):
        super(PreviewOverlay, self).__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint |
                                             Qt.WindowType.WindowTransparentForInput |
                                             Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.lines = []      # [(noktalar, QColor)]

    def show_lines(self, picker, lines, colors=None):
        """picker: .widget ve .view'i olan herhangi bir nesne (Picker, Modal).
        lines: port koordinatinda nokta listeleri; colors: her cizgi icin QColor (varsayilan sari)."""
        widget = picker.widget
        sx = widget.width() / float(max(1, picker.view.portWidth()))
        sy = widget.height() / float(max(1, picker.view.portHeight()))
        h = picker.view.portHeight()
        colors = colors or [LOOPCUT_COLOR] * len(lines)
        self.lines = [([QtCore.QPointF(x * sx, (h - y) * sy) for x, y in line], color)
                      for line, color in zip(lines, colors)]
        self.setGeometry(QtCore.QRect(widget.mapToGlobal(QtCore.QPoint(0, 0)), widget.size()))
        if not self.isVisible():
            self.show()
        self.update()

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        for line, color in self.lines:
            painter.setPen(QtGui.QPen(color, 2))
            painter.drawPolyline(QtGui.QPolygonF(line))
        painter.end()


LOOPCUT_COLOR = QtGui.QColor(255, 215, 0)
# Blender tema renkleri: X kirmizi, Y yesil, Z mavi
AXIS_COLORS = {'x': QtGui.QColor(255, 51, 82), 'y': QtGui.QColor(139, 220, 0), 'z': QtGui.QColor(40, 144, 255)}
NORMAL_COLOR = QtGui.QColor(40, 144, 255)


# ---------------------------------------------------------------- Viewport 2.0 katmani (orange_overlay eklentisi)
PLUGIN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'orange_overlay.py')
PLUGIN_NAME = 'orange_overlay'
OVERLAY_NODE = 'orangeOverlay'
OVERLAY_SHAPE = 'orangeOverlayShape'
OVERLAY_STORE = '_orange_overlay'


def _overlay_store():
    main = sys.modules['__main__']
    data = getattr(main, OVERLAY_STORE, None)
    if data is None:
        data = {'camera': None, 'lines': []}
        setattr(main, OVERLAY_STORE, data)
    return data


def overlay_plugin_loaded():
    try:
        return bool(cmds.pluginInfo(PLUGIN_NAME, q=True, loaded=True))
    except Exception:
        return False


def load_overlay_plugin():
    """orange_overlay eklentisini yukle. Donus: VP2 cizimi kullanilabilir mi."""
    if overlay_plugin_loaded():
        return True
    try:
        cmds.loadPlugin(PLUGIN_FILE, quiet=True)
    except Exception as exc:
        _warn('overlay plug-in: %s' % exc)
    if not overlay_plugin_loaded():
        return False
    try:
        # yardimci dugum kaydedilmiyor; sahne dosyasina 'requires' da yazilmasin (Orange'i olmayan acinca uyari)
        cmds.pluginInfo(PLUGIN_NAME, edit=True, writeRequires=False)
    except Exception:
        pass
    return True


class Vp2Overlay(object):
    """PreviewOverlay ile ayni arayuz; cizgiler Viewport 2.0 icinde (MUIDrawManager) cizilir."""

    def __init__(self):
        self.visible = False
        self.views = []

    @staticmethod
    def _ensure_node():
        if cmds.objExists(OVERLAY_SHAPE):
            return
        modified = cmds.file(q=True, modified=True)
        with _NoUndo():
            tr = cmds.createNode('transform', name=OVERLAY_NODE, skipSelect=True)
            shape = cmds.createNode('orangeOverlay', name=OVERLAY_SHAPE, parent=tr, skipSelect=True)
            cmds.setAttr(tr + '.hiddenInOutliner', True)
            cmds.setAttr(tr + '.overrideEnabled', 1)
            cmds.setAttr(tr + '.overrideDisplayType', 2)      # reference: viewport'ta secilemez
            for node in (tr, shape):
                obj = om.MSelectionList().add(node).getDependNode(0)
                om.MFnDependencyNode(obj).setDoNotWrite(True)   # sahneyle kaydedilmez
        cmds.file(modified=modified)    # yardimci dugum sahneyi 'degisti' yapmasin

    def show_lines(self, picker, lines, colors=None):
        colors = colors or [LOOPCUT_COLOR] * len(lines)
        self._ensure_node()
        store = _overlay_store()
        store['camera'] = picker.view.getCamera().fullPathName()
        store['lines'] = [([(float(x), float(y)) for x, y in pts], (c.redF(), c.greenF(), c.blueF()), 2.0)
                          for pts, c in zip(lines, colors)]
        self.visible = True
        if picker.view not in self.views:
            self.views.append(picker.view)
        picker.view.refresh(False, True)

    def hide(self):
        store = _overlay_store()
        had = bool(store['lines'])
        store['lines'] = []
        store['camera'] = None
        self.visible = False
        _delete_overlay_node()   # dugum yalniz onizleme gorunurken var: sahne dosyasina 'requires' bile yazilmaz
        if had:
            for view in self.views:
                try:
                    view.refresh(False, True)
                except Exception:
                    pass
        self.views = []

    def isVisible(self):
        return self.visible


_overlay = []
_vp2_failed = []


def preview_overlay():
    """Onizleme cizgisi katmani. Ayar 'overlay': 'qt' (varsayilan; viewport ustunde seffaf Qt penceresi) ya da
    'vp2' (orange_overlay eklentisiyle Viewport 2.0 icinde; kompozitorsuz Linux / macOS icin). Maya 2026+
    guvenilir olmayan klasorden eklenti yuklerken her oturumda izin sorar; bu yuzden VP2 isteğe baglidir."""
    want_vp2 = setting('overlay') == 'vp2' and not _vp2_failed
    if _overlay:
        current = _overlay[0]
        if isinstance(current, Vp2Overlay) == want_vp2:
            return current
        try:
            current.hide()
        except Exception:
            pass
        del _overlay[:]
    backend = None
    if want_vp2:
        if load_overlay_plugin():
            backend = Vp2Overlay()
        else:
            _vp2_failed.append(True)    # bir kez dene; yuklenemiyorsa bu oturumda Qt katmani
    _overlay.append(backend or PreviewOverlay())
    return _overlay[0]


def _delete_overlay_node():
    if not cmds.objExists(OVERLAY_NODE):
        return
    modified = cmds.file(q=True, modified=True)
    with _NoUndo():
        cmds.delete(OVERLAY_NODE)
    cmds.file(modified=modified)


def shutdown_overlay():
    """Kapatirken: cizgileri gizle, yardimci dugumu sil, eklentiyi bosalt (Maya varsayilanina don)."""
    for w in _overlay:
        try:
            w.hide()
        except Exception:
            pass
    del _overlay[:]
    _delete_overlay_node()
    if overlay_plugin_loaded():
        try:
            cmds.unloadPlugin(PLUGIN_NAME, force=True)
        except Exception:
            pass


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
