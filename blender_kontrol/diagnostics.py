# -*- coding: utf-8 -*-
"""Tus testi penceresi ve 'Sorun bildir': kullanici raporlari icin tanilama bilgisi (telemetri yok, her sey yerel)."""
from __future__ import absolute_import, division, print_function

import os
import platform as _pyplatform
import sys

import maya.cmds as cmds

from .compat import Qt, QtCore, QtGui, QtWidgets, _main_window
from .core import _filter, _msg, _state
from .settings import SETTINGS, setting
from .i18n import _lang, _t
from .keys import PLATFORM, _combo, _key_name, _phys

# Depo yeniden adlandirilinca GitHub eski adresi yeni adrese yonlendirir.
REPO_URL = 'https://github.com/TeaYololo/orange-for-maya'
ISSUES_URL = REPO_URL + '/issues/new/choose'


def _qt_versions():
    try:
        import PySide6 as pyside
    except ImportError:  # Maya 2024 ve oncesi
        import PySide2 as pyside
    return QtCore.qVersion(), getattr(pyside, '__version__', '?')


def diagnostics_text():
    """Sorun bildirimi icin duz metin (kisisel veri yok: yol, surum, platform, ayarlar)."""
    from . import __version__   # dongusel import: cagri aninda
    qt, pyside = _qt_versions()
    app = QtGui.QGuiApplication.instance()
    try:
        layout = QtGui.QGuiApplication.inputMethod().locale().name()
    except Exception:
        layout = '?'
    filt = _filter()
    lines = [
        'Orange %s' % __version__,
        'Maya: %s (%s)' % (cmds.about(version=True), cmds.about(cutIdentifier=True)),
        'OS: %s / %s' % (cmds.about(operatingSystemVersion=True), _pyplatform.platform()),
        'Python: %s' % sys.version.split()[0],
        'Qt: %s, PySide: %s, platform plugin: %s' % (qt, pyside, app.platformName() if app else '?'),
        'Key table: %s, input locale: %s, UI language: %s / Maya %s' % (
            PLATFORM, layout, _lang(), cmds.about(uiLanguage=True)),
        'Installed: %s, key replays: %s' % (filt is not None, getattr(filt, 'replays', '-')),
        'Package: %s' % os.path.dirname(os.path.abspath(__file__)).replace('\\', '/'),
        'Custom shortcuts: %d' % len(_state.get('overrides') or {}),
        'Settings: ' + ', '.join('%s=%s' % (k, setting(k)) for k in sorted(SETTINGS) if k != 'favorites'),
    ]
    return '\n'.join(lines)


def report_issue():
    """Tanilama bilgisini panoya kopyala ve GitHub'da yeni sorun sayfasini ac."""
    text = diagnostics_text()
    QtWidgets.QApplication.clipboard().setText(text)
    QtGui.QDesktopServices.openUrl(QtCore.QUrl(ISSUES_URL))
    _msg(_t('Tanılama bilgisi panoya kopyalandı; sorun formuna yapıştır'))
    print(text)
    return text


def _flags(value):
    """Qt bayragi -> int (PySide6 6.5+ Flag enum'larinda int() calismiyor)."""
    try:
        return int(value)
    except TypeError:
        return int(getattr(value, 'value', 0))


class KeyTestDialog(QtWidgets.QDialog):
    """Basilan tusun ham kodlarini ve Orange'in onu nasil okudugunu gosterir (macOS / Linux tablolarini
    duzeltmek icin). Acikken Orange kisayollari devre disidir."""

    def __init__(self):
        super(KeyTestDialog, self).__init__(_main_window())
        self.setObjectName('BlenderKontrolKeyTest')
        self.setWindowTitle(_t('Orange: tuş testi'))
        self.resize(560, 300)
        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(_t('Bir tuşa bas (Esc dahil her tuş yakalanır; kapatmak için pencereyi kapat). '
                                   'Çalışmayan bir tuşu bildirirken son satırı kopyala.'))
        info.setWordWrap(True)
        layout.addWidget(info)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.log)
        buttons = QtWidgets.QHBoxLayout()
        copy = QtWidgets.QPushButton(_t('Kopyala'))
        copy.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        copy.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(self.log.toPlainText()))
        close = QtWidgets.QPushButton(_t('Kapat'))
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.clicked.connect(self.close)
        buttons.addStretch(1)
        buttons.addWidget(copy)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.lines = []
        _state['capturing'] = True

    @staticmethod
    def describe(ev):
        phys, numpad = _phys(ev)
        name = _key_name(ev)
        return ('Qt=0x%X text=%r scan=0x%X vkey=0x%X mods=0x%X keypad=%s -> phys=%s name=%s combo=%s [%s]' % (
            int(ev.key()), ev.text(), ev.nativeScanCode(), ev.nativeVirtualKey(), _flags(ev.modifiers()),
            numpad, phys, name, _combo(ev, name) if name else None, PLATFORM))

    def keyPressEvent(self, ev):
        if ev.isAutoRepeat():
            return
        line = self.describe(ev)
        self.lines.append(line)
        self.log.appendPlainText(line)

    def event(self, ev):
        # Tab / Shift+Tab odak gezintisine gitmesin, Esc pencereyi kapatmasin: hepsi yakalanir
        if ev.type() == QtCore.QEvent.Type.KeyPress:
            self.keyPressEvent(ev)
            return True
        if ev.type() == QtCore.QEvent.Type.ShortcutOverride:
            ev.accept()
            return True
        return super(KeyTestDialog, self).event(ev)

    def closeEvent(self, ev):
        _state['capturing'] = False
        super(KeyTestDialog, self).closeEvent(ev)


def show_key_test():
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.objectName() == 'BlenderKontrolKeyTest':
            w.close()
            w.deleteLater()
    dlg = KeyTestDialog()
    dlg.show()
    dlg.activateWindow()
    return dlg
