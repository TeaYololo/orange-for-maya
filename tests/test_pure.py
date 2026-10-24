# -*- coding: utf-8 -*-
"""Maya'siz calisan testler (CI): `python -m pytest tests` (PySide6 gerekir)."""
import ast
import io
import json
import os
import re
import shutil
import sys

import pytest

import blender_kontrol as bk
from blender_kontrol import keys, keymap, picking, util, i18n, modes

try:
    from PySide6 import QtCore, QtGui
except ImportError:  # pragma: no cover
    from PySide2 import QtCore, QtGui

Qt = QtCore.Qt
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(REPO, 'blender_kontrol')
NO = Qt.KeyboardModifier.NoModifier
KP = Qt.KeyboardModifier.KeypadModifier
ORDER = [m.__name__.rpartition('.')[2] for m in bk.MODULES]


def _sources():
    for f in sorted(os.listdir(PKG)):
        if f.endswith('.py') and f != 'i18n_en.py':
            yield f, io.open(os.path.join(PKG, f), encoding='utf-8').read()


# ---------------------------------------------------------------- mimari
def test_corner_fill_plan():
    """F tek kose (#5): delik halkasi 0..n-1; secili kose 0, komsular 1 ve n-1."""
    from blender_kontrol import mesh

    def ring(n, pos=None):
        def step(prev, cur):
            for nxt in ((cur + 1) % n, (cur - 1) % n):
                if nxt != prev:
                    return nxt
        pos = pos or {i: (i, 0) for i in range(n)}

        def dist(p, q):
            return ((pos[p][0] - pos[q][0]) ** 2 + (pos[p][1] - pos[q][1]) ** 2) ** 0.5
        return step, dist

    step, dist = ring(3)
    assert mesh.corner_fill_plan(0, 1, 2, step, dist) == ([2, 0, 1], None)
    step, dist = ring(4)
    assert mesh.corner_fill_plan(0, 1, 3, step, dist) == ([3, 0, 1, 2], None)
    # 2 x 1 merdiven delik: ust 0-1-2, alt 5-4-3; kose 0, a = 1 (ust), b = 5 (alt)
    pos = {0: (0, 1), 1: (1, 1), 2: (2, 1), 3: (2, 0), 4: (1, 0), 5: (0, 0)}
    step, dist = ring(6, pos)
    cycle, nxt = mesh.corner_fill_plan(0, 1, 5, step, dist)
    assert cycle == [4, 5, 0, 1] and nxt == 1          # kisa basamak (1-4), kalan delik dortgen
    # komsular tersine verilse de ayni basamak
    cycle, nxt = mesh.corner_fill_plan(0, 5, 1, step, dist)
    assert sorted(cycle) == [0, 1, 4, 5]
    assert mesh.corner_fill_plan(0, 1, 5, lambda p, c: None, dist) is None


def test_edge_chain():
    from blender_kontrol import mesh
    assert mesh.edge_chain([(1, 2), (2, 3)]) in (([1, 2, 3], False), ([3, 2, 1], False))
    order, closed = mesh.edge_chain([(1, 2), (2, 3), (3, 1)])
    assert closed and sorted(order) == [1, 2, 3]
    assert mesh.edge_chain([(1, 2), (3, 4)]) is None              # iki parca: kopru
    assert mesh.edge_chain([(1, 2), (1, 3), (1, 4)]) is None      # dallanma


def test_version_and_product():
    assert re.match(r'^\d+\.\d+\.\d+$', bk.__version__)
    assert bk.PRODUCT == 'Orange'


@pytest.mark.parametrize('name', ORDER)
def test_layering(name):
    """Alt katman, ust katmani modul basinda import etmez (dongu yok). Fonksiyon icindekiler serbest."""
    tree = ast.parse(io.open(os.path.join(PKG, name + '.py'), encoding='utf-8').read())
    mine = ORDER.index(name)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            other = node.module.split('.')[0]
            if other == 'i18n_en':
                continue
            assert other in ORDER, other
            assert ORDER.index(other) < mine, '%s modul basinda ust katman %s import ediyor' % (name, other)


def test_package_reexports_legacy_names():
    for name in ('install', 'uninstall', 'Modal', 'BINDINGS', 'Picker', 'PieMenu', '_key_name', 'setting'):
        assert hasattr(bk, name), name


