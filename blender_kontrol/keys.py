# -*- coding: utf-8 -*-
"""Fiziksel tus okuma (Windows scan code, Linux evdev, macOS kVK) ve kisayol adlari."""
from __future__ import absolute_import, division, print_function

import sys

from .compat import ALT, CTRL, KEYPAD, Qt, SHIFT
from .settings import setting


# Windows scan code -> tus adi (klavye dilinden bagimsiz)
SCAN = {
    0x10: 'q', 0x11: 'w', 0x12: 'e', 0x13: 'r', 0x14: 't', 0x15: 'y', 0x16: 'u',
    0x17: 'i', 0x18: 'o', 0x19: 'p', 0x1E: 'a', 0x1F: 's', 0x20: 'd', 0x21: 'f',
    0x22: 'g', 0x23: 'h', 0x24: 'j', 0x25: 'k', 0x26: 'l', 0x2C: 'z', 0x2D: 'x',
    0x2E: 'c', 0x2F: 'v', 0x30: 'b', 0x31: 'n', 0x32: 'm',
    0x02: '1', 0x03: '2', 0x04: '3', 0x05: '4', 0x06: '5', 0x07: '6', 0x08: '7',
    0x09: '8', 0x0A: '9', 0x0B: '0', 0x29: 'grave', 0x0F: 'tab', 0x33: 'comma', 0x34: 'period',
}
NUMPAD_SCAN = {
    0x52: '0', 0x4F: '1', 0x50: '2', 0x51: '3', 0x4B: '4', 0x4C: '5', 0x4D: '6',
    0x47: '7', 0x48: '8', 0x49: '9', 0x53: '.', 0x4E: '+', 0x4A: '-', 0x37: '*',
    0x35: '/',
}
# Linux / X11 (xcb) ve Wayland: Qt'nin nativeScanCode'u X keycode = evdev kodu + 8. evdev kodlari ana blokta
# PC set-1 scan code'larla ayni (KEY_Q = 16 = 0x10), yani SCAN tablosu -8 ile kullanilir. Fark: KP / = 98.
LINUX_NUMPAD = dict(NUMPAD_SCAN)
LINUX_NUMPAD[0x62] = '/'

# macOS: nativeScanCode hep 0; nativeVirtualKey = Carbon kVK_* (fiziksel konum, klavye dilinden bagimsiz)
MAC_VK = {
    0x00: 'a', 0x01: 's', 0x02: 'd', 0x03: 'f', 0x04: 'h', 0x05: 'g', 0x06: 'z', 0x07: 'x', 0x08: 'c',
    0x09: 'v', 0x0B: 'b', 0x0C: 'q', 0x0D: 'w', 0x0E: 'e', 0x0F: 'r', 0x10: 'y', 0x11: 't',
    0x12: '1', 0x13: '2', 0x14: '3', 0x15: '4', 0x16: '6', 0x17: '5', 0x19: '9', 0x1A: '7', 0x1C: '8',
    0x1D: '0', 0x1F: 'o', 0x20: 'u', 0x22: 'i', 0x23: 'p', 0x25: 'l', 0x26: 'j', 0x28: 'k',
    0x2B: 'comma', 0x2D: 'n', 0x2E: 'm', 0x2F: 'period', 0x30: 'tab', 0x32: 'grave',
}
MAC_NUMPAD = {
    0x52: '0', 0x53: '1', 0x54: '2', 0x55: '3', 0x56: '4', 0x57: '5', 0x58: '6', 0x59: '7', 0x5B: '8',
    0x5C: '9', 0x41: '.', 0x45: '+', 0x4E: '-', 0x43: '*', 0x4B: '/',
}


def _platform():
    if sys.platform == 'darwin':
        return 'mac'
    if sys.platform.startswith('linux'):
        return 'linux'
    return 'win'


PLATFORM = _platform()


def _phys(ev, platform=None):
    """Klavye dilinden bagimsiz fiziksel tus: (ad, numpad_mi). Bulunamazsa (None, numpad_mi)."""
    platform = platform or PLATFORM
    keypad = bool(ev.modifiers() & KEYPAD)
    if platform == 'mac':
        vk = ev.nativeVirtualKey()
        if vk in MAC_NUMPAD and (keypad or vk not in MAC_VK):
            return MAC_NUMPAD[vk], True
        if vk == 0 and int(ev.key()) != int(Qt.Key.Key_A) and ev.text().lower() not in ('a', 'q'):
            return None, keypad   # kVK_ANSI_A = 0 ile "bilgi yok" ayni deger
        return MAC_VK.get(vk), False
    sc = ev.nativeScanCode()
    if platform == 'linux':
        code = sc - 8 if sc > 8 else 0
        if keypad:
            return LINUX_NUMPAD.get(code), True
        return SCAN.get(code), False
    if keypad:
        return NUMPAD_SCAN.get(sc & 0xFF), True
    if sc and not sc & 0x100:
        return SCAN.get(sc & 0xFF), False
    return None, False


QT_KEYS = {
    int(Qt.Key.Key_Delete): 'delete', int(Qt.Key.Key_Home): 'home',
    int(Qt.Key.Key_Space): 'space', int(Qt.Key.Key_Left): 'left',
    int(Qt.Key.Key_Right): 'right', int(Qt.Key.Key_Up): 'up',
    int(Qt.Key.Key_Down): 'down', int(Qt.Key.Key_F1): 'f1',
    int(Qt.Key.Key_F12): 'f12', int(Qt.Key.Key_Tab): 'tab', int(Qt.Key.Key_F2): 'f2',
    int(Qt.Key.Key_F3): 'f3', int(Qt.Key.Key_F9): 'f9', int(Qt.Key.Key_F11): 'f11',
    int(Qt.Key.Key_Backtab): 'tab', int(Qt.Key.Key_Comma): 'comma', int(Qt.Key.Key_Period): 'period',
    int(Qt.Key.Key_PageUp): 'pgup', int(Qt.Key.Key_PageDown): 'pgdown', int(Qt.Key.Key_End): 'end',
}
SPECIAL_KEYS = ('delete', 'home', 'space', 'left', 'right', 'up', 'down', 'f1', 'f2', 'f3', 'f9', 'f11', 'f12',
                'pgup', 'pgdown', 'end')
for _c in range(26):
    QT_KEYS.setdefault(int(Qt.Key.Key_A) + _c, chr(ord('a') + _c))


def _combo_label(combo):
    parts = combo.split('+')
    out = []
    for p in parts:
        if p.startswith('np') and len(p) > 2:
            out.append('Numpad ' + p[2:])
        elif p == 'grave':
            out.append('`')
        elif p == 'comma':
            out.append(',')
        elif p in ('pgup', 'pgdown'):
            out.append('PageUp' if p == 'pgup' else 'PageDown')
        elif p == 'period':
            out.append('.')
        else:
            out.append(p.capitalize() if len(p) > 1 else p.upper())
    return '+'.join(out)


def _key_name(ev, platform=None):
    phys, numpad = _phys(ev, platform)
    if numpad:
        return ('np' + phys) if phys else None
    name = QT_KEYS.get(int(ev.key()))
    if name in SPECIAL_KEYS:
        return name
    name = phys or name
    if name and name.isdigit() and setting('emulate_numpad'):
        return 'np' + name   # Blender "Emulate Numpad": ust siradaki rakamlar numpad gibi
    return name


def _combo(ev, name):
    mods = ev.modifiers()
    parts = []
    if mods & CTRL:
        parts.append('ctrl')
    if mods & ALT:
        parts.append('alt')
    if mods & SHIFT:
        parts.append('shift')
    return '+'.join(parts + [name])
