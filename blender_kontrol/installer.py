# -*- coding: utf-8 -*-
"""Orange kurulumu: Maya modulu (.mod) olarak kur / kaldir.

Bu dosya kendi basina calisir (paketin diger modullerini import etmez): drag_drop_install.py onu dosya
yolundan yukler, boylece Maya'da eski bir surum yukluyken de dogru (yeni) kurulum kodu calisir.

Kurulum duzeni (Maya 2022+ MAYA_MODULE_PATH varsayilan olarak Documents/maya/modules'u tarar):

    Documents/maya/modules/orange.mod           + Orange <surum> <yol>
    Documents/maya/modules/orange/scripts/blender_kontrol/   paket
    Documents/maya/modules/orange/scripts/userSetup.py       otomatik baslatma (Maya sys.path'teki
                                                             tum userSetup.py dosyalarini calistirir)
    Documents/maya/modules/orange/icons/orange.png           raf ikonu

Kullanicinin kendi userSetup.py dosyasina dokunulmaz. 0.6 ve oncesinin scripts klasorune kopyalanan paketi
ve userSetup.py'ye eklenen isaretli blok yukseltmede temizlenir.
"""
from __future__ import absolute_import, print_function

import io
import os
import re
import shutil
import sys

PACKAGE = 'blender_kontrol'
PRODUCT = 'Orange'
MODULE_NAME = 'Orange'
MODULE_DIR = 'orange'
MOD_FILE = 'orange.mod'
SHELF_LABEL = 'Orange'
LEGACY_SHELF_LABELS = ('BlenderForMaya',)
SHELF_COMMAND = ('import blender_kontrol as bk\n'
                 'bk.uninstall() if bk.is_installed() else bk.install()')
MARK_BEGIN = '# >>> Blender for Maya (auto start) >>>'
MARK_END = '# <<< Blender for Maya (auto start) <<<'
MODULE_USERSETUP = u'''# Orange (Maya, the Blender way): Maya acilinca otomatik baslat.
# Bu dosya Orange modulunun parcasidir; kaldirmak icin Orange menusu > Kaldir.
import maya.utils


def _orange_startup():
    try:
        import blender_kontrol
        blender_kontrol.install()
    except Exception as exc:
        print("[Orange] could not start: %s" % exc)


maya.utils.executeDeferred(_orange_startup)
'''
# 0.4 - 0.6 surumlerinin userSetup.py'ye ekledigi blok (yalniz eski testler / elle kurulum icin)
USERSETUP_BLOCK = MARK_BEGIN + u'''
import maya.utils


def _blender_for_maya_startup():
    try:
        import blender_kontrol
        blender_kontrol.install()
    except Exception as exc:
        print("[Blender for Maya] could not start: %s" % exc)


maya.utils.executeDeferred(_blender_for_maya_startup)
''' + MARK_END + u'\n'


def _cmds():
    import maya.cmds as cmds
    return cmds


def _norm(path):
    return os.path.abspath(path).replace('\\', '/')


def source_version(source_dir):
    """Kaynak paketteki __version__ (import etmeden)."""
    text = io.open(os.path.join(source_dir, PACKAGE, '__init__.py'), encoding='utf-8').read()
    m = re.search(r"^__version__\s*=\s*'([^']+)'", text, re.M)
    return m.group(1) if m else '0.0.0'


def maya_app_dir():
    return _cmds().internalVar(userAppDir=True)


def default_modules_dir():
    return os.path.join(maya_app_dir(), 'modules')


def legacy_script_dirs():
    """0.6 ve oncesinin kopyalandigi yerler: surume ozel ve surumden bagimsiz scripts klasorleri."""
    cmds = _cmds()
    dirs = [cmds.internalVar(userScriptDir=True), os.path.join(maya_app_dir(), 'scripts')]
    out = []
    for d in dirs:
        d = _norm(d)
        if d not in out:
            out.append(d)
    return out


# ---------------------------------------------------------------- modul
def copy_package(source_dir, target_dir):
    """Paketi target_dir/blender_kontrol'e kopyala (eski kopya ve tek dosyali eski surum silinir)."""
    src = os.path.join(source_dir, PACKAGE)
    if not os.path.isdir(src):
        raise RuntimeError('%s klasoru bulunamadi / not found: %s' % (PACKAGE, src))
    if not os.path.isdir(target_dir):
        os.makedirs(target_dir)
    for old in (PACKAGE + '.py', PACKAGE + '.pyc'):
        path = os.path.join(target_dir, old)
        if os.path.exists(path):
            os.remove(path)
    dst = os.path.join(target_dir, PACKAGE)
    if _norm(dst) == _norm(src):
        return dst
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return dst