# ---------------------------------------------------------------- tuslar
KEY_CASES = [
    ('win', Qt.Key.Key_G, NO, 0x22, 0, 'g', 'g'), ('win', Qt.Key.Key_unknown, NO, 0x17, 0, u'ı', 'i'),
    ('win', Qt.Key.Key_7, KP, 0x47, 0, '7', 'np7'), ('win', Qt.Key.Key_Slash, KP, 0x135, 0, '/', 'np/'),
    ('win', Qt.Key.Key_Comma, NO, 0x33, 0, ',', 'comma'), ('win', Qt.Key.Key_PageUp, NO, 0x149, 0, '', 'pgup'),
    ('win', Qt.Key.Key_Tab, NO, 0x0F, 0, '\t', 'tab'),
    ('linux', Qt.Key.Key_G, NO, 42, 0, 'g', 'g'), ('linux', Qt.Key.Key_1, KP, 87, 0, '1', 'np1'),
    ('linux', Qt.Key.Key_Slash, KP, 106, 0, '/', 'np/'), ('linux', Qt.Key.Key_QuoteLeft, NO, 49, 0, '`', 'grave'),
    ('mac', Qt.Key.Key_G, NO, 0, 0x05, 'g', 'g'), ('mac', Qt.Key.Key_A, NO, 0, 0, 'a', 'a'),
    ('mac', Qt.Key.Key_unknown, NO, 0, 0, '', None), ('mac', Qt.Key.Key_unknown, NO, 0, 0x22, u'ı', 'i'),
    ('mac', Qt.Key.Key_7, KP, 0, 0x59, '7', 'np7'), ('mac', Qt.Key.Key_Period, KP, 0, 0x41, '.', 'np.'),
]


@pytest.mark.parametrize('plat,key,mods,sc,vk,text,want', KEY_CASES)
def test_physical_key(plat, key, mods, sc, vk, text, want):
    ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, key, mods, sc, vk, 0, text)
    assert keys._key_name(ev, plat) == want


def test_combo_and_labels():
    ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_C,
                         Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier |
                         Qt.KeyboardModifier.ShiftModifier, 0x2E, 0, 0, 'C')
    assert keys._combo(ev, keys._key_name(ev, 'win')) == 'ctrl+alt+shift+c'
    assert keys._combo_label('ctrl+alt+shift+np7') == 'Ctrl+Alt+Shift+Numpad 7'
    assert [keys._combo_label(x) for x in ('grave', 'comma', 'ctrl+pgup')] == ['`', ',', 'Ctrl+PageUp']


def test_scan_tables_are_consistent():
    assert len(set(keys.SCAN.values())) == len(keys.SCAN)
    assert set(keys.NUMPAD_SCAN.values()) <= set(keys.MAC_NUMPAD.values()) | {'/'}
    assert set(keys.MAC_VK.values()) == set(keys.SCAN.values())


# ---------------------------------------------------------------- kisayol tablosu
def _known_key(part):
    return (part in keys.SCAN.values() or part in keys.SPECIAL_KEYS or part in ('tab', 'grave', 'comma', 'period')
            or (part.startswith('np') and part[2:] in keys.NUMPAD_SCAN.values()) or re.match(r'^f\d+$', part))


def test_binding_combos_are_well_formed():
    tables = [keymap.BINDINGS, keymap.SCULPT_KEYMAP] + list(keymap.CONTEXT_KEYMAPS.values())
    for table in tables:
        for combo, binding in table.items():
            parts = combo.split('+')
            if combo.endswith('np+'):
                parts = parts[:-2] + ['np+']
            mods, key = parts[:-1], parts[-1]
            assert all(m in ('ctrl', 'alt', 'shift') for m in mods), combo
            assert mods == [m for m in ('ctrl', 'alt', 'shift') if m in mods], 'modifier sirasi: ' + combo
            assert _known_key(key), combo
            assert callable(binding['fn']), combo
            assert binding['ctx'], combo


def test_bindings_have_unique_ids_and_titles():
    for combo, binding in keymap.BINDINGS.items():
        assert binding['id'] == combo
        assert binding['title'], 'F3 basligi eksik: ' + combo


def test_sculpt_global_keys_exist():
    assert [c for c in modes.SCULPT_GLOBAL if c not in keymap.BINDINGS] == []


def test_user_overrides_roundtrip():
    keymap._save_overrides({'g': 'alt+shift+g', 'r': ''})
    try:
        act = keymap._rebuild_keymap()
        assert act.get('alt+shift+g') is keymap.BINDINGS['g']
        assert 'g' not in act and 'r' not in act
        assert keymap._combo_for('r') == ''
    finally:
        keymap._save_overrides({})
        keymap._rebuild_keymap()
    assert keymap._active_bindings().get('g') is keymap.BINDINGS['g']


