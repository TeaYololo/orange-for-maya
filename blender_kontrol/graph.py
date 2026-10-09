# -*- coding: utf-8 -*-
"""Graph Editor / Dope Sheet baglami."""
from __future__ import absolute_import, division, print_function

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om

from .compat import CTRL, EV_KEY_PRESS, QtCore, QtGui, QtWidgets, wrapInstance
from .core import _current_filter_set_modal, _msg, _tip, _warn
from .i18n import _t
from .keys import _phys
from .util import popup
from .ui import _PopupLine, hint_bar
from .modal import Modal
from .valuemodal import ValueModal


# ---------------------------------------------------------------- Graph Editor / Dope Sheet baglami
def _graph_editor(panel):
    kind = cmds.scriptedPanel(panel, q=True, type=True) if panel else None
    return panel + ('GraphEd' if kind == 'graphEditor' else 'DopeSheetEd'), kind


def _selected_keys():
    return cmds.keyframe(q=True, selected=True, name=True) or []


class KeyMoveModal(ValueModal):
    """Graph Editor / Dope Sheet'te G: secili anahtarlari fareyle zaman (X) ve deger (Y) ekseninde tasi."""

    def __init__(self, panel, editor, graph):
        super(KeyMoveModal, self).__init__(panel, 'KEY TAŞI', None, om.MPoint())
        self.editor, self.graph = editor, graph
        self.axis = None
        self.applied = (0.0, 0.0)

    def start(self):
        if not _selected_keys():
            _msg(_t('Önce anahtar (key) seç'))
            return False
        import maya.OpenMayaUI as omui_old
        ptr = omui_old.MQtUtil.findControl(self.editor)
        self.widget = wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None
        if self.widget is None:
            return False
        try:
            t0, t1 = cmds.animView(self.editor, q=True, startTime=True), cmds.animView(self.editor, q=True, endTime=True)
            v0, v1 = cmds.animView(self.editor, q=True, minValue=True), cmds.animView(self.editor, q=True, maxValue=True)
            self.tpp = (t1 - t0) / float(max(1, self.widget.width()))
            self.vpp = (v1 - v0) / float(max(1, self.widget.height())) if self.graph else 0.0
        except Exception:
            self.tpp, self.vpp = 0.1, 0.01
        self.start_pos = QtGui.QCursor.pos()
        cmds.undoInfo(openChunk=True, chunkName='blender_keymove')
        self.chunk_open = True
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(15)
        self.update(force=True)
        return True

    def update(self, force=False):
        try:
            d = QtGui.QCursor.pos() - self.start_pos
            num = Modal._parse(self.numeric) if self.numeric else None
            dt = 0.0 if self.axis == 'y' else (num if num is not None else d.x() * self.tpp)
            dv = 0.0 if (self.axis == 'x' or not self.graph) else (num if (num is not None and self.axis == 'y') else -d.y() * self.vpp)
            if not Modal._mods() & CTRL:
                dt = round(dt)            # Blender: en yakin kareye otomatik snap
            if (dt, dv) != self.applied:
                cmds.keyframe(edit=True, relative=True, option='over', includeUpperBound=True,
                              timeChange=dt - self.applied[0], valueChange=dv - self.applied[1])
                self.applied = (dt, dv)
                self.dirty = True
            self.value = dt
            self._show_keys()
        except Exception as exc:
            _warn('key: %s' % exc)
            self.finish(False)

    def _show_keys(self):
        title = _t('KEY TAŞI') + '  ·  Δt %.2f  Δv %.3f' % self.applied
        if self.axis:
            title += '  ·  ' + (_t('sadece zaman') if self.axis == 'x' else _t('sadece değer'))
        keys = [_t('<b>X</b> sadece zaman'), _t('<b>Y</b> sadece değer'), _t('<b>Ctrl</b> kare snap kapalı'),
                _t('<b>Sayı</b> yaz'), _t('<b>Sol tık/Enter</b> onay'), _t('<b>Sağ tık/Esc</b> iptal')]
        try:
            hint_bar().show(self.widget, '<span style="color:#e8a33d; font-weight:bold">%s</span><br>%s'
                            % (title, '&nbsp;&nbsp;·&nbsp;&nbsp;'.join(keys)))
        except Exception:
            _tip(title)

    def key(self, ev, etype):
        if etype == EV_KEY_PRESS:
            phys, _np = _phys(ev)
            if phys in ('x', 'y'):
                self.axis = None if self.axis == phys else phys
                self.update(force=True)
                return True
        return super(KeyMoveModal, self).key(ev, etype)


