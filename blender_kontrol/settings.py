# -*- coding: utf-8 -*-
"""Kalici ayarlar (optionVar)."""
from __future__ import absolute_import, division, print_function

import maya.cmds as cmds

from .core import _search_cache, _state


# ---------------------------------------------------------------- ayarlar (optionVar, Maya kapaninca da kalir)
SETTINGS = {
    'emulate_numpad': ('bk_emulateNumpad', 0),
    'emulate_3button': ('bk_emulate3Button', 0),
    'space_action': ('bk_spaceAction', 'play'),   # play | hotbox | search
    'zoom_to_mouse': ('bk_zoomToMouse', 0),       # Blender: Zoom to Mouse Position
    'orbit_selection': ('bk_orbitSelection', 0),  # Blender: Orbit Around Selection
    'pivot': ('bk_pivot', 'median'),              # median | bbox | cursor | active | individual
    'orientation': ('bk_orientation', 'global'),  # global | local | normal | view | cursor | parent
    'snap_on': ('bk_snapOn', 0),                  # Shift+Tab
    'snap_target': ('bk_snapTarget', 'increment'),  # increment | vertex | edge | face
    'language': ('bk_language', 'auto'),          # auto | tr | en
    'cursor_orient': ('bk_cursorOrient', 'none'), # Shift+sag tik: none | view | surface
    'favorites': ('bk_favorites', '[]'),          # Q: JSON [[tur, ad], ...]
    'destructive_edit': ('bk_destructiveEdit', 0),  # edit modu islemleri gecmis birakmasin (Blender gibi)
    'overlay': ('bk_overlay', 'qt'),              # onizleme cizimi: qt (viewport ustu pencere) | vp2 (eklenti)
}

PIVOT_NAMES = {'median': 'orta nokta', 'bbox': 'sınır kutusu', 'cursor': '3D imleç',
               'active': 'aktif eleman', 'individual': 'tek tek'}
FRAME_NAMES = {'global': 'global', 'local': 'lokal', 'normal': 'normal', 'view': 'görünüm',
               'cursor': 'imleç', 'parent': 'ebeveyn'}
SNAP_NAMES = {'increment': 'artım (grid)', 'vertex': 'köşe', 'edge': 'kenar', 'face': 'yüz'}


def setting(name):
    var, default = SETTINGS[name]
    if not cmds.optionVar(exists=var):
        return default
    return cmds.optionVar(q=var)


def set_setting(name, value):
    from .mayaprefs import _apply_camera_settings  # dongusel import: cagri aninda
    var, _ = SETTINGS[name]
    if isinstance(value, str):
        cmds.optionVar(stringValue=(var, value))
    else:
        cmds.optionVar(intValue=(var, int(value)))
    if name in ('zoom_to_mouse', 'orbit_selection'):
        _apply_camera_settings()
    if name == 'language':
        _state['lang'] = None
        del _search_cache[:]