# ---------------------------------------------------------------- ceviri
TURKISH = re.compile(u'[çğıöşüÇĞİÖŞÜ]')


def test_every_turkish_ui_string_is_translated():
    missing = set()
    for _f, src in _sources():
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_t':
                for c in ast.walk(node):
                    if isinstance(c, ast.Constant) and isinstance(c.value, str) and TURKISH.search(c.value) \
                            and c.value not in i18n.EN:
                        missing.add(c.value)
    assert not missing, sorted(missing)[:10]


def test_titles_translated_and_formats_match():
    titles = [b['title'] for b in keymap.BINDINGS.values()] + [t for t, _ in keymap.EXTRA_COMMANDS]
    assert [t for t in titles if t not in i18n.EN] == []
    fmt = re.compile(r'%[-0-9.]*[sdf]')
    assert [k for k, v in i18n.EN.items() if sorted(fmt.findall(k)) != sorted(fmt.findall(v))] == []
    assert bk.HELP.count('<tr>') == i18n.HELP_EN.count('<tr>')


# ---------------------------------------------------------------- algoritmalar
def test_expression_parser():
    P = bk.Modal._parse
    cases = {'2*3': 6.0, '-1.5': -1.5, '2m': 200.0, '10cm': 10.0, '25mm': 2.5, '90d': 90.0, '1in': 2.54,
             'pi/2': 3.141592653589793 / 2, 'sqrt(4)': 2.0, '2mm+1cm': 1.2, '1,5': 1.5}
    for expr, want in cases.items():
        assert P(expr) == pytest.approx(want), expr
    for evil in ('__import__("os")', 'abc', '().__class__', 'open("x")'):
        assert P(evil) is None, evil


def test_ranges_and_hops():
    assert util._ranges('o', 'face', [3, 4, 5, 9, 1]) == ['o.f[1]', 'o.f[3:5]', 'o.f[9]']
    hops = picking._hops(0, lambda n: [m for m in (n - 1, n + 1) if 0 <= m < 10])
    assert hops[9] == 9 and len(hops) == 10


def test_segment_distance():
    d, t = picking._seg_dist(5, 5, (0, 0), (10, 0))
    assert d == pytest.approx(5) and t == pytest.approx(0.5)
    d, t = picking._seg_dist(-3, 4, (0, 0), (10, 0))
    assert d == pytest.approx(5) and t == 0.0


class _P(object):
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


class _Box(object):
    def __init__(self, lo, hi):
        self.min, self.max = _P(*lo), _P(*hi)


def test_ray_box():
    box = _Box((-1, -1, -1), (1, 1, 1))
    assert picking._ray_hits_box(_P(0, 0, 10), _P(0, 0, -1), box)
    assert not picking._ray_hits_box(_P(5, 0, 10), _P(0, 0, -1), box)
    assert not picking._ray_hits_box(_P(0, 0, 10), _P(0, 0, 1), box)


def test_dijkstra():
    # 0-1-2 zincir + 0-2 uzun kenar
    adj = {0: [(1, 'a', 1.0), (2, 'c', 5.0)], 1: [(0, 'a', 1.0), (2, 'b', 1.0)], 2: [(1, 'b', 1.0), (0, 'c', 5.0)]}
    path, links = picking.MeshGraph._dijkstra([0], [2], lambda n: adj[n])
    assert path == [0, 1, 2] and links == ['a', 'b']


def test_flag_conversion_and_key_test_line():
    from blender_kontrol import diagnostics
    mods = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
    assert diagnostics._flags(mods) == 0x06000000
    ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_G, mods, 0x22, 0x47, 0, 'G')
    line = diagnostics.KeyTestDialog.describe(ev)
    assert 'scan=0x22' in line and 'combo=ctrl+shift+g' in line


def test_hotkey_editor_command_names():
    from blender_kontrol import hotkeys
    names = hotkeys.command_names()
    assert len(names) == len([b for b in keymap.BINDINGS.values() if b.get('title')])
    assert len(set(names.values())) == len(names)
    for name in names.values():
        assert re.match(r'^Orange_[A-Za-z0-9_]+$', name), name
    assert names['ctrl+r'] == 'Orange_LoopCut'


