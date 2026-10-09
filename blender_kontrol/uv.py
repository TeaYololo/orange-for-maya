# -*- coding: utf-8 -*-
"""UV editoru baglami."""
from __future__ import absolute_import, division, print_function

import maya.cmds as cmds
import maya.mel as mel

from .compat import (CTRL, EV_KEY_PRESS, EV_MMOVE, EV_MPRESS, EV_SHORTCUT, LMB, Qt, QtCore, QtGui, QtWidgets, RMB,
    SHIFT, _main_window, wrapInstance)
from .core import _current_filter_set_modal, _msg, _tip, _warn
from .i18n import _t
from .keys import _phys
from .util import _sel, _shape_type, popup
from .ui import hint_bar
from .modal import Modal


# ---------------------------------------------------------------- UV editoru baglami
def _uv_objs():
    objs = cmds.ls(hilite=True, long=True) or cmds.ls(sl=True, objectsOnly=True, long=True) or []
    out = []
    for o in objs:
        if cmds.nodeType(o) != 'transform':
            o = (cmds.listRelatives(o, parent=True, fullPath=True) or [o])[0]
        if _shape_type(o) == 'mesh' and o not in out:
            out.append(o)
    return out


def _uvs():
    return cmds.ls(cmds.polyListComponentConversion(_sel(), toUV=True) or [], flatten=True)


def uv_select_all():
    objs = _uv_objs()
    if objs:
        cmds.select([o + '.map[*]' for o in objs], replace=True)


def uv_select_mode(kind):
    mel.eval({'vertex': 'SelectUVMask', 'edge': 'SelectEdgeMask', 'face': 'SelectFacetMask',
              'island': 'SelectUVShell'}[kind])


def uv_select_linked():
    if _sel():
        mel.eval('polySelectBorderShell 0')


def uv_pin(value):
    uvs = _uvs()
    if uvs:
        cmds.polyPinUV(uvs, value=value)
        _msg(_t('UV pin: %d') % len(uvs) if value else _t('UV pin kaldırıldı: %d') % len(uvs))


def uv_split():
    if _uvs():
        mel.eval('polySplitTextureUV')


def uv_stitch():
    edges = cmds.polyListComponentConversion(_uvs(), toEdge=True, internal=True)
    if edges:
        cmds.polyMapSewMove(edges)


def uv_align(axis):
    """U ya da V'yi ortalamaya hizala (Blender Align X / Y)."""
    uvs = _uvs()
    if not uvs:
        return
    coords = cmds.polyEditUV(uvs, q=True)
    values = coords[0::2] if axis == 'u' else coords[1::2]
    avg = sum(values) / len(values)
    cmds.polyEditUV(uvs, relative=False, **({'uValue': avg} if axis == 'u' else {'vValue': avg}))


def uv_center():
    uvs = _uvs()
    if not uvs:
        return
    c = cmds.polyEditUV(uvs, q=True)
    u = (min(c[0::2]) + max(c[0::2])) / 2.0
    v = (min(c[1::2]) + max(c[1::2])) / 2.0
    cmds.polyEditUV(uvs, relative=True, uValue=0.5 - u, vValue=0.5 - v)


def uv_snap_menu():
    popup(_t('UV hizala (Shift+S)'), [
        (_t('&U hizala (dikey çizgi)'), lambda: uv_align('u')),
        (_t('&V hizala (yatay çizgi)'), lambda: uv_align('v')),
        (_t('&Ortala (0.5, 0.5)'), uv_center),
        (_t('&Normalize (0-1)'), lambda: cmds.polyNormalizeUV(_uvs() or _uv_objs(), normalizeType=1, preserveAspectRatio=True)),
        (_t('&Paketle (Layout)'), lambda: cmds.u3dLayout(_uv_objs())),
    ])


def uv_transform_tool(kind):
    """UV editorunde G / R / S: Maya'nin UV manipulatoru (eski davranis; F3'ten erisilebilir)."""
    cmds.setToolTo({'move': 'moveSuperContext', 'rotate': 'RotateSuperContext', 'scale': 'scaleSuperContext'}[kind])
    _msg(_t('UV %s: manipülatörü sürükle') % _t({'move': 'taşı', 'rotate': 'döndür', 'scale': 'ölçekle'}[kind]))