def build_module(source_dir, module_root):
    """Modul klasorunu kur: scripts/ (paket + userSetup.py) ve icons/."""
    scripts = os.path.join(module_root, 'scripts')
    copy_package(source_dir, scripts)
    with io.open(os.path.join(scripts, 'userSetup.py'), 'w', encoding='utf-8') as fh:
        fh.write(MODULE_USERSETUP)
    icons_src = os.path.join(source_dir, 'icons')
    icons_dst = os.path.join(module_root, 'icons')
    if os.path.isdir(icons_src):
        if os.path.isdir(icons_dst):
            shutil.rmtree(icons_dst)
        shutil.copytree(icons_src, icons_dst)
    return scripts


def mod_file_text(module_root, version):
    return u'+ %s %s %s\n' % (MODULE_NAME, version, _norm(module_root))


def write_mod_file(modules_dir, module_root, version):
    if not os.path.isdir(modules_dir):
        os.makedirs(modules_dir)
    path = os.path.join(modules_dir, MOD_FILE)
    with io.open(path, 'w', encoding='utf-8') as fh:
        fh.write(mod_file_text(module_root, version))
    return path


# ---------------------------------------------------------------- eski kurulum (0.6 ve oncesi)
def add_to_usersetup(target_dir):
    """Eski yontem: userSetup.py'ye otomatik baslatma blogunu bir kez ekle. Donus: True = eklendi."""
    path = os.path.join(target_dir, 'userSetup.py')
    content = u''
    if os.path.exists(path):
        with io.open(path, encoding='utf-8') as fh:
            content = fh.read()
    if MARK_BEGIN in content or 'blender_kontrol.install' in content:
        return False
    if content and not content.endswith('\n'):
        content += '\n'
    with io.open(path, 'w', encoding='utf-8') as fh:
        fh.write(content + ('\n' if content else '') + USERSETUP_BLOCK)
    return True


def remove_from_usersetup(target_dir):
    """userSetup.py'den isaretli eski blogu kaldir (kullanicinin kendi satirlari kalir)."""
    path = os.path.join(target_dir, 'userSetup.py')
    if not os.path.exists(path):
        return False
    with io.open(path, encoding='utf-8') as fh:
        content = fh.read()
    if MARK_BEGIN not in content:
        return False
    start = content.index(MARK_BEGIN)
    end = content.index(MARK_END, start) + len(MARK_END)
    content = (content[:start].rstrip('\n') + '\n' + content[end:].lstrip('\n')).strip('\n')
    with io.open(path, 'w', encoding='utf-8') as fh:
        fh.write(content + '\n' if content else u'')
    return True


def remove_legacy(script_dirs):
    """Eski scripts klasoru kopyasini ve userSetup blogunu kaldir. Donus: kaldirilanlarin listesi."""
    removed = []
    for d in script_dirs:
        pkg = os.path.join(d, PACKAGE)
        if os.path.isdir(pkg):
            shutil.rmtree(pkg, ignore_errors=True)
            removed.append(pkg)
        for old in (PACKAGE + '.py', PACKAGE + '.pyc'):
            path = os.path.join(d, old)
            if os.path.exists(path):
                os.remove(path)
                removed.append(path)
        if remove_from_usersetup(d):
            removed.append(os.path.join(d, 'userSetup.py') + ' (block)')
    return removed


# ---------------------------------------------------------------- raf
def _current_shelf():
    import maya.mel as mel
    top = mel.eval('global string $gShelfTopLevel; $gShelfTopLevel = $gShelfTopLevel;')
    return top + '|' + _cmds().tabLayout(top, q=True, selectTab=True), top


def shelf_buttons(labels):
    """[(raf_dugmesi, etiket)] tum raflarda."""
    cmds = _cmds()
    out = []
    try:
        _shelf, top = _current_shelf()
    except Exception:
        return out
    for shelf in cmds.tabLayout(top, q=True, childArray=True) or []:
        for child in cmds.shelfLayout(top + '|' + shelf, q=True, childArray=True) or []:
            try:
                label = cmds.shelfButton(child, q=True, label=True)
            except RuntimeError:
                continue
            if label in labels:
                out.append((child, label))
    return out


def add_shelf_button(shelf=None, icon=None):
    """Secili rafa ac/kapa dugmesi ekle (varsa ekleme); eski 'BL' dugmesini kaldir. Donus: dugme adi."""
    cmds = _cmds()
    if cmds.about(batch=True):
        return None
    for button, label in shelf_buttons(LEGACY_SHELF_LABELS):
        cmds.deleteUI(button)
    existing = shelf_buttons((SHELF_LABEL,))
    if existing:
        return existing[0][0]
    if shelf is None:
        shelf = _current_shelf()[0]
    kwargs = dict(parent=shelf, label=SHELF_LABEL, annotation='Orange: Maya, the Blender way (on / off)',
                  sourceType='python', command=SHELF_COMMAND)
    if icon and os.path.exists(icon):
        kwargs['image'] = _norm(icon)
    else:
        kwargs.update(image='pythonFamily.png', imageOverlayLabel='OR')
    return cmds.shelfButton(**kwargs)


