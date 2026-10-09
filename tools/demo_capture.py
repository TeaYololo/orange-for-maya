# -*- coding: utf-8 -*-
"""Tanitim videosu / README GIF'i icin kare yakalama (Maya GUI icinde calisir).

Gercek tus ve fare olaylariyla kisa bir senaryo oynatir (tests/maya_live_tests.py yardimcilari) ve her karede
TUM Maya penceresini (baslik cubugu ve menuler dahil: Maya oldugu belli olsun) PNG olarak kaydeder. Basilan tuslar
ekranda bir tus gostergesinde (KeyCast), adimlar kisa bir altyazida gorunur; fare imlecinin yeri cursor.json'a yazilir
ve sonradan karelere cizilir. Sonra:
    python tools/make_video.py <kare_klasoru> docs/media/demo.gif docs/media/demo.mp4

Maya Script Editor (Python):
    import sys; sys.path.insert(0, r'<depo>/tools'); sys.path.insert(0, r'<depo>/tests'); sys.path.insert(0, r'<depo>')
    import demo_capture; demo_capture.run(r'C:/tmp/frames')
Fare imleci senaryo boyunca hareket eder; kullanicinin sahnesine dokunmaz (yeni sahne acar, sorar).
"""
from __future__ import print_function

import io
import json
import os
import time

import maya.cmds as cmds

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

import maya_live_tests as T

Qt = QtCore.Qt
FPS = 15
ORANGE = '#e8a33d'


def _overlay_label(point_size, style):
    label = QtWidgets.QLabel()
    label.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowTransparentForInput | Qt.WindowType.NoDropShadowWindowHint)
    label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    label.setTextFormat(Qt.TextFormat.RichText)
    font = QtGui.QFont('Segoe UI', point_size)
    font.setBold(True)
    label.setFont(font)
    label.setStyleSheet(style)
    return label


