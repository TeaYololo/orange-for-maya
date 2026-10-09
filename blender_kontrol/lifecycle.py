# -*- coding: utf-8 -*-
"""Kurulum, kaldirma, yeniden yukleme ve Blender menusu."""
from __future__ import absolute_import, division, print_function

import functools
import sys

import maya.cmds as cmds

from .compat import QtCore, QtWidgets
from .core import _JOB_KEY, _KEY, _filter, _msg, _warn
from .settings import set_setting, setting
from .i18n import _t
from .ui import _hint_bar, shutdown_overlay
from .mayaprefs import _apply_camera_settings, _restore_maya_defaults, _save_maya_defaults
from .cursor import CURSOR, _deselect_cursor, _style_cursor
from .pivot import set_snap_target
from .modal import _abort_modal, _on_app_state
from .helptext import show_help
from .settings_ui import show_settings
from .diagnostics import report_issue, show_key_test
from . import cheatsheet, hotkeys, interop, modifiers
from .events import BlenderFilter


def _kill_old_cursor_job():
    """Bu modulun kurdugu scriptJob'lari temizle (eski surumun tek is numarasi ya da liste)."""
    jobs = getattr(sys.modules['__main__'], _JOB_KEY, None)
    if jobs is None:
        return
    for job in (jobs if isinstance(jobs, (list, tuple)) else [jobs]):
        try:
            cmds.scriptJob(kill=job, force=True)
        except Exception:
            pass
    delattr(sys.modules['__main__'], _JOB_KEY)


def is_installed():
    return _filter() is not None


def install(quiet=False):
    uninstall(quiet=True)
    app = QtWidgets.QApplication.instance()
    filt = BlenderFilter(app)
    app.installEventFilter(filt)
    setattr(sys.modules['__main__'], _KEY, filt)
    _save_maya_defaults()
    try:
        cmds.selectPref(trackSelectionOrder=True)
    except Exception:
        pass
    _kill_old_cursor_job()
    jobs = []
    for event in ('PreFileNewOrOpened', 'SceneOpened', 'NewSceneOpened'):
        try:
            jobs.append(cmds.scriptJob(event=[event, _abort_modal]))
        except Exception:
            pass   # bu Maya surumunde olmayan olay
    try:
        jobs.append(cmds.scriptJob(event=['SelectionChanged', _deselect_cursor]))
    except Exception:
        pass
    setattr(sys.modules['__main__'], _JOB_KEY, jobs)
    try:
        app.applicationStateChanged.connect(_on_app_state)
    except Exception:
        pass
    if cmds.objExists(CURSOR):
        _style_cursor(CURSOR)
    _apply_camera_settings()
    try:
        hotkeys.register()
    except Exception as exc:
        _warn('Hotkey Editor: %s' % exc)
    _build_menu()
    # Maya acilista ve sonra (yeni paneller acilinca) kendi uygulama filtrelerini kuruyor; en son kurulan filtre
    # once cagrildigi icin bazi tuslari (Tab; Maya kisayolu olan Ctrl+R gibi) bizden once yutabiliyor.
    # Filtremiz duzenli olarak en uste alinir (maliyeti yok); arada kacan olursa _check_pending kendini onarir.
    for delay in (500, 3000):
        QtCore.QTimer.singleShot(delay, functools.partial(_raise_filter, filt))
    filt.keep_on_top = QtCore.QTimer(filt)
    filt.keep_on_top.timeout.connect(functools.partial(_raise_filter, filt))
    filt.keep_on_top.start(RAISE_INTERVAL_MS)
    if not quiet:
        _msg(_t('Orange AÇIK: Blender tuşları etkin  -  F1: kısayol listesi'))


RAISE_INTERVAL_MS = 3000


def _raise_filter(filt):
    if _filter() is filt:
        try:
            filt.raise_to_top()
        except RuntimeError:
            pass   # Qt nesnesi silinmis (yeniden yukleme)


def uninstall(quiet=False):
    filt = _filter()
    if filt is None:
        return
    app = QtWidgets.QApplication.instance()
    timer = getattr(filt, 'keep_on_top', None)
    if timer is not None:
        timer.stop()
    app.removeEventFilter(filt)
    try:
        app.applicationStateChanged.disconnect(_on_app_state)
    except Exception:
        pass
    if filt.modal:
        filt.modal.finish(False)
    filt.deleteLater()
    delattr(sys.modules['__main__'], _KEY)
    _kill_old_cursor_job()
    for w in _hint_bar:
        try:
            w.hide()
        except Exception:
            pass
    try:
        shutdown_overlay()
    except Exception as exc:
        _warn('overlay: %s' % exc)
    _restore_maya_defaults()
    _build_menu()
    if not quiet:
        _msg(_t('Orange KAPALI (Maya varsayılanı)'))


def reload_module():
    """Diskteki son surumu yukle (tum alt moduller dahil). Menu callback'inden evalDeferred ile
    cagrilir (menuyu kendi callback'i icinde silmek Maya'yi cokertebilir).

    Once kaldirilir (olay filtresi, scriptJob'lar, pencereler), sonra paketin butun modulleri
    sys.modules'tan silinip bastan import edilir: alt modullerin birbirine verdigi eski adlar kalmaz."""
    import importlib
    uninstall(quiet=True)
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.objectName().startswith('BlenderKontrol'):
            w.close()
            w.deleteLater()
    package = __name__.rpartition('.')[0]
    for name in [n for n in list(sys.modules) if n == package or n.startswith(package + '.')]:
        del sys.modules[name]
    importlib.import_module(package).install()


