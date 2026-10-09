# -*- coding: utf-8 -*-
"""Qt / PySide2-6 uyumlulugu, olay ve dugme sabitleri, ana pencere."""
from __future__ import absolute_import, division, print_function

try:
    import numpy as _np          # Maya 2022+ ile geliyor; ekran uzayi kose snap'i icin
except ImportError:
    _np = None

import maya.OpenMayaUI as omui

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:  # Maya 2024 ve oncesi
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance


Qt = QtCore.Qt
QEvent = QtCore.QEvent

EV_KEY_PRESS = QEvent.Type.KeyPress
EV_KEY_RELEASE = QEvent.Type.KeyRelease
EV_SHORTCUT = QEvent.Type.ShortcutOverride
EV_MPRESS = QEvent.Type.MouseButtonPress
EV_MRELEASE = QEvent.Type.MouseButtonRelease
EV_MMOVE = QEvent.Type.MouseMove
EV_MDBL = QEvent.Type.MouseButtonDblClick
EV_WHEEL = QEvent.Type.Wheel
KEY_EVENTS = (EV_SHORTCUT, EV_KEY_PRESS, EV_KEY_RELEASE)
MOUSE_EVENTS = (EV_MPRESS, EV_MRELEASE, EV_MMOVE, EV_MDBL, EV_WHEEL)

LMB = Qt.MouseButton.LeftButton
MMB = Qt.MouseButton.MiddleButton
RMB = Qt.MouseButton.RightButton
NOBTN = Qt.MouseButton.NoButton
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
ALT = Qt.KeyboardModifier.AltModifier
KEYPAD = Qt.KeyboardModifier.KeypadModifier
NOMOD = Qt.KeyboardModifier.NoModifier


# ---------------------------------------------------------------- yardimcilar
def _main_window():
    return wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)


def _exec_menu(menu):
    pos = QtGui.QCursor.pos()
    if hasattr(menu, 'exec'):
        getattr(menu, 'exec')(pos)
    else:
        menu.exec_(pos)


def _event_global_pos(ev):
    if hasattr(ev, 'globalPosition'):
        return ev.globalPosition().toPoint()
    return ev.globalPos()
