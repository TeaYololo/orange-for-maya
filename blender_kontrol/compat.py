# -*- coding: utf-8 -*-
"""Qt / PySide2-6 uyumlulugu, olay ve dugme sabitleri, ana pencere."""
from __future__ import absolute_import, division, print_function

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
_numpy_holder = []     # [modul | None]; ilk kullanimda dolar (paket importunda yuklemek acilisi 100-300 ms uzatiyor)


def _numpy():
    """numpy modulu (Maya 2022+ ile geliyor) ya da None. Yalniz picking kullanir; tembel yuklenir."""
    if not _numpy_holder:
        try:
            import numpy
        except ImportError:
            numpy = None
        _numpy_holder.append(numpy)
    return _numpy_holder[0]


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
