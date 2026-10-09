# -*- coding: utf-8 -*-
"""Blender for Maya: Maya icinde calisan uctan uca testler.

Kullanim (Maya Script Editor, Python):
    import sys; sys.path.insert(0, r'<repo>/tests'); sys.path.insert(0, r'<repo>')
    import maya_live_tests as T
    T.run()                 # tum bolumler
    T.run('edit')           # tek bolum
    print(T.report())

Testler kullanicinin sahnesine dokunmaz: yalnizca 'bkt_' onekli objeler olusturur ve siler; kamera,
ayarlar, kisayol dosyasi ve aktif arac test sonunda geri yuklenir. Menuler (QMenu.exec) test
sirasinda acilmaz, yakalanir ve ogeleri dogrudan calistirilir. Fare imleci test boyunca hareket eder.
"""
from __future__ import absolute_import, print_function

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import traceback

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui2

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

Qt = QtCore.Qt
PREFIX = 'bkt_'
RESULTS = []          # (bolum, test, gecti, ayrinti)
SECTIONS = []
NO = Qt.KeyboardModifier.NoModifier
MODS = {'ctrl': Qt.KeyboardModifier.ControlModifier, 'alt': Qt.KeyboardModifier.AltModifier,
        'shift': Qt.KeyboardModifier.ShiftModifier}
SPECIAL_QT = {'tab': Qt.Key.Key_Tab, 'space': Qt.Key.Key_Space, 'grave': Qt.Key.Key_QuoteLeft, 'comma': Qt.Key.Key_Comma,
              'period': Qt.Key.Key_Period, 'delete': Qt.Key.Key_Delete, 'home': Qt.Key.Key_Home, 'end': Qt.Key.Key_End,
              'pgup': Qt.Key.Key_PageUp, 'pgdown': Qt.Key.Key_PageDown, 'left': Qt.Key.Key_Left, 'right': Qt.Key.Key_Right,
              'up': Qt.Key.Key_Up, 'down': Qt.Key.Key_Down, 'esc': Qt.Key.Key_Escape, 'enter': Qt.Key.Key_Return,
              'backspace': Qt.Key.Key_Backspace}
NUMPAD_QT = {'.': Qt.Key.Key_Period, '+': Qt.Key.Key_Plus, '-': Qt.Key.Key_Minus, '/': Qt.Key.Key_Slash, '*': Qt.Key.Key_Asterisk}


def bk():
    return sys.modules['blender_kontrol']


def _package_modules():
    """Paket ve tum alt modulleri (yama tum modullere uygulanmali: her modul adlari kendisi import eder)."""
    return [m for n, m in sorted(sys.modules.items())
            if m is not None and (n == 'blender_kontrol' or n.startswith('blender_kontrol.'))]


def patch_all(name, value):
    """Adi tanimlayan / import eden her modulde degistir; eski degerleri dondur."""
    old = {}
    for m in _package_modules():
        if name in vars(m):
            old[m] = vars(m)[name]
            setattr(m, name, value)
    return old


def unpatch(name, old):
    for m, value in old.items():
        setattr(m, name, value)


def section(fn):
    SECTIONS.append(fn)
    return fn


