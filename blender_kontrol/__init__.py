# -*- coding: utf-8 -*-
"""Orange: Maya, the Blender way.

Blender'in klavye ve fare duzenini, modal araclarini, pie menulerini ve 3D imlecini Maya'ya getirir.
Tuslar fiziksel konumdan (scan code) okunur; Maya'nin kendi kisayollarina dokunulmaz ve kapatilinca
her sey Maya varsayilanina doner.

    import blender_kontrol; blender_kontrol.install()    # ac
    blender_kontrol.uninstall()                          # kapat
    blender_kontrol.show_help()                          # kisayol listesi

Paket yapisi, alttan uste (alt katman ust katmani modul basinda import etmez; gereken birkac yerde
fonksiyon icinde import edilir):

    compat      Qt / PySide2-6, olay sabitleri          keys        fiziksel tus okuma
    core        paylasilan durum, mesajlar              util        secim / undo / menu yardimcilari
    settings    kalici ayarlar (optionVar)              ui          ipucu cubugu, overlay, pie, satir kutusu
    i18n        TR / EN                                 picking     fare alti mesh, mesh grafigi
    mayaprefs   Maya ayarlarini sakla / geri yukle      editmode    Tab, 1 / 2 / 3
    cursor      3D imlec                                pivot       pivot / oryantasyon / snap
    anim, view  animasyon, gorunum                      modal       G / R / S / extrude / inset / bevel
    valuemodal, loopcut, slide                          tek degerli modal, Ctrl+R, G G
    selection, mesh, objects                            secim, edit modu ve obje modu islemleri
    modifiers   Blender modifier karsiliklari ve paneli   interop     Blender ile FBX gidis-donus
    modes, uv, graph                                    sculpt / boyama, UV editoru, Graph Editor
    adjust, helptext, settings_ui, search               F9, F1, Ctrl+, F3 ve Q
    diagnostics tus testi, sorun bildir                 cheatsheet  yazdirilabilir kisayol karti
    hotkeys     Hotkey Editor'da 'Orange' komutlari (runTimeCommand)
    keymap      tus tablosu, kullanici kisayollari      events      Qt olay filtresi
    lifecycle   install / uninstall / reload / menu
"""
from __future__ import absolute_import, division, print_function

__version__ = '0.9.0'
PRODUCT = 'Orange'
TAGLINE = 'Maya, the Blender way'

from . import compat, core, settings, i18n, keys, util, ui, picking, mayaprefs  # noqa: E402
from . import editmode, cursor, pivot, anim, view, modal, valuemodal, loopcut, slide  # noqa: E402
from . import selection, mesh, objects, modifiers, interop, modes, uv, graph, adjust, helptext, settings_ui  # noqa: E402
from . import diagnostics, search, keymap, cheatsheet, hotkeys, events, lifecycle  # noqa: E402

MODULES = (compat, core, settings, i18n, keys, util, ui, picking, mayaprefs, editmode, cursor, pivot, anim,
           view, modal, valuemodal, loopcut, slide, selection, mesh, objects, modifiers, interop, modes, uv, graph, adjust,
           helptext, settings_ui, diagnostics, search, keymap, cheatsheet, hotkeys, events, lifecycle)

# Geriye uyumluluk: tek dosyali surumdeki adlar paket uzerinden de erisilebilir
# (blender_kontrol.install(), blender_kontrol.Modal ...). Yeni kodda alt modulu kullan.
for _mod in MODULES:
    for _name, _value in vars(_mod).items():
        if not _name.startswith('__'):
            globals().setdefault(_name, _value)
del _mod, _name, _value

from .lifecycle import install, uninstall, is_installed, reload_module  # noqa: E402,F401