def remove_shelf_buttons():
    cmds = _cmds()
    for button, _label in shelf_buttons((SHELF_LABEL,) + LEGACY_SHELF_LABELS):
        cmds.deleteUI(button)


# ---------------------------------------------------------------- calistir
def _purge_package():
    old = sys.modules.get(PACKAGE)
    if old is not None:
        try:
            old.uninstall(quiet=True)
        except Exception:
            pass
    for name in [n for n in list(sys.modules) if n == PACKAGE or n.startswith(PACKAGE + '.')]:
        del sys.modules[name]


def start(scripts_dir):
    """Kurulan paketi bu oturumda yukle ve ac (modul yolu Maya yeniden acilinca kendiliginden eklenir)."""
    _purge_package()
    scripts_dir = _norm(scripts_dir)
    for p in list(sys.path):
        if _norm(p) == scripts_dir:
            sys.path.remove(p)
    sys.path.insert(0, scripts_dir)
    import blender_kontrol
    blender_kontrol.install()
    return blender_kontrol


def install(source_dir, modules_dir=None, shelf=True, start_now=True, clean_legacy=True):
    """source_dir: blender_kontrol klasorunu iceren klasor (depo / indirilen zip)."""
    modules_dir = modules_dir or default_modules_dir()
    module_root = os.path.join(modules_dir, MODULE_DIR)
    version = source_version(source_dir)
    scripts = build_module(source_dir, module_root)
    mod = write_mod_file(modules_dir, module_root, version)
    removed = remove_legacy(legacy_script_dirs()) if clean_legacy else []
    button = add_shelf_button(icon=os.path.join(module_root, 'icons', 'orange.png')) if shelf else None
    module = start(scripts) if start_now else None
    message = '%s %s -> %s' % (PRODUCT, version, _norm(module_root))
    if removed:
        message += '  |  removed old copy: %d' % len(removed)
    if button:
        message += '  |  shelf'
    print('[Orange] ' + message + '  |  ' + _norm(mod))
    try:
        _cmds().inViewMessage(assistMessage='Orange %s OK  -  F1: shortcuts' % version, position='topCenter',
                              fade=True, fadeStayTime=2500)
    except Exception:
        pass
    return {'module_root': module_root, 'mod_file': mod, 'removed': removed, 'button': button,
            'module': module, 'version': version}


def remove_runtime_commands():
    """Orange'in Hotkey Editor komutlarini (kategori 'Orange', ad 'Orange_...') sil."""
    cmds = _cmds()
    removed = 0
    for name in cmds.runTimeCommand(q=True, commandArray=True) or []:
        if not name.startswith('Orange_'):
            continue
        try:
            if cmds.runTimeCommand(name, q=True, category=True) == 'Orange':
                cmds.runTimeCommand(name, edit=True, delete=True)
                removed += 1
        except Exception:
            pass
    return removed


def uninstall(modules_dir=None, shelf=True, clean_legacy=True):
    """Orange'i kapat ve kaldir: modul klasoru, .mod dosyasi, raf dugmesi, eski kopyalar.
    Kullanici ayarlari (optionVar) ve kisayol dosyasi kalir."""
    _purge_package()
    modules_dir = modules_dir or default_modules_dir()
    module_root = os.path.join(modules_dir, MODULE_DIR)
    removed = []
    if os.path.isdir(module_root):
        shutil.rmtree(module_root, ignore_errors=True)
        removed.append(module_root)
    mod = os.path.join(modules_dir, MOD_FILE)
    if os.path.exists(mod):
        os.remove(mod)
        removed.append(mod)
    if clean_legacy:
        removed += remove_legacy(legacy_script_dirs())
    if shelf:
        try:
            remove_shelf_buttons()
        except Exception:
            pass
    try:
        n = remove_runtime_commands()
        if n:
            removed.append('%d Hotkey Editor commands' % n)
    except Exception:
        pass
    try:
        cmds = _cmds()
        if cmds.menu('BlenderKontrolMenu', exists=True):
            cmds.deleteUI('BlenderKontrolMenu')
    except Exception:
        pass
    scripts = _norm(os.path.join(module_root, 'scripts'))
    for p in list(sys.path):
        if _norm(p) == scripts:
            sys.path.remove(p)
    print('[Orange] removed: %s' % ', '.join(_norm(r) for r in removed))
    return removed