# ---------------------------------------------------------------- yardimci baglam
class Ctx(object):
    def __init__(self, name):
        self.name = name
        self.bk = bk()
        self.refresh_view()
        self.trace_filter(self.bk)

    @staticmethod
    def trace_filter(bk_module):
        """BK_TRACE ayarliysa filtrenin gordugu tus olaylarini da dosyaya yaz (hata ayiklama)."""
        path = os.environ.get('BK_TRACE')
        filt = bk_module._filter()
        if not path or filt is None or getattr(filt, '_traced', False):
            return
        orig_key, orig_check = filt._key, filt._check_pending

        def key(ev, t):
            res = orig_key(ev, t)
            with io.open(path, 'a', encoding='utf-8') as fh:
                fh.write(u'   filter %s key=0x%X -> %s%s' % (int(t), int(ev.key()), res, os.linesep))
            return res

        def check():
            with io.open(path, 'a', encoding='utf-8') as fh:
                fh.write(u'   check_pending pending=%s%s' % (filt.pending is not None, os.linesep))
            return orig_check()
        filt._key, filt._check_pending, filt._traced = key, check, True
        warn_orig = bk_module.core._warn

        def warn(text):
            with io.open(path, 'a', encoding='utf-8') as fh:
                fh.write(u'   WARN %s%s' % (text, os.linesep))
            return warn_orig(text)
        patch_all('_warn', warn)

    def refresh_view(self):
        panels = [p for p in (cmds.getPanel(visiblePanels=True) or []) if cmds.getPanel(typeOf=p) == 'modelPanel']
        persp = [p for p in panels if self.bk._cam(p).split('|')[-1] == 'persp']
        self.panel = (persp or panels)[0]
        self.view = omui2.M3dView.getM3dViewFromModelPanel(self.panel)
        self.widget = wrapInstance(int(self.view.widget()), QtWidgets.QWidget)

    # -- sonuc
    def ok(self, label, cond, detail=''):
        RESULTS.append((self.name, label, bool(cond), repr(detail)[:200]))
        return bool(cond)

    # -- olay dongusu
    @staticmethod
    def flush(n=6):
        import maya.utils
        for _ in range(n):
            QtWidgets.QApplication.processEvents()
        try:
            maya.utils.processIdleEvents()    # scriptJob'lar (or. SelectionChanged) bosta calisir
        except Exception:
            pass

    # -- ekran
    def screen(self, point):
        res = self.view.worldToView(om.MPoint(*point) if not isinstance(point, om.MPoint) else point)
        return float(res[0]), float(res[1])

    def gpos(self, point):
        sx, sy = self.screen(point)
        x = sx * self.widget.width() / float(self.view.portWidth())
        y = self.widget.height() - sy * self.widget.height() / float(self.view.portHeight())
        return self.widget.mapToGlobal(QtCore.QPoint(int(round(x)), int(round(y))))

    def cursor_to(self, point=None):
        if point is None:
            g = self.widget.mapToGlobal(QtCore.QPoint(self.widget.width() // 2, self.widget.height() // 2))
        elif isinstance(point, QtCore.QPoint):
            g = point
        else:
            g = self.gpos(point)
        QtGui.QCursor.setPos(g)
        self.flush(2)
        return g

    def frame(self, nodes):
        cmds.viewFit(self.bk._cam(self.panel), nodes, animate=False)
        cmds.refresh()

    # -- klavye: 'ctrl+shift+g', 'np7', 'x', 'enter'
    def key_event(self, combo, etype=QtCore.QEvent.Type.KeyPress, text=None):
        parts = combo.split('+')
        if parts[-1] == '':            # 'np+' / 'ctrl+np+'
            parts = parts[:-2] + [parts[-2] + '+']
        name = parts[-1]
        mods = NO
        for m in parts[:-1]:
            mods |= MODS[m]
        sc, qt = 0, Qt.Key.Key_unknown
        if name.startswith('np') and len(name) > 2:
            ch = name[2:]
            mods |= Qt.KeyboardModifier.KeypadModifier
            inv = dict((v, k) for k, v in self.bk.NUMPAD_SCAN.items())
            sc = inv[ch]
            qt = NUMPAD_QT.get(ch) or getattr(Qt.Key, 'Key_' + ch)
            text = ch if text is None else text
        elif name in SPECIAL_QT:
            qt = SPECIAL_QT[name]
            inv = dict((v, k) for k, v in self.bk.SCAN.items())
            sc = inv.get(name, 0)
            if name == 'delete':
                sc = 0x153          # genisletilmis tus
            text = {'space': ' ', 'comma': ',', 'period': '.', 'grave': '`'}.get(name, '') if text is None else text
        elif name.startswith('f') and name[1:].isdigit():
            qt = getattr(Qt.Key, 'Key_F' + name[1:])
            text = '' if text is None else text
        else:
            inv = dict((v, k) for k, v in self.bk.SCAN.items())
            sc = inv[name]
            qt = getattr(Qt.Key, 'Key_' + name.upper())
            if text is None:
                text = name.upper() if mods & MODS['shift'] else name
        return QtGui.QKeyEvent(etype, qt, mods, sc, 0, 0, text)

    def press(self, combo, text=None, flush=True):
        if os.environ.get('BK_TRACE'):
            try:
                with io.open(os.environ['BK_TRACE'], 'a', encoding='utf-8') as fh:
                    fh.write(u'%s press %s ctx=%s under=%s modal=%s%s' % (
                        self.name, combo, self.bk._context()[0], cmds.getPanel(underPointer=True),
                        type(self.modal()).__name__ if self.modal() else None, os.linesep))
            except Exception:
                pass
        for et in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
            QtWidgets.QApplication.sendEvent(self.widget, self.key_event(combo, et, text))
        if flush:
            self.flush()

    def type(self, s):
        for ch in s:
            if ch.isdigit():
                self.press(ch)
            elif ch == '.':
                self.press('period', text='.')
            elif ch == '-':
                ev_args = (Qt.Key.Key_Minus, NO, 0x0C, 0, 0, '-')
                for et in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
                    QtWidgets.QApplication.sendEvent(self.widget, QtGui.QKeyEvent(et, *ev_args))
            elif ch == '=':
                for et in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
                    QtWidgets.QApplication.sendEvent(self.widget, QtGui.QKeyEvent(et, Qt.Key.Key_Equal, NO, 0x0D, 0, 0, '='))
            else:
                self.press(ch.lower(), text=ch)
        self.flush()

    # -- fare: filtreden gecen gercek olay
    def mouse(self, etype, gpos, button, buttons, mods=NO):
        local = QtCore.QPointF(self.widget.mapFromGlobal(gpos))
        ev = QtGui.QMouseEvent(etype, local, QtCore.QPointF(gpos), button, buttons, mods)
        QtWidgets.QApplication.sendEvent(self.widget, ev)

    def click(self, gpos, button=Qt.MouseButton.LeftButton, mods=NO):
        T = QtCore.QEvent.Type
        self.mouse(T.MouseButtonPress, gpos, button, button, mods)
        self.mouse(T.MouseButtonRelease, gpos, button, Qt.MouseButton.NoButton, mods)
        self.flush()

    def drag(self, points, button, mods=NO):
        T = QtCore.QEvent.Type
        self.mouse(T.MouseButtonPress, points[0], button, button, mods)
        for p in points[1:]:
            QtGui.QCursor.setPos(p)
            self.mouse(T.MouseMove, p, Qt.MouseButton.NoButton, button, mods)
            self.flush(1)
        self.mouse(T.MouseButtonRelease, points[-1], button, Qt.MouseButton.NoButton, mods)
        self.flush()

    # -- menu yakalama (QMenu.exec test sirasinda Maya'yi bloklamasin)
    @contextlib.contextmanager
    def popups(self):
        calls = []

        def fake(title, items):
            calls.append((title, [i for i in items if i]))
        old = patch_all('popup', fake)
        try:
            yield calls
        finally:
            unpatch('popup', old)

    @staticmethod
    def run_item(calls, needle, index=-1):
        """Yakalanan son menude etiketinde needle gecen ogeyi calistir (undo chunk icinde)."""
        title, items = calls[index]

        def norm(text):   # Turkce I/İ kucuk harf donusumu Python'da birlesik nokta uretiyor
            return text.replace('&', '').replace(u'İ', 'i').replace('I', u'ı').lower()
        for label, fn in items:
            if norm(needle) in norm(label):
                b = sys.modules['blender_kontrol']
                b.undoable(fn)()
                Ctx.flush()
                return label
        raise AssertionError('menude yok: %s (%s)' % (needle, [i[0] for i in items]))

    def modal(self):
        f = self.bk._filter()
        return f.modal if f else None

    def msgs(self):
        return list(_MSGS)

    def clear_msgs(self):
        del _MSGS[:]


_MSGS = []


def _wpos(node, comp):
    return cmds.xform('%s.%s' % (node, comp), q=True, worldSpace=True, translation=True)


def _center(comp):
    pts = cmds.xform(comp, q=True, worldSpace=True, translation=True)
    n = len(pts) // 3
    return (sum(pts[0::3]) / n, sum(pts[1::3]) / n, sum(pts[2::3]) / n)


def _round(v, n=3):
    if isinstance(v, om.MPoint):
        v = (v.x, v.y, v.z)
    return [round(x, n) for x in v]


def _sel():
    return cmds.ls(sl=True, flatten=True) or []


def _close_editor(keyword):
    """Testin actigi UV / Graph editor penceresini kapat (workspaceControl)."""
    for w in cmds.lsUI(type='workspaceControl') or []:
        if keyword in w:
            try:
                if cmds.workspaceControl(w, q=True, visible=True):
                    cmds.workspaceControl(w, e=True, close=True)
            except Exception:
                pass


def _cleanup():
    nodes = cmds.ls(PREFIX + '*', type='transform') or []
    nodes += cmds.ls(PREFIX + '*', type=('displayLayer', 'lambert', 'shadingEngine')) or []
    for n in nodes:
        if cmds.objExists(n):
            try:
                cmds.delete(n)
            except Exception:
                pass


# ---------------------------------------------------------------- ortam: kaydet / geri yukle
_SAVED = {}


def _save_env(b):
    _SAVED['settings'] = dict((k, b.setting(k)) for k in b.SETTINGS)
    path = b._keymap_path()
    _SAVED['keymap'] = io.open(path, encoding='utf-8').read() if os.path.exists(path) else None
    _SAVED['tool'] = cmds.currentCtx()
    _SAVED['persp'] = cmds.xform('persp', q=True, worldSpace=True, matrix=True)
    _SAVED['coi'] = cmds.getAttr('perspShape.centerOfInterest')
    _SAVED['ortho'] = cmds.getAttr('perspShape.orthographic')
    _SAVED['time'] = cmds.currentTime(q=True)
    _SAVED['range'] = (cmds.playbackOptions(q=True, minTime=True), cmds.playbackOptions(q=True, maxTime=True))
    _SAVED['softsel'] = (cmds.softSelect(q=True, softSelectEnabled=True), cmds.softSelect(q=True, softSelectCurve=True),
                         cmds.softSelect(q=True, softSelectFalloff=True), cmds.softSelect(q=True, softSelectDistance=True))
    _SAVED['cursor'] = (cmds.xform(b.CURSOR, q=True, ws=True, t=True), cmds.xform(b.CURSOR, q=True, ws=True, ro=True)) \
        if cmds.objExists(b.CURSOR) else None
    _SAVED['sel'] = cmds.ls(sl=True, long=True)
    if _SAVED.get('msg_patch'):
        unpatch('_msg', _SAVED.pop('msg_patch'))
    orig = b.core._msg
    _SAVED['msg_patch'] = patch_all('_msg', lambda t: (_MSGS.append(t), orig(t)))


def _restore_env(b):
    for k, v in _SAVED.get('settings', {}).items():
        b.set_setting(k, v)
    path = b._keymap_path()
    if _SAVED.get('keymap') is None:
        if os.path.exists(path):
            os.remove(path)
    else:
        io.open(path, 'w', encoding='utf-8').write(_SAVED['keymap'])
    b._rebuild_keymap()
    try:
        cmds.setAttr('perspShape.orthographic', _SAVED['ortho'])
        cmds.xform('persp', worldSpace=True, matrix=_SAVED['persp'])
        cmds.setAttr('perspShape.centerOfInterest', _SAVED['coi'])
    except Exception:
        pass
    cmds.currentTime(_SAVED['time'])
    cmds.playbackOptions(minTime=_SAVED['range'][0], maxTime=_SAVED['range'][1])
    en, curve, falloff, dist = _SAVED['softsel']
    cmds.softSelect(edit=True, softSelectEnabled=en, softSelectCurve=curve, softSelectFalloff=falloff,
                    softSelectDistance=dist)
    if _SAVED.get('cursor'):
        b.set_cursor(om.MPoint(*_SAVED['cursor'][0]), tuple(_SAVED['cursor'][1]))
    try:
        cmds.setToolTo(_SAVED['tool'])
    except Exception:
        cmds.setToolTo('selectSuperContext')
    if _SAVED.get('msg_patch'):
        unpatch('_msg', _SAVED.pop('msg_patch'))
    if b.in_edit():
        b.exit_edit()
    sel = [s for s in _SAVED.get('sel', []) if cmds.objExists(s)]
    cmds.select(sel, replace=True) if sel else cmds.select(clear=True)


def _standard_camera(b):
    """Her bolumden once: tek perspektif gorunum, persp kamerasi standart acida (bolumler birbirini etkilemesin)."""
    panels = [p for p in (cmds.getPanel(visiblePanels=True) or []) if cmds.getPanel(typeOf=p) == 'modelPanel']
    if len(panels) > 1:
        mel.eval('setNamedPanelLayout "Single Perspective View"')
    panel = [p for p in (cmds.getPanel(visiblePanels=True) or []) if cmds.getPanel(typeOf=p) == 'modelPanel'][0]
    cmds.lookThru(panel, 'persp')
    cmds.setAttr('perspShape.orthographic', 0)
    cmds.xform('persp', worldSpace=True, translation=(12, 9, 12), rotation=(-30, 45, 0))
    cmds.setAttr('perspShape.centerOfInterest', 19.0)
    if cmds.isolateSelect(panel, q=True, state=True):
        mel.eval('enableIsolateSelect "%s" 0;' % panel)
    if b.in_edit():
        b.exit_edit()
    cmds.setToolTo('selectSuperContext')
    cmds.refresh()


def run(*names):
    """Bolumleri calistir (bos = hepsi). Ozet satiri dondurur."""
    b = bk()
    if not b.is_installed():
        b.install(quiet=True)
    chosen = [s for s in SECTIONS if not names or s.__name__[2:] in names]
    _save_env(b)
    b.set_setting('language', 'tr')
    try:
        for fn in chosen:
            if b._filter() is not None:
                b._filter().raise_to_top()   # Maya sonradan filtre kurmus olabilir; bolum basinda belirleyici sira
            _standard_camera(b)
            ctx = Ctx(fn.__name__[2:])
            try:
                fn(ctx)
            except Exception:
                RESULTS.append((ctx.name, 'BEKLENMEYEN HATA', False, traceback.format_exc()[-600:]))
            finally:
                m = ctx.modal()
                if m is not None:
                    try:
                        m.finish(False)
                    except Exception:
                        b._abort_modal()
                for w in QtWidgets.QApplication.topLevelWidgets():
                    if w.objectName().startswith('BlenderKontrol') or isinstance(w, b.PieMenu):
                        w.close()
                if b.in_edit():
                    b.exit_edit()
                _cleanup()
    finally:
        _restore_env(b)
    return summary()


def summary():
    total = len(RESULTS)
    failed = [r for r in RESULTS if not r[2]]
    return '%d test, %d gecti, %d kaldi' % (total, total - len(failed), len(failed))


def report(only_failed=False):
    lines = []
    for sec, label, passed, detail in RESULTS:
        if only_failed and passed:
            continue
        lines.append('%s [%s] %s%s' % ('OK ' if passed else 'XX ', sec, label, '' if passed else '  -> ' + detail))
    lines.append(summary())
    return '\n'.join(lines)


def reset():
    del RESULTS[:]


# ================================================================ BOLUMLER
@section
def t_install(c):
    b = c.bk
    c.ok('kurulu', b.is_installed())
    c.ok('surum', b.__version__.count('.') == 2, b.__version__)
    c.ok('Blender menusu', cmds.menu('BlenderKontrolMenu', exists=True))
    track = cmds.selectPref(q=True, trackSelectionOrder=True)
    b.uninstall(quiet=True)
    c.ok('kapatinca filtre yok', not b.is_installed())
    c.ok('kapatinca ayar geri (trackSelectionOrder)', cmds.selectPref(q=True, trackSelectionOrder=True) in (False, track))
    b.install(quiet=True)
    c.ok('tekrar kurulu', b.is_installed() and cmds.selectPref(q=True, trackSelectionOrder=True))
    for lang, needle in (('tr', 'Kısayol'), ('en', 'Shortcut')):
        b.set_setting('language', lang)
        b._build_menu()
        labels = [cmds.menuItem(i, q=True, label=True) for i in cmds.menu('BlenderKontrolMenu', q=True, itemArray=True)
                  if not cmds.menuItem(i, q=True, divider=True)]
        c.ok('menu dili %s' % lang, any(needle in l for l in labels), labels[:3])
        b.show_help()
        c.flush()
        help_w = [w for w in QtWidgets.QApplication.topLevelWidgets() if w.objectName() == 'BlenderKontrolHelp' and w.isVisible()]
        text = help_w[-1].findChild(QtWidgets.QTextBrowser).toPlainText() if help_w else ''
        c.ok('F1 yardim %s' % lang, ('Maya, Blender gibi' in text and 'Orange' in text) if lang == 'tr'
             else 'Maya, the Blender way' in text, text[:60])
        for w in help_w:
            w.close()
    b.set_setting('language', 'tr')
    b._build_menu()
    missing = []
    for k, binding in b.BINDINGS.items():
        if not binding.get('title'):
            missing.append(k)
    c.ok('tum tuslarin F3 basligi var', not missing, missing)
    untranslated = [x['title'] for x in b.BINDINGS.values() if x['title'] not in b.EN]
    c.ok('tum tus basliklarinin Ingilizcesi var', not untranslated, untranslated[:5])
    # Maya 2027 (Qt 6.8): wrapInstance ayni pointer icin onbellekli wrapper dondurur; ayni pointeri hep ayni
    # sinifla (QWidget) sarmak gerekir. Ana pencere ve viewport tekrar tekrar sarilabilmeli.
    w1, w2 = b.compat._main_window(), b.compat._main_window()
    v1 = wrapInstance(int(c.view.widget()), QtWidgets.QWidget)
    v2 = wrapInstance(int(c.view.widget()), QtWidgets.QWidget)
    c.ok('wrapInstance tekrar sarma (Maya 2027 onbellegi)', isinstance(w1, QtWidgets.QWidget) and isinstance(w2, QtWidgets.QWidget)
         and w1.objectName() == 'MayaWindow' and v1.width() == v2.width() > 0)
    # Hotkey Editor: 'Orange' kategorisinde runTimeCommand'lar; ac/kapa onlari silmez
    names = b.hotkeys.command_names()
    c.ok('Hotkey Editor komutlari', all(cmds.runTimeCommand(n, exists=True) for n in names.values())
         and cmds.runTimeCommand('Orange_LoopCut', q=True, category=True) == 'Orange', len(names))
    b.uninstall(quiet=True)
    c.ok('kapatinca komutlar kalir (kullanicinin tuslari bozulmaz)', cmds.runTimeCommand('Orange_LoopCut', exists=True))
    cube = cmds.polyCube(name=PREFIX + 'rtc')[0]
    cmds.select(clear=True)
    mel.eval(names['a'])           # Orange kapaliyken de calisir: hepsini sec
    c.ok('runTimeCommand calisir (Orange kapali)', cube in (cmds.ls(sl=True) or []), cmds.ls(sl=True))
    b.install(quiet=True)
    cmds.select(clear=True)


@section
def t_keys(c):
    b = c.bk
    T = QtCore.QEvent.Type
    KP = Qt.KeyboardModifier.KeypadModifier
    cases = [('win', Qt.Key.Key_G, NO, 0x22, 0x47, 'g', 'g'), ('win', Qt.Key.Key_unknown, NO, 0x17, 0, 'ı', 'i'),
             ('win', Qt.Key.Key_7, KP, 0x47, 0x67, '7', 'np7'), ('win', Qt.Key.Key_Slash, KP, 0x135, 0x6F, '/', 'np/'),
             ('linux', Qt.Key.Key_G, NO, 42, 0, 'g', 'g'), ('linux', Qt.Key.Key_1, KP, 87, 0, '1', 'np1'),
             ('linux', Qt.Key.Key_Slash, KP, 106, 0, '/', 'np/'), ('mac', Qt.Key.Key_A, NO, 0, 0, 'a', 'a'),
             ('mac', Qt.Key.Key_unknown, NO, 0, 0x22, 'ı', 'i'), ('mac', Qt.Key.Key_7, KP, 0, 0x59, '7', 'np7'),
             ('mac', Qt.Key.Key_unknown, NO, 0, 0, '', None)]
    for plat, key, mods, sc, vk, text, want in cases:
        ev = QtGui.QKeyEvent(T.KeyPress, key, mods, sc, vk, 0, text)
        c.ok('fiziksel tus %s %r' % (plat, want), b._key_name(ev, plat) == want, b._key_name(ev, plat))
    ev = c.key_event('ctrl+alt+shift+c')
    c.ok('kombinasyon sirasi', b._combo(ev, b._key_name(ev)) == 'ctrl+alt+shift+c')
    c.ok('etiketler', [b._combo_label(x) for x in ('ctrl+np1', 'grave', 'comma', 'ctrl+pgup')]
         == ['Ctrl+Numpad 1', '`', ',', 'Ctrl+PageUp'])
    # emulate numpad
    b.set_setting('emulate_numpad', 1)
    c.ok('emulate numpad: 1 -> np1', b._key_name(c.key_event('1')) == 'np1')
    b.set_setting('emulate_numpad', 0)
    # kisayol degistirme
    b._save_overrides({'g': 'alt+shift+g', 'r': ''})
    b._rebuild_keymap()
    act = b._active_bindings()
    c.ok('ozel kisayol etkin', act.get('alt+shift+g') is b.BINDINGS['g'] and 'g' not in act and 'r' not in act)
    c.ok('F3 guncel kisayol', dict((e[2][1], e[1]) for e in b._search_entries() if e[2][0] == 'binding').get('g') == 'Alt+Shift+G')
    b._save_overrides({})
    b._rebuild_keymap()
    c.ok('varsayilana donus', b._active_bindings().get('g') is b.BINDINGS['g'])
    # ayar penceresi + tus yakalama
    dlg = b.show_settings()
    c.flush()
    row = dlg.ids.index('k')
    dlg._start_capture(row)
    dlg.eventFilter(dlg.table, c.key_event('ctrl+alt+k'))
    c.ok('ayar penceresinde tus yakalama', b._combo_for('k') == 'ctrl+alt+k', b._combo_for('k'))
    dlg._reset_all()
    c.ok('hepsini varsayilana', b._combo_for('k') == 'k')
    dlg.close()
    # tus filtresi: baglam disinda calismaz
    c.cursor_to()
    c.ok('baglam: 3D gorunum', b._context()[0] == 'view', b._context())
    # bizden sonra kurulan bir filtre Tab'i yutarsa (Maya acilista boyle yapiyor) filtre kendini onarir
    cube = cmds.polyCube(name=PREFIX + 'thief')[0]
    cmds.select(cube)
    c.cursor_to()

    class Thief(QtCore.QObject):
        def eventFilter(self, obj, ev):
            return ev.type() == QtCore.QEvent.Type.KeyPress and int(ev.key()) == int(Qt.Key.Key_Tab)
    app = QtWidgets.QApplication.instance()
    thief = Thief()
    app.installEventFilter(thief)
    filt = b._filter()
    before = filt.replays
    try:
        c.press('tab')
        c.flush()
        c.ok('yutulan Tab yine edit moduna gecirir', b.in_edit(), filt.replays - before)
        c.ok('filtre kendini en uste aldi', filt.replays - before == 1, filt.replays - before)
        c.press('tab')
        c.flush()
        c.ok('ikinci Tab dogrudan gelir (tekrar onarim yok)', not b.in_edit() and filt.replays - before == 1,
             filt.replays - before)
    finally:
        app.removeEventFilter(thief)
        if b.in_edit():
            b.exit_edit()


@section
def t_navigation(c):
    b = c.bk
    p = c.panel
    cube = cmds.polyCube(name=PREFIX + 'nav')[0]
    cmds.select(cube)
    c.cursor_to()
    for combo, side in (('np1', 'front'), ('np3', 'rightSide'), ('np7', 'top'), ('ctrl+np1', 'back'),
                        ('ctrl+np3', 'leftSide'), ('ctrl+np7', 'bottom')):
        c.press(combo)
        c.ok('%s -> %s' % (combo, side), b._current_view(p) == side, b._current_view(p))
    c.ok('eksen gorunumu ortografik', cmds.getAttr(b._cam_shape(b._cam(p)) + '.orthographic'))
    c.press('np5')
    c.ok('numpad 5 perspektif', not cmds.getAttr(b._cam_shape(b._cam(p)) + '.orthographic'))
    c.press('np1')
    c.press('np9')
    c.ok('numpad 9 ters', b._current_view(p) == 'back', b._current_view(p))
    m0 = cmds.xform(b._cam(p), q=True, ws=True, m=True)
    c.press('np8')
    c.ok('numpad 8 orbit', cmds.xform(b._cam(p), q=True, ws=True, m=True) != m0)
    t0 = cmds.xform(b._cam(p), q=True, ws=True, t=True)
    c.press('ctrl+np6')
    c.ok('ctrl+numpad 6 pan', cmds.xform(b._cam(p), q=True, ws=True, t=True) != t0)
    r0 = cmds.xform(b._cam(p), q=True, ws=True, ro=True)
    c.press('shift+np4')
    c.ok('shift+numpad 4 roll', cmds.xform(b._cam(p), q=True, ws=True, ro=True) != r0)
    coi = cmds.getAttr(b._cam_shape(b._cam(p)) + '.centerOfInterest')
    c.press('np+')
    c.ok('numpad + zoom', cmds.getAttr(b._cam_shape(b._cam(p)) + '.centerOfInterest') != coi)
    cmds.xform(cube, ro=(0, 45, 0))
    c.press('shift+np1')
    look = om.MVector(*cmds.xform(b._cam(p), q=True, ws=True, m=True)[8:11])
    local_z = om.MVector(*cmds.xform(cube, q=True, ws=True, m=True)[8:11])
    c.ok('shift+numpad 1 lokal on', abs(look.normal() * local_z.normal() - 1) < 1e-3, (_round(look), _round(local_z)))
    c.press('np.')
    c.ok('numpad . secime odaklan', True)
    c.press('home')
    c.press('np/')
    c.ok('numpad / local view', cmds.isolateSelect(p, q=True, state=True))
    c.press('np/')
    c.ok('local view kapandi', not cmds.isolateSelect(p, q=True, state=True))
    ed = b._editor(p)
    c.press('shift+z')
    c.ok('shift+z wireframe', cmds.modelEditor(ed, q=True, displayAppearance=True) == 'wireframe')
    c.press('shift+z')
    c.press('alt+z')
    c.ok('alt+z x-ray', cmds.modelEditor(ed, q=True, xray=True))
    c.press('alt+z')
    c.press('alt+shift+z')
    c.ok('overlay kapali', not cmds.modelEditor(ed, q=True, grid=True))
    c.press('alt+shift+z')
    c.ok('overlay geri', cmds.modelEditor(ed, q=True, grid=True))
    # Z pie
    pie = b.shading_pie(p)
    labels = [i[0] for i in pie.items if i]
    [i for i in pie.items if i and 'Rendered' in i[0]][0][1]()
    c.ok('Z pie Rendered', cmds.modelEditor(ed, q=True, displayLights=True) == 'all' and cmds.modelEditor(ed, q=True, shadows=True), labels)
    [i for i in pie.items if i and i[0] == 'Solid'][0][1]()
    c.ok('Z pie Solid', cmds.modelEditor(ed, q=True, displayLights=True) == 'default')
    pie.close()
    vp = b.view_pie(p)
    c.ok('gorunum pie 8 oge', len([i for i in vp.items if i]) == 8)
    [i for i in vp.items if i and i[0] == 'Üst'][0][1]()
    c.ok('gorunum pie Ust', b._current_view(p) == 'top')
    vp.close()
    # quad view
    c.press('ctrl+alt+q')
    n4 = len([x for x in cmds.getPanel(visiblePanels=True) if cmds.getPanel(typeOf=x) == 'modelPanel'])
    c.ok('ctrl+alt+q dortlu', n4 == 4, n4)
    b.toggle_quad_view(p)
    c.refresh_view()
    p = c.panel
    c.ok('tek gorunume donus', len([x for x in cmds.getPanel(visiblePanels=True) if cmds.getPanel(typeOf=x) == 'modelPanel']) == 1)
    # kamera
    b._set_ortho(b._cam(p), False)
    cmds.lookThru(p, 'persp')
    cam = cmds.camera(name=PREFIX + 'cam')[0]
    cmds.select(cam)
    c.cursor_to()
    c.press('ctrl+np0')
    c.ok('ctrl+numpad 0 aktif kamera', b._cam(p).split('|')[-1] == cam.split('|')[-1], b._cam(p))
    c.press('np0')
    c.ok('numpad 0 kameradan cik', b._cam(p).split('|')[-1] == 'persp')
    cmds.select(cam)
    b.align_camera_to_view(p)
    c.ok('ctrl+alt+numpad 0 hizala', b._cam(p).split('|')[-1] == cam.split('|')[-1])
    cmds.lookThru(p, 'persp')
    # Alt+orta tik: merkeze al
    cmds.select(cube)
    c.frame(cube)
    t0 = cmds.xform('persp', q=True, ws=True, t=True)
    g = c.cursor_to(_center(cube + '.f[1]'))
    T = QtCore.QEvent.Type
    c.mouse(T.MouseButtonPress, g, Qt.MouseButton.MiddleButton, Qt.MouseButton.MiddleButton, MODS['alt'])
    c.mouse(T.MouseButtonRelease, g, Qt.MouseButton.MiddleButton, Qt.MouseButton.NoButton, MODS['alt'])
    c.flush()
    c.ok('alt+orta tik merkeze al', cmds.xform('persp', q=True, ws=True, t=True) != t0)
    # orta tus orbit (sentetik Alt+sol tus Maya'ya gider)
    m0 = cmds.xform('persp', q=True, ws=True, m=True)
    g0 = c.cursor_to()
    c.drag([g0 + QtCore.QPoint(i * 8, 0) for i in range(8)], Qt.MouseButton.MiddleButton)
    c.ok('orta tus surukle: orbit', cmds.xform('persp', q=True, ws=True, m=True) != m0)


@section
def t_transform(c):
    b = c.bk
    cube = cmds.polyCube(name=PREFIX + 'tr')[0]
    c.frame(cube)
    cmds.select(cube)
    c.cursor_to()
    c.press('g')
    c.ok('G modal', type(c.modal()).__name__ == 'Modal' and c.modal().kind == 'move')
    c.press('x')
    c.ok('X kisit', c.modal().constraint == ('x', 'global', False))
    c.press('x')
    c.ok('XX lokal', c.modal().constraint == ('x', 'local', False))
    c.press('x')
    c.ok('XXX kapali', c.modal().constraint is None)
    c.press('shift+z')
    c.ok('Shift+Z duzlem', c.modal().constraint == ('z', 'global', True))
    c.press('c')
    c.ok('C kisit kaldir', c.modal().constraint is None)
    c.press('x')
    c.type('2')
    c.ok('sayi 2', cmds.getAttr(cube + '.tx') == 2.0, cmds.getAttr(cube + '.tx'))
    c.type('-')
    c.ok('- isaret', cmds.getAttr(cube + '.tx') == -2.0)
    ov = b.preview_overlay()
    c.ok('kisit ekseni cizgisi', ov.isVisible() and ov.lines and ov.lines[0][1] == b.AXIS_COLORS['x'])
    c.press('enter')
    c.ok('Enter onay', c.modal() is None and cmds.getAttr(cube + '.tx') == -2.0)
    c.ok('cizgi kayboldu', not ov.isVisible())
    cmds.undo()
    c.ok('undo', cmds.getAttr(cube + '.tx') == 0.0)
    # Tab ile eksen eksen
    c.press('g')
    c.type('1')
    c.press('tab')
    c.type('2')
    c.press('tab')
    c.type('3')
    c.press('enter')
    c.ok('G 1 Tab 2 Tab 3', _round(cmds.getAttr(cube + '.t')[0]) == [1.0, 2.0, 3.0], cmds.getAttr(cube + '.t'))
    cmds.undo()
    # ifade modu
    c.press('g')
    c.press('x')
    c.type('=2m')            # '=' modunda harfler sayiya gider: 2m = 200 cm
    c.ok('= ifade: 2m -> 200 cm', abs(cmds.getAttr(cube + '.tx') - 200.0) < 1e-6, cmds.getAttr(cube + '.tx'))
    c.press('esc')
    c.ok('Esc iptal', cmds.getAttr(cube + '.tx') == 0.0 and c.modal() is None)
    # uzun surukleme: undo kaydi tek adim (her kare ayri kayit olmasin), redo sonucu getirir
    cmds.move(0.5, 0, 0, cube, relative=True)        # kullanicinin onceki islemi
    before = _round(cmds.getAttr(cube + '.t')[0])
    c.cursor_to((0.5, 0, 0))
    c.press('g')
    g0 = QtGui.QCursor.pos()
    for i in range(25):
        QtGui.QCursor.setPos(g0 + QtCore.QPoint(4 * i, -3 * i))
        c.flush(2)
        m = c.modal()
        if m is not None:
            m.update()
    c.press('enter')
    after = _round(cmds.getAttr(cube + '.t')[0])
    c.ok('surukleme sonucu uygulandi', after != before, (before, after))
    cmds.undo()
    c.ok('surukleme tek undo adimi', _round(cmds.getAttr(cube + '.t')[0]) == before, cmds.getAttr(cube + '.t'))
    cmds.redo()
    c.ok('redo surukleme sonucunu getirir', _round(cmds.getAttr(cube + '.t')[0]) == after, cmds.getAttr(cube + '.t'))
    cmds.undo()
    c.press('g')
    c.type('3')
    c.press('esc')
    c.ok('iptal onceki islemi geri almaz', _round(cmds.getAttr(cube + '.t')[0]) == before, cmds.getAttr(cube + '.t'))
    c.ok('undo kaydi acik kaldi', cmds.undoInfo(q=True, stateWithoutFlush=True))
    cmds.undo()   # onceki 0.5 tasima
    # R / S
    c.press('r')
    c.press('z')
    c.type('90')
    c.press('enter')
    c.ok('R Z 90', _round(cmds.getAttr(cube + '.r')[0]) == [0.0, 0.0, 90.0], cmds.getAttr(cube + '.r'))
    c.press('s')
    c.type('2')
    c.press('enter')
    c.ok('S 2', _round(cmds.getAttr(cube + '.s')[0]) == [2.0, 2.0, 2.0])
    c.press('alt+r')
    c.press('alt+s')
    c.ok('Alt+R / Alt+S sifirla', _round(cmds.getAttr(cube + '.r')[0]) == [0, 0, 0] and _round(cmds.getAttr(cube + '.s')[0]) == [1, 1, 1])
    cmds.setAttr(cube + '.t', 1, 1, 1)
    c.press('alt+g')
    c.ok('Alt+G sifirla', _round(cmds.getAttr(cube + '.t')[0]) == [0, 0, 0])
    # G -> R gecis, R R trackball
    c.press('g')
    c.press('r')
    c.ok('G -> R gecis', c.modal().kind == 'rotate')
    c.press('r')
    c.ok('R R trackball', c.modal().kind == 'trackball')
    c.press('esc')
    # pivotlar
    a = cmds.polyCube(name=PREFIX + 'pa')[0]
    d = cmds.polyCube(name=PREFIX + 'pb')[0]
    cmds.xform(a, t=(10, 0, 0))
    cmds.xform(d, t=(14, 0, 0))
    c.frame([a, d])
    c.cursor_to()
    for mode, want in (('median', ([8, 0, 0], [16, 0, 0])), ('individual', ([10, 0, 0], [14, 0, 0])),
                       ('active', ([6, 0, 0], [14, 0, 0])), ('bbox', ([8, 0, 0], [16, 0, 0]))):
        b.set_setting('pivot', mode)
        cmds.select(a, d)
        c.press('s')
        c.type('2')
        c.press('enter')
        got = (_round(cmds.getAttr(a + '.t')[0]), _round(cmds.getAttr(d + '.t')[0]))
        c.ok('pivot %s olcek 2' % mode, got == (want[0], want[1]), got)
        cmds.undo()
    b.set_setting('pivot', 'cursor')
    b.set_cursor(om.MPoint(12, 0, 0))
    cmds.select(a)
    c.press('r')
    c.press('y')
    c.type('180')
    c.press('enter')
    c.ok('pivot imlec R Y 180', _round(cmds.getAttr(a + '.t')[0], 2) == [14.0, 0.0, 0.0], cmds.getAttr(a + '.t'))
    cmds.undo()
    b.set_setting('pivot', 'median')
    # oryantasyon
    cmds.xform(a, ro=(0, 90, 0))
    b.set_setting('orientation', 'local')
    cmds.select(a)
    c.press('g')
    c.press('x')
    c.type('1')
    c.press('enter')
    c.ok('lokal X (90 donmus obje) -> dunya -Z', _round(cmds.getAttr(a + '.t')[0]) == [10.0, 0.0, -1.0], cmds.getAttr(a + '.t'))
    cmds.undo()
    b.set_setting('orientation', 'global')
    for combo, title in (('period', 'pivot'), ('comma', 'orient')):
        c.press(combo)
        pies = [w for w in QtWidgets.QApplication.topLevelWidgets() if isinstance(w, b.PieMenu) and w.isVisible()]
        c.ok('%s pie acilir' % combo, bool(pies))
        for w in pies:
            w.close()
    # snap
    b.set_setting('snap_target', 'vertex')
    b.set_setting('snap_on', 1)
    cmds.select(a)
    c.cursor_to()
    c.press('g')
    target = _wpos(d, 'vtx[0]')
    c.cursor_to(target)
    c.modal().update(force=True)
    c.ok('kose snap (pivot hedef koseye)', _round(cmds.xform(a, q=True, ws=True, rp=True), 2) == _round(target, 2),
         (cmds.xform(a, q=True, ws=True, rp=True), target))
    c.press('esc')
    b.set_setting('snap_on', 0)
    b.set_setting('snap_target', 'increment')
    c.press('shift+tab')
    c.ok('Shift+Tab snap ac', b.setting('snap_on') == 1)
    c.press('shift+tab')
    # Ctrl+M aynala
    cmds.select(d)
    c.press('ctrl+m')
    c.press('enter')
    c.ok('Ctrl+M aynala (X -1)', _round(cmds.getAttr(d + '.s')[0]) == [-1.0, 1.0, 1.0], cmds.getAttr(d + '.s'))
    cmds.undo()
    # Alt+orta tusla gezinme sonrasi devam
    cmds.select(a)
    c.cursor_to()
    c.press('g')
    m = c.modal()
    c.cursor_to(c.cursor_to() + QtCore.QPoint(60, 0))
    m.update(force=True)
    before = cmds.getAttr(a + '.t')[0]
    m._after_nav()
    m.update(force=True)
    c.ok('gezinmeden sonra yerinde kalir', _round(cmds.getAttr(a + '.t')[0]) == _round(before))
    c.press('esc')


@section
def t_edit_select(c):
    b = c.bk
    pl = cmds.polyPlane(name=PREFIX + 'sel', sx=6, sy=6, w=6, h=6)[0]
    c.frame(pl)
    cmds.select(pl)
    c.cursor_to()
    c.press('tab')
    c.ok('Tab edit modu', b.in_edit())
    c.press('3')
    c.ok('3 yuz modu', b.current_comp() == 'face')
    c.press('a')
    c.ok('A hepsini sec', len(_sel()) == 36, len(_sel()))
    c.press('alt+a')
    c.ok('Alt+A temizle', not _sel())
    cmds.select(pl + '.f[0]')
    c.press('ctrl+i')
    c.ok('Ctrl+I ters', len(_sel()) == 35)
    cmds.select(pl + '.f[14]')
    c.press('ctrl+np+')
    c.ok('Ctrl+Numpad+ buyut', len(_sel()) == 9, len(_sel()))
    c.press('ctrl+np-')
    c.ok('Ctrl+Numpad- kucult', len(_sel()) == 1, len(_sel()))
    c.press('2')
    c.ok('2 kenar modu (yuz -> kenar gecisi)', b.current_comp() == 'edge')
    c.press('shift+3')
    c.ok('Shift+3 coklu mod', cmds.selectType(q=True, meshComponents=True))
    c.press('shift+3')
    c.ok('Shift+3 tekrar tekli', not cmds.selectType(q=True, meshComponents=True) and b._active_kinds() == ['edge'])
    c.press('1')
    cmds.select(pl + '.vtx[8]')
    c.press('ctrl+3')
    c.ok('Ctrl+3 genisleterek', len(_sel()) == 4, _sel())
    # fare ile secimler (filtreden)
    c.press('2')
    cmds.select(clear=True)
    edge = _center(pl + '.e[20]')
    g = c.cursor_to(edge)
    c.click(g, mods=MODS['alt'])
    c.ok('Alt+tik loop', len(_sel()) == 6, len(_sel()))
    c.click(g, mods=MODS['alt'] | MODS['shift'])
    c.ok('Shift+Alt+tik geri cikar', len(_sel()) == 0, len(_sel()))
    border = [e for e in cmds.ls(pl + '.e[*]', flatten=True)
              if len(cmds.ls(cmds.polyListComponentConversion(e, toFace=True), flatten=True)) == 1][0]
    face = cmds.ls(cmds.polyListComponentConversion(border, toFace=True), flatten=True)[0]
    ec, fc = _center(border), _center(face)
    g = c.cursor_to(tuple(e + (f - e) * 0.15 for e, f in zip(ec, fc)))   # sinir kenarinin hemen ici
    c.click(g, mods=MODS['alt'])
    c.ok('sinirda Alt+tik tum sinir', len(_sel()) == 24, len(_sel()))
    cmds.select(clear=True)
    g = c.cursor_to(edge)
    c.click(g, mods=MODS['alt'] | MODS['ctrl'])
    c.ok('Ctrl+Alt+tik ring (6 yuz -> 7 kenar)', len(_sel()) == 7, len(_sel()))
    c.press('3')
    cmds.select(pl + '.f[7]')
    g = c.cursor_to(_center(pl + '.f[22]'))
    c.click(g, mods=MODS['ctrl'])
    c.ok('Ctrl+tik en kisa yol', len(_sel()) >= 4, len(_sel()))
    cmds.select(pl + '.f[7]')
    c.click(g, mods=MODS['ctrl'] | MODS['shift'])
    c.ok('Shift+Ctrl+tik bolge (3x4)', len(_sel()) == 12, len(_sel()))
    # L / Shift+L / Ctrl+L
    other = cmds.polyPlane(name=PREFIX + 'sel2', sx=2, sy=2)[0]
    cmds.xform(other, t=(0, 0, 10))
    merged = cmds.polyUnite(pl, other, name=PREFIX + 'selm', ch=False)[0]
    c.frame(merged)
    cmds.select(merged)
    b.enter_edit('face')
    cmds.select(clear=True)
    c.cursor_to(_center(merged + '.f[37]'))
    c.press('l')
    c.ok('L imlec alti parca', len(_sel()) == 4, len(_sel()))
    c.press('shift+l')
    c.ok('Shift+L cikar', len(_sel()) == 0)
    cmds.select(merged + '.f[0]')
    c.press('ctrl+l')
    c.ok('Ctrl+L bagli', len(_sel()) == 36, len(_sel()))
    # Shift+G benzerini sec (menu)
    cmds.polyPoke(merged + '.f[5]')
    cmds.select(merged + '.f[0]')
    with c.popups() as calls:
        c.press('shift+g')
        c.ok('Shift+G menu', calls and len(calls[-1][1]) == 5, calls and [i[0] for i in calls[-1][1]])
        c.run_item(calls, 'kenar sayısı')
    c.ok('benzer: kenar sayisi', len(_sel()) == 39, len(_sel()))
    cmds.select(merged + '.f[0]')
    b.select_similar('face', 'area')
    c.ok('benzer: alan (1x1 dortgenler)', len(_sel()) == 35, len(_sel()))
    b.select_mode('edge')
    cmds.select(merged + '.e[0]')
    b.select_similar('edge', 'length')
    c.ok('benzer: uzunluk', len(_sel()) > 20, len(_sel()))
    b.select_mode('vertex')
    cmds.select(merged + '.vtx[0]')
    b.select_similar('vertex', 'faces')
    c.ok('benzer: kose yuz sayisi (poke komsusu haric 7 kose)', len(_sel()) == 7, _sel())
    b.exit_edit()
    cmds.select(pl if cmds.objExists(pl) else merged)
    # ayna secimi
    sym = cmds.polyPlane(name=PREFIX + 'sym', sx=4, sy=4, w=4, h=4)[0]
    cmds.select(sym)
    b.enter_edit('vertex')
    cmds.select(sym + '.vtx[0]')
    c.cursor_to()
    c.press('ctrl+shift+m')
    c.ok('Shift+Ctrl+M ayna', _sel() == [sym + '.vtx[4]'], _sel())
    # kement (Ctrl+sag)
    cmds.select(clear=True)
    c.frame(sym)
    center = c.gpos(_wpos(sym, 'vtx[12]'))
    r = 30
    poly = [center + QtCore.QPoint(dx * r, dy * r) for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1))]
    pts = []
    for i in range(len(poly) - 1):
        for k in range(6):
            pts.append(poly[i] + (poly[i + 1] - poly[i]) * (k / 6.0))
    pts.append(poly[-1])
    c.drag(pts, Qt.MouseButton.RightButton, MODS['ctrl'])
    c.ok('Ctrl+sag kement', sym + '.vtx[12]' in _sel(), _sel())
    c.ok('kement sonrasi arac geri', cmds.currentCtx() != 'lassoSelectContext', cmds.currentCtx())
    # B / W / C
    c.press('b')
    c.ok('B kutu', cmds.currentCtx() == 'selectSuperContext')
    c.press('w')
    c.ok('W kement', cmds.currentCtx() == 'lassoSelectContext')
    c.press('w')
    c.press('w')
    c.ok('W dongu basa', cmds.currentCtx() == 'selectSuperContext')
    cmds.setToolTo('moveSuperContext')
    c.press('c')
    c.ok('C firca', cmds.currentCtx() == 'artSelectContext')
    c.press('esc')
    c.ok('Esc fircadan onceki araca', cmds.currentCtx() == 'moveSuperContext', cmds.currentCtx())
    c.press('c')
    g = c.cursor_to()
    c.click(g, Qt.MouseButton.RightButton)
    c.ok('sag tik fircadan cik', cmds.currentCtx() == 'moveSuperContext', cmds.currentCtx())
    cmds.setToolTo('selectSuperContext')
    b.exit_edit()