# ---------------------------------------------------------------- kurulum / guncelleme (Maya'siz)
def test_build_module_on_every_platform(monkeypatch, tmp_path):
    """Yerel .mll yalniz Windows'ta paketlenir; diger platformlarda kurulum TypeError ile cokmemeli."""
    from blender_kontrol import installer
    has_mll = os.path.isfile(os.path.join(PKG, 'orangeArray.mll'))
    for platform in ('darwin', 'linux', 'win32'):
        monkeypatch.setattr(sys, 'platform', platform)
        root = str(tmp_path / platform)
        installer.build_module(REPO, root)
        plugins = os.path.join(root, 'plug-ins')
        assert os.path.isfile(os.path.join(plugins, 'orangeArray.py')), platform
        assert os.path.isfile(os.path.join(plugins, 'orangeArray.mll')) == (platform == 'win32' and has_mll), platform


def test_copy_package_keeps_old_install_when_copy_fails(monkeypatch, tmp_path):
    """Kopyalama yarida kalirsa (disk, izin) eski paket yerinde kalir; sonraki deneme onu degistirir."""
    from blender_kontrol import installer
    target = str(tmp_path)
    dst = os.path.join(target, 'blender_kontrol')
    os.makedirs(dst)
    io.open(os.path.join(dst, 'marker.txt'), 'w').write(u'old')

    def boom(*_a, **_k):
        raise OSError('disk full')
    monkeypatch.setattr(shutil, 'copytree', boom)
    with pytest.raises(OSError):
        installer.copy_package(REPO, target)
    assert io.open(os.path.join(dst, 'marker.txt')).read() == 'old'
    assert not os.path.exists(dst + '.new') and not os.path.exists(dst + '.old')
    monkeypatch.undo()
    installer.copy_package(REPO, target)
    assert os.path.isfile(os.path.join(dst, '__init__.py'))
    assert not os.path.exists(os.path.join(dst, 'marker.txt'))
    assert not os.path.exists(dst + '.new') and not os.path.exists(dst + '.old')


def test_replace_file_falls_back_to_rename_when_locked(monkeypatch, tmp_path):
    """Windows'ta yuklu .mll ustune yazilamaz; eskisi .old olur, yenisi yazilir."""
    from blender_kontrol import installer
    src = tmp_path / 'new.mll'
    src.write_text(u'new')
    dst = tmp_path / 'plug-ins' / 'orangeArray.mll'
    dst.parent.mkdir()
    dst.write_text(u'old')
    real, calls = shutil.copy2, []

    def locked(s, d, *a, **k):
        calls.append(d)
        if len(calls) == 1:
            raise PermissionError('locked')
        return real(s, d, *a, **k)
    monkeypatch.setattr(shutil, 'copy2', locked)
    installer._replace_file(str(src), str(dst))
    assert dst.read_text() == 'new'
    assert (tmp_path / 'plug-ins' / 'orangeArray.mll.old').read_text() == 'old'


def test_update_version_key():
    from blender_kontrol import update
    assert update._version_key('v0.10.0') == (0, 10, 0, 1, 0)
    assert update._version_key('0.9.0') < update._version_key('0.10.0')
    assert update._version_key('abc') is None


def test_update_safe_extract_and_release_root(tmp_path):
    import zipfile
    from blender_kontrol import update
    bad = tmp_path / 'bad.zip'
    with zipfile.ZipFile(str(bad), 'w') as z:
        z.writestr('../evil.txt', 'x')
    with pytest.raises(ValueError):
        update._safe_extract(str(bad), str(tmp_path / 'out'))
    assert not (tmp_path / 'evil.txt').exists()
    good = tmp_path / 'good.zip'
    with zipfile.ZipFile(str(good), 'w') as z:
        z.writestr('Orange-1.0.0/blender_kontrol/__init__.py', "__version__ = '1.0.0'\n")
        z.writestr('Orange-1.0.0/icons/orange.png', 'png')
    out = tmp_path / 'out'
    update._safe_extract(str(good), str(out))
    assert update._find_release_root(str(out)) == os.path.join(str(out), 'Orange-1.0.0')


def _staged_update(tmp_path, version):
    """Bekleyen guncelleme duzeni: <modules>/orange/.update/stage-*/ paket + pending.json isareti."""
    modules = tmp_path / 'modules'
    update_root = modules / 'orange' / '.update'
    staging = update_root / 'stage-test'
    source = staging / ('Orange-' + version)
    (source / 'blender_kontrol').mkdir(parents=True)
    (source / 'blender_kontrol' / '__init__.py').write_text(u"__version__ = '%s'\n" % version)
    (source / 'icons').mkdir()
    (update_root / 'pending.json').write_text(json.dumps(
        {'version': version, 'staging_dir': str(staging), 'source_dir': str(source)}))
    return modules


