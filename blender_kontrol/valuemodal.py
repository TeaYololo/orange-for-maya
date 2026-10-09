# -*- coding: utf-8 -*-
"""Fareyle tek deger ayarlayan modal (Alt+S, Shift+E, sculpt F ...)."""
from __future__ import absolute_import, division, print_function

import math

import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui2

from .compat import (CTRL, EV_KEY_PRESS, EV_MMOVE, EV_MPRESS, EV_SHORTCUT, LMB, Qt, QtCore, QtGui, QtWidgets, RMB,
    SHIFT, wrapInstance)
from .core import _current_filter_set_modal, _tip, _warn, run_after_op
from .i18n import _t
from .util import _last_view_panel
from .ui import hint_bar
from .modal import Modal


# ---------------------------------------------------------------- deger modalleri (Alt+S, Shift+Alt+S, Shift+E)
class ValueModal(object):
    """Fareyle tek bir sayi ayarlayan modal: merkezden uzaklasip yaklasmak degeri degistirir.
    apply_fn(value) her degisiklikte cagrilir. Surukleme boyunca undo kaydi kapalidir; bitiste baslangica
    donulur (revert_fn ya da apply_fn(start)) ve son deger tek islem olarak kaydedilir. Iptalde yalnizca geri
    donulur (bos undo adimi bir onceki islemi silmesin)."""

    def __init__(self, panel, title, apply_fn, center, start=0.0, scale=None, lo=None, hi=None,
                 step=0.1, fmt='%.3f', revert_fn=None):
        self.panel = panel
        self.revert_fn = revert_fn
        self.undo_prev = None
        self.title = title
        self.apply_fn = apply_fn
        self.center_world = center
        self.start_value = start
        self.scale = scale
        self.lo, self.hi, self.step, self.fmt = lo, hi, step, fmt
        self.numeric = ''
        self.timer = None
        self.chunk_open = False
        self.dirty = False
        self.value = start
        self.last_applied = None

    def start(self):
        self.view = omui2.M3dView.getM3dViewFromModelPanel(self.panel)
        self.widget = wrapInstance(int(self.view.widget()), QtWidgets.QWidget)
        res = self.view.worldToView(self.center_world)
        self.center_2d = (float(res[0]), float(res[1]))
        if self.scale is None:   # piksel -> dunya birimi (merkezde)
            cam = om.MFnCamera(self.view.getCamera())
            right = cam.rightDirection(om.MSpace.kWorld).normal()
            b = self.view.worldToView(self.center_world + right)
            ppu = max(1e-3, math.hypot(float(b[0]) - self.center_2d[0], float(b[1]) - self.center_2d[1]))
            self.scale = 1.0 / ppu
        self.raw_last = QtGui.QCursor.pos()
        self.eff = QtCore.QPointF(self.raw_last)
        sx, sy = self._port(self.eff)
        self.d0 = math.hypot(sx - self.center_2d[0], sy - self.center_2d[1])
        cmds.undoInfo(openChunk=True, chunkName='blender_value')
        self.chunk_open = True
        self.undo_prev = cmds.undoInfo(q=True, stateWithoutFlush=True)
        cmds.undoInfo(stateWithoutFlush=False)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(15)
        self.update(force=True)
        return True

    def _port(self, global_pos):
        local = self.widget.mapFromGlobal(QtCore.QPointF(global_pos))
        sx = self.view.portWidth() / float(max(1, self.widget.width()))
        sy = self.view.portHeight() / float(max(1, self.widget.height()))
        return local.x() * sx, self.view.portHeight() - local.y() * sy

    def _compute(self):
        num = Modal._parse(self.numeric) if self.numeric else None
        if num is not None:
            v = num
        else:
            x, y = self._port(self.eff)
            v = self.start_value + (math.hypot(x - self.center_2d[0], y - self.center_2d[1]) - self.d0) * self.scale
            if Modal._mods() & CTRL:
                step = self.step * (0.1 if Modal._mods() & SHIFT else 1.0)
                v = round(v / step) * step
        if self.lo is not None:
            v = max(self.lo, v)
        if self.hi is not None:
            v = min(self.hi, v)
        return v

    def update(self, force=False):
        raw = QtGui.QCursor.pos()
        d = raw - self.raw_last
        self.raw_last = raw
        factor = 0.1 if (Modal._mods() & SHIFT) else 1.0
        self.eff = QtCore.QPointF(self.eff.x() + d.x() * factor, self.eff.y() + d.y() * factor)
        if not force and d.x() == 0 and d.y() == 0:
            return
        try:
            self.value = self._compute()
            if self.last_applied is None or abs(self.value - self.last_applied) > 1e-9:
                self.apply_fn(self.value)
                self.last_applied = self.value
                self.dirty = True
            self._show()
        except Exception as exc:
            _warn('%s: %s' % (self.title, exc))
            self.finish(False)

    def _show(self):
        title = '%s  ·  %s' % (_t(self.title), self.fmt % self.value)
        if self.numeric:
            title += '   [ %s ]' % self.numeric
        keys = [_t('<b>Fare</b> merkezden uzaklaş / yaklaş'), _t('<b>Shift</b> hassas'), _t('<b>Ctrl</b> adımlı'),
                _t('<b>Sayı</b> yaz'), _t('<b>Sol tık/Enter</b> onay'), _t('<b>Sağ tık/Esc</b> iptal')]
        html = ('<span style="color:#e8a33d; font-weight:bold">%s</span><br>%s'
                % (title, '&nbsp;&nbsp;·&nbsp;&nbsp;'.join(keys)))
        try:
            hint_bar().show(self.widget, html)
        except Exception:
            _tip(title)

    def key(self, ev, etype):
        if etype == EV_SHORTCUT:
            ev.accept()
            return True
        if etype != EV_KEY_PRESS:
            return True
        key = int(ev.key())
        text = ev.text()
        if key in (int(Qt.Key.Key_Return), int(Qt.Key.Key_Enter), int(Qt.Key.Key_Space)):
            self.finish(True)
        elif key == int(Qt.Key.Key_Escape):
            self.finish(False)
        elif key == int(Qt.Key.Key_Backspace):
            self.numeric = '' if ev.modifiers() & CTRL else self.numeric[:-1]
            self.update(force=True)
        elif text and text in '0123456789.,-':
            if text == '-' and self.numeric:
                self.numeric = self.numeric[1:] if self.numeric.startswith('-') else '-' + self.numeric
            else:
                self.numeric += text
            self.update(force=True)
        elif key in (int(Qt.Key.Key_Shift), int(Qt.Key.Key_Control)):
            self.update(force=True)
        return True

    def mouse(self, ev, etype, obj=None):
        if etype == EV_MPRESS:
            if ev.button() == LMB:
                self.finish(True)
            elif ev.button() == RMB:
                self.finish(False)
        return etype != EV_MMOVE

    def _resume_undo(self):
        """Sahne degisince (_abort_modal) askidaki undo kaydini geri ac."""
        prev = getattr(self, 'undo_prev', None)
        if prev is not None:
            cmds.undoInfo(stateWithoutFlush=prev)
            self.undo_prev = None

    def finish(self, ok):
        if self.timer:
            self.timer.stop()
            self.timer = None
        try:
            hint_bar().hide()
        except Exception:
            pass
        _current_filter_set_modal(None)
        if self.undo_prev is not None:
            final = self.last_applied if ok else None
            try:
                if self.last_applied is not None:
                    self.revert_fn() if self.revert_fn else self.apply_fn(self.start_value)
            except Exception as exc:
                _warn('%s: %s' % (self.title, exc))
            cmds.undoInfo(stateWithoutFlush=self.undo_prev)
            self.undo_prev = None
            if final is not None:
                try:
                    self.apply_fn(final)
                except Exception as exc:
                    _warn('%s: %s' % (self.title, exc))
                run_after_op()
            if self.chunk_open:
                cmds.undoInfo(closeChunk=True)
                self.chunk_open = False
        if self.chunk_open:     # undo kaydi acik calisan alt siniflar (KeyMoveModal)
            cmds.undoInfo(closeChunk=True)
            self.chunk_open = False
            if not ok and self.dirty:
                cmds.undo()
        cmds.refresh()


def _start_value_modal(**kwargs):
    panel = _last_view_panel()
    if not panel:
        return
    tool = ValueModal(panel, **kwargs)
    _current_filter_set_modal(tool)
    if not tool.start():
        _current_filter_set_modal(None)