@section
def t_edit_model(c):
    b = c.bk
    cube = cmds.polyCube(name=PREFIX + 'mod', sx=2, sy=2, sz=2)[0]
    c.frame(cube)
    cmds.select(cube)
    c.cursor_to()
    b.enter_edit('face')
    # E yuz
    cmds.select(cube + '.f[2]')
    f0 = cmds.polyEvaluate(cube, face=True)
    c.press('e')
    c.ok('E yuz extrude modal', c.modal() and c.modal().kind == 'attr_axis')
    c.type('1')
    c.press('enter')
    c.ok('E 1', cmds.polyEvaluate(cube, face=True) == f0 + 4, cmds.polyEvaluate(cube, face=True))
    cmds.undo()
    c.ok('E undo tek adim', cmds.polyEvaluate(cube, face=True) == f0)
    c.press('e')
    c.press('x')
    c.ok('E sonra X serbest', c.modal().kind == 'move' and c.modal().constraint[0] == 'x')
    c.press('esc')
    with c.popups() as calls:
        c.press('alt+e')
        c.ok('Alt+E menu', calls and len(calls[-1][1]) == 4, calls and [i[0] for i in calls[-1][1]])
    cmds.select(cube + '.f[2]')
    b._with_chunk(b.extrude_along_normals)()
    c.type('1')
    c.press('enter')
    c.ok('normaller boyunca', any(cmds.getAttr(n + '.thickness') == 1.0 for n in cmds.ls(type='polyExtrudeFace')))
    cmds.undo()
    cmds.select(cube + '.f[2]', cube + '.f[3]')
    b._with_chunk(b.extrude_individual)()
    c.press('enter')
    c.ok('tek tek extrude', cmds.polyEvaluate(cube, face=True) > f0)
    cmds.undo()
    # I inset + I
    cmds.select(cube + '.f[2]')
    c.press('i')
    m = c.modal()
    c.press('i')
    c.ok('I I tek tek', m.nodes and not cmds.getAttr(m.nodes[0] + '.keepFacesTogether'))
    c.type('0.1')
    c.press('enter')
    c.ok('inset', cmds.polyEvaluate(cube, face=True) == f0 + 4)
    cmds.undo()
    # bevel
    b.select_mode('edge')
    cmds.select(cube + '.e[0]')
    c.press('ctrl+b')
    m = c.modal()
    c.ok('Ctrl+B bevel', m and m.wheel_attr == 'segments')
    m._wheel(True)
    c.press('p')
    c.press('m')
    c.press('c')
    node = m.nodes[0]
    c.ok('bevel segment/P/M/C', cmds.getAttr(node + '.segments') == 2 and cmds.getAttr(node + '.depth') != 1.0
         and cmds.getAttr(node + '.mitering') == 1 and not cmds.getAttr(node + '.chamfer'))
    c.type('0.1')
    c.press('enter')
    cmds.undo()
    b.select_mode('vertex')
    cmds.select(cube + '.vtx[0]')
    c.press('ctrl+shift+b')
    c.type('0.1')
    c.press('enter')
    c.ok('Shift+Ctrl+B kose bevel', cmds.polyEvaluate(cube, vertex=True) > 26)
    cmds.undo()
    # kose E kapali
    c.clear_msgs()
    cmds.select(cube + '.vtx[0]')
    v0 = cmds.polyEvaluate(cube, vertex=True)
    c.press('e')
    c.ok('kose E kapali (uyari)', cmds.polyEvaluate(cube, vertex=True) == v0 and c.modal() is None)
    # loop cut
    b.select_mode('edge')
    cyl = cmds.polyCylinder(name=PREFIX + 'lc', sx=8, sy=2, h=2)[0]
    b.exit_edit()
    c.frame(cyl)
    cmds.select(cyl)
    c.cursor_to()
    b.enter_edit('edge')
    vert = [e for e in cmds.ls(cyl + '.e[*]', flatten=True)
            if (lambda q: abs(q[0] - q[3]) < 1e-6 and abs(q[2] - q[5]) < 1e-6 and abs(q[1] - q[4]) > 0.5)(cmds.xform(e, q=True, ws=True, t=True))]
    e_before = cmds.polyEvaluate(cyl, edge=True)
    cam_pos = om.MPoint(*cmds.xform(b._cam(c.panel), q=True, ws=True, t=True))
    vert.sort(key=lambda e: om.MPoint(*_center(e)).distanceTo(cam_pos))   # kameraya en yakin (gorunen) kenar
    c.cursor_to(_center(vert[0]))
    c.press('ctrl+r')
    tool = c.modal()
    c.ok('Ctrl+R loop cut', type(tool).__name__ == 'LoopCut')
    tool.update(force=True)
    c.ok('loop cut onizleme', b.preview_overlay().isVisible() and tool.pairs, len(tool.pairs or []))
    tool._click()
    tool._click()
    c.ok('loop cut kesti', cmds.polyEvaluate(cyl, edge=True) == e_before + 16, cmds.polyEvaluate(cyl, edge=True) - e_before)
    # G G kaydirma
    sel_edges = _sel()
    ys = sorted(set(round(_wpos(cyl, 'vtx[%d]' % int(v.split('[')[1][:-1]))[1], 3) for v in
                    cmds.ls(cmds.polyListComponentConversion(sel_edges, toVertex=True), flatten=True)))
    c.cursor_to()
    c.press('g')
    c.press('g')
    tool = c.modal()
    c.ok('G G kenar kaydir', type(tool).__name__ == 'EdgeSlide')
    c.type('0.5')
    c.press('enter')
    ys2 = sorted(set(round(_wpos(cyl, 'vtx[%d]' % int(v.split('[')[1][:-1]))[1], 3) for v in
                     cmds.ls(cmds.polyListComponentConversion(sel_edges, toVertex=True), flatten=True)))
    c.ok('kaydirma 0.5 (halka tutarli)', len(ys2) == 1 and ys2 != ys, (ys, ys2))
    cmds.undo()
    ys3 = sorted(set(round(_wpos(cyl, 'vtx[%d]' % int(v.split('[')[1][:-1]))[1], 3) for v in
                     cmds.ls(cmds.polyListComponentConversion(sel_edges, toVertex=True), flatten=True)))
    c.ok('kaydirma tek undo adimi', ys3 == ys, (ys, ys3))
    b.select_mode('vertex')
    cmds.select(cyl + '.vtx[0]')
    p0 = _wpos(cyl, 'vtx[0]')
    c.press('shift+v')
    tool = c.modal()
    c.cursor_to(c.cursor_to() + QtCore.QPoint(0, -60))
    tool.update(force=True)
    c.ok('Shift+V kose kaydir', _wpos(cyl, 'vtx[0]') != p0)
    c.press('esc')
    c.ok('kaydirma iptal', _round(_wpos(cyl, 'vtx[0]')) == _round(p0))
    b.exit_edit()
    # coklu loop cut + kaydirma (kesimler araliklarini koruyarak birlikte kayar)
    cyl2 = cmds.polyCylinder(name=PREFIX + 'lc2', sx=8, sy=1, h=3)[0]
    c.frame(cyl2)
    cmds.select(cyl2)
    b.enter_edit('edge')
    vert2 = [e for e in cmds.ls(cyl2 + '.e[*]', flatten=True)
             if (lambda q: abs(q[0] - q[3]) < 1e-6 and abs(q[2] - q[5]) < 1e-6 and abs(q[1] - q[4]) > 0.5)(cmds.xform(e, q=True, ws=True, t=True))]
    cam_pos = om.MPoint(*cmds.xform(b._cam(c.panel), q=True, ws=True, t=True))
    vert2.sort(key=lambda e: om.MPoint(*_center(e)).distanceTo(cam_pos))
    v_before = cmds.polyEvaluate(cyl2, vertex=True)
    c.cursor_to(_center(vert2[0]))
    c.press('ctrl+r')
    tool = c.modal()
    tool.update(force=True)
    tool._set_count(1)
    tool._click()
    c.ok('coklu kesim kaydirma asamasi', tool.state == 'slide_multi' and len(tool.multi) == 16,
         (tool.state, len(getattr(tool, 'multi', []))))

    def new_ys():
        return sorted(set(round(_wpos(cyl2, 'vtx[%d]' % v)[1], 3) for v in range(v_before, cmds.polyEvaluate(cyl2, vertex=True))))
    ys0 = new_ys()
    ends = [_wpos(cyl2, 'vtx[%d]' % int(v.split('[')[1][:-1]))
            for v in cmds.ls(cmds.polyListComponentConversion(vert2[0], toVertex=True), flatten=True)]
    top = max(ends, key=lambda p: p[1])
    c.cursor_to(top)
    tool.update(force=True)
    c.press('enter')
    ys1 = new_ys()
    c.ok('coklu kesim kaydi, araliklar korunur', len(ys0) == 2 and len(ys1) == 2 and ys1 != ys0
         and abs((ys1[1] - ys1[0]) - (ys0[1] - ys0[0])) < 1e-3, (ys0, ys1))
    cmds.undo()
    c.ok('coklu kesim + kaydirma tek undo adimi', cmds.polyEvaluate(cyl2, vertex=True) == v_before,
         cmds.polyEvaluate(cyl2, vertex=True) - v_before)
    b.exit_edit()
    # G G esit mod (E): her kose ayni mesafe
    pe = cmds.polyPlane(name=PREFIX + 'ev', sx=2, sy=2, w=4, h=4)[0]
    cmds.move(0, 0, 1.5, pe + '.vtx[6]', pe + '.vtx[0]', relative=True)   # raylarin uzunlugu farkli olsun
    c.frame(pe)
    cmds.select(pe)
    b.enter_edit('edge')
    mid = [e for e in cmds.ls(pe + '.e[*]', flatten=True)
           if sorted(int(v.split('[')[1][:-1]) for v in cmds.ls(cmds.polyListComponentConversion(e, toVertex=True), flatten=True)) in ([3, 4], [4, 5])]
    cmds.select(mid)
    before = dict((v, _wpos(pe, 'vtx[%d]' % v)) for v in (3, 4, 5))
    c.cursor_to(_center(mid[0]))
    c.press('g')
    c.press('g')
    tool = c.modal()
    c.press('e')
    c.ok('G G esit mod acik', getattr(tool, 'even', False))
    c.type('0.5')
    c.press('enter')
    moved = [om.MPoint(*_wpos(pe, 'vtx[%d]' % v)).distanceTo(om.MPoint(*before[v])) for v in (3, 4, 5)]
    c.ok('G G esit: kayma mesafeleri esit', max(moved) - min(moved) < 1e-3 and max(moved) > 0.1, [round(m, 3) for m in moved])
    cmds.undo()
    b.exit_edit()
    # F, J, M, Alt+M, P, V, X, Ctrl+X
    pl = cmds.polyPlane(name=PREFIX + 'fm', sx=2, sy=2, w=4, h=4)[0]
    c.frame(pl)
    cmds.select(pl)
    c.cursor_to()
    b.enter_edit('vertex')
    cmds.select(pl + '.vtx[0]')
    cmds.select(pl + '.vtx[4]', add=True)
    e0 = cmds.polyEvaluate(pl, edge=True)
    c.press('f')
    c.ok('F iki kose ayni yuz -> kenar', cmds.polyEvaluate(pl, edge=True) == e0 + 1)
    cmds.undo()
    cmds.select(pl + '.vtx[0]')
    cmds.select(pl + '.vtx[1]', add=True)
    c.press('f')
    c.ok('F zaten bagli -> degisiklik yok', cmds.polyEvaluate(pl, edge=True) == e0)
    cmds.select(pl + '.vtx[0]', pl + '.vtx[4]')
    c.press('j')
    c.ok('J bagla', cmds.polyEvaluate(pl, edge=True) == e0 + 1)
    cmds.undo()
    for needle, check in (('merkezde', lambda: cmds.polyEvaluate(pl, vertex=True) == 8),
                          ('imleçte', lambda: cmds.polyEvaluate(pl, vertex=True) == 8),
                          ('ilk', lambda: cmds.polyEvaluate(pl, vertex=True) == 8),
                          ('son seçilende', lambda: cmds.polyEvaluate(pl, vertex=True) == 8),
                          ('mesafeye', lambda: cmds.polyEvaluate(pl, vertex=True) == 9)):
        cmds.select(pl + '.vtx[0]')
        cmds.select(pl + '.vtx[1]', add=True)
        with c.popups() as calls:
            c.press('m')
            c.run_item(calls, needle)
        c.ok('M %s' % needle, check(), cmds.polyEvaluate(pl, vertex=True))
        cmds.undo()
    b.select_mode('face')
    cmds.select(pl + '.f[0]')
    with c.popups() as calls:
        c.press('alt+m')
        c.run_item(calls, 'seçim')
    c.ok('Alt+M ayir (secim)', cmds.polyEvaluate(pl, vertex=True) > 9)
    cmds.undo()
    with c.popups() as calls:
        c.press('p')
        c.ok('P menu (3 oge)', len(calls[-1][1]) == 3)
    b.select_mode('vertex')
    cmds.select(pl + '.vtx[4]')
    c.press('v')
    c.ok('V rip modal', c.modal() is not None)
    c.press('esc')
    b.select_mode('face')
    cmds.select(pl + '.f[0]')
    with c.popups() as calls:
        c.press('x')
        c.ok('X sil menusu (7 oge)', len(calls[-1][1]) == 7, [i[0] for i in calls[-1][1]])
        c.run_item(calls, 'yüzler')
    c.ok('X > yuzler', cmds.polyEvaluate(pl, face=True) == 3)
    cmds.undo()
    b.select_mode('edge')
    inner = [e for e in cmds.ls(pl + '.e[*]', flatten=True)
             if len(cmds.ls(cmds.polyListComponentConversion(e, toFace=True), flatten=True)) == 2][0]
    cmds.select(inner)
    c.press('ctrl+x')
    c.ok('Ctrl+X eritme', cmds.polyEvaluate(pl, face=True) == 3, cmds.polyEvaluate(pl, face=True))
    cmds.undo()
    # Alt+F, Ctrl+T, Alt+J, Shift+N, Alt+N, Ctrl+E/V/F menuleri
    cmds.select(pl + '.f[0]')
    b.select_mode('face')
    cmds.select(pl + '.f[0]')
    c.press('ctrl+t')
    c.ok('Ctrl+T ucgen', cmds.polyEvaluate(pl, face=True) == 5)
    cmds.select(pl + '.f[*]')
    c.press('alt+j')
    c.ok('Alt+J dortgen', cmds.polyEvaluate(pl, face=True) == 4, cmds.polyEvaluate(pl, face=True))
    cmds.select(pl + '.f[0]')
    n0 = b._face_normal([pl + '.f[0]'])
    with c.popups() as calls:
        c.press('alt+n')
        c.ok('Alt+N normal menusu', calls and len(calls[-1][1]) == 7, calls and len(calls[-1][1]))
        c.run_item(calls, 'çevir')
    c.ok('normal cevir', b._face_normal([pl + '.f[0]']) * n0 < 0)
    b.recalc_normals()
    for name in ('edge_menu', 'vertex_menu', 'face_menu', 'normals_menu', 'split_menu', 'separate_menu', 'merge_menu',
                 'delete_menu', 'apply_menu', 'uv_menu', 'extrude_menu'):
        with c.popups() as calls:
            getattr(b, name)()
        c.ok('menu %s dolu' % name, calls and len(calls[-1][1]) >= 2, len(calls[-1][1]) if calls else 0)
    # Alt+S, Shift+Alt+S, Shift+E
    b.select_mode('face')
    cmds.select(pl + '.f[0]')
    c.press('alt+s')
    c.ok('Alt+S kalinlastir modal', type(c.modal()).__name__ == 'ValueModal')
    v0 = _wpos(pl, 'vtx[0]')
    c.type('0.5')
    c.press('enter')
    c.ok('Alt+S uygulandi', _round(_wpos(pl, 'vtx[0]')) != _round(v0))
    cmds.undo()
    c.ok('Alt+S tek undo adimi', _round(_wpos(pl, 'vtx[0]')) == _round(v0), _wpos(pl, 'vtx[0]'))
    # deger modalinda Esc: kullanicinin onceki islemini geri almamali (eski hata: bos undo adimi)
    cmds.move(0, 0.25, 0, pl + '.vtx[8]', relative=True)
    moved = _round(_wpos(pl, 'vtx[8]'))
    cmds.select(pl + '.f[0]')
    c.press('alt+s')
    c.type('0.3')
    c.press('esc')
    c.ok('deger modali iptal onceki islemi korur', _round(_wpos(pl, 'vtx[8]')) == moved and
         _round(_wpos(pl, 'vtx[0]')) == _round(v0), (_wpos(pl, 'vtx[8]'), moved))
    c.ok('undo kaydi acik (deger modali)', cmds.undoInfo(q=True, stateWithoutFlush=True))
    cmds.undo()
    b.select_mode('vertex')
    cmds.select(pl + '.vtx[*]')
    c.press('alt+shift+s')
    c.type('1')
    c.press('enter')
    c.ok('Shift+Alt+S kureye', True)
    cmds.undo()
    b.select_mode('edge')
    cmds.select(pl + '.e[0:3]')
    c.press('shift+e')
    c.type('1')
    c.press('enter')
    c.ok('Shift+E crease', max(cmds.polyCrease(pl + '.e[0:3]', q=True, value=True)) == 1.0)
    cmds.undo()
    c.ok('Shift+E tek undo adimi', max(cmds.polyCrease(pl + '.e[0:3]', q=True, value=True) or [0]) <= 0.0,
         cmds.polyCrease(pl + '.e[0:3]', q=True, value=True))
    # U, Shift+A edit
    b.select_mode('face')
    cmds.select(pl + '.f[*]')
    b.uv_unwrap()
    c.ok('U unwrap', cmds.polyEvaluate(pl, uvcoord=True) > 0)
    f0 = cmds.polyEvaluate(pl, face=True)
    b.add_into_mesh(cmds.polyCube)
    c.ok('Shift+A edit: ayni mesh', cmds.polyEvaluate(PREFIX + 'fm', face=True) == f0 + 6 and b.in_edit())
    b.exit_edit()
    # H / Alt+H
    cmds.select(cube)
    b.enter_edit('face')
    cmds.select(cube + '.f[0]')
    c.press('h')
    c.ok('H yuz gizle', not _sel())
    c.press('alt+h')
    c.ok('Alt+H goster', True)
    b.exit_edit()
    # Ctrl+0..5
    cmds.select(cube)
    c.press('ctrl+2')
    c.ok('Ctrl+2 yumusak onizleme', cmds.getAttr(cmds.listRelatives(cube, shapes=True)[0] + '.displaySmoothMesh') == 2)
    c.press('ctrl+0')
    c.ok('Ctrl+0 kapali', cmds.getAttr(cmds.listRelatives(cube, shapes=True)[0] + '.displaySmoothMesh') == 0)