class KeyCast(object):
    """Ekranda basilan tuslar (screenkey gibi): son birkac tus, kisa sure sonra kaybolur."""

    def __init__(self, viewport, ttl_frames):
        self.viewport = viewport
        self.ttl_frames = ttl_frames
        self.ttl = 0
        self.keys = []
        self.label = _overlay_label(26, 'QLabel { background: rgba(20, 20, 20, 225); color: #ffffff; padding: 12px 26px;'
                                        ' border: 2px solid %s; border-radius: 12px; }' % ORANGE)

    def push(self, text):
        self.keys = (self.keys + [text])[-5:]
        self.ttl = self.ttl_frames
        self.label.setText('&nbsp;&nbsp;'.join('<span style="color:%s">%s</span>' % (ORANGE, k) if i == len(self.keys) - 1
                                                else k for i, k in enumerate(self.keys)))
        self.label.adjustSize()
        w = self.viewport
        pos = w.mapToGlobal(QtCore.QPoint((w.width() - self.label.width()) // 2, w.height() - self.label.height() - 96))
        self.label.move(pos)
        self.label.show()
        self.label.raise_()

    def tick(self):
        if self.ttl > 0:
            self.ttl -= 1
            if self.ttl == 0:
                self.keys = []
                self.label.hide()


class Caption(object):
    """Adim altyazisi: viewport'un ust ortasinda."""

    def __init__(self, viewport):
        self.viewport = viewport
        self.label = _overlay_label(21, 'QLabel { background: rgba(20, 20, 20, 215); color: #f2f2f2; padding: 10px 22px;'
                                        ' border-left: 5px solid %s; border-radius: 6px; }' % ORANGE)

    def set(self, html):
        if not html:
            self.label.hide()
            return
        self.label.setText(html)
        self.label.adjustSize()
        w = self.viewport
        self.label.move(w.mapToGlobal(QtCore.QPoint((w.width() - self.label.width()) // 2, 54)))
        self.label.show()
        self.label.raise_()


class Recorder(object):
    def __init__(self, ctx, out_dir, fps=FPS):
        self.c = ctx
        self.out = out_dir
        self.n = 0
        self.fps = fps
        self.dt = 1.0 / fps
        self.cursor = []           # kare -> (x, y, durum) yakalama dikdortgenine gore
        self.state = ''            # '' | 'lmb' | 'rmb'
        self.keycast = KeyCast(ctx.widget, int(fps * 1.3))
        self.caption = Caption(ctx.widget)
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        for f in os.listdir(out_dir):
            if f.endswith('.png') or f.endswith('.json'):
                os.remove(os.path.join(out_dir, f))
        mw = [w for w in QtWidgets.QApplication.topLevelWidgets() if w.objectName() == 'MayaWindow'][0]
        screen = QtGui.QGuiApplication.screenAt(mw.geometry().center()) or QtGui.QGuiApplication.primaryScreen()
        self.screen = screen
        self.rect = mw.frameGeometry().intersected(screen.geometry())      # tum Maya penceresi
        self.rect.setLeft(self.rect.left() + 1)                            # cerceve kalintisi
        self.rect.setRight(self.rect.right() - 1)

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            QtWidgets.QApplication.processEvents()
            time.sleep(0.005)

    def shot(self, hold=1):
        """Bir kare (hold: ayni kareyi kac kez yaz = bekleme)."""
        self.pump(self.dt)
        cmds.refresh(force=True)
        QtWidgets.QApplication.processEvents()
        r, geo = self.rect, self.screen.geometry()
        full = self.screen.grabWindow(0)
        dpr = full.devicePixelRatio() or 1.0
        pix = full.copy(QtCore.QRect(int((r.x() - geo.x()) * dpr), int((r.y() - geo.y()) * dpr),
                                     int(r.width() * dpr), int(r.height() * dpr)))
        cp = QtGui.QCursor.pos()
        entry = [int((cp.x() - r.x()) * dpr), int((cp.y() - r.y()) * dpr), self.state]
        for _ in range(hold):
            pix.save(os.path.join(self.out, 'f%04d.png' % self.n))
            self.cursor.append(entry)
            self.n += 1
            self.keycast.tick()

    def hold(self, seconds):
        self.shot(hold=max(1, int(round(seconds * self.fps))))

    def finish(self):
        with open(os.path.join(self.out, 'cursor.json'), 'w') as fh:
            json.dump({'fps': self.fps, 'frames': self.cursor, 'missed': self.MISSED}, fh)
        self.keycast.label.hide()
        self.caption.set('')

    # -- giris: her tus / tik gostergeye yazilir
    KEY_LABELS = {'tab': 'Tab', 'enter': '⏎ Enter', 'ctrl': 'Ctrl', 'shift': 'Shift', 'alt': 'Alt', 'f3': 'F3',
                  'period': '.', 'comma': ',', 'grave': '`', 'space': 'Space', 'escape': 'Esc'}

    def label_for(self, combo):
        return ' + '.join(self.KEY_LABELS.get(p, p.upper()) for p in combo.split('+'))

    MISSED = []

    def key(self, combo, hold=2, expect=None):
        """Tusu gonder; expect verilirse (callable) sonucu bekle, olmadiysa bir kez daha gonder (kayda gecmez)."""
        self.keycast.push(self.label_for(combo))
        self._send(combo)
        if expect is not None:
            for _ in range(3):
                self.c.flush()
                if expect():
                    break
                self.pump(0.3)
                if expect():
                    break
                self.MISSED.append(combo)
                self._send(combo)
        self.shot(hold)

    def _send(self, combo):
        try:                                   # Maya kendi filtresini sonradan kurmus olabilir (Ctrl+R = Create Reference)
            self.c.bk.lifecycle._raise_filter(self.c.bk._filter())
        except Exception:
            pass
        under = cmds.getPanel(underPointer=True) or ''
        if '+' in combo and (not under or cmds.getPanel(typeOf=under) != 'modelPanel'):
            pos = QtGui.QCursor.pos()
            _front(self.c.widget)
            QtGui.QCursor.setPos(pos)
            self.c.flush()
        self.c.press(combo)

    def type(self, text, hold=2):
        for ch in text:
            self.keycast.push(ch)
            self.c.type(ch)
            self.shot(hold)

    def click(self, pos, button=Qt.MouseButton.LeftButton, mods=T.NO, hold=2):
        name = 'LMB' if button == Qt.MouseButton.LeftButton else 'RMB' if button == Qt.MouseButton.RightButton else 'MMB'
        prefix = ''.join(self.KEY_LABELS[m] + ' + ' for m in ('ctrl', 'shift', 'alt') if mods & T.MODS[m])
        self.keycast.push(prefix + name)
        self.state = name.lower()
        QtGui.QCursor.setPos(pos)
        self.c.click(pos, button, mods)
        self.shot(1)
        self.state = ''
        self.shot(hold - 1 if hold > 1 else 1)

    def click_widget(self, widget, pos, hold=2):
        """Ayri bir pencereye (pie menu) sol tik: olaylar viewport'a degil o pencereye gonderilir."""
        self.keycast.push('LMB')
        QtGui.QCursor.setPos(pos)
        local = QtCore.QPointF(widget.mapFromGlobal(pos))
        T_ = QtCore.QEvent.Type
        L = Qt.MouseButton.LeftButton
        NoB = Qt.MouseButton.NoButton
        NoM = Qt.KeyboardModifier.NoModifier
        QtWidgets.QApplication.sendEvent(widget, QtGui.QMouseEvent(T_.MouseMove, local, QtCore.QPointF(pos), NoB, NoB, NoM))
        self.state = 'lmb'
        QtWidgets.QApplication.sendEvent(widget, QtGui.QMouseEvent(T_.MouseButtonPress, local, QtCore.QPointF(pos), L, L, NoM))
        self.shot(1)
        self.state = ''
        try:
            QtWidgets.QApplication.sendEvent(widget, QtGui.QMouseEvent(T_.MouseButtonRelease, local, QtCore.QPointF(pos),
                                                                       L, NoB, NoM))
        except RuntimeError:
            pass                                    # pencere tikla kapanip silinmis olabilir
        self.c.flush()
        self.shot(max(1, hold - 1))

    def wheel(self, pos, up=True, hold=3):
        self.keycast.push('Wheel ' + ('▲' if up else '▼'))
        ev = QtGui.QWheelEvent(QtCore.QPointF(self.c.widget.mapFromGlobal(pos)), QtCore.QPointF(pos), QtCore.QPoint(0, 0),
                               QtCore.QPoint(0, 120 if up else -120), Qt.MouseButton.NoButton,
                               Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QtWidgets.QApplication.sendEvent(self.c.widget, ev)
        self.shot(hold)

    def glide(self, a, b, steps=10, hold_end=1):
        """Imleci a'dan b'ye kayarak tasi, her adimda kare al."""
        for i in range(1, steps + 1):
            t = i / float(steps)
            t = t * t * (3 - 2 * t)          # yumusak hizlanma
            p = QtCore.QPoint(int(a.x() + (b.x() - a.x()) * t), int(a.y() + (b.y() - a.y()) * t))
            QtGui.QCursor.setPos(p)
            self.c.mouse(QtCore.QEvent.Type.MouseMove, p, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton)
            self.shot(hold_end if i == steps else 1)
        return b


def _settle(seconds):
    """Maya'nin ertelenmis / bosta islerini de calistirarak bekle (yeni sahneden sonra secim modunu sifirliyor)."""
    import maya.utils
    end = time.time() + seconds
    while time.time() < end:
        QtWidgets.QApplication.processEvents()
        try:
            maya.utils.processIdleEvents()
        except Exception:
            pass
        time.sleep(0.02)


def _front(viewport, timeout=15.0):
    """Maya penceresini one al ve imlec altindaki panelin modelPanel oldugunu bekle: aksi halde Orange baglam
    bulamaz, tuslar Maya'ya kalir (Ctrl+R = Create Reference penceresi senaryoyu kilitler)."""
    app = QtWidgets.QApplication.instance()
    mw = [w for w in app.topLevelWidgets() if w.objectName() == 'MayaWindow'][0]
    mw.showMaximized()
    mw.raise_()
    mw.activateWindow()
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.keybd_event(0x12, 0, 0, 0)          # Alt: Windows on plan kilidini acar
        user32.SetForegroundWindow(int(mw.winId()))
        user32.keybd_event(0x12, 0, 2, 0)
    except Exception:
        pass
    end = time.time() + timeout
    while time.time() < end:
        QtGui.QCursor.setPos(viewport.mapToGlobal(QtCore.QPoint(viewport.width() // 2, viewport.height() // 2)))
        for _ in range(5):
            app.processEvents()
        under = cmds.getPanel(underPointer=True) or ''
        if under and cmds.getPanel(typeOf=under) == 'modelPanel':
            return True
        time.sleep(0.3)
    return False


def _close_floating():
    """Gorunumun ustunde yuzen paneller (UV Toolkit vb.) kareye girmesin."""
    for w in cmds.lsUI(type='workspaceControl') or []:
        try:
            if cmds.workspaceControl(w, q=True, floating=True) and cmds.workspaceControl(w, q=True, visible=True):
                cmds.workspaceControl(w, e=True, close=True)
        except Exception:
            pass


def _pie():
    from blender_kontrol import PieMenu
    for w in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(w, PieMenu) and w.isVisible():
            return w


def _pie_item_pos(pie, label):
    for i, it in enumerate(pie.items):
        if it and it[0] == label:
            r = pie._rect(i)
            return pie.mapToGlobal(QtCore.QPoint(int(r.center().x()), int(r.center().y())))
    raise RuntimeError('pie item yok: %s' % label)


def run(out_dir, fps=FPS):
    lock = os.path.join(out_dir, '.running')
    if os.path.exists(lock) and time.time() - os.path.getmtime(lock) < 900:
        print('kayit zaten suruyor, atlandi: %s' % lock)
        return 0
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    io.open(lock, 'w').write(u'%s' % time.time())
    try:
        return _run(out_dir, fps)
    finally:
        pie = _pie()
        if pie is not None:
            pie.close()
        if os.path.exists(lock):
            os.remove(lock)


def _run(out_dir, fps):
    b = T.bk()
    if not b.is_installed():
        b.install(quiet=True)
    cmds.file(new=True, force=True)
    _settle(5.0)     # Maya yeni sahneden sonra ertelenmis islerinde secim modunu sifirliyor
    _close_floating()
    b.set_setting('language', 'en')
    T._standard_camera(b)
    c = T.Ctx('demo')
    if not _front(c.widget):
        raise RuntimeError('Maya penceresi one alinamadi; imlec altinda modelPanel yok')
    _settle(3.0)
    cube = cmds.polyCube(name='Cube', w=4, h=4, d=4, sx=1, sy=1, sz=1)[0]
    cmds.xform('persp', worldSpace=True, translation=(13, 9.5, 13), rotation=(-27, 45, 0))
    cmds.setAttr('perspShape.centerOfInterest', 19.0)
    cmds.select(cube)
    cmds.refresh(force=True)
    rec = Recorder(c, out_dir, fps)
    center = c.gpos((0, 0, 0))
    QtGui.QCursor.setPos(center)
    _settle(1.0)

    def modal():
        return c.modal() is not None

    def no_modal():
        return c.modal() is None

    rec.caption.set('<b>Orange</b> &nbsp;·&nbsp; Maya, the Blender way &nbsp;·&nbsp; Blender keys and modal tools inside Maya')
    rec.hold(2.2)

    # 1. Tab edit modu, 3 yuz, E extrude + yazilan deger
    rec.caption.set('<b>Tab</b> edit mode &nbsp;·&nbsp; <b>3</b> face select')
    rec.key('tab', hold=10, expect=b.in_edit)
    rec.key('3', hold=6)
    top = c.gpos((0, 2, 0))
    rec.glide(center, top, steps=10)
    cmds.select(cube + '.f[1]')            # ust yuz (sentetik tik Maya secimine gitmiyor)
    rec.click(top, hold=6)
    rec.caption.set('<b>E</b> extrude &nbsp;·&nbsp; drag, then type <b>1.5</b> and press <b>Enter</b>')
    rec.key('e', hold=4, expect=modal)
    up = QtCore.QPoint(top.x(), top.y() - 110)
    rec.glide(top, up, steps=14, hold_end=4)
    rec.type('1.5', hold=4)
    rec.key('enter', hold=12, expect=no_modal)

    # 2. Ctrl+R loop cut: onizleme, tekerlek kesim sayisi, tik
    rec.caption.set('<b>Ctrl+R</b> loop cut with live preview &nbsp;·&nbsp; mouse wheel = number of cuts')
    side = c.gpos((2, 0.5, 0))
    rec.glide(up, side, steps=10)
    rec.key('ctrl+r', hold=5, expect=modal)
    near = c.gpos((2, 0.6, 1.0))
    rec.glide(side, near, steps=10, hold_end=5)
    for _ in range(2):
        rec.wheel(near, up=True, hold=6)
    rec.click(near, hold=12)

    # 3. Ctrl+B bevel: yeni kenarlar secili, tekerlek segment
    rec.caption.set('<b>Ctrl+B</b> bevel the new edges &nbsp;·&nbsp; wheel = segments')
    rec.key('ctrl+b', hold=4, expect=modal)
    off = QtCore.QPoint(near.x() + 50, near.y() + 20)
    rec.glide(near, off, steps=12, hold_end=4)
    for _ in range(2):
        rec.wheel(off, up=True, hold=6)
    rec.key('enter', hold=12, expect=no_modal)

    # 4. Tab obje modu, G X 2, R Z 45
    rec.caption.set('<b>Tab</b> back to object mode &nbsp;·&nbsp; <b>G X 2 Enter</b> moves 2 units on X')
    rec.key('tab', hold=8, expect=lambda: not b.in_edit())
    rec.key('g', hold=4, expect=modal)
    rec.key('x', hold=5)
    right = QtCore.QPoint(off.x() + 150, off.y() + 40)
    rec.glide(off, right, steps=12, hold_end=3)
    rec.type('2', hold=5)
    rec.key('enter', hold=10, expect=no_modal)
    rec.caption.set('<b>R Z 45 Enter</b> rotates 45° around Z &nbsp;·&nbsp; every modal tool takes typed values')
    rec.key('r', hold=4, expect=modal)
    rec.key('z', hold=5)
    rec.type('45', hold=4)
    rec.key('enter', hold=12, expect=no_modal)

    # 5. Z shading pie
    rec.caption.set('<b>Z</b> shading pie menu &nbsp;·&nbsp; pies for view, pivot, orientation, snapping, tools')
    mid = c.gpos((2, 2, 0))
    rec.glide(right, mid, steps=8)
    rec.key('z', hold=10, expect=lambda: _pie() is not None)
    pie = _pie()
    if pie:
        wire = _pie_item_pos(pie, 'Wireframe')
        rec.glide(mid, wire, steps=10, hold_end=3)
        rec.click_widget(pie, wire, hold=14)
        if _pie() is not None:
            rec.MISSED.append('pie click')
            _pie().close()
        QtGui.QCursor.setPos(mid)
        rec.key('z', hold=8, expect=lambda: _pie() is not None)
        pie = _pie()
        if pie:
            solid = _pie_item_pos(pie, 'Solid')
            rec.glide(mid, solid, steps=8, hold_end=2)
            rec.click_widget(pie, solid, hold=8)
            if _pie() is not None:
                rec.MISSED.append('pie click 2')
                _pie().close()

    # 6. F3 arama -> modifier paneli -> Subdivision + Array
    rec.caption.set('<b>F3</b> search any command')
    from blender_kontrol.search import SearchPalette

    def palette():
        for w in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(w, SearchPalette) and w.isVisible():
                return w

    def panel_widget():
        for w in QtWidgets.QApplication.topLevelWidgets():
            if w.objectName() == 'BlenderKontrolModifiers' and w.isVisible():
                return w

    rec.key('f3', hold=6, expect=lambda: palette() is not None)
    dlg = palette()
    if dlg:
        for ch in 'modifier panel':
            rec.keycast.push(ch if ch != ' ' else 'Space')
            QtWidgets.QApplication.sendEvent(dlg.edit, QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_unknown,
                                                                       Qt.KeyboardModifier.NoModifier, ch))
            rec.shot(2)
        rec.hold(0.6)
        rec.keycast.push('⏎ Enter')
        QtWidgets.QApplication.sendEvent(dlg.edit, QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                                                   Qt.KeyboardModifier.NoModifier, '\r'))
        end = time.time() + 2.0
        while time.time() < end and panel_widget() is None:
            rec.pump(0.1)
        rec.hold(0.8)
    panel = panel_widget()
    if panel is None:
        rec.MISSED.append('f3 -> modifier panel')
        panel = b.modifiers.show_panel()
    vp = c.widget
    panel.move(vp.mapToGlobal(QtCore.QPoint(24, 110)))
    cmds.viewFit('persp', cube, animate=False, fitFactor=0.35)
    rec.hold(0.8)
    rec.caption.set('Modifiers, the Blender way &nbsp;·&nbsp; <b>Subdivision Surface</b> (smooth preview) '
                    '+ <b>Array</b> (live instances)')
    panel.add_box.setCurrentIndex(panel.add_box.findData('subdiv'))
    rec.hold(0.7)
    panel._add()
    rec.hold(1.3)
    panel.add_box.setCurrentIndex(panel.add_box.findData('array'))
    rec.hold(0.7)
    panel._add()
    cmds.select(cube)
    cmds.viewFit('persp', animate=False, fitFactor=0.42)
    cmds.select(cube)
    rec.hold(1.5)
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.objectName() == 'MayaWindow':
            w.activateWindow()
    c.widget.setFocus(Qt.FocusReason.OtherFocusReason)
    _front(c.widget)
    QtGui.QCursor.setPos(mid)
    c.flush()

    # 7. Edit modunda kose tasima: instance'lar canli
    rec.caption.set('Edit the base mesh &nbsp;·&nbsp; <b>Tab</b>, <b>1</b> vertex, <b>G</b> &nbsp;·&nbsp; modifiers update live')
    rec.key('tab', hold=6, expect=b.in_edit)
    rec.key('1', hold=4)
    base = cmds.ls(cube, long=True)[0]
    verts = cmds.ls(base + '.vtx[*]', flatten=True)
    pts = [(v, cmds.xform(v, q=True, ws=True, t=True)) for v in verts]
    v_top = max(pts, key=lambda p: p[1][1] - 0.2 * p[1][0])[0]        # ustteki, kameraya yakin kose
    vp_pos = c.gpos(cmds.xform(v_top, q=True, ws=True, t=True))
    rec.glide(QtGui.QCursor.pos(), vp_pos, steps=10)
    rec.click(vp_pos, hold=3)
    cmds.select(v_top)                     # tik secimi kacirirsa G bos kalmasin
    rec.shot(3)
    rec.key('g', hold=4, expect=modal)
    away = QtCore.QPoint(vp_pos.x() + 130, vp_pos.y() - 160)
    rec.glide(vp_pos, away, steps=18, hold_end=5)
    rec.click(away, hold=14)
    rec.key('tab', hold=10, expect=lambda: not b.in_edit())

    rec.caption.set('Free and open source &nbsp;·&nbsp; <b>github.com/TeaYololo/orange-for-maya</b> &nbsp;·&nbsp; Maya 2022–2027')
    rec.hold(3.0)
    rec.finish()
    panel.close()
    b.set_setting('language', 'auto')
    print('kare: %d -> %s  kacirilan tus: %s' % (rec.n, out_dir, rec.MISSED))
    return rec.n