def test_apply_pending_update_reports_install_errors(monkeypatch, tmp_path):
    """Kurulum hatasi (kilitli .mll, izin) sessizce yutulmaz: uyari verilir, isaret temizlenir."""
    import maya.cmds as cmds
    from blender_kontrol import installer, update
    modules = _staged_update(tmp_path, '99.0.0')
    monkeypatch.setattr(update, '_modules_dir', lambda: str(modules))

    def locked(*_a, **_k):
        raise PermissionError('orangeArray.mll is in use')
    monkeypatch.setattr(installer, 'install', locked)
    warnings = []
    monkeypatch.setattr(cmds, 'warning', lambda msg: warnings.append(msg))
    assert update.apply_pending_update() is False
    assert warnings and 'orangeArray.mll' in warnings[0]
    assert not (modules / 'orange' / '.update' / 'pending.json').exists()
    assert not (modules / 'orange' / '.update' / 'stage-test').exists()


def test_apply_pending_update_without_marker_is_silent(monkeypatch, tmp_path):
    import maya.cmds as cmds
    from blender_kontrol import update
    monkeypatch.setattr(update, '_modules_dir', lambda: str(tmp_path))
    warnings = []
    monkeypatch.setattr(cmds, 'warning', lambda msg: warnings.append(msg))
    assert update.apply_pending_update() is False
    assert not warnings


# ---------------------------------------------------------------- guncelleme: surum kurali, dizin duzeni, hata metinleri
def test_update_prerelease_versions_are_ordered():
    """1.0.0 > 1.0.0-rc2 > 1.0.0-rc1 > 1.0.0-beta1 > 1.0.0-alpha1 > 0.9.9; etiketler kabul edilir."""
    from blender_kontrol import update
    key = update._version_key
    assert key('1.0.0') > key('1.0.0-rc1') > key('1.0.0-beta.1') > key('1.0.0-alpha1') > key('0.9.9')
    assert key('v1.0.0-rc2') > key('1.0.0rc1')
    assert key('1.0.0+build.5') == key('1.0.0')
    assert key('1.0') is None and key('1.0.0-foo') is None
    assert update._is_prerelease('1.0.0-rc1') and not update._is_prerelease('1.0.0')
    # on surum otomatik denetimde yalniz kurulu surum de on surumse; elle denetimde her zaman
    assert update._should_offer('1.0.0', '0.9.0')
    assert not update._should_offer('1.0.0-rc1', '0.9.0')
    assert update._should_offer('1.0.0-rc1', '0.9.0', force=True)
    assert update._should_offer('1.0.0-rc2', '1.0.0-rc1')
    assert update._should_offer('1.0.0', '1.0.0-rc1')
    assert not update._should_offer('1.0.0-rc1', '1.0.0', force=True)
    assert not update._should_offer('0.9.0', '0.9.0', force=True)
    assert not update._should_offer('abc', '0.9.0', force=True)


def test_update_staging_lives_under_module_root(monkeypatch, tmp_path):
    """Hazirlik klasoru ve isaret Maya'nin taradigi modules/ icinde degil, modules/orange/.update altinda."""
    from blender_kontrol import update
    modules = str(tmp_path / 'modules')
    root = os.path.join(modules, 'orange', '.update')
    assert update._update_root(modules) == root
    assert update._pending_marker(modules) == os.path.join(root, 'pending.json')
    assert update._is_staging_dir(modules, os.path.join(root, 'stage-abc'))
    assert not update._is_staging_dir(modules, os.path.join(modules, 'stage-abc'))
    assert not update._is_staging_dir(modules, os.path.join(root, 'other'))
    assert not update._is_staging_dir(modules, '')
    # eski duzende (dogrudan modules/) bekleyen bir isaret artik gecerli sayilmaz: temizlenir, kurulmaz
    staging = tmp_path / 'modules' / '.orange-update-old'
    (staging / 'blender_kontrol').mkdir(parents=True)
    (tmp_path / 'modules' / 'orange' / '.update').mkdir(parents=True)
    (tmp_path / 'modules' / 'orange' / '.update' / 'pending.json').write_text(json.dumps(
        {'version': '99.0.0', 'staging_dir': str(staging), 'source_dir': str(staging)}))
    monkeypatch.setattr(update, '_modules_dir', lambda: modules)
    import maya.cmds as cmds
    warnings = []
    monkeypatch.setattr(cmds, 'warning', lambda msg: warnings.append(msg))
    assert update.apply_pending_update() is False
    assert warnings and not os.path.exists(update._pending_marker(modules))
    assert staging.exists()      # .update disindaki klasore dokunulmaz
    # _clear_pending yalniz kendi hazirlik klasorunu siler
    stage = tmp_path / 'modules' / 'orange' / '.update' / 'stage-x'
    stage.mkdir()
    update._clear_pending(modules, str(stage))
    assert not stage.exists()