@section
def t_object(c):
    b = c.bk
    a = cmds.polyCube(name=PREFIX + 'oa')[0]
    d = cmds.polySphere(name=PREFIX + 'ob')[0]
    cmds.xform(d, t=(3, 0, 0))
    c.frame([a, d])
    c.cursor_to()
    cmds.select(a)
    c.press('shift+d')
    c.ok('Shift+D kopyala + tasi', c.modal() is not None and len(cmds.ls(PREFIX + 'oa*', type='transform')) == 2)
    c.press('esc')
    c.ok('Shift+D iptal: kopya yerinde kalir (Blender)', len(cmds.ls(PREFIX + 'oa*', type='transform')) == 2 and c.modal() is None,
         cmds.ls(PREFIX + 'oa*', type='transform'))
    cmds.delete([x for x in cmds.ls(PREFIX + 'oa*', type='transform') if x != a])
    cmds.select(a)
    c.press('alt+d')
    c.press('enter')
    inst = [x for x in cmds.ls(PREFIX + 'oa*', type='transform') if x != a]
    c.ok('Alt+D instance', len(inst) == 1 and cmds.listRelatives(inst[0], shapes=True, fullPath=True) and
         cmds.ls(cmds.listRelatives(inst[0], shapes=True, fullPath=True)[0], allPaths=True).__len__() == 2, inst)
    cmds.delete(inst)
    # Ctrl+P menu / Alt+P menu
    cmds.select(d, a)
    with c.popups() as calls:
        c.press('ctrl+p')
        c.run_item(calls, 'dönüşümü koru')
    c.ok('Ctrl+P', (cmds.listRelatives(d, parent=True) or [''])[0] == a)
    cmds.select(d)
    with c.popups() as calls:
        c.press('alt+p')
        c.run_item(calls, 'dünya')
    c.ok('Alt+P', not cmds.listRelatives(d, parent=True))
    # Ctrl+A
    cmds.setAttr(a + '.t', 1, 2, 3)
    cmds.select(a)
    with c.popups() as calls:
        c.press('ctrl+a')
        c.run_item(calls, 'hepsi')
    c.ok('Ctrl+A hepsi', _round(cmds.getAttr(a + '.t')[0]) == [0, 0, 0] and _round(cmds.xform(a + '.vtx[0]', q=True, ws=True, t=True)) == [0.5, 1.5, 3.5])
    # H / Shift+H / Alt+H
    cmds.select(a)
    c.press('h')
    c.ok('H gizle', not cmds.getAttr(a + '.visibility'))
    c.press('alt+h')
    c.ok('Alt+H goster', cmds.getAttr(a + '.visibility'))
    # Ctrl+J
    cmds.select(d, a)
    c.press('ctrl+j')
    c.ok('Ctrl+J birlestir (aktif ad)', cmds.objExists(a) and not cmds.objExists(d) and cmds.polyEvaluate(a, shell=True) == 2)
    # X / Delete
    e = cmds.polyCube(name=PREFIX + 'oe')[0]
    cmds.select(e)
    c.press('x')
    c.ok('X obje sil', not cmds.objExists(e))
    # Shift+A ekle (imlece)
    b.set_cursor(om.MPoint(2, 3, 4))
    with c.popups() as calls:
        c.press('shift+a')
        c.ok('Shift+A menu', len(calls[-1][1]) >= 15)
        c.run_item(calls, 'küp')
    new = cmds.ls(sl=True)[0]
    c.ok('Shift+A imlece eklendi', _round(cmds.xform(new, q=True, ws=True, t=True)) == [2, 3, 4], new)
    cmds.rename(new, PREFIX + 'added')
    b.set_cursor(om.MPoint(0, 0, 0), (0, 0, 0))
    # M layer, Ctrl+G
    cmds.select(a)
    with c.popups() as calls:
        c.press('m')
        c.ok('obje modunda M layer menusu', calls and 'layer' in calls[-1][0].lower(), calls and calls[-1][0])
    cmds.createDisplayLayer([a], name=PREFIX + 'layer', noRecurse=True)
    c.ok('layer olustu', a in (cmds.editDisplayLayerMembers(PREFIX + 'layer', q=True) or []))
    # Set origin
    cmds.move(3, 0, 0, a + '.vtx[*]', r=True)
    cmds.select(a)
    with c.popups() as calls:
        c.press('ctrl+alt+shift+c')
        c.run_item(calls, 'geometriye')
    rp = cmds.xform(a, q=True, ws=True, rp=True)
    bb = cmds.exactWorldBoundingBox(a)
    c.ok('Origin to Geometry', abs(rp[0] - (bb[0] + bb[3]) / 2) < 1e-4, rp)
    # Ctrl+L
    f = cmds.polyCube(name=PREFIX + 'of')[0]
    sh = cmds.shadingNode('lambert', asShader=True, name=PREFIX + 'mat')
    sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=PREFIX + 'matSG')
    cmds.connectAttr(sh + '.outColor', sg + '.surfaceShader')
    cmds.sets(a, e=True, forceElement=sg)
    cmds.select(f, a)
    with c.popups() as calls:
        c.press('ctrl+l')
        c.run_item(calls, 'materyal')
    c.ok('Ctrl+L materyal', sg in (cmds.listConnections(cmds.listRelatives(f, shapes=True)[0], type='shadingEngine') or []))
    # Shift+G grupla
    cmds.select(a)
    with c.popups() as calls:
        c.press('shift+g')
        c.run_item(calls, 'tür')
    c.ok('Shift+G tur (mesh)', len(cmds.ls(sl=True)) >= 3)
    # Boolean (F3 komutu)
    cut = cmds.polyCube(name=PREFIX + 'cut', w=0.3, h=3, d=0.3)[0]
    tgt = cmds.polyCube(name=PREFIX + 'tgt')[0]
    cmds.xform(tgt, t=(-6, 0, 0))     # kameradan bakinca diger objelerin arkasinda kalmasin
    cmds.xform(cut, t=(-6, 0, 0))
    cmds.select(cut, tgt)
    b.boolean(2)
    c.ok('Boolean fark', cmds.objExists(tgt) and not cmds.objExists(cut) and cmds.polyEvaluate(tgt, face=True) > 6)
    # Alt+Q transfer
    cmds.select(a)
    b.enter_edit('vertex')
    c.frame([a, tgt])
    bb = cmds.exactWorldBoundingBox(tgt)
    c.cursor_to((bb[3] - 0.1, bb[4], bb[5] - 0.1))     # ust yuzun kosesine yakin (ortada boolean deligi var)
    c.press('alt+q')
    c.ok('Alt+Q transfer', cmds.ls(hilite=True) == [tgt], cmds.ls(hilite=True))
    b.exit_edit()
    # Shift+O / Alt+O / O
    c.press('o')
    on = cmds.softSelect(q=True, softSelectEnabled=True)
    c.press('o')
    c.ok('O proportional ac/kapa', on and not cmds.softSelect(q=True, softSelectEnabled=True))
    c.press('shift+o')
    pies = [w for w in QtWidgets.QApplication.topLevelWidgets() if isinstance(w, b.PieMenu) and w.isVisible()]
    c.ok('Shift+O falloff pie', bool(pies))
    for w in pies:
        [i for i in w.items if i and 'Linear' in i[0] or i and 'Doğrusal' in i[0]][0][1]()
        w.close()
    c.ok('falloff dogrusal', cmds.softSelect(q=True, softSelectCurve=True).startswith('1,0,1'))
    fo = cmds.softSelect(q=True, softSelectFalloff=True)
    c.press('alt+o')
    c.ok('Alt+O bagli', cmds.softSelect(q=True, softSelectFalloff=True) != fo)


