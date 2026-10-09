# -*- coding: utf-8 -*-
"""Orange (Maya, the Blender way) kurulumu / Installer.

TR: Bu dosyayi Maya'nin 3D gorunumune surukleyip birak. Orange bir Maya modulu olarak
    Belgeler/maya/modules/orange klasorune kurulur, Maya her acildiginda otomatik baslar ve
    rafa Orange ac/kapa dugmesi eklenir. Kendi userSetup.py dosyana dokunulmaz.
EN: Drag and drop this file onto a Maya viewport. Orange is installed as a Maya module in
    Documents/maya/modules/orange, starts automatically with Maya and adds an on / off shelf button.
    Your own userSetup.py is not touched.

Elle / manually (Script Editor, Python):
    import sys; sys.path.insert(0, r'<this folder>')
    import drag_drop_install; drag_drop_install.install()      # kur / install
    drag_drop_install.uninstall()                              # kaldir / remove

Kurulum mantigi blender_kontrol/installer.py dosyasindadir; burada dosya yolundan yuklenir
(Maya'da eski bir surum yukluyken de yeni kurulum kodu calissin diye).
"""
from __future__ import absolute_import, print_function

import importlib.util
import inspect
import os


def _source_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:   # bazi Maya surumlerinde surukle-birak sirasinda __file__ yok
        return os.path.dirname(os.path.abspath(inspect.getsourcefile(_source_dir)))


def _load_installer():
    path = os.path.join(_source_dir(), 'blender_kontrol', 'installer.py')
    spec = importlib.util.spec_from_file_location('orange_installer', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_installer = _load_installer()
# Geriye uyumluluk ve testler icin installer adlari burada da erisilebilir
for _name in dir(_installer):
    if not _name.startswith('__'):
        globals().setdefault(_name, getattr(_installer, _name))
del _name


def install(source_dir=None, **kwargs):
    return _installer.install(source_dir or _source_dir(), **kwargs)


def uninstall(**kwargs):
    return _installer.uninstall(**kwargs)


def onMayaDroppedPythonFile(*_):
    """Maya bu fonksiyonu dosya viewport'a birakilinca cagirir."""
    install()