def test_update_error_messages_are_actionable():
    """Ham Python hatasi degil, cevrilmis ve yol gosteren metin (ayrinti Script Editor'a yazilir)."""
    import socket
    import urllib.error
    from blender_kontrol import update
    bk.core._state['lang'] = 'en'
    try:
        offline = update._friendly_error(urllib.error.URLError('getaddrinfo failed'))
        assert 'internet' in offline.lower() and 'getaddrinfo' not in offline
        assert update._friendly_error(socket.timeout('timed out')) == offline
        assert update._friendly_error(ConnectionResetError(104, 'reset')) == offline
        limited = update._friendly_error(urllib.error.HTTPError('u', 403, 'rate limit', {}, None))
        assert 'rate limit' in limited.lower()
        assert 'HTTP 500' in update._friendly_error(urllib.error.HTTPError('u', 500, 'oops', {}, None))
        assert 'package' in update._friendly_error(ValueError('Unsafe path in update archive')).lower()
        disk = update._friendly_error(PermissionError(13, 'denied', 'C:/x/release.zip'))
        assert 'write' in disk.lower() and 'release.zip' in disk
    finally:
        bk.core._state['lang'] = None
    bk.core._state['lang'] = 'tr'
    try:
        assert update._friendly_error(urllib.error.URLError('x')).startswith(u'İnternet bağlantısı yok')
    finally:
        bk.core._state['lang'] = None


def test_update_check_result_is_non_blocking_at_startup(monkeypatch):
    """Acilis denetimi pencere acmaz: kisa bildirim + modul durumu (menu ogesi); elle denetim pencereyi acar."""
    import maya.cmds as cmds
    from blender_kontrol import update
    release = {'version': '99.0.0', 'asset_url': None, 'page_url': update.RELEASES_PAGE, 'name': '', 'body': 'x'}
    shown, messages, dialogs = [], [], []
    monkeypatch.setattr(update, 'show_update_dialog', lambda r=None: shown.append(r))
    monkeypatch.setattr(update, '_info', lambda m: dialogs.append(m))
    monkeypatch.setattr(cmds, 'inViewMessage', lambda **kw: messages.append(kw.get('assistMessage')))
    monkeypatch.setattr(update, '_rebuild_menu', lambda: None)
    monkeypatch.setattr(update, 'available_release', None)
    update._handle_check_result({'ok': True, 'force': False, 'release': release})
    assert update.available_release is release and not shown and not dialogs and messages
    update._handle_check_result({'ok': True, 'force': True, 'release': release})
    assert shown == [release] and not dialogs
    # guncel surum: elle denetimde bilgi, acilista sessiz
    current = dict(release, version=bk.__version__)
    update._handle_check_result({'ok': True, 'force': False, 'release': current})
    update._handle_check_result({'ok': True, 'force': True, 'release': current})
    assert len(dialogs) == 1
    # cevrimdisi: acilista sessiz, elle denetimde yol gosteren metin
    import urllib.error
    exc = urllib.error.URLError('offline')
    update._handle_check_result({'ok': False, 'force': False, 'error': 'offline', 'exc': exc})
    assert len(dialogs) == 1
    update._handle_check_result({'ok': False, 'force': True, 'error': 'offline', 'exc': exc})
    assert len(dialogs) == 2 and 'offline' not in dialogs[-1]
    update.available_release = None


def test_update_download_rejects_second_click(monkeypatch):
    from blender_kontrol import update
    messages = []
    monkeypatch.setattr(update, '_msg', lambda m: messages.append(m))
    monkeypatch.setattr(update, '_downloading', True)
    update._start_download({'version': '99.0.0', 'asset_url': 'https://github.com/x'})
    assert len(messages) == 1


def test_update_bridge_is_created_on_the_main_thread_only():
    import threading
    from blender_kontrol import update
    assert update._get_bridge() is update._get_bridge()
    errors = []

    def worker():
        update._bridge = None
        try:
            update._get_bridge()
        except RuntimeError as exc:
            errors.append(exc)
    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert errors and update._bridge is None
    update._get_bridge()


def _t_literals():
    """Kaynaktaki her _t(...) cagrisinin dogrudan (ilk) argumani olan sabit metinler."""
    out = set()
    for _f, src in _sources():
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_t' and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    out.add(arg.value)
    return out