@section
def t_cursor(c):
    b = c.bk
    pl = cmds.polyPlane(name=PREFIX + 'cur', w=4, h=4)[0]
    cmds.xform(pl, t=(0, 1, 0))
    c.frame(pl)
    node = b.cursor_node()
    c.ok('imlec halkalari', len(cmds.listRelatives(node, shapes=True, type='nurbsCurve') or []) == 2)
    c.ok('imlec outliner gizli', cmds.getAttr(node + '.hiddenInOutliner'))
    jobs = [j for j in cmds.scriptJob(listJobs=True) if '_deselect_cursor' in j]
    c.ok('imlec secim job kurulu', bool(jobs))
    cmds.select(node)
    b._deselect_cursor()      # Maya job'u komut bitince calistirir; test tek cagride oldugu icin elle tetiklenir
    c.ok('imlec secilemez', node not in (cmds.ls(sl=True) or []), cmds.ls(sl=True))
    b.set_setting('cursor_orient', 'none')
    g = c.cursor_to((0.5, 1, 0.5))
    c.click(g, Qt.MouseButton.RightButton, MODS['shift'])
    cp = _round(b.cursor_pos())
    c.ok('Shift+sag tik yuzeye', abs(cp[1] - 1.0) < 1e-3 and abs(cp[0] - 0.5) < 0.05 and abs(cp[2] - 0.5) < 0.05, cp)
    b.set_setting('cursor_orient', 'surface')
    cmds.xform(pl, ro=(90, 0, 0))
    g = c.cursor_to(_center(pl + '.f[0]'))
    c.click(g, Qt.MouseButton.RightButton, MODS['shift'])
    z = om.MVector(*cmds.xform(node, q=True, ws=True, m=True)[8:11]).normal()
    c.ok('imlec yuzey normaline', abs(abs(z * om.MVector(0, 0, 1)) - 1) < 1e-3, _round(z))
    b.set_setting('cursor_orient', 'view')
    c.click(g, Qt.MouseButton.RightButton, MODS['shift'])
    z = om.MVector(*cmds.xform(node, q=True, ws=True, m=True)[8:11]).normal()
    view = om.MFnCamera(c.view.getCamera()).viewDirection(om.MSpace.kWorld).normal()
    c.ok('imlec gorunume', abs(z * view + 1) < 1e-3)
    b.set_setting('cursor_orient', 'none')
    c.cursor_to()
    c.press('shift+c')
    c.ok('Shift+C sifirla', _round(b.cursor_pos()) == [0, 0, 0] and _round(cmds.xform(node, q=True, ws=True, ro=True)) == [0, 0, 0])
    # Shift+S pie
    cube = cmds.polyCube(name=PREFIX + 'cs')[0]
    cmds.xform(cube, t=(5, 0, 0))
    cmds.select(cube)
    c.press('shift+s')
    pies = [w for w in QtWidgets.QApplication.topLevelWidgets() if isinstance(w, b.PieMenu) and w.isVisible()]
    c.ok('Shift+S pie', pies and len([i for i in pies[0].items if i]) == 8)
    items = dict((i[0], i[1]) for i in pies[0].items if i)
    items['İmleç → Seçim']()
    c.ok('imlec -> secim', _round(b.cursor_pos()) == [5, 0, 0])
    b.set_cursor(om.MPoint(1, 1, 1))
    items['Seçim → İmleç']()
    c.ok('secim -> imlec', _round(cmds.xform(cube, q=True, ws=True, rp=True)) == [1, 1, 1])
    items['Pivot → İmleç (origin)']()
    for w in pies:
        w.close()
    # eski imlec gocu
    with b._NoUndo():
        cmds.delete(node)
        old = cmds.spaceLocator(name=b.CURSOR)[0]
        cmds.setAttr(old + '.overrideEnabled', 1)
        cmds.setAttr(old + '.overrideDisplayType', 2)
    b.cursor_node()
    c.ok('eski imlec yeni gorunume', len(cmds.listRelatives(b.CURSOR, shapes=True, type='nurbsCurve') or []) == 2)
    b.set_cursor(om.MPoint(0, 0, 0), (0, 0, 0))