class UvModal(object):
    """UV editorunde fareyle G / R / S (Blender gibi modal).

    Maya UV editorunun pan / zoom bilgisini disari vermiyor; bu yuzden hareket goreli: fare yer degistirmesi
    piksel basina sabit bir UV miktarina cevrilir (varsayilan cerceve: 0..1 alani editor yuksekliginin ~%80'i).
    Tam deger icin sayi yazilir (G 0.25 Enter). X / Y eksen kilidi, Ctrl adimli, Shift hassas. Surukleme kayitsiz,
    sonuc tek undo adimi."""

    TITLES = {'move': 'UV TAŞI', 'rotate': 'UV DÖNDÜR', 'scale': 'UV ÖLÇEKLE'}

    def __init__(self, panel, kind):
        self.panel = panel
        self.kind = kind
        self.axis = None
        self.numeric = ''
        self.timer = None
        self.chunk_open = False
        self.undo_prev = None
        self.applied = self._identity()
        self.widget = None

    def _identity(self):
        return {'move': (0.0, 0.0), 'rotate': 0.0, 'scale': (1.0, 1.0)}[self.kind]

    def start(self):
        self.uvs = _uvs()
        if not self.uvs:
            _msg(_t('Önce UV seç'))
            return False
        import maya.OpenMayaUI as omui_old
        ptr = omui_old.MQtUtil.findControl(self.panel) if self.panel else None
        self.widget = wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else _main_window()
        coords = cmds.polyEditUV(self.uvs, q=True) or [0.0, 0.0]
        us, vs = coords[0::2], coords[1::2]
        self.pivot = ((min(us) + max(us)) / 2.0, (min(vs) + max(vs)) / 2.0)
        self.ppu = max(50.0, self.widget.height() * 0.8)        # piksel / UV birimi (tahmini)
        self.raw_last = QtGui.QCursor.pos()
        self.eff = QtCore.QPointF(self.raw_last)
        self.start_pos = QtCore.QPointF(self.eff)
        cmds.undoInfo(openChunk=True, chunkName='blender_uv')
        self.chunk_open = True
        self.undo_prev = cmds.undoInfo(q=True, stateWithoutFlush=True)
        cmds.undoInfo(stateWithoutFlush=False)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(15)
        self.update(force=True)
        return True

    # -- hesap
    def _value(self):
        num = Modal._parse(self.numeric) if self.numeric else None
        dx = (self.eff.x() - self.start_pos.x())
        dy = -(self.eff.y() - self.start_pos.y())
        ctrl = bool(Modal._mods() & CTRL)
        if self.kind == 'move':
            if num is not None:
                du, dv = (0.0, num) if self.axis == 'y' else (num, 0.0)
            else:
                du, dv = dx / self.ppu, dy / self.ppu
                if ctrl:
                    step = 1.0 / 64 if Modal._mods() & SHIFT else 1.0 / 16
                    du, dv = round(du / step) * step, round(dv / step) * step
            if self.axis == 'x':
                dv = 0.0
            elif self.axis == 'y':
                du = 0.0
            return (du, dv)
        if self.kind == 'rotate':
            angle = num if num is not None else dx * 0.5
            if ctrl and num is None:
                angle = round(angle / 5.0) * 5.0
            return angle
        f = num if num is not None else max(0.001, 1.0 + dx / 200.0)
        if ctrl and num is None:
            f = round(f * 10) / 10.0
        if self.axis == 'x':
            return (f, 1.0)
        if self.axis == 'y':
            return (1.0, f)
        return (f, f)

    def _apply_delta(self, old, new):
        """Goreli: old -> new (uygulanan toplam)."""
        pu, pv = self.pivot
        if self.kind == 'move':
            du, dv = new[0] - old[0], new[1] - old[1]
            if abs(du) > 1e-12 or abs(dv) > 1e-12:
                cmds.polyEditUV(self.uvs, relative=True, uValue=du, vValue=dv)
        elif self.kind == 'rotate':
            d = new - old
            if abs(d) > 1e-9:
                cmds.polyEditUV(self.uvs, pivotU=pu, pivotV=pv, angle=d)
        else:
            su = new[0] / old[0] if abs(old[0]) > 1e-9 else 1.0
            sv = new[1] / old[1] if abs(old[1]) > 1e-9 else 1.0
            if abs(su - 1.0) > 1e-9 or abs(sv - 1.0) > 1e-9:
                cmds.polyEditUV(self.uvs, pivotU=pu, pivotV=pv, scaleU=su, scaleV=sv)

    def update(self, force=False):
        raw = QtGui.QCursor.pos()
        d = raw - self.raw_last
        self.raw_last = raw
        factor = 0.1 if (Modal._mods() & SHIFT) else 1.0
        self.eff = QtCore.QPointF(self.eff.x() + d.x() * factor, self.eff.y() + d.y() * factor)
        if not force and d.x() == 0 and d.y() == 0:
            return
        try:
            value = self._value()
            if value != self.applied:
                self._apply_delta(self.applied, value)
                self.applied = value
            self._show()
        except Exception as exc:
            _warn('UV: %s' % exc)
            self.finish(False)

    def _show(self):
        a = self.applied
        if self.kind == 'move':
            value = 'U %.4f  V %.4f' % a
        elif self.kind == 'rotate':
            value = '%.1f°' % a
        else:
            value = 'U %.3f  V %.3f' % a
        title = _t(self.TITLES[self.kind]) + '  ·  ' + value
        if self.axis:
            title += '  ·  ' + self.axis.upper()
        if self.numeric:
            title += '   [ %s ]' % self.numeric
        keys = [_t('<b>Fare</b> hareket (göreli)'), _t('<b>X Y</b> eksen'), _t('<b>G R S</b> değiştir'),
                _t('<b>Ctrl</b> adımlı'), _t('<b>Shift</b> hassas'), _t('<b>Sayı</b> yaz'),
                _t('<b>Sol tık/Enter</b> onay'), _t('<b>Sağ tık/Esc</b> iptal')]
        try:
            hint_bar().show(self.widget, '<span style="color:#e8a33d; font-weight:bold">%s</span><br>%s'
                            % (title, '&nbsp;&nbsp;·&nbsp;&nbsp;'.join(keys)))
        except Exception:
            _tip(title)

    # -- olaylar
    def key(self, ev, etype):
        if etype == EV_SHORTCUT:
            ev.accept()
            return True
        if etype != EV_KEY_PRESS:
            return True
        key = int(ev.key())
        text = ev.text()
        name = _phys(ev)[0]
        if key in (int(Qt.Key.Key_Return), int(Qt.Key.Key_Enter), int(Qt.Key.Key_Space)):
            self.finish(True)
        elif key == int(Qt.Key.Key_Escape):
            self.finish(False)
        elif name in ('x', 'y') and not ev.isAutoRepeat():
            self._revert()
            self.axis = None if self.axis == name else name
            self.update(force=True)
        elif name in ('g', 'r', 's') and not ev.isAutoRepeat():
            self._revert()
            self.kind = {'g': 'move', 'r': 'rotate', 's': 'scale'}[name]
            self.applied = self._identity()
            self.numeric = ''
            self.start_pos = QtCore.QPointF(self.eff)
            self.update(force=True)
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

    def _revert(self):
        identity = self._identity()
        if self.applied != identity:
            self._apply_delta(self.applied, identity)
        self.applied = identity

    def mouse(self, ev, etype, obj=None):
        if etype == EV_MPRESS:
            if ev.button() == LMB:
                self.finish(True)
            elif ev.button() == RMB:
                self.finish(False)
        return etype != EV_MMOVE

    def _resume_undo(self):
        if self.undo_prev is not None:
            cmds.undoInfo(stateWithoutFlush=self.undo_prev)
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
        final = self.applied if ok else None
        try:
            self._revert()
        except Exception as exc:
            _warn('UV: %s' % exc)
        self._resume_undo()
        if final is not None and final != self._identity():
            self._apply_delta(self._identity(), final)
        if self.chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.chunk_open = False


def uv_modal(panel, kind):
    """UV editoru G / R / S."""
    tool = UvModal(panel, kind)
    _current_filter_set_modal(tool)
    if not tool.start():
        _current_filter_set_modal(None)
