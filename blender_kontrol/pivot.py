# -*- coding: utf-8 -*-
"""Pivot noktasi, donusum oryantasyonu ve snap ayarlari."""
from __future__ import absolute_import, division, print_function

import functools

from .core import _msg
from .settings import FRAME_NAMES, PIVOT_NAMES, SNAP_NAMES, set_setting, setting
from .i18n import _t
from .util import popup
from .ui import pie


# ---------------------------------------------------------------- pivot / oryantasyon / snap
def set_pivot(mode):
    set_setting('pivot', mode)
    _msg(_t('Pivot: %s') % _t(PIVOT_NAMES[mode]))


def set_orientation(name):
    set_setting('orientation', name)
    _msg(_t('Oryantasyon: %s') % _t(FRAME_NAMES[name]))


def toggle_snap():
    on = not setting('snap_on')
    set_setting('snap_on', on)
    _msg(_t('Snap: %s (%s)') % (_t('açık') if on else _t('kapalı'), _t(SNAP_NAMES[setting('snap_target')])))


def set_snap_target(target):
    set_setting('snap_target', target)
    _msg(_t('Snap hedefi: %s') % _t(SNAP_NAMES[target]))


def snap_target_menu():
    """Shift+Ctrl+Tab: snap hedefi."""
    now = setting('snap_target')
    popup(_t('Snap hedefi (Shift+Tab açar / kapar, Ctrl geçici)'), [
        ('%s %s' % ('●' if now == key else '○', _t(label)), functools.partial(set_snap_target, key))
        for key, label in (('increment', 'Artım (grid adımı)'), ('vertex', 'Köşe'),
                           ('edge', 'Kenar'), ('face', 'Yüz'))
    ])


def pivot_pie():
    now = setting('pivot')
    return pie(_t('Pivot noktası (.)'), [
        (_t('Sınır kutusu merkezi'), lambda: set_pivot('bbox'), now == 'bbox'),
        (_t('3D İmleç'), lambda: set_pivot('cursor'), now == 'cursor'),
        (_t('Tek tek (Individual Origins)'), lambda: set_pivot('individual'), now == 'individual'),
        (_t('Orta nokta (Median)'), lambda: set_pivot('median'), now == 'median'),
        (_t('Aktif eleman'), lambda: set_pivot('active'), now == 'active'),
    ])


def orientation_pie():
    now = setting('orientation')
    return pie(_t('Dönüşüm oryantasyonu (,)'), [
        (_t('Global'), lambda: set_orientation('global'), now == 'global'),
        (_t('Lokal'), lambda: set_orientation('local'), now == 'local'),
        (_t('Normal'), lambda: set_orientation('normal'), now == 'normal'),
        (_t('Görünüm (View)'), lambda: set_orientation('view'), now == 'view'),
        (_t('İmleç (Cursor)'), lambda: set_orientation('cursor'), now == 'cursor'),
        (_t('Ebeveyn (Parent)'), lambda: set_orientation('parent'), now == 'parent'),
    ])