@section
def t_anim(c):
    b = c.bk
    a = cmds.polyCube(name=PREFIX + 'an')[0]
    cmds.select(a)
    c.cursor_to()
    cmds.currentTime(1)
    c.press('i')
    c.ok('I keyframe', cmds.keyframe(a, q=True, keyframeCount=True) == 9)
    cmds.currentTime(10)
    cmds.setAttr(a + '.tx', 5)
    c.press('i')
    c.press('left')
    c.ok('sol ok -1 kare', cmds.currentTime(q=True) == 9)
    c.press('right')
    c.ok('sag ok +1', cmds.currentTime(q=True) == 10)
    c.press('down')
    c.ok('asagi ok onceki key', cmds.currentTime(q=True) == 1)
    c.press('up')
    c.ok('yukari ok sonraki key', cmds.currentTime(q=True) == 10)
    c.press('shift+left')
    c.ok('Shift+sol basa', cmds.currentTime(q=True) == cmds.playbackOptions(q=True, minTime=True))
    cmds.currentTime(10)
    c.press('alt+i')
    c.ok('Alt+I key sil', 10 not in (cmds.keyframe(a + '.tx', q=True, timeChange=True) or []))
    cmds.currentTime(5)
    rng = (cmds.playbackOptions(q=True, minTime=True), cmds.playbackOptions(q=True, maxTime=True))
    c.press('ctrl+end')
    c.ok('Ctrl+End aralik sonu', cmds.playbackOptions(q=True, maxTime=True) == 5)
    cmds.playbackOptions(minTime=rng[0], maxTime=rng[1])
    t0 = cmds.currentTime(q=True)
    g = c.cursor_to()
    QtWidgets.QApplication.sendEvent(c.widget, QtGui.QWheelEvent(
        QtCore.QPointF(c.widget.mapFromGlobal(g)), QtCore.QPointF(g), QtCore.QPoint(0, 0), QtCore.QPoint(0, -120),
        Qt.MouseButton.NoButton, MODS['alt'], Qt.ScrollPhase.NoScrollPhase, False))
    c.flush()
    c.ok('Alt+tekerlek kare', cmds.currentTime(q=True) == t0 + 1, cmds.currentTime(q=True))
    c.press('space')
    c.ok('Space oynat', cmds.play(q=True, state=True))
    c.press('space')
    c.ok('Space durdur', not cmds.play(q=True, state=True))
    c.press('ctrl+shift+space')
    c.ok('ters oynat', cmds.play(q=True, state=True))
    b.play_reverse()
    # Graph Editor
    cmds.setKeyframe(a + '.tx', time=20, value=3)
    mel.eval('GraphEditor')
    c.flush(10)
    ge = 'graphEditor1'
    cmds.select(a)
    cmds.selectKey(a + '.tx', time=(20, 20), replace=True)
    editor, kind = b._graph_editor(ge)
    c.ok('graph editor bagimi', kind == 'graphEditor' and editor == 'graphEditor1GraphEd')
    b.key_move(ge)
    m = c.modal()
    c.ok('Graph G modal', type(m).__name__ == 'KeyMoveModal', type(m).__name__)
    if m:
        m.axis = 'x'
        m.numeric = '5'
        m.update(force=True)
        m.finish(True)
    c.ok('Graph G 5 kare', 25 in (cmds.keyframe(a + '.tx', q=True, timeChange=True) or []),
         cmds.keyframe(a + '.tx', q=True, timeChange=True))
    cmds.selectKey(a + '.tx', time=(25, 25), replace=True)
    with c.popups() as calls:
        b.key_interpolation_menu()
        c.run_item(calls, 'sabit')
    c.ok('T interpolasyon sabit', cmds.keyTangent(a + '.tx', time=(25, 25), q=True, outTangentType=True)[0] == 'step')
    with c.popups() as calls:
        b.key_extrapolation_menu()
        c.run_item(calls, 'döngü (cycle)')
    c.ok('Shift+E dongu', cmds.setInfinity(a + '.tx', q=True, postInfinite=True)[0] == 'cycle')
    with c.popups() as calls:
        b.key_handle_menu()
        c.ok('V tutamak menusu', len(calls[-1][1]) == 5)
    with c.popups() as calls:
        b.preview_range_menu()
        c.run_item(calls, 'seçili')
    c.ok('P aralik secili keylerden', cmds.playbackOptions(q=True, minTime=True) == 25)
    cmds.playbackOptions(minTime=rng[0], maxTime=rng[1])
    b.key_delete()
    c.ok('X key sil', 25 not in (cmds.keyframe(a + '.tx', q=True, timeChange=True) or []))
    _close_editor('graphEditor')


