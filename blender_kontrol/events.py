# -*- coding: utf-8 -*-
"""Uygulama geneli Qt olay filtresi."""
from __future__ import absolute_import, division, print_function

import functools

import maya.cmds as cmds

from .compat import (ALT, CTRL, EV_KEY_PRESS, EV_KEY_RELEASE, EV_MDBL, EV_MMOVE, EV_MPRESS, EV_MRELEASE,
    EV_SHORTCUT, EV_WHEEL, KEY_EVENTS, LMB, MMB, MOUSE_EVENTS, NOBTN, Qt, QtCore, QtGui, QtWidgets, RMB, SHIFT,
    _event_global_pos)
from .core import _state, _warn
from .settings import setting
from .i18n import _t
from .keys import _combo, _key_name
from .util import _context, _last_view_panel
from .editmode import in_edit
from .cursor import place_cursor
from .anim import frame_step
from .view import _alt_mmb_action, leave_auto_ortho
from .modal import _abort_modal
from .selection import _end_circle_select, select_fill_region, select_loop, select_path
from .modes import SCULPT_GLOBAL, _sculpting
from .keymap import CONTEXT_KEYMAPS, SCULPT_KEYMAP, _active_bindings, _run_binding


def _typing():
    w = QtWidgets.QApplication.focusWidget()
    if isinstance(w, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit,
                      QtWidgets.QAbstractSpinBox)):
        return True
    return isinstance(w, QtWidgets.QComboBox) and w.isEditable()