def test_translation_table_covers_every_literal_and_translates_turkish():
    """_t('...') ile verilen her sabit metnin EN karsiligi var (Turkce karakter icermese de: 'Sculpt',
    '-X → +X', '%s → %s'); Turkce karakterli bir anahtarin EN degeri anahtarin kendisi olamaz."""
    missing = sorted(s for s in _t_literals() if s not in i18n.EN and re.search(r'[A-Za-z]', s))
    assert not missing, missing[:15]
    untranslated = sorted(k for k, v in i18n.EN.items() if TURKISH.search(k) and v == k)
    assert not untranslated, untranslated[:15]


def test_settings_ui_pages_and_groups_have_turkish_sources():
    """Ayar sayfasi / grup / sutun adlari Turkce kaynakli ve cevrilmis (Turkce arayuzde Ingilizce sizmasin)."""
    from blender_kontrol import settings_ui
    D = settings_ui.SettingsDialog
    labels = [D.LABELS[k] for k in D.LABELS if k != 'language']      # 'Language / Dil' bilerek iki dilli
    for label in list(D.PAGE_LABELS.values()) + D.GROUPS + list(D.NOTES.values()) + labels:
        assert label in i18n.EN, label
    assert i18n.EN['Arayüz'] == 'Interface' and i18n.EN['Diğer'] == 'Other' and i18n.EN['Ad'] == 'Name'
    assert D._context_name({'ctx': ('view',)}) == '3D Görünüm'
    assert D._context_name({'ctx': ()}) == 'Diğer'
    assert all(len(D.LABELS[k]) <= 60 for k in ('emulate_numpad', 'emulate_3button', 'destructive_edit'))


def test_help_has_no_duplicate_rows_and_mentions_menu_items():
    """F1: ayni tusun birden cok satiri yok (M, Shift+A obje modunda); dil, guncelleme ve kisayol karti anlatilir."""
    for text in (bk.HELP, i18n.HELP_EN):
        rows = re.findall(r'<tr><td><b>([^<]+)</b></td>', text)      # tek basina tus (edit modu ekleri haric)
        assert rows.count('M') == 1 and rows.count('Shift + A') == 1, [r for r in rows if r in ('M', 'Shift + A')]
    assert 'Language / Dil' in bk.HELP and 'Language / Dil' in i18n.HELP_EN
    assert u'Güncellemeleri denetle' in bk.HELP and 'Check for updates' in i18n.HELP_EN
    assert u'Kısayol kartı' in bk.HELP and 'Shortcut card' in i18n.HELP_EN


def test_cheatsheet_context_sections_are_readable():
    """UV / Graph / Sculpt bolumleri yalin tus listesi degil: basliksiz tablolarda F1 ozeti kullanilir."""
    from blender_kontrol import cheatsheet
    for lang, needle in (('tr', u'ada seç'), ('en', 'select island')):
        bk.core._state['lang'] = lang
        try:
            page = cheatsheet.html()
        finally:
            bk.core._state['lang'] = None
        assert needle in page, lang
        assert '<p><kbd>' not in page


def test_clamp_to_screen_keeps_popups_on_screen():
    from blender_kontrol import objects
    screen = QtGui.QGuiApplication.primaryScreen().availableGeometry()
    size = QtCore.QSize(300, 200)
    far = objects.clamp_to_screen(QtCore.QPoint(screen.right() + 500, screen.bottom() + 500), size)
    assert far.x() + size.width() <= screen.right() and far.y() + size.height() <= screen.bottom()
    near = objects.clamp_to_screen(QtCore.QPoint(screen.left() - 50, screen.top() - 50), size)
    assert near.x() >= screen.left() and near.y() >= screen.top()
    inside = QtCore.QPoint(screen.left() + 40, screen.top() + 40)
    assert objects.clamp_to_screen(inside, size) == inside


# ---------------------------------------------------------------- performans duzeltmeleri (kare basi maliyet)
def test_bound_combos_cover_every_table_and_refresh_with_keymap():
    from blender_kontrol import events
    combos = events._bound_combos()
    assert 'g' in combos and 'ctrl+r' in combos and 'alt+v' in combos and 'shift+f' in combos
    assert 'ctrl+alt+shift+y' not in combos
    assert events._bound_combos() is combos          # ayni tablo: ayni kume
    keymap._save_overrides({'g': 'ctrl+alt+shift+y'})
    try:
        keymap._rebuild_keymap()
        assert 'ctrl+alt+shift+y' in events._bound_combos()
    finally:
        keymap._save_overrides({})
        keymap._rebuild_keymap()
    assert 'g' in events._bound_combos()