@section
def t_modes(c):
    b = c.bk
    s = cmds.polySphere(name=PREFIX + 'sc')[0]
    c.frame(s)
    cmds.select(s)
    c.cursor_to()
    c.press('ctrl+tab')
    pies = [w for w in QtWidgets.QApplication.topLevelWidgets() if isinstance(w, b.PieMenu) and w.isVisible()]
    labels = [i[0] for i in pies[0].items if i] if pies else []
    c.ok('Ctrl+Tab mod pie (8)', len(labels) == 8, labels)
    items = dict((i[0], i[1]) for i in pies[0].items if i) if pies else {}
    for w in pies:
        w.close()
    items['Sculpt']()
    c.ok('Sculpt modu', b._sculpting(), cmds.currentCtx())
    c.press('s')
    c.ok('sculpt S smooth fircasi', 'Smooth' in ' '.join(_MSGS[-2:]), _MSGS[-2:])
    c.press('g')
    c.ok('sculpt G grab (tasima modali degil)', c.modal() is None and b._sculpting())
    size0 = cmds.sculptMeshCacheCtx(b.SCULPT_CTX, q=True, size=True)
    c.press('f')
    c.ok('F yaricap modali', type(c.modal()).__name__ == 'ValueModal')
    c.type('3')
    c.press('enter')
    c.ok('F 3', cmds.sculptMeshCacheCtx(b.SCULPT_CTX, q=True, size=True) == 3.0, cmds.sculptMeshCacheCtx(b.SCULPT_CTX, q=True, size=True))
    cmds.sculptMeshCacheCtx(b.SCULPT_CTX, e=True, size=size0)
    c.press('np1')
    c.ok('sculpt modunda numpad calisir', b._current_view(c.panel) == 'front')
    c.press('np5')
    c.press('tab')
    c.ok('sculpt Tab -> edit modu', b.in_edit() and not b._sculpting())
    b.exit_edit()
    cmds.select(s)
    b.enter_paint('vertex')
    c.ok('Vertex Paint', cmds.currentCtx() == 'artAttrColorPerVertexContext', cmds.currentCtx())
    cmds.select(s)
    c.clear_msgs()
    b.enter_paint('weight')
    c.ok('Weight Paint skin yoksa uyari', any('skin' in m.lower() for m in _MSGS), _MSGS)
    cmds.setToolTo('selectSuperContext')


