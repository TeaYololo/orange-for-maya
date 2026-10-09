# -*- coding: utf-8 -*-
"""pytest ayarlari: Maya yoksa (CI) sahte `maya` modulleri, Qt icin ekransiz uygulama.

Gercek Maya islevleri burada calismaz; bu testler yalnizca Maya'dan bagimsiz mantigi (tus tablolari, ifade
ayristirma, mesh grafigi algoritmalari, kisayol tablosu, ceviri kapsami, katman kurali) sinar.
Maya icindeki testler: tests/headless_tests.py (mayapy) ve tests/maya_live_tests.py (Maya GUI).
"""
import os
import sys
import tempfile
import types
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['ORANGE_KEYMAP'] = os.path.join(tempfile.mkdtemp(prefix='orange_keymap_'), 'keymap.json')


class _StubModule(types.ModuleType):
    """Her ozelligi MagicMock olan modul (maya.cmds.ls(...) gibi cagrilar hata vermeden doner)."""

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        value = mock.MagicMock(name='%s.%s' % (self.__name__, name))
        setattr(self, name, value)
        return value


def _install_maya_stubs():
    try:
        import maya.cmds  # noqa: F401  gercek Maya (mayapy ile pytest)
        return False
    except ImportError:
        pass
    names = ['maya', 'maya.cmds', 'maya.mel', 'maya.utils', 'maya.OpenMaya', 'maya.OpenMayaUI', 'maya.api',
             'maya.api.OpenMaya', 'maya.api.OpenMayaUI', 'maya.standalone']
    for name in names:
        mod = _StubModule(name)
        mod.__path__ = []          # paket gibi davransin
        sys.modules[name] = mod
    for name in names:
        parent, _, child = name.rpartition('.')
        if parent:
            setattr(sys.modules[parent], child, sys.modules[name])
    cmds = sys.modules['maya.cmds']
    cmds.currentUnit = lambda **kw: 'cm'
    cmds.optionVar = lambda *a, **kw: 0     # ayar yok -> varsayilan
    cmds.about = lambda **kw: False
    return True


STUBBED = _install_maya_stubs()

try:
    from PySide6 import QtWidgets
except ImportError as _pyside6_error:  # pragma: no cover
    try:
        from PySide2 import QtWidgets
    except ImportError:
        # asil sebep PySide6'nin hatasidir (Linux'ta eksik libEGL / libxkbcommon gibi); onu goster
        raise _pyside6_error
if QtWidgets.QApplication.instance() is None:
    _APP = QtWidgets.QApplication([])
