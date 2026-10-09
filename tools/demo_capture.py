# -*- coding: utf-8 -*-
"""README demo GIF'i icin kare yakalama (Maya GUI icinde calisir).

Gercek tus ve fare olaylariyla kisa bir senaryo oynatir (tests/maya_live_tests.py yardimcilari) ve her adimda
ekrandan viewport bolgesini PNG olarak kaydeder. Sonra: python tools/make_gif.py <kare_klasoru> docs/media/demo.gif

Maya Script Editor (Python):
    import sys; sys.path.insert(0, r'<depo>/tools'); sys.path.insert(0, r'<depo>/tests'); sys.path.insert(0, r'<depo>')
    import demo_capture; demo_capture.run(r'C:/tmp/frames')
Fare imleci senaryo boyunca hareket eder; kullanicinin sahnesine dokunmaz (yeni sahne acar, sorar).
"""
from __future__ import print_function

import os
import time

import maya.cmds as cmds

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

import maya_live_tests as T

Qt = QtCore.Qt


class Recorder(object):
    def __init__(self, ctx, out_dir, fps=12):
        self.c = ctx
        self.out = out_dir
        self.n = 0
        self.dt = 1.0 / fps
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        for f in os.listdir(out_dir):
            if f.endswith('.png'):
                os.remove(os.path.join(out_dir, f))

    def rect(self):
        w = self.c.widget
        top_left = w.mapToGlobal(QtCore.QPoint(0, 0))
        return QtCore.QRect(top_left, w.size())

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
        r = self.rect()
        screen = QtGui.QGuiApplication.screenAt(r.center()) or QtGui.QGuiApplication.primaryScreen()
        geo = screen.geometry()
        full = screen.grabWindow(0)          # tum ekran; kirpmayi DPI oraniyla kendimiz yapiyoruz
        dpr = full.devicePixelRatio() or 1.0
        pix = full.copy(QtCore.QRect(int((r.x() - geo.x()) * dpr), int((r.y() - geo.y()) * dpr),
                                     int(r.width() * dpr), int(r.height() * dpr)))
        for _ in range(hold):
            pix.save(os.path.join(self.out, 'f%04d.png' % self.n))
            self.n += 1

    def wheel(self, pos, up=True):
        ev = QtGui.QWheelEvent(QtCore.QPointF(self.c.widget.mapFromGlobal(pos)), QtCore.QPointF(pos), QtCore.QPoint(0, 0),
                               QtCore.QPoint(0, 120 if up else -120), Qt.MouseButton.NoButton,
                               Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QtWidgets.QApplication.sendEvent(self.c.widget, ev)

    def glide(self, a, b, steps=10, hold_end=1):
        """Imleci a'dan b'ye kayarak tasi, her adimda kare al."""
        for i in range(1, steps + 1):
            t = i / float(steps)
            p = QtCore.QPoint(int(a.x() + (b.x() - a.x()) * t), int(a.y() + (b.y() - a.y()) * t))
            QtGui.QCursor.setPos(p)
            self.c.mouse(QtCore.QEvent.Type.MouseMove, p, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton)
            self.shot(hold_end if i == steps else 1)


def _settle(seconds):
    end = time.time() + seconds
    while time.time() < end:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)


def _close_floating():
    """Gorunumun ustunde yuzen paneller (UV Toolkit vb.) kareye girmesin."""
    for w in cmds.lsUI(type='workspaceControl') or []:
        try:
            if cmds.workspaceControl(w, q=True, floating=True) and cmds.workspaceControl(w, q=True, visible=True):
                cmds.workspaceControl(w, e=True, close=True)
        except Exception:
            pass


def run(out_dir):
    b = T.bk()
    if not b.is_installed():
        b.install(quiet=True)
    cmds.file(new=True, force=True)
    _settle(1.5)     # Maya yeni sahneden sonra ertelenmis islerinde secim modunu sifirliyor
    _close_floating()
    b.set_setting('language', 'en')
    T._standard_camera(b)
    c = T.Ctx('demo')
    cube = cmds.polyCube(name='Cube', w=4, h=4, d=4, sx=1, sy=1, sz=1)[0]
    cmds.xform('persp', worldSpace=True, translation=(11, 8, 11), rotation=(-27, 45, 0))
    cmds.setAttr('perspShape.centerOfInterest', 16.0)
    cmds.select(cube)
    cmds.refresh(force=True)
    rec = Recorder(c, out_dir)
    center = c.gpos((0, 0, 0))
    QtGui.QCursor.setPos(center)
    rec.shot(hold=6)

    # Tab: edit modu, 3: yuz, ust yuze tikla
    c.press('tab')
    rec.shot(hold=4)
    c.press('3')
    rec.shot(hold=3)
    top = c.gpos((0, 2, 0))
    rec.glide(center, top, steps=6)
    cmds.select(cube + '.f[1]')            # ust yuz (sentetik tik Maya secimine gitmiyor)
    rec.shot(hold=4)

    # E: extrude, fareyle yukari, sonra 1.5 yaz
    c.press('e')
    rec.shot(hold=2)
    up = QtCore.QPoint(top.x(), top.y() - 120)
    rec.glide(top, up, steps=10, hold_end=3)
    for ch in '1.5':
        c.type(ch)
        rec.shot(hold=2)
    c.press('enter')
    rec.shot(hold=6)

    # Ctrl+R: loop cut onizleme, tekerlek 3 kesim, tikla
    side = c.gpos((2, 0.5, 0))
    rec.glide(up, side, steps=8)
    c.press('ctrl+r')
    rec.shot(hold=3)
    near = c.gpos((2, 0.6, 1.0))
    rec.glide(side, near, steps=6, hold_end=3)
    for _ in range(2):
        rec.wheel(near, up=True)
        rec.shot(hold=3)
    c.click(near)
    rec.shot(hold=6)

    # Tab: obje modu, G X 2 Enter (kirmizi eksen cizgisi)
    c.press('tab')
    rec.shot(hold=3)
    c.press('g')
    rec.shot(hold=2)
    c.press('x')
    rec.shot(hold=3)
    right = QtCore.QPoint(near.x() + 160, near.y() + 40)
    rec.glide(near, right, steps=8)
    c.type('2')
    rec.shot(hold=3)
    c.press('enter')
    rec.shot(hold=6)

    # Z: shading pie
    mid = c.gpos((2, 2, 0))
    QtGui.QCursor.setPos(mid)
    c.press('z')
    rec.shot(hold=8)
    for w in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(w, b.PieMenu):
            w.close()
    rec.shot(hold=4)
    b.set_setting('language', 'auto')
    print('kare: %d -> %s' % (rec.n, out_dir))
    return rec.n