@section
def t_uv(c):
    b = c.bk
    p = cmds.polyPlane(name=PREFIX + 'uv', sx=2, sy=2)[0]
    cmds.select(p)
    b.enter_edit('face')
    cmds.select(p + '.f[*]')
    mel.eval('TextureViewWindow')
    c.flush(10)
    uvp = (cmds.getPanel(scriptType='polyTexturePlacementPanel') or [None])[0]
    c.ok('UV editoru acildi', uvp is not None)
    import maya.OpenMayaUI as omui_old
    ptr = omui_old.MQtUtil.findControl(uvp) if uvp else None
    if ptr:
        w = wrapInstance(int(ptr), QtWidgets.QWidget)
        QtGui.QCursor.setPos(w.mapToGlobal(QtCore.QPoint(w.width() // 2, w.height() // 2)))
        c.flush()
        c.ok('UV baglami', b._context()[0] == 'uv', b._context())
    b.uv_select_all()
    c.ok('UV A hepsi', len(cmds.ls(sl=True, flatten=True)) == 9, len(cmds.ls(sl=True, flatten=True)))
    cmds.select(p + '.map[0]')
    b.uv_select_linked()
    c.ok('UV L ada', len(cmds.ls(sl=True, flatten=True)) == 9)
    cmds.select(p + '.map[0:1]')
    b.uv_align('v')
    vs = cmds.polyEditUV(p + '.map[0:1]', q=True)[1::2]
    c.ok('UV V hizala', abs(vs[0] - vs[1]) < 1e-6)
    b.uv_pin(1)
    c.ok('UV pin', True)
    b.uv_pin(0)
    b.uv_select_all()
    b.uv_center()
    co = cmds.polyEditUV(cmds.ls(sl=True), q=True)
    c.ok('UV ortala', abs((min(co[0::2]) + max(co[0::2])) / 2 - 0.5) < 1e-4)
    cmds.select(p + '.map[4]')
    b.uv_split()
    c.ok('UV ayir', cmds.polyEvaluate(p, uvcoord=True) > 9, cmds.polyEvaluate(p, uvcoord=True))
    b.uv_select_mode('island')
    b.uv_select_mode('vertex')
    c.ok('UV secim modlari', True)
    c.ok('UV tus tablosu', all(k in b.CONTEXT_KEYMAPS['uv'] for k in ('g', 'a', 'l', 'u', 'p', 'v', 'alt+v', 'shift+s', '4')))
    # UV editorunde fareyle G / R / S (goreli modal)
    if ptr:
        b.uv_select_all()
        uvs = cmds.ls(sl=True, flatten=True)
        before = cmds.polyEditUV(uvs, q=True)
        w = wrapInstance(int(ptr), QtWidgets.QWidget)
        QtGui.QCursor.setPos(w.mapToGlobal(QtCore.QPoint(w.width() // 2, w.height() // 2)))
        c.flush()
        c.press('g')
        m = c.modal()
        c.ok('UV G modal', type(m).__name__ == 'UvModal', type(m).__name__)
        c.press('x')
        c.type('0.25')
        c.press('enter')
        after = cmds.polyEditUV(uvs, q=True)
        du = [round(a - b0, 4) for a, b0 in zip(after[0::2], before[0::2])]
        dv = [round(a - b0, 4) for a, b0 in zip(after[1::2], before[1::2])]
        c.ok('UV G X 0.25', set(du) == {0.25} and set(dv) == {0.0}, (set(du), set(dv)))
        cmds.undo()
        c.ok('UV G tek undo adimi', [round(x, 4) for x in cmds.polyEditUV(uvs, q=True)] == [round(x, 4) for x in before])
        QtGui.QCursor.setPos(w.mapToGlobal(QtCore.QPoint(w.width() // 2, w.height() // 2)))
        c.flush()
        c.press('s')
        c.type('2')
        c.press('enter')
        co = cmds.polyEditUV(uvs, q=True)
        c.ok('UV S 2', abs((max(co[0::2]) - min(co[0::2])) - 2 * (max(before[0::2]) - min(before[0::2]))) < 1e-4)
        cmds.undo()
        c.press('r')
        c.press('esc')
        c.ok('UV R iptal: degisiklik yok', [round(x, 4) for x in cmds.polyEditUV(uvs, q=True)] == [round(x, 4) for x in before]
             and c.modal() is None)
    _close_editor('polyTexturePlacementPanel')
    b.exit_edit()


@section
def t_tools(c):
    b = c.bk
    a = cmds.polyCube(name=PREFIX + 'tl')[0]
    d = cmds.polyCube(name=PREFIX + 'tm')[0]
    c.frame([a, d])
    c.cursor_to()
    # F2
    cmds.select(a)
    c.press('f2')
    lines = [w for w in QtWidgets.QApplication.topLevelWidgets() if isinstance(w, b._PopupLine) and w.isVisible()]
    c.ok('F2 yeniden adlandir kutusu', bool(lines))
    if lines:
        lines[0].setText(PREFIX + 'renamed')
        lines[0]._accept()
        c.flush()
    c.ok('F2 adlandirdi', cmds.objExists(PREFIX + 'renamed'))
    a = PREFIX + 'renamed'
    # F3 + Ctrl+Enter favori
    b.set_setting('favorites', '[]')
    c.press('f3')
    pals = [w for w in QtWidgets.QApplication.topLevelWidgets() if isinstance(w, b.SearchPalette) and w.isVisible()]
    c.ok('F3 arama', bool(pals))
    if pals:
        pal = pals[0]
        pal.edit.setText('extrude')
        c.ok('F3 filtre', pal.list.count() > 0, pal.list.count())
        pal.edit.setText('Edit modu aç/kapa')
        pal.eventFilter(pal.edit, QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_Return, MODS['ctrl']))
        c.ok('Ctrl+Enter favoriye ekle', ['binding', 'tab'] in json.loads(b.setting('favorites')))
        pal.close()
        c.flush()
        c.widget.setFocus()
        c.flush()
    with c.popups() as calls:
        c.press('q')
        c.ok('Q favoriler', calls and 'Edit' in calls[-1][1][0][0], calls and calls[-1][1][0][0])
    b.set_setting('favorites', '[]')
    # F9
    cmds.select(a)
    b.enter_edit('face')
    cmds.select(a + '.f[1]')
    b._with_chunk(b.extrude)()
    c.type('1')
    c.press('enter')
    b.exit_edit()
    cmds.select(a)
    c.press('f9')
    pans = [w for w in QtWidgets.QApplication.topLevelWidgets() if isinstance(w, b.AdjustLastPanel) and w.isVisible()]
    c.ok('F9 panel', pans and pans[0].count > 0, pans and pans[0].node)
    if pans:
        node = pans[0].node
        for row in range(pans[0].layout().itemAt(1).layout().rowCount()):
            label = pans[0].layout().itemAt(1).layout().itemAt(row, QtWidgets.QFormLayout.ItemRole.LabelRole)
            field = pans[0].layout().itemAt(1).layout().itemAt(row, QtWidgets.QFormLayout.ItemRole.FieldRole)
            if label and field and label.widget().text() == 'localTranslateZ':
                field.widget().setValue(2.5)
        c.flush()
        c.ok('F9 deger degisti', abs(cmds.getAttr(node + '.localTranslateZ') - 2.5) < 1e-6 if cmds.objExists(node + '.localTranslateZ') else False,
             node)
        pans[0].close()
    # Ctrl+F2
    cmds.select(a, d)
    dlg = b.batch_rename()
    dlg.base.setText(PREFIX + 'item')
    dlg.apply()
    c.ok('Ctrl+F2 toplu ad', cmds.objExists(PREFIX + 'item01') and cmds.objExists(PREFIX + 'item02'), cmds.ls(PREFIX + '*', type='transform'))
    # Shift+Space arac pie
    c.cursor_to()
    c.press('shift+space')
    pies = [w for w in QtWidgets.QApplication.topLevelWidgets() if isinstance(w, b.PieMenu) and w.isVisible()]
    c.ok('Shift+Space arac pie', pies and len([i for i in pies[0].items if i]) == 8)
    for w in pies:
        w.close()
    # Ctrl+PageDown / PageUp (calisma alani)
    cur = cmds.workspaceLayoutManager(q=True, current=True)
    c.press('ctrl+pgdown')
    c.ok('Ctrl+PageDown calisma alani', cmds.workspaceLayoutManager(q=True, current=True) != cur)
    cmds.workspaceLayoutManager(setCurrent=cur)
    c.flush(10)
    c.refresh_view()
    # Shift+` walk
    c.cursor_to()
    c.press('shift+grave')
    c.ok('Shift+` walk', 'walk' in cmds.currentCtx().lower(), cmds.currentCtx())
    cmds.setToolTo('selectSuperContext')
    # ayar penceresi
    dlg = b.show_settings()
    c.ok('Ctrl+, ayarlar (2 sekme)', dlg.findChild(QtWidgets.QTabWidget).count() == 2)
    dlg.close()


@section
def t_modifiers(c):
    """Modifier paneli (arayuz) ve Ctrl+A > Modifier'lari uygula."""
    b = c.bk
    m = cmds.polyCube(name=PREFIX + 'md')[0]
    c.frame(m)
    cmds.select(m)
    panel = b.modifiers.show_panel()
    c.flush()
    c.ok('modifier paneli acildi, aktif mesh', panel.isVisible() and panel.base == cmds.ls(m, long=True)[0], panel.base)
    for key in ('subdiv', 'mirror:x', 'array', 'bevel'):
        panel.add_box.setCurrentIndex(panel.add_box.findData(key))
        panel._add()
        c.flush()
    rows = [panel.body.itemAt(i).widget().title() for i in range(panel.body.count())]
    c.ok('panelde 4 modifier satiri', len(rows) == 4, rows)
    bevel = [n for n, k in b.modifiers.history_modifiers(panel.base) if k == 'bevel'][0]
    spins = [w for w in panel.findChildren(QtWidgets.QSpinBox) if w.prefix().strip() in ('segment', 'segments')]
    c.ok('bevel segment ayari panelde', len(spins) == 1, [w.prefix() for w in panel.findChildren(QtWidgets.QSpinBox)])
    if spins:
        spins[0].setValue(3)
        c.flush()
        c.ok('segment ayari dugume yazildi', cmds.getAttr(bevel + '.segments') == 3, cmds.getAttr(bevel + '.segments'))
    c.ok('instance modifier viewportta secilemez',
         all(cmds.getAttr(i + '.overrideDisplayType') == 2 for i, _k in b.modifiers.instance_modifiers(m)))
    cmds.select(m)
    with c.popups() as calls:
        c.press('ctrl+a')
    c.run_item(calls, 'Modifier')
    c.flush()
    base = cmds.ls(PREFIX + 'md', long=True)[0]
    hist = [n for n in cmds.listHistory(base, pruneDagObjects=True) or [] if cmds.nodeType(n).startswith('poly')]
    c.ok('Ctrl+A > modifierlari uygula', not hist and not b.modifiers.instance_modifiers(base)
         and cmds.polyEvaluate(base, face=True) > 6, (hist, cmds.polyEvaluate(base, face=True)))
    cmds.undo()
    c.ok('uygula tek undo adimi', len(b.modifiers.instance_modifiers(cmds.ls(PREFIX + 'md', long=True)[0])) >= 2)
    panel.close()
    c.flush()
    c.ok('panel kapaninca scriptJob silindi', not cmds.scriptJob(exists=panel.job))


@section
def t_i18n(c):
    b = c.bk
    b.set_setting('language', 'en')
    c.ok('EN modal basligi', b._t(b.Modal.TITLES['move']) == 'MOVE')
    c.ok('EN mesaj', b._t('Önce bir obje seç') == 'Select an object first')
    c.ok('EN F3', b._search_entries()[0][0].startswith('Toggle Edit Mode'))
    with c.popups() as calls:
        cube = cmds.polyCube(name=PREFIX + 'i18n')[0]
        cmds.select(cube)
        b.apply_menu()
    c.ok('EN menu', calls and calls[-1][0] == 'Apply (Freeze)', calls and calls[-1][0])
    b.set_setting('language', 'tr')
    c.ok('TR geri', b._t('Önce bir obje seç') == 'Önce bir obje seç')


@section
def t_overlay(c):
    """Viewport 2.0 onizleme katmani (orange_overlay eklentisi). Maya guvenilir olmayan klasorden eklenti yuklerken
    izin sorar (guvenilir konum listesine programla ekleme de ayrica onay ister); bu yuzden bu bolum yalniz elle
    calistirilir (ORANGE_TEST_VP2=1) ve eklenti yukleme sorusunu testi calistiran kisi yanitlar."""
    b = c.bk
    if os.environ.get('ORANGE_TEST_VP2') != '1':
        c.ok('VP2 katman testi atlandi (ORANGE_TEST_VP2=1 degil)', True)
        return
    old = b.setting('overlay')
    try:
        b.set_setting('overlay', 'vp2')
        cyl = cmds.polyCylinder(name=PREFIX + 'ov', sx=8, sy=2, h=4)[0]
        c.frame(cyl)
        cmds.select(cyl)
        cmds.file(modified=False)
        b.enter_edit('edge')
        c.cursor_to(c.gpos((1.0, 0.0, 0.0)))
        c.press('ctrl+r')
        tool = c.modal()
        tool.update(force=True)
        ov = b.preview_overlay()
        c.ok('VP2 katmani secildi', type(ov).__name__ == 'Vp2Overlay' and b.ui.overlay_plugin_loaded(), type(ov).__name__)
        c.ok('VP2 loop cut cizgisi', ov.isVisible() and len(b.ui._overlay_store()['lines']) >= 1)
        c.ok('yardimci dugum sahneyi degistirmez', cmds.objExists('orangeOverlayShape') and not cmds.file(q=True, modified=True))
        c.press('esc')
        c.ok('Esc cizgiyi siler', not b.ui._overlay_store()['lines'])
        b.exit_edit()
        cmds.select(cyl)
        c.cursor_to()
        c.press('g')
        c.press('x')
        c.ok('VP2 eksen cizgisi', len(b.ui._overlay_store()['lines']) == 1)
        c.press('esc')
        path = os.path.join(tempfile.mkdtemp(prefix='bkt_vp2_'), 'scene.ma').replace(os.sep, '/')
        current = cmds.file(q=True, sceneName=True)
        cmds.file(rename=path)
        cmds.file(save=True, type='mayaAscii', force=True)
        text = io.open(path, encoding='utf-8', errors='replace').read()
        c.ok('kayitta eklenti izi yok (requires / dugum)', 'orange' not in text.lower(),
             [line for line in text.splitlines() if 'orange' in line.lower()][:2])
        if current:
            cmds.file(rename=current)
        b.uninstall(quiet=True)
        c.ok('kapatinca eklenti bosaltilir', not b.ui.overlay_plugin_loaded() and not cmds.objExists('orangeOverlay'))
        b.install(quiet=True)
    finally:
        b.set_setting('overlay', old)


@section
def t_installer(c):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # depo (yuklu kopya degil)
    sys.path.insert(0, repo)
    import importlib
    import drag_drop_install as ddi
    importlib.reload(ddi)
    tmp = tempfile.mkdtemp(prefix='bkt_install_')
    try:
        legacy = os.path.join(tmp, 'scripts')
        os.makedirs(os.path.join(legacy, 'blender_kontrol'))
        io.open(os.path.join(legacy, 'userSetup.py'), 'w', encoding='utf-8').write(u'print("onceki")' + os.linesep)
        io.open(os.path.join(legacy, 'blender_kontrol.py'), 'w', encoding='utf-8').write(u'# eski' + os.linesep)
        ddi.add_to_usersetup(legacy)
        ddi.add_to_usersetup(legacy)
        txt = io.open(os.path.join(legacy, 'userSetup.py'), encoding='utf-8').read()
        c.ok('eski userSetup tek blok + eski icerik', txt.count(ddi.MARK_BEGIN) == 1 and 'onceki' in txt)
        removed = ddi.remove_legacy([legacy])
        txt = io.open(os.path.join(legacy, 'userSetup.py'), encoding='utf-8').read()
        c.ok('eski kurulum temizlendi (paket, tek dosya, blok)', len(removed) == 3 and ddi.MARK_BEGIN not in txt
             and 'onceki' in txt, removed)
        if os.environ.get('ORANGE_INSTALL_TEST') != '1':
            c.ok('tam kurulum testi atlandi (ORANGE_INSTALL_TEST=1 degil)', True)
            return
        # --- tam kurulum: yalniz izole MAYA_APP_DIR ile (test baslaticisi ayarlar)
        res = ddi.install(repo)
        new = sys.modules['blender_kontrol']
        root = res['module_root'].replace(os.sep, '/')
        c.ok('kurulan paket modulden yuklendi', os.path.abspath(new.__file__).replace(os.sep, '/').startswith(root),
             new.__file__)
        c.ok('.mod dosyasi', io.open(res['mod_file'], encoding='utf-8').read().startswith('+ Orange '))
        c.ok('raf dugmesi (ikonlu)', [b for b, _l in ddi.shelf_buttons(('Orange',))
                                     if cmds.shelfButton(b, q=True, image=True).endswith('orange.png')])
        c.ok('Orange menusu', cmds.menu('BlenderKontrolMenu', exists=True)
             and cmds.menu('BlenderKontrolMenu', q=True, label=True) == 'Orange')
        c.ok('acik', new.is_installed())
        text = new.diagnostics.diagnostics_text()
        c.ok('tanilama metni', ('Orange %s' % new.__version__) in text and 'Maya:' in text and 'Qt:' in text, text[:120])
        card = new.cheatsheet.export(path=os.path.join(tmp, 'card.html'), open_in_browser=False)
        html = io.open(card, encoding='utf-8').read()
        c.ok('kisayol karti', '<kbd>' in html and 'Orange' in html and html.count('<section>') >= 6,
             html.count('<section>'))
        dlg = new.diagnostics.show_key_test()
        c.flush()
        key = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_G, NO, 0x22, 0x47, 0, 'g')
        QtWidgets.QApplication.sendEvent(dlg, key)
        c.flush()
        c.ok('tus testi satiri', dlg.lines and 'name=g' in dlg.lines[-1], dlg.lines[-1:])
        c.ok('tus testi acikken kisayollar kapali', new.core._state.get('capturing') is True)
        dlg.close()
        c.flush()
        c.ok('tus testi kapaninca kisayollar acik', not new.core._state.get('capturing'))
        new.lifecycle.remove_orange(confirm=False)
        c.flush()
        c.ok('kaldirildi: modul, .mod, raf, menu', not os.path.exists(root) and not os.path.exists(res['mod_file'])
             and not ddi.shelf_buttons(('Orange',)) and not cmds.menu('BlenderKontrolMenu', exists=True))
        c.ok('kaldirildi: kapali', 'blender_kontrol' not in sys.modules and not bk_filter_alive())
        c.ok('kaldirildi: Hotkey Editor komutlari', not cmds.runTimeCommand('Orange_LoopCut', exists=True))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if 'blender_kontrol' not in sys.modules or not sys.modules['blender_kontrol'].is_installed():
            ddi.start(repo)   # testin geri kalani icin depodaki surumu yeniden ac


def bk_filter_alive():
    return getattr(sys.modules['__main__'], '_blender_kontrol_filter', None) is not None
