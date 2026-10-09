# -*- coding: utf-8 -*-
"""Paylasilan durum, kullanici mesajlari ve kurulu olay filtresine erisim."""
from __future__ import absolute_import, division, print_function

import sys

import maya.cmds as cmds

from .compat import QtCore, QtGui, QtWidgets


_state = {'comp': 'vertex', 'auto_ortho': set()}


def _msg(text):
    try:
        cmds.inViewMessage(assistMessage=text, position='topCenter', fade=True,
                           fadeStayTime=900, fadeOutTime=300)
    except Exception:
        print('[Orange] ' + text)


def _tip(text):
    """Farenin yaninda canli deger kutusu (headsUpMessage Turkce karakter gosteremiyor)."""
    QtWidgets.QToolTip.showText(QtGui.QCursor.pos() + QtCore.QPoint(20, 20), text)


def _warn(text):
    cmds.warning('[Orange] ' + text)


_search_cache = []

# Her kullanici islemi (undo chunk'i kapanmadan hemen once) cagrilan kancalar: ust katmanlar kaydeder
# (ornegin editmode: 'edit modunda gecmis birakma' ayari). Kanca hata verirse islem bozulmaz.
after_op_hooks = []


def run_after_op():
    for hook in list(after_op_hooks):
        try:
            hook()
        except Exception as exc:
            _warn('after-op: %s' % exc)


# ---------------------------------------------------------------- kurulum
_KEY = '_blender_kontrol_filter'
_JOB_KEY = '_blender_kontrol_cursor_job'


def _filter():
    return getattr(sys.modules['__main__'], _KEY, None)


def _current_filter_set_modal(modal):
    filt = _filter()
    if filt is not None:
        filt.modal = modal
