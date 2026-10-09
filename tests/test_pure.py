# -*- coding: utf-8 -*-
"""Maya'siz calisan testler (CI): `python -m pytest tests` (PySide6 gerekir)."""
import ast
import io
import os
import re

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
