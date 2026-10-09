# -*- coding: utf-8 -*-
"""Eklentinin degistirdigi Maya ayarlarini sakla / geri yukle; kamera ayarlari."""
from __future__ import absolute_import, division, print_function

import maya.cmds as cmds

from .core import _warn
from .settings import setting
from .i18n import _t


_PREV_VARS = {'track': 'bk_prevTrackSelectionOrder', 'dolly': 'bk_prevDollyTowardsCenter',
              'tumble': 'bk_prevObjectTumble'}


def _save_maya_defaults():
    """Degistirecegimiz Maya ayarlarinin eski degerlerini sakla (uninstall geri yukler)."""
    if cmds.optionVar(exists=_PREV_VARS['track']):
        return   # zaten saklanmis (ac/kapat/yeniden yukle arasinda ustune yazma)
    try:
        cmds.optionVar(intValue=(_PREV_VARS['track'], int(bool(cmds.selectPref(q=True, trackSelectionOrder=True)))))
        cmds.optionVar(intValue=(_PREV_VARS['dolly'],
                                 int(bool(cmds.dollyCtx('dollyContext', q=True, dollyTowardsCenter=True)))))
        cmds.optionVar(intValue=(_PREV_VARS['tumble'],
                                 int(bool(cmds.tumbleCtx('tumbleContext', q=True, objectTumble=True)))))
    except Exception as exc:
        _warn(_t('ayarlar saklanamadı: %s') % exc)


def _restore_maya_defaults():
    if not cmds.optionVar(exists=_PREV_VARS['track']):
        return
    try:
        cmds.selectPref(trackSelectionOrder=bool(cmds.optionVar(q=_PREV_VARS['track'])))
    except Exception:
        pass
    try:
        cmds.dollyCtx('dollyContext', edit=True, dollyTowardsCenter=bool(cmds.optionVar(q=_PREV_VARS['dolly'])))
    except Exception:
        pass
    try:
        cmds.tumbleCtx('tumbleContext', edit=True, objectTumble=bool(cmds.optionVar(q=_PREV_VARS['tumble'])))
    except Exception:
        pass
    for var in _PREV_VARS.values():
        cmds.optionVar(remove=var)


def _apply_camera_settings():
    """Blender'in navigasyon ayarlarini Maya'nin kamera araclarina aktar."""
    try:
        cmds.dollyCtx('dollyContext', edit=True, dollyTowardsCenter=not setting('zoom_to_mouse'))
    except Exception as exc:
        _warn(_t('zoom ayarı uygulanamadı: %s') % exc)
    try:
        cmds.tumbleCtx('tumbleContext', edit=True, objectTumble=bool(setting('orbit_selection')))
    except Exception as exc:
        _warn(_t('orbit ayarı uygulanamadı: %s') % exc)
