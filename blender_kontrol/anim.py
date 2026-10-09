# -*- coding: utf-8 -*-
"""Animasyon ve zaman cizelgesi kisayollari."""
from __future__ import absolute_import, division, print_function

import maya.cmds as cmds

from .core import _msg
from .settings import setting
from .i18n import _t
from .util import _objs


# ---------------------------------------------------------------- animasyon
def insert_key():
    objs = _objs()
    if objs:
        cmds.setKeyframe(objs, attribute=['translate', 'rotate', 'scale'])
        _msg(_t('Keyframe eklendi (kare %d)') % cmds.currentTime(q=True))


def clear_key():
    objs = _objs()
    if objs:
        t = cmds.currentTime(q=True)
        cmds.cutKey(objs, time=(t, t), clear=True)
        _msg(_t('Keyframe silindi'))


def play_toggle():
    cmds.play(state=not cmds.play(q=True, state=True))


def play_reverse():
    """Shift+Ctrl+Space: geriye dogru oynat / durdur."""
    if cmds.play(q=True, state=True):
        cmds.play(state=False)
    else:
        cmds.play(state=True, forward=False)


def frame_step(step):
    cmds.currentTime(cmds.currentTime(q=True) + step)


def frame_jump(end):
    t = cmds.playbackOptions(q=True, maxTime=True) if end else cmds.playbackOptions(q=True, minTime=True)
    cmds.currentTime(t)


def key_jump(forward):
    """Yukari / asagi ok: secili objelerin sonraki / onceki anahtari (secim yoksa zaman cubugu)."""
    which = 'next' if forward else 'previous'
    targets = cmds.ls(sl=True, objectsOnly=True) or []
    t = cmds.findKeyframe(targets, which=which) if targets else cmds.findKeyframe(timeSlider=True, which=which)
    cmds.currentTime(t)


    # Not: menuyu burada yeniden kurma; kendi callback'i icinde menu silmek Maya'yi cokertebilir


def space_action():
    from .search import show_search  # dongusel import: cagri aninda
    if setting('space_action') == 'search':
        show_search()
    else:
        play_toggle()


def set_range_end(end):
    """Ctrl+Home / Ctrl+End: oynatma araliginin basini / sonunu gecerli kareye ayarla."""
    now = cmds.currentTime(q=True)
    cmds.playbackOptions(**({'maxTime': now} if end else {'minTime': now}))
    _msg(_t('Aralık: %d - %d') % (cmds.playbackOptions(q=True, minTime=True), cmds.playbackOptions(q=True, maxTime=True)))