def key_move(panel):
    editor, kind = _graph_editor(panel)
    tool = KeyMoveModal(panel, editor, kind == 'graphEditor')
    _current_filter_set_modal(tool)
    if not tool.start():
        _current_filter_set_modal(None)


def key_scale(panel):
    """S: secili anahtarlari gecerli kare etrafinda zamanda olcekle (sayi ile)."""
    if not _selected_keys():
        _msg(_t('Önce anahtar (key) seç'))
        return
    now = cmds.currentTime(q=True)
    box = _PopupLine('1.0', lambda text: cmds.scaleKey(timeScale=Modal._parse(text) or 1.0, timePivot=now))
    box.move(QtGui.QCursor.pos() - QtCore.QPoint(130, 15))
    box.show()
    box.setFocus()
    _msg(_t('Zaman ölçeği yaz (pivot: geçerli kare), Enter'))


def key_interpolation_menu():
    def tangent(it, ot):
        cmds.keyTangent(inTangentType=it, outTangentType=ot)
    popup(_t('İnterpolasyon (T)'), [
        (_t('&Sabit (Constant)'), lambda: tangent('linear', 'step')),
        (_t('&Doğrusal (Linear)'), lambda: tangent('linear', 'linear')),
        (_t('&Bezier (Auto)'), lambda: tangent('auto', 'auto')),
        (_t('&Spline'), lambda: tangent('spline', 'spline')),
        (_t('Düz (&Flat)'), lambda: tangent('flat', 'flat')),
    ])


def key_handle_menu():
    popup(_t('Tutamak tipi (V)'), [
        (_t('&Serbest (Free)'), lambda: cmds.keyTangent(lock=False)),
        (_t('&Hizalı (Aligned)'), lambda: cmds.keyTangent(lock=True)),
        (_t('&Vektör (Vector)'), lambda: cmds.keyTangent(inTangentType='linear', outTangentType='linear')),
        (_t('&Otomatik (Automatic)'), lambda: cmds.keyTangent(inTangentType='auto', outTangentType='auto')),
        (_t('Otomatik &sınırlı (Auto Clamped)'), lambda: cmds.keyTangent(inTangentType='clamped', outTangentType='clamped')),
    ])


def key_extrapolation_menu():
    def infinity(kind):
        if _selected_keys():
            cmds.setInfinity(preInfinite=kind, postInfinite=kind)   # secili egriler (egri dugumu adiyla calismiyor)
    popup(_t('Ekstrapolasyon (Shift+E)'), [
        (_t('&Sabit (Constant)'), lambda: infinity('constant')),
        (_t('&Doğrusal (Linear)'), lambda: infinity('linear')),
        (_t('&Döngü (Cycle)'), lambda: infinity('cycle')),
        (_t('Göreli döngü (Cycle with &Offset)'), lambda: infinity('cycleRelative')),
        (_t('&Salınım (Oscillate)'), lambda: infinity('oscillate')),
    ])


def key_delete():
    if _selected_keys():
        cmds.cutKey(animation='keys', clear=True)


def key_select_all(panel, select=True):
    editor, _kind = _graph_editor(panel)
    if not select:
        cmds.selectKey(clear=True)
        return
    curves = cmds.animCurveEditor(editor, q=True, curvesShown=True) if cmds.animCurveEditor(editor, exists=True) else None
    curves = curves or cmds.keyframe(cmds.ls(sl=True) or [], q=True, name=True) or []
    if curves:
        cmds.selectKey(curves, replace=True)


def key_frame(panel, selected=False):
    editor, kind = _graph_editor(panel)
    if kind == 'graphEditor':
        cmds.animCurveEditor(editor, edit=True, lookAt='selected' if selected else 'all')
    else:
        mel.eval('FrameAllInAllViews' if not selected else 'FrameSelectedInAllViews')


def preview_range_menu():
    def from_keys():
        times = cmds.keyframe(q=True, selected=True, timeChange=True) or []
        if times:
            cmds.playbackOptions(minTime=min(times), maxTime=max(times))

    def reset():
        cmds.playbackOptions(minTime=cmds.playbackOptions(q=True, animationStartTime=True),
                             maxTime=cmds.playbackOptions(q=True, animationEndTime=True))
    popup(_t('Önizleme aralığı (P)'), [
        (_t('&Seçili anahtarlardan'), from_keys),
        (_t('&Sıfırla (animasyon aralığı)'), reset),
    ])
