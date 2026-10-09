# -*- coding: utf-8 -*-
"""Arayuz dili (TR / EN)."""
from __future__ import absolute_import, division, print_function

from .compat import QtCore
from .core import _state
from .settings import setting


# ---------------------------------------------------------------- dil (TR / EN)
EN = {}       # Turkce metin -> Ingilizce (i18n_en modulunden doldurulur)
HELP_EN = ''  # F1 yardiminin Ingilizcesi


def _lang():
    """'tr' | 'en'. Ayar 'auto' ise sistem dili Turkce degilse Ingilizce."""
    code = _state.get('lang')
    if code is None:
        code = setting('language')
        if code not in ('tr', 'en'):
            turkish = QtCore.QLocale.system().language() == QtCore.QLocale.Language.Turkish
            code = 'tr' if turkish else 'en'
        _state['lang'] = code
    return code


def _t(text):
    """Kullaniciya gorunen metni secili dile cevir (bilinmeyen metin aynen doner)."""
    if not text or _lang() != 'en':
        return text
    return EN.get(text, text)


def _load_translations():
    """Ingilizce metinleri paketin i18n_en modulunden yukle (paket disinda calisiyorsa sessizce gec)."""
    global HELP_EN
    try:
        from . import i18n_en
    except ImportError:
        return
    EN.clear()
    EN.update(i18n_en.EN)
    HELP_EN = i18n_en.HELP_EN


_load_translations()