def test_unbound_key_returns_before_context_lookup(monkeypatch):
    from blender_kontrol import events
    calls = []
    monkeypatch.setattr(events, '_context', lambda: calls.append(1) or ('other', None))
    filt = events.BlenderFilter()
    mods = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier
    ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_Y, mods, 0x15, 0, 0, 'y')
    assert filt._key(ev, QtCore.QEvent.Type.KeyPress) is False and not calls
    ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_G, NO, 0x22, 0, 0, 'g')
    assert filt._key(ev, QtCore.QEvent.Type.KeyPress) is False and len(calls) == 1


def test_parse_memo_caches_per_text():
    class Owner(object):
        pass
    owner = Owner()
    assert bk.Modal._parse_memo(owner, '') is None
    assert bk.Modal._parse_memo(owner, '2*3') == pytest.approx(6.0)
    assert owner._parse_cache['2*3'] == pytest.approx(6.0)
    owner._parse_cache['2*3'] = 42.0
    assert bk.Modal._parse_memo(owner, '2*3') == 42.0      # metin degismedikce yeniden ayristirilmaz
    assert bk.Modal._parse_memo(owner, '-1.5') == pytest.approx(-1.5)


def test_ranges_named_compresses_soft_buckets():
    assert util._ranges_named('|o', 'vtx', [5, 3, 4, 9, 9]) == ['|o.vtx[3:5]', '|o.vtx[9]']
    assert util._ranges_named('|o', 'cv', [1]) == ['|o.cv[1]']


def test_hint_bar_skips_relayout_when_unchanged(monkeypatch):
    from blender_kontrol import ui
    from blender_kontrol.compat import QtWidgets
    bar = ui.HintBar()
    assert bar.label.objectName() == 'BlenderKontrolHintBar'
    widget = QtWidgets.QWidget()
    widget.resize(640, 480)
    calls = []
    monkeypatch.setattr(bar.label, 'setText', lambda text: calls.append(text))
    for _ in range(5):
        bar.show(widget, '<b>G</b> tasi')
    assert len(calls) == 1
    bar.show(widget, '<b>R</b> dondur')
    assert len(calls) == 2
    bar.dispose()


def test_preview_overlay_repaints_only_on_change(monkeypatch):
    from blender_kontrol import ui
    from blender_kontrol.compat import QtWidgets

    class View(object):
        def portWidth(self):
            return 640

        def portHeight(self):
            return 480

    class Picker(object):
        view = View()
        widget = QtWidgets.QWidget()
    Picker.widget.resize(640, 480)
    overlay = ui.PreviewOverlay()
    assert overlay.objectName() == 'BlenderKontrolPreviewOverlay'
    updates = []
    monkeypatch.setattr(overlay, 'update', lambda: updates.append(1))
    lines = [[(0.0, 0.0), (10.0, 10.0)]]
    for _ in range(4):
        overlay.show_lines(Picker(), lines)
    first = len(updates)
    overlay.show_lines(Picker(), [[(0.0, 0.0), (20.0, 10.0)]])
    assert first <= 2 and len(updates) == first + 1
    overlay.deleteLater()


def test_clamp_to_screen_helper_in_ui():
    from blender_kontrol import ui
    area = QtGui.QGuiApplication.primaryScreen().availableGeometry()
    size = QtCore.QSize(520, 380)
    p = ui._clamp_to_screen(QtCore.QPoint(area.right() + 300, area.bottom() + 300), size)
    assert p.x() + size.width() - 1 <= area.right() and p.y() + size.height() - 1 <= area.bottom()
    p = ui._clamp_to_screen(QtCore.QPoint(area.left() - 90, area.top() - 90), size)
    assert p.x() == area.left() and p.y() == area.top()
    inside = QtCore.QPoint(area.left() + 30, area.top() + 30)
    assert ui._clamp_to_screen(inside, size) == inside


def test_numpy_is_imported_lazily():
    from blender_kontrol import compat
    src = io.open(os.path.join(PKG, 'compat.py'), encoding='utf-8').read()
    assert 'import numpy' not in src.split('def _numpy')[0]
    assert compat._numpy() is compat._numpy()
    assert 'import numpy' not in io.open(os.path.join(PKG, 'picking.py'), encoding='utf-8').read()


def test_search_palette_reject_closes():
    from blender_kontrol import search
    from blender_kontrol.compat import QtWidgets
    assert search.SearchPalette.reject is not QtWidgets.QDialog.reject