# ---------------------------------------------------------------- olay filtresi
class BlenderFilter(QtCore.QObject):
    def __init__(self, parent=None):
        super(BlenderFilter, self).__init__(parent)
        self.modal = None
        self.nav = None        # (basilan_tus, Maya'ya giden tus) navigasyon surerken
        self.eat_release = None
        self.alt_mmb = None    # (baslangic_konumu, panel) Alt+orta tus basiliyken
        self.fwd = None        # (basilan_tus, Maya'ya giden tus, modifier) kement surerken
        self.sending = False
        self.pending = None    # kabul ettigimiz ShortcutOverride'in KeyPress'i bekleniyor (kopya olay)
        self.replays = 0       # baska bir filtre KeyPress'i yuttugu icin kendimiz isledigimiz tus sayisi

    def eventFilter(self, obj, ev):
        if self.sending:
            return False
        try:
            t = ev.type()
            if t in KEY_EVENTS:
                if t == EV_KEY_PRESS:
                    self.pending = None
                handled = self._key(ev, t)
                if t == EV_SHORTCUT and handled:
                    self._expect_press(ev)
                return handled
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
            _warn(_t('beklenmeyen hata (Maya normal çalışmaya devam ediyor): %s') % exc)
            return False

    # -- filtre sirasi
    def _expect_press(self, ev):
        """ShortcutOverride'i kabul ettik: Qt ayni olay zincirinde KeyPress'i de gonderir. Gelmezse bizden sonra
        kurulan bir filtre (Maya acilisinda kendi filtresini kuruyor; Tab'i yutuyordu) onu yutmustur: filtremizi
        en uste tasi ve tusu kendimiz isle (kullanicinin basisi kaybolmasin)."""
        try:
            copy = QtGui.QKeyEvent(EV_KEY_PRESS, ev.key(), ev.modifiers(), ev.nativeScanCode(), ev.nativeVirtualKey(),
                                   ev.nativeModifiers(), ev.text(), ev.isAutoRepeat(), ev.count())
        except Exception:
            return
        self.pending = copy
        QtCore.QTimer.singleShot(0, self._check_pending)

    def _check_pending(self):
        ev, self.pending = self.pending, None
        if ev is None:
            return
        self.raise_to_top()
        self.replays += 1
        try:
            self._key(ev, EV_KEY_PRESS)
        except Exception as exc:
            _warn(_t('beklenmeyen hata (Maya normal çalışmaya devam ediyor): %s') % exc)

    def raise_to_top(self):
        """Filtreyi yeniden kur: Qt en son kurulan uygulama filtresini once cagirir."""
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
            app.installEventFilter(self)

    # -- klavye
    def _key(self, ev, t):
        if self.modal:
            return self.modal.key(ev, t)
        if QtWidgets.QApplication.activePopupWidget() or _typing() or _state.get('capturing'):
            return False
        if (int(ev.key()) == int(Qt.Key.Key_Escape) and _state.get('circle_prev')
                and cmds.currentCtx() == 'artSelectContext'):
            if t == EV_KEY_PRESS:
                QtCore.QTimer.singleShot(0, _end_circle_select)   # firca seciminden Esc ile cik
            return True
        name = _key_name(ev)
        if not name:
            return False
        combo = _combo(ev, name)
        if combo == 'space' and setting('space_action') == 'hotbox':
            return False   # Maya'nin hotbox'i calissin
        binding = _active_bindings().get(combo)
        ctx, panel = _context()
        if ctx == 'view' and _sculpting():
            # sculpt modu: firca tuslari once; genel tuslardan yalniz gorunum / oynatma vb.
            sculpt = SCULPT_KEYMAP.get(combo)
            if sculpt is not None:
                binding = sculpt
            elif binding is None or not (binding['panel'] or combo in SCULPT_GLOBAL):
                return False
        elif ctx in CONTEXT_KEYMAPS:
            binding = CONTEXT_KEYMAPS[ctx].get(combo) or binding
        if not binding or ctx not in binding['ctx']:
            return False
        if t == EV_SHORTCUT:
            ev.accept()
            return True
        if t == EV_KEY_RELEASE:
            return True
        if ev.isAutoRepeat() and not binding['repeat']:
            return True
        if binding['panel'] and ctx not in ('view', 'uv', 'graph'):
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
            return self.modal.mouse(ev, t, obj)
        if t == EV_WHEEL:
            mods = ev.modifiers()
            if mods & ALT and not mods & (CTRL | SHIFT) and _context()[0] == 'view':
                # Blender Alt+tekerlek: kare kaydir (asagi = ileri)
                QtCore.QTimer.singleShot(0, functools.partial(frame_step, -1 if ev.angleDelta().y() > 0 else 1))
                return True
            return False
        if QtWidgets.QApplication.activePopupWidget():
            return False
        if self.alt_mmb is not None:
            if t == EV_MRELEASE and ev.button() == MMB:
                start, panel = self.alt_mmb
                self.alt_mmb = None
                end = _event_global_pos(ev)
                QtCore.QTimer.singleShot(0, functools.partial(_alt_mmb_action, panel, start,
                                                              end.x() - start.x(), end.y() - start.y()))
            return True
        if self.fwd is not None:
            source, target, fmods = self.fwd
            if t == EV_MMOVE:
                self._send(obj, ev, t, NOBTN, target, fmods)
            elif t == EV_MRELEASE and ev.button() == source:
                self._send(obj, ev, t, target, NOBTN, fmods)
                self.fwd = None
                prev = _state.pop('lasso_prev', None) or 'selectSuperContext'
                QtCore.QTimer.singleShot(0, functools.partial(cmds.setToolTo, prev))
            return True
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
        if t == EV_MDBL:
            if ev.button() == MMB:
                return _context()[0] == 'view'
            mods = ev.modifiers()
            if (ev.button() == LMB and mods & CTRL and not mods & ALT and in_edit()
                    and _context()[0] == 'view'):
                # Ctrl+cift tik = ring (Blender, Emulate 3 Button acikken; Maya cift tik = loop)
                try:
                    handled = select_loop(_event_global_pos(ev), ring=True, add=bool(mods & SHIFT))
                except Exception as exc:
                    _warn(_t('seçim: %s') % exc)
                    handled = False
                if handled:
                    self.eat_release = LMB
                    return True
            return False
        if t != EV_MPRESS:
            return False
        button, mods = ev.button(), ev.modifiers()
        emulate = button == LMB and mods & ALT and setting('emulate_3button')
        if button == MMB and mods & ALT and not mods & (SHIFT | CTRL):
            ctx, panel = _context()
            if ctx != 'view':
                return False
            self.alt_mmb = (_event_global_pos(ev), panel)   # Alt+orta: merkeze al / eksene hizala
            return True
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
        if (button == RMB and _state.get('circle_prev') and _context()[0] == 'view'
                and cmds.currentCtx() == 'artSelectContext'):
            _end_circle_select()          # Blender: firca seciminden sag tikla cik
            self.eat_release = RMB
            return True
        if button == RMB and mods & CTRL and not mods & ALT and _context()[0] == 'view':
            # Blender: Ctrl+sag surukle = kement ekle, Shift+Ctrl+sag = kement cikar
            _state['lasso_prev'] = cmds.currentCtx()
            cmds.setToolTo('lassoSelectContext')
            fmods = CTRL if mods & SHIFT else (CTRL | SHIFT)    # Maya kement: Ctrl cikar, Ctrl+Shift ekle
            self.fwd = (RMB, LMB, fmods)
            self._send(obj, ev, t, LMB, LMB, fmods)
            return True
        if button == RMB and mods & SHIFT and not mods & (CTRL | ALT) and _context()[0] == 'view':
            try:
                if place_cursor(_event_global_pos(ev)):   # Shift+sag tik: 3D imlec
                    self.eat_release = RMB
                    return True
            except Exception as exc:
                _warn(_t('imlec: %s') % exc)
        if button == LMB and mods & (ALT | CTRL) and in_edit() and _context()[0] == 'view':
            pos = _event_global_pos(ev)
            try:
                if mods & ALT:
                    # Alt+tik loop, Ctrl+Alt+tik ring; Shift ile ekle
                    handled = select_loop(pos, ring=bool(mods & CTRL), add=bool(mods & SHIFT))
                elif mods & SHIFT:
                    handled = select_fill_region(pos)   # Shift+Ctrl+tik: bolge doldur
                else:
                    handled = select_path(pos)   # Ctrl+tik: en kisa yol
            except Exception as exc:
                _warn(_t('seçim: %s') % exc)
                handled = False
            if handled:
                self.eat_release = LMB
                return True
        return False