def remove_orange(confirm=True):
    """Orange menusu > Kaldir: modulu, .mod dosyasini, raf dugmesini ve eski kopyalari sil (ayarlar kalir)."""
    if confirm:
        yes, no = _t('Kaldır'), _t('Vazgeç')
        answer = cmds.confirmDialog(
            title='Orange', button=[yes, no], defaultButton=no, cancelButton=no, dismissString=no,
            message=_t('Orange kapatılıp kaldırılsın mı? (modül klasörü, .mod dosyası ve raf düğmesi silinir; '
                       'ayarların ve kısayolların kalır)'))
        if answer != yes:
            return None
    from . import installer   # dongusel import: cagri aninda (bagimsiz modul)
    return installer.uninstall()


def _toggle(*_):
    cmds.evalDeferred(uninstall if is_installed() else install)


def _build_menu():
    from . import __version__  # dongusel import: cagri aninda
    name = 'BlenderKontrolMenu'
    if cmds.about(batch=True):
        return
    if cmds.menu(name, exists=True):
        cmds.deleteUI(name)
    menu = cmds.menu(name, label='Orange', parent='MayaWindow', tearOff=True)
    cmds.menuItem(label=_t('Orange açık (Blender tuşları)'), checkBox=is_installed(), command=_toggle, parent=menu)
    cmds.menuItem(label=_t('Kısayol listesi  (F1)'), command=lambda *_: show_help(), parent=menu)
    cmds.menuItem(label=_t('Ayarlar ve kısayollar...  (Ctrl+,)'), command=lambda *_: show_settings(), parent=menu)
    cmds.menuItem(label=_t('Kısayol kartı (yazdırılabilir)'), command=lambda *_: cheatsheet.export(), parent=menu)
    cmds.menuItem(label=_t('Modifier paneli...'), command=lambda *_: modifiers.show_panel(), parent=menu)
    cmds.menuItem(label=_t('Blender için FBX dışa aktar...'), command=lambda *_: interop.export_for_blender(), parent=menu)
    cmds.menuItem(label=_t('Blender FBX içe aktar...'), command=lambda *_: interop.import_from_blender(), parent=menu)
    cmds.menuItem(divider=True, dividerLabel=_t('Ayarlar'), parent=menu)
    cmds.menuItem(label=_t('Emulate Numpad (üst sıradaki rakamlar = numpad)'), parent=menu,
                  checkBox=bool(setting('emulate_numpad')),
                  command=lambda on: set_setting('emulate_numpad', on))
    cmds.menuItem(label=_t('Emulate 3 Button Mouse (Alt + sol tık = orta tuş)'), parent=menu,
                  checkBox=bool(setting('emulate_3button')),
                  command=lambda on: set_setting('emulate_3button', on))
    space = cmds.menuItem(label=_t('Space tuşu'), subMenu=True, parent=menu)
    cmds.radioMenuItemCollection(parent=space)
    for value, label in (('play', 'Oynat / durdur (Blender)'), ('search', 'Arama (F3 gibi)'),
                         ('hotbox', 'Maya hotbox')):
        cmds.menuItem(label=_t(label), radioButton=setting('space_action') == value, parent=space,
                      command=functools.partial(lambda v, *_: set_setting('space_action', v), value))
    cmds.menuItem(label=_t('Zoom to Mouse Position (tekerlek fareye doğru)'), parent=menu,
                  checkBox=bool(setting('zoom_to_mouse')),
                  command=lambda on: set_setting('zoom_to_mouse', on))
    cmds.menuItem(label=_t('Orbit Around Selection (seçimin etrafında dön)'), parent=menu,
                  checkBox=bool(setting('orbit_selection')),
                  command=lambda on: set_setting('orbit_selection', on))
    snap = cmds.menuItem(label=_t('Snap hedefi (Shift+Tab açar / kapar)'), subMenu=True, parent=menu)
    cmds.radioMenuItemCollection(parent=snap)
    for value, label in (('increment', 'Artım (grid adımı)'), ('vertex', 'Köşe'), ('edge', 'Kenar'),
                         ('face', 'Yüz')):
        cmds.menuItem(label=_t(label), radioButton=setting('snap_target') == value, parent=snap,
                      command=functools.partial(lambda v, *_: set_snap_target(v), value))
    cmds.menuItem(divider=True, dividerLabel=_t('Yardım'), parent=menu)
    cmds.menuItem(label=_t('Tuş testi (çalışmayan tuşu bildirmek için)...'), parent=menu,
                  command=lambda *_: show_key_test())
    cmds.menuItem(label=_t('Sorun bildir (tanılama bilgisini kopyalar)...'), parent=menu,
                  command=lambda *_: report_issue())
    cmds.menuItem(divider=True, parent=menu)
    cmds.menuItem(label=_t('Yeniden yükle (güncelleme sonrası)'), parent=menu,
                  command=lambda *_: cmds.evalDeferred(reload_module))
    cmds.menuItem(label=_t("Orange'ı kaldır..."), parent=menu, command=lambda *_: cmds.evalDeferred(remove_orange))
    cmds.menuItem(label=_t('Orange v%s  ·  Maya, Blender gibi') % __version__, enable=False, parent=menu)
