# -*- coding: utf-8 -*-
"""Eklentinin degistirdigi Maya ayarlarini sakla / geri yukle; kamera ayarlari."""
from __future__ import absolute_import, division, print_function

import maya.cmds as cmds

from .core import _warn
from .settings import setting
from .i18n import _t


_PREV_VARS = {'track': 'bk_prevTrackSelectionOrder', 'dolly': 'bk_prevDollyTowardsCenter',
              'tumble': 'bk_prevObjectTumble', 'local_tumble': 'bk_prevLocalTumble',
              'auto_pivot': 'bk_prevAutoSetPivot', 'depth': 'bk_prevUseDepth',
              'paint_depth': 'bk_prevPaintSelectWithDepth'}

# Her Maya ayari: (sorgu, geri yukleme). Sorgu degeri int olarak saklanir.
_PREV_GETSET = {
    'track': (lambda: cmds.selectPref(q=True, trackSelectionOrder=True),
              lambda v: cmds.selectPref(trackSelectionOrder=bool(v))),
    'dolly': (lambda: cmds.dollyCtx('dollyContext', q=True, dollyTowardsCenter=True),
              lambda v: cmds.dollyCtx('dollyContext', edit=True, dollyTowardsCenter=bool(v))),
    'tumble': (lambda: cmds.tumbleCtx('tumbleContext', q=True, objectTumble=True),
               lambda v: cmds.tumbleCtx('tumbleContext', edit=True, objectTumble=bool(v))),
    'local_tumble': (lambda: cmds.tumbleCtx('tumbleContext', q=True, localTumble=True),
                     lambda v: cmds.tumbleCtx('tumbleContext', edit=True, localTumble=int(v))),
    'auto_pivot': (lambda: cmds.tumbleCtx('tumbleContext', q=True, autoSetPivot=True),
                   lambda v: cmds.tumbleCtx('tumbleContext', edit=True, autoSetPivot=bool(v))),
    'depth': (lambda: cmds.selectPref(q=True, useDepth=True),
              lambda v: cmds.selectPref(useDepth=bool(v))),
    'paint_depth': (lambda: cmds.selectPref(q=True, paintSelectWithDepth=True),
                    lambda v: cmds.selectPref(paintSelectWithDepth=bool(v))),
}


def _save_maya_defaults():
    """Degistirecegimiz Maya ayarlarinin eski degerlerini sakla (uninstall geri yukler). Her ayar ayri
    saklanir: sonradan eklenen bir ayar (ornegin useDepth) eski kurulumlarda da bir kez kaydedilir, zaten
    saklanmis olanin ustune yazilmaz (ac / kapat / yeniden yukle)."""
    for key, var in _PREV_VARS.items():
        if cmds.optionVar(exists=var):
            continue
        try:
            cmds.optionVar(intValue=(var, int(_PREV_GETSET[key][0]())))
        except Exception as exc:
            _warn(_t('ayarlar saklanamadı: %s') % exc)


def _prev(key, default):
    var = _PREV_VARS[key]
    return cmds.optionVar(q=var) if cmds.optionVar(exists=var) else default


def _restore_maya_defaults():
    for key, var in _PREV_VARS.items():
        if not cmds.optionVar(exists=var):
            continue
        try:
            _PREV_GETSET[key][1](cmds.optionVar(q=var))
        except Exception:
            pass
        cmds.optionVar(remove=var)


def _apply_camera_settings():
    """Blender'in navigasyon ayarlarini Maya'nin kamera araclarina aktar."""
    try:
        cmds.dollyCtx('dollyContext', edit=True, dollyTowardsCenter=not setting('zoom_to_mouse'))
    except Exception as exc:
        _warn(_t('zoom ayarı uygulanamadı: %s') % exc)
    try:
        if setting('orbit_selection'):
            # Blender "Orbit Around Selection" = Maya tumble pivot + Auto-set pivot (her secim pivotu secimin
            # merkezine koyar). Onceki surum objectTumble'i aciyordu; o "imlecin altindaki objenin etrafinda"
            # demek ve secimle ilgisi yok, bu yuzden ayar hicbir sey yapmiyor gibiydi (#9).
            cmds.tumbleCtx('tumbleContext', edit=True, localTumble=0, autoSetPivot=True, objectTumble=False)
        else:
            cmds.tumbleCtx('tumbleContext', edit=True, localTumble=int(_prev('local_tumble', 1)),
                           autoSetPivot=bool(_prev('auto_pivot', 0)), objectTumble=bool(_prev('tumble', 0)))
    except Exception as exc:
        _warn(_t('orbit ayarı uygulanamadı: %s') % exc)


def sync_camera_selection(through):
    """Blender: Solid'de yalniz gorunen secilir; Wireframe / X-Ray'de arkadakiler de (#6).
    through: True = arkadakiler de secilsin (Maya'da camera based selection kapali)."""
    if not setting('auto_camera_select'):
        return
    try:
        cmds.selectPref(useDepth=not through, paintSelectWithDepth=not through)
    except Exception as exc:
        _warn(_t('seçim ayarı uygulanamadı: %s') % exc)
