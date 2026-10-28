# -*- coding: utf-8 -*-
"""Blender for Maya: arayuzsuz testler (mayapy ile).

    "C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe" tests/headless_tests.py

Saf mantik ve sahne komutlari: ceviri kapsami, fiziksel tus eslemesi, sayi ayristirma, mesh grafigi,
isin-kutu testi, kisayol ozellestirme, kurulum yardimcilari, mesh islemleri. Cikis kodu: kalan test sayisi.
"""
from __future__ import print_function

import ast
import io
import os
import re
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

# Kullanicinin gercek kisayol dosyasina asla yazma (testler gecici dosya kullanir)
os.environ['ORANGE_KEYMAP'] = os.path.join(tempfile.mkdtemp(prefix='orange_keymap_'), 'keymap.json')

import maya.standalone  # noqa: E402
maya.standalone.initialize(name='python')
import maya.cmds as cmds  # noqa: E402
import maya.api.OpenMaya as om  # noqa: E402

import blender_kontrol as bk  # noqa: E402
import drag_drop_install as ddi  # noqa: E402

try:
    from PySide6 import QtCore, QtGui
except ImportError:
    from PySide2 import QtCore, QtGui
Qt = QtCore.Qt

RESULTS = []


def ok(label, cond, detail=''):
    RESULTS.append((label, bool(cond), repr(detail)[:200]))


def test_i18n():
    pkg = os.path.join(REPO, 'blender_kontrol')
    trees = [ast.parse(io.open(os.path.join(pkg, f), encoding='utf-8').read())
             for f in sorted(os.listdir(pkg)) if f.endswith('.py') and f != 'i18n_en.py']
    turkish = re.compile(u'[çğıöşüÇĞİÖŞÜ]')
    missing = set()
    for n in (node for tree in trees for node in ast.walk(tree)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_t':
            for c in ast.walk(n):
                if isinstance(c, ast.Constant) and isinstance(c.value, str) and turkish.search(c.value) and c.value not in bk.EN:
                    missing.add(c.value)
    ok('_t() icindeki Turkce metinlerin hepsi cevrilmis', not missing, sorted(missing)[:5])
    titles = [b['title'] for b in bk.BINDINGS.values()] + [t for t, _ in bk.EXTRA_COMMANDS]
    ok('tus ve F3 basliklari cevrilmis', all(t in bk.EN for t in titles), [t for t in titles if t not in bk.EN][:5])
    fmt = re.compile(r'%[-0-9.]*[sdf]')
    bad = [k for k, v in bk.EN.items() if sorted(fmt.findall(k)) != sorted(fmt.findall(v))]
    ok('ceviri bicim belirtecleri tutarli', not bad, bad[:5])
    ok('Ingilizce yardim tablo sayisi Turkceyle ayni', bk.HELP.count('<tr>') == bk.HELP_EN.count('<tr>'),
       (bk.HELP.count('<tr>'), bk.HELP_EN.count('<tr>')))
    bk.set_setting('language', 'en')
    ok('dil en', bk._t('Önce bir obje seç') == 'Select an object first')
    bk.set_setting('language', 'tr')
    ok('dil tr', bk._t('Önce bir obje seç') == 'Önce bir obje seç')
    bk.set_setting('language', 'auto')


def test_keys():
    T = QtCore.QEvent.Type
    KP = Qt.KeyboardModifier.KeypadModifier
    NO = Qt.KeyboardModifier.NoModifier
    cases = [('win', Qt.Key.Key_G, NO, 0x22, 0, 'g', 'g'), ('win', Qt.Key.Key_unknown, NO, 0x17, 0, u'ı', 'i'),
             ('win', Qt.Key.Key_7, KP, 0x47, 0, '7', 'np7'), ('win', Qt.Key.Key_Slash, KP, 0x135, 0, '/', 'np/'),
             ('win', Qt.Key.Key_Comma, NO, 0x33, 0, ',', 'comma'), ('win', Qt.Key.Key_PageUp, NO, 0x149, 0, '', 'pgup'),
             ('linux', Qt.Key.Key_G, NO, 42, 0, 'g', 'g'), ('linux', Qt.Key.Key_1, KP, 87, 0, '1', 'np1'),
             ('linux', Qt.Key.Key_Slash, KP, 106, 0, '/', 'np/'), ('linux', Qt.Key.Key_QuoteLeft, NO, 49, 0, '`', 'grave'),
             ('mac', Qt.Key.Key_G, NO, 0, 0x05, 'g', 'g'), ('mac', Qt.Key.Key_A, NO, 0, 0, 'a', 'a'),
             ('mac', Qt.Key.Key_unknown, NO, 0, 0, '', None), ('mac', Qt.Key.Key_unknown, NO, 0, 0x22, u'ı', 'i'),
             ('mac', Qt.Key.Key_7, KP, 0, 0x59, '7', 'np7'), ('mac', Qt.Key.Key_Period, KP, 0, 0x41, '.', 'np.')]
    for plat, key, mods, sc, vk, text, want in cases:
        ev = QtGui.QKeyEvent(T.KeyPress, key, mods, sc, vk, 0, text)
        ok('tus %s -> %r' % (plat, want), bk._key_name(ev, plat) == want, bk._key_name(ev, plat))
    ok('etiket', bk._combo_label('ctrl+alt+shift+np7') == 'Ctrl+Alt+Shift+Numpad 7')


def test_parse():
    P = bk.Modal._parse
    cases = {'2*3': 6.0, '-1.5': -1.5, '2m': 200.0, '10cm': 10.0, '25mm': 2.5, '90d': 90.0, '1in': 2.54,
             'pi/2': 3.141592653589793 / 2, 'sqrt(4)': 2.0, '2mm+1cm': 1.2, '1,5': 1.5}
    for expr, want in cases.items():
        got = P(expr)
        ok('ifade %s' % expr, got is not None and abs(got - want) < 1e-9, got)
    for evil in ('__import__("os")', 'abc', '().__class__', 'open("x")'):
        ok('guvenli ifade %r' % evil, P(evil) is None, P(evil))


def test_mesh_helpers():
    ok('_ranges', bk._ranges('o', 'face', [3, 4, 5, 9, 1]) == ['o.f[1]', 'o.f[3:5]', 'o.f[9]'])
    hops = bk._hops(0, lambda n: [m for m in (n - 1, n + 1) if 0 <= m < 10])
    ok('_hops BFS', hops[9] == 9 and len(hops) == 10)
    box = om.MBoundingBox(om.MPoint(-1, -1, -1), om.MPoint(1, 1, 1))
    ok('isin kutuya deger', bk._ray_hits_box(om.MPoint(0, 0, 10), om.MVector(0, 0, -1), box))
    ok('isin kutuyu iskalar', not bk._ray_hits_box(om.MPoint(5, 0, 10), om.MVector(0, 0, -1), box))
    ok('isin geride', not bk._ray_hits_box(om.MPoint(0, 0, 10), om.MVector(0, 0, 1), box))
    pl = cmds.polyPlane(name='hlPlane', sx=4, sy=4)[0]
    fn, dag = bk._mesh_fn(pl)
    g = bk._mesh_graph(fn, dag.fullPathName())
    ok('mesh grafigi onbellek', g is bk._mesh_graph(fn, dag.fullPathName()))
    ok('en kisa yol (kose 0 -> 24)', len(g.vertex_path([0], [24])[0]) == 9, len(g.vertex_path([0], [24])[0]))
    ok('yuz kabugu', len(g.shell(0)) == 16)
    cmds.delete(pl)


def test_selection_ops():
    pl = cmds.polyPlane(name='hsPlane', sx=4, sy=4, w=4, h=4)[0]
    cmds.select(pl + '.f[0]')
    bk.select_similar('face', 'sides')
    ok('benzer: kenar sayisi', len(cmds.ls(sl=True, flatten=True)) == 16)
    cmds.select(pl + '.vtx[0]')
    bk.select_mirror()
    ok('ayna secimi', cmds.ls(sl=True, flatten=True) == [pl + '.vtx[4]'], cmds.ls(sl=True, flatten=True))
    cmds.select(pl + '.e[0]')
    bk.select_similar('edge', 'direction')
    ok('benzer: yon', len(cmds.ls(sl=True, flatten=True)) == 20, len(cmds.ls(sl=True, flatten=True)))
    cmds.delete(pl)


def test_mesh_ops():
    c = cmds.polyCube(name='hmCube', sx=3, sy=3, sz=3)[0]
    cmds.select(c)
    bk.limited_dissolve()
    ok('sinirli erit 3x3 kup -> 6 yuz', cmds.polyEvaluate(c, face=True) == 6, cmds.polyEvaluate(c, face=True))
    cmds.delete(c)
    p = cmds.polyPlane(name='hmPlane', sx=3, sy=1, w=3, h=1)[0]
    cmds.delete(p + '.f[1]')
    cmds.select(p + '.e[*]')
    edges = [e for e in cmds.ls(p + '.e[*]', flatten=True) if len(cmds.ls(cmds.polyListComponentConversion(e, toFace=True), flatten=True)) == 1]
    cmds.select(edges[:2])
    f0 = cmds.polyEvaluate(p, face=True)
    bk.fill_beauty()
    ok('Alt+F doldur', cmds.polyEvaluate(p, face=True) > f0)
    cmds.delete(p)
    q = cmds.polyPlane(name='hqPlane', sx=2, sy=2)[0]
    cmds.select(q + '.vtx[0]', q + '.vtx[1]')
    bk._merge_to(om.MPoint(5, 5, 5))
    ok('imlecte birlestir', cmds.polyEvaluate(q, vertex=True) == 8 and [round(x, 3) for x in cmds.xform(q + '.vtx[0]', q=True, ws=True, t=True)] == [5, 5, 5])
    cmds.delete(q)
    a = cmds.polyCube(name='hoCube')[0]
    cmds.move(3, 0, 0, a + '.vtx[*]', r=True)
    cmds.select(a)
    bk.set_origin('origin_to_geometry')
    ok('origin -> geometri', [round(x, 3) for x in cmds.xform(a, q=True, ws=True, rp=True)] == [3, 0, 0])
    bk.set_origin('geometry_to_origin')
    bb = cmds.exactWorldBoundingBox(a)
    ok('geometri -> origin', abs((bb[0] + bb[3]) / 2.0 - 3.0) < 1e-4, bb)
    cut = cmds.polyCube(name='hoCut', w=0.3, h=3, d=0.3)[0]
    cmds.xform(cut, t=(3, 0, 0))
    cmds.select(cut, a)
    bk.boolean(2)
    ok('boolean fark', cmds.objExists('hoCube') and not cmds.objExists('hoCut'))
    cmds.delete('hoCube')


def test_fill_corner():
    """F (Blender): tek sinir kosesi deligi yuz yuz doldurur; acik kenar zinciri tek yuz olur."""
    p = cmds.polyPlane(name='hfPlane', sx=4, sy=3, w=4, h=3)[0]
    normals_before = cmds.polyInfo(p + '.f[0]', faceNormals=True)[0]
    cmds.delete(p + '.f[5]', p + '.f[6]')          # orta sirada 2 dortgenlik delik (6 sinir kosesi)
    corner = [v for v in cmds.ls(p + '.vtx[*]', flatten=True)
              if len(bk.mesh._boundary_neighbors(bk.mesh._mesh_fn(p)[1], bk.mesh._comp_index(v))) == 2
              and len(cmds.ls(cmds.polyListComponentConversion(v, toFace=True), flatten=True)) == 3]
    ok('delik kosesi bulundu', corner, corner)
    cmds.select(corner[0])
    bk.fill()
    ok('F tek kose: bir dortgen', cmds.polyEvaluate(p, face=True) == 11, cmds.polyEvaluate(p, face=True))
    nxt = cmds.ls(sl=True, flatten=True)
    ok('F tek kose: sonraki kose secili', len(nxt) == 1 and '.vtx[' in nxt[0], nxt)
    bk.fill()
    ok('F ikinci kez: delik kapandi', cmds.polyEvaluate(p, face=True) == 12, cmds.polyEvaluate(p, face=True))
    sides = [len(cmds.ls(cmds.polyListComponentConversion('%s.f[%d]' % (p, i), toVertex=True), flatten=True))
             for i in range(12)]
    ok('F tek kose: n-gon yok', set(sides) == {4}, sides)
    ref = [float(x) for x in normals_before.split(':')[1].split()]
    up = all(sum(a * b for a, b in zip(ref, [float(x) for x in line.split(':')[1].split()])) > 0.9
             for line in cmds.polyInfo(p + '.f[*]', faceNormals=True))
    ok('F tek kose: normaller tutarli', up)
    cmds.delete(p)
    q = cmds.polyPlane(name='hfPlane2', sx=3, sy=3, w=3, h=3)[0]
    cmds.delete(q + '.f[4]')                          # tek dortgen delik
    fn, dag = bk.mesh._mesh_fn(q)
    edges = [e for e in cmds.ls(q + '.e[*]', flatten=True)
             if len(cmds.ls(cmds.polyListComponentConversion(e, toFace=True), flatten=True)) == 1
             and cmds.polyListComponentConversion(e, toVertex=True)]
    inner = [e for e in edges if all(abs(c) < 1.4 for v in cmds.ls(cmds.polyListComponentConversion(e, toVertex=True), flatten=True)
                                     for c in cmds.xform(v, q=True, ws=True, t=True)[::2])]
    pair = None
    for i, e1 in enumerate(inner):
        for e2 in inner[i + 1:]:
            v1 = set(cmds.ls(cmds.polyListComponentConversion(e1, toVertex=True), flatten=True))
            v2 = set(cmds.ls(cmds.polyListComponentConversion(e2, toVertex=True), flatten=True))
            if v1 & v2:
                pair = [e1, e2]
                break
        if pair:
            break
    ok('bitisik iki sinir kenari', pair, inner)
    cmds.select(pair)
    bk.fill()
    ok('F iki kenar: ucgen', cmds.polyEvaluate(q, face=True) == 9 and
       len(cmds.ls(cmds.polyListComponentConversion(cmds.ls(sl=True)[0], toVertex=True), flatten=True)) == 3,
       (cmds.polyEvaluate(q, face=True), cmds.ls(sl=True)))
    cmds.delete(q)


def test_startup_guard():
    """#4: onceki baslatma yarida kaldiysa (Maya coktu) Orange acilista baslamaz, adim menude / tanilamada gorunur."""
    lc = bk.lifecycle
    marker = lc._marker_path()
    try:
        lc._state['startup_settled'] = True
        lc.startup_stage('menu')
        ok('yerlesik durumda isaret yazilmaz', not os.path.exists(marker))
        lc._state['startup_settled'] = False
        lc.startup_stage('hotkey editor commands')
        ok('baslarken adim diske yazilir', (lc._read_marker() or {}).get('stage') == 'hotkey editor commands',
           lc._read_marker())
        lc.clear_startup_marker()
        ok('bitince isaret silinir', not os.path.exists(marker))
        # baska bir surecin (coken Maya'nin) biraktigi isaret
        io.open(marker, 'w', encoding='utf-8').write(u'{"stage": "event filter", "pid": -1, "version": "1.0.1"}')
        started = lc.startup()
        ok('cokme sonrasi acilista Orange baslamaz', started is False)
        ok('yarida kalan adim saklanir', lc.startup_blocked() == 'event filter', lc.startup_blocked())
        ok('eski isaret temizlenir', not os.path.exists(marker))
        ok('tanilamada adim', 'event filter' in bk.diagnostics.diagnostics_text())
        ok('ikinci acilista da bekler', lc.startup() is False)
        lc._unblock()
        ok('elle baslatinca engel kalkar', lc.startup_blocked() == '')
    finally:
        lc._unblock()
        lc.clear_startup_marker()


def test_update_proxies():
    """#4: is parcacigi sistem proxy sorgusu yapmaz; proxy'ler ana is parcaciginda okunur ve acıcıya verilir."""
    import urllib.request
    calls = []
    real, real_bypass = urllib.request.getproxies, urllib.request.proxy_bypass
    urllib.request.getproxies = lambda: calls.append(1) or {'https': 'http://proxy.test:8080'}
    urllib.request.proxy_bypass = lambda host: calls.append(host) or host == 'api.github.com'
    try:
        config = bk.update._main_thread_proxies()
        proxies, bypass = config
        ok('proxy ve bypass ana is parcaciginda okunur', proxies == {'https': 'http://proxy.test:8080'}
           and bypass.get('api.github.com') is True and bypass.get('github.com') is False, config)
        n = len(calls)
        opener = bk.update._opener(config)
        handlers = [h for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler)]
        ok('acici verilen proxy ile kurulur', handlers and handlers[0].proxies == proxies)
        req = urllib.request.Request('https://github.com/x')
        handlers[0].proxy_open(req, proxies['https'], 'https')
        bk.update._opener(({}, {}))
        ok('acici ve proxy_open sistem sorgusu yapmaz', len(calls) == n, calls[n:])
    finally:
        urllib.request.getproxies, urllib.request.proxy_bypass = real, real_bypass


def test_keymap_and_settings():
    tmp = tempfile.mkdtemp(prefix='bk_keymap_')
    km = sys.modules['blender_kontrol.keymap']
    orig = km._keymap_path
    km._keymap_path = lambda: os.path.join(tmp, 'keymap.json')
    try:
        bk._save_overrides({'g': 'alt+g', 'r': ''})
        act = bk._rebuild_keymap()
        ok('ozel tus: alt+g = Tasi (cakisan varsayilan ezilir)', act.get('alt+g') is bk.BINDINGS['g'])
        ok('kapali tus', 'r' not in act and bk._combo_for('r') == '')
        bk._save_overrides({})
        bk._rebuild_keymap()
        ok('varsayilana donus', bk._active_bindings().get('g') is bk.BINDINGS['g'] and bk._combo_for('alt+g') == 'alt+g')
        ok('gercek kisayol dosyasina dokunulmadi', not os.path.exists(os.environ['ORANGE_KEYMAP']))
    finally:
        km._keymap_path = orig
        bk._rebuild_keymap()
        shutil.rmtree(tmp, ignore_errors=True)
    for name, (var, default) in bk.SETTINGS.items():
        ok('ayar varsayilani %s' % name, bk.setting(name) is not None)


def test_installer():
    tmp = tempfile.mkdtemp(prefix='orange_inst_')
    try:
        ok('kaynak surumu', ddi.source_version(REPO) == bk.__version__, ddi.source_version(REPO))
        modules = os.path.join(tmp, 'modules')
        res = ddi.install(REPO, modules_dir=modules, shelf=False, start_now=False, clean_legacy=False)
        root = res['module_root']
        scripts = os.path.join(root, 'scripts')
        ok('modul: paket', all(os.path.isfile(os.path.join(scripts, 'blender_kontrol', f))
                               for f in ('__init__.py', 'i18n_en.py', 'installer.py', 'keymap.py', 'orangeArray.py')))
        ok('modul: __pycache__ yok', not os.path.exists(os.path.join(scripts, 'blender_kontrol', '__pycache__')))
        ok('modul: userSetup.py baslatir', 'blender_kontrol.startup()' in io.open(os.path.join(scripts, 'userSetup.py'),
                                                                               encoding='utf-8').read())
        ok('modul: ikon', os.path.isfile(os.path.join(root, 'icons', 'orange.png')))
        ok('modul: Array Maya eklentisi', os.path.isfile(os.path.join(root, 'plug-ins', 'orangeArray.py')))
        native_plugin = os.path.join(REPO, 'blender_kontrol', 'orangeArray.mll')
        if os.path.isfile(native_plugin):
            ok('modul: yerel Array plug-in paketlendi',
               os.path.isfile(os.path.join(root, 'plug-ins', 'orangeArray.mll')))
        mod = io.open(res['mod_file'], encoding='utf-8').read()
        ok('.mod dosyasi', mod.startswith('+ Orange %s ' % bk.__version__) and root.replace(os.sep, '/') in mod, mod)
        # eski (0.6) kurulum temizligi
        legacy = os.path.join(tmp, 'scripts')
        os.makedirs(os.path.join(legacy, 'blender_kontrol'))
        io.open(os.path.join(legacy, 'blender_kontrol.py'), 'w', encoding='utf-8').write(u'#' + os.linesep)
        io.open(os.path.join(legacy, 'userSetup.py'), 'w', encoding='utf-8').write(u'print("x")' + os.linesep)
        ddi.add_to_usersetup(legacy)
        ddi.add_to_usersetup(legacy)
        txt = io.open(os.path.join(legacy, 'userSetup.py'), encoding='utf-8').read()
        ok('eski userSetup blogu bir kez', txt.count(ddi.MARK_BEGIN) == 1 and 'print("x")' in txt)
        removed = ddi.remove_legacy([legacy])
        txt = io.open(os.path.join(legacy, 'userSetup.py'), encoding='utf-8').read()
        ok('eski kurulum temizlendi', len(removed) == 3 and not os.path.exists(os.path.join(legacy, 'blender_kontrol'))
           and ddi.MARK_BEGIN not in txt and 'print("x")' in txt, removed)
        gone = ddi.uninstall(modules_dir=modules, shelf=False, clean_legacy=False)
        ok('kaldir', not os.path.exists(root) and not os.path.exists(res['mod_file'])
           and len([g for g in gone if 'orange' in g.lower()]) == 2, gone)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        sys.modules.setdefault('blender_kontrol', bk)


def test_grid_fill():
    """Grid Fill: 4x4 duzlemin ortasindaki 2x2 delik 8 sinir kenari -> 2x2 izgara, kapali, normaller ayni yonde."""
    cmds.file(new=True, force=True)
    pl = cmds.polyPlane(name='gfPlane', sx=4, sy=4, w=4, h=4)[0]
    cmds.delete(cmds.ls(cmds.polyListComponentConversion(pl + '.vtx[12]', toFace=True), flatten=True))
    border = [e for e in cmds.ls(pl + '.e[*]', flatten=True)
              if len(cmds.ls(cmds.polyListComponentConversion(e, toFace=True), flatten=True)) == 1]
    def central(e):
        p = cmds.xform(e, q=True, ws=True, t=True)
        return all(abs(c) < 1.5 for c in p[0::3] + p[2::3])
    inner = [e for e in border if central(e)]
    ok('Grid Fill: delik siniri 8 kenar', len(inner) == 8, len(inner))
    f0 = cmds.polyEvaluate(pl, face=True)
    cmds.select(pl)
    bk.enter_edit('edge')
    cmds.select(inner)
    new_faces = bk.grid_fill()
    obj = 'gfPlane'
    ok('Grid Fill: 4 yeni yuz', cmds.polyEvaluate(obj, face=True) == f0 + 4, (f0, cmds.polyEvaluate(obj, face=True)))
    open_edges = [e for e in cmds.ls(obj + '.e[*]', flatten=True)
                  if len(cmds.ls(cmds.polyListComponentConversion(e, toFace=True), flatten=True)) == 1]
    ok('Grid Fill: yalniz dis sinir acik (16 kenar)', len(open_edges) == 16, len(open_edges))
    fn, _dag = bk._mesh_fn(obj)
    ups = [fn.getPolygonNormal(i, om.MSpace.kWorld).y for i in range(fn.numPolygons)]
    ok('Grid Fill: normaller tutarli', all(u > 0.99 for u in ups), [round(u, 2) for u in ups if u <= 0.99])
    ok('Grid Fill: yeni yuzler secili', new_faces and cmds.ls(sl=True, flatten=True) and
       len(cmds.ls(sl=True, flatten=True)) == 4)
    bk.exit_edit()
    cmds.file(new=True, force=True)


def _world_matrix(obj):
    return [round(v, 4) for v in cmds.xform(obj, q=True, ws=True, matrix=True)]


def test_modifiers():
    M = bk.modifiers
    cmds.file(new=True, force=True)
    c = cmds.polyCube(name='mdSub')[0]
    sub = M.add_subdivision(c, 1)
    M.set_subdivision(c, 2)
    ok('subdivision history and level', M.history_modifiers(c) == [(sub, 'subdiv')]
       and cmds.getAttr(sub + '.divisions') == 2 and cmds.polyEvaluate(c, face=True) == 96)
    cmds.setAttr(sub + '.method', 1)
    linear_faces = cmds.polyEvaluate(c, face=True)
    cmds.setAttr(sub + '.method', 0)
    ok('Subdivision Catmull-Clark and Linear schemes evaluate distinctly',
       linear_faces != 96 and cmds.polyEvaluate(c, face=True) == 96)
    cage = M.cage_shape(c)
    cage = M.enter_source_edit(c)
    cmds.move(3, 0, 0, cage + '.vtx[0]', relative=True)
    ok('edit cage drives live modifier output', cmds.exactWorldBoundingBox(c)[3] > 2.0
       and cmds.getAttr(cage + '.intermediateObject') is False)
    M.exit_source_edit(c)
    ok('edit cage restores result display state', cmds.getAttr(cage + '.intermediateObject') is True)
    M.set_subdivision(c, 0)
    ok('subdivision bypass retains card', M.history_modifiers(c) == [(sub, 'subdiv')]
       and cmds.polyEvaluate(c, face=True) == 6)
    M.set_subdivision(c, 1)
    uuid = cmds.ls(c, uuid=True)[0]
    ok('Apply All bakes Subdivision', M.apply_all(c) == c and not M.history_modifiers(c)
       and cmds.polyEvaluate(c, face=True) == 24 and cmds.ls(c, uuid=True)[0] == uuid)

    m = cmds.polyCube(name='mdMir', w=1, h=1, d=1)[0]
    mirror = M.add_mirror(m, 'x')
    ok('Mirror native history and wildcard', M.history_modifiers(m) == [(mirror, 'mirror')]
       and cmds.getAttr(mirror + '.inputComponents') == ['f[*]'])
    ok('Apply All reports native Maya history', 'polyCube' in [cmds.nodeType(n) for n in M.foreign_history_nodes(m)])
    base_faces = 6
    M.set_enabled(mirror, False)
    ok('Mirror bypass', cmds.polyEvaluate(m, face=True) == base_faces and not M.is_enabled(mirror))
    M.set_enabled(mirror, True)
    mirror_y = M.set_mirror_axis(m, 'y', True, node=mirror)
    ok('Mirror X/Y toggles share one logical card', mirror_y
       and M._mirror_group_for_node(m, mirror) == [mirror, mirror_y]
       and sorted(cmds.getAttr(n + '.axis') for n in (mirror, mirror_y)) == [0, 1]
       and cmds.polyEvaluate(m, face=True) == 24)
    M.remove_mirror_group(m, mirror)
    ok('Mirror remove restores input', cmds.polyEvaluate(m, face=True) == base_faces)

    legacy = cmds.polyCube(name='mdLegacy')[0]
    M._set_base_value(legacy, M.ARRAY_ATTRS[0], 3)
    for name, value in zip(M.ARRAY_ATTRS[1:], (1.0, 0.0, 0.0, 0.0, 0.0, 0.0)):
        M._set_base_value(legacy, name, value)
    M._set_base_value(legacy, M.MIRROR_MERGE_ATTR, True, 'bool')
    M._set_base_value(legacy, M.MIRROR_THRESHOLD_ATTR, 0.001)
    M._instance(legacy, 'mirror:x', [-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
    M._instance(legacy, 'array', [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 2, 0, 0, 1])
    M._instance(legacy, 'array', [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 4, 0, 0, 1])
    ok('legacy modifier previews detected', len(M.instance_modifiers(legacy)) == 3)
    migrated = bk.undoable(lambda: M.migrate_legacy_instances(legacy))()
    ok('legacy instance modifiers convert to live stack', migrated
       and not M.instance_modifiers(legacy)
       and [kind for _, kind in M.history_modifiers(legacy)] == ['mirror', 'array']
       and cmds.getAttr(next(n for n, kind in M.history_modifiers(legacy) if kind == 'array') + '.count') == 3
       and cmds.polyEvaluate(legacy, face=True) == 36)
    cmds.undo()
    ok('legacy stack migration undo restores previews', not M.history_modifiers(legacy)
       and len(M.instance_modifiers(legacy)) == 3)
    cmds.redo()
    ok('legacy stack migration redo restores live stack', not M.instance_modifiers(legacy)
       and [kind for _, kind in M.history_modifiers(legacy)] == ['mirror', 'array'])

    a = cmds.polyCube(name='mdArr')[0]
    arr = M.add_array(a, 3, 'x')
    shape = M._shape(a)
    ok('Array single mesh output', M.history_modifiers(a) == [(arr, 'array')]
       and cmds.polyEvaluate(shape, vertex=True) == 24 and cmds.polyEvaluate(shape, face=True) == 18)
    ok('Array duplicates UV coordinates', cmds.polyEvaluate(shape, uvcoord=True) == 42,
       cmds.polyEvaluate(shape, uvcoord=True))

    offset_base = cmds.polyCube(name='mdArrayObjectOffset')[0]
    offset_node = M.add_array(offset_base, 3, 'x')
    offset_target = cmds.group(empty=True, name='mdArrayOffsetControl')
    cmds.setAttr(offset_target + '.translateX', 2.0)
    M.set_array_object_offset(offset_node, offset_base, offset_target)
    offset_sel = om.MSelectionList()
    offset_sel.add(M._shape(offset_base))
    offset_fn = om.MFnMesh(offset_sel.getDagPath(0))
    offset_points = offset_fn.getPoints(om.MSpace.kObject)
    first_step = offset_points[8].x - offset_points[0].x
    cmds.setAttr(offset_target + '.translateX', 3.0)
    offset_points = offset_fn.getPoints(om.MSpace.kObject)
    animated_step = offset_points[8].x - offset_points[0].x
    second_step = offset_points[16].x - offset_points[8].x
    ok('Array Object Offset combines relative spacing and follows transform edits',
       cmds.getAttr(offset_node + '.useObjectOffset') and abs(first_step - 3.0) < 1e-5
       and abs(animated_step - 4.0) < 1e-5 and abs(second_step - 4.0) < 1e-5,
       (first_step, animated_step, second_step))
    offset_scene = os.path.join(tempfile.mkdtemp(prefix='orange_array_offset_'), 'offset.ma').replace(os.sep, '/')
    cmds.file(rename=offset_scene)
    cmds.file(save=True, type='mayaAscii', force=True)
    cmds.file(new=True, force=True)
    cmds.file(offset_scene, open=True, force=True)
    offset_base = cmds.ls('mdArrayObjectOffset', long=True)[0]
    reopened_node = next(n for n, kind in M.history_modifiers(offset_base) if kind == 'array')
    reopened_links = cmds.listConnections(reopened_node + '.objectWorldMatrix', source=True,
                                          destination=False, plugs=True) or []
    reopened_sel = om.MSelectionList()
    reopened_sel.add(M._shape(offset_base))
    reopened_points = om.MFnMesh(reopened_sel.getDagPath(0)).getPoints(om.MSpace.kObject)
    ok('Array Object Offset connections and result survive scene reopen',
       cmds.getAttr(reopened_node + '.useObjectOffset') and len(reopened_links) == 1
       and abs(reopened_points[8].x - reopened_points[0].x - 4.0) < 1e-5,
       (reopened_links, reopened_points[8].x - reopened_points[0].x))
    offset_rejected = False
    try:
        M.set_array_object_offset(offset_node, offset_base, offset_base)
    except RuntimeError:
        offset_rejected = True
    ok('Array Object Offset rejects a self-reference', offset_rejected)

    normal_base = cmds.polySphere(name='mdArrayOffsetNormals', subdivisionsAxis=8, subdivisionsHeight=4)[0]
    cmds.polySoftEdge(normal_base, angle=180.0, constructionHistory=False)
    normal_sel = om.MSelectionList()
    normal_sel.add(M._shape(normal_base))
    normal_path = normal_sel.getDagPath(0)
    normal_source = om.MFnMesh(normal_path)
    source_face_count = normal_source.numPolygons
    source_normals = normal_source.getFaceVertexNormals(0, om.MSpace.kObject)
    normal_node = M.add_array(normal_base, 2, relative=[0.0, 0.0, 0.0], constant=[0.0, 0.0, 0.0])
    normal_offset = cmds.group(empty=True, name='mdArrayNormalOffset')
    cmds.setAttr(normal_offset + '.rotateY', 90.0)
    M.set_array_object_offset(normal_node, normal_base, normal_offset)
    normal_result = om.MFnMesh(normal_path)
    rotated_normals = normal_result.getFaceVertexNormals(source_face_count, om.MSpace.kObject)
    offset_sel = om.MSelectionList()
    offset_sel.add(normal_offset)
    offset_path = offset_sel.getDagPath(0)
    expected_normal = om.MVector(source_normals[0]) * offset_path.inclusiveMatrix()
    actual_normal = om.MVector(rotated_normals[0])
    ok('Array Object Offset rotates smooth face-vertex normals',
       actual_normal.normal() * expected_normal.normal() > 0.999)

    merge_base = cmds.polyCube(name='mdArrayMerge')[0]
    cmds.polySoftEdge(merge_base, angle=180.0, constructionHistory=False)
    cmds.polyCrease(merge_base + '.e[0]', value=1.0)
    merge_node = M.add_array(merge_base, 2, relative=[0.0, 0.0, 0.0], constant=[1.0, 0.0, 0.0])
    before_merge_shape = M._shape(merge_base)
    before_merge_uvs = cmds.polyEvaluate(before_merge_shape, uvcoord=True)
    cmds.setAttr(merge_node + '.mergeDistance', 0.0001)
    cmds.setAttr(merge_node + '.mergeCopies', True)
    after_merge_vertices = cmds.polyEvaluate(before_merge_shape, vertex=True)
    after_merge_uvs = cmds.polyEvaluate(before_merge_shape, uvcoord=True)
    ok('Array Merge welds touching copy seams and retains per-copy UVs',
       after_merge_vertices == 12 and cmds.polyEvaluate(before_merge_shape, face=True) == 12
       and after_merge_uvs == before_merge_uvs, (after_merge_vertices, before_merge_uvs, after_merge_uvs))
    merge_sel = om.MSelectionList()
    merge_sel.add(before_merge_shape)
    merge_fn = om.MFnMesh(merge_sel.getDagPath(0))
    ok('Array Merge keeps smooth-edge flags with crease-bearing input',
       all(merge_fn.isEdgeSmooth(edge) for edge in range(merge_fn.numEdges)), merge_fn.numEdges)

    shaded = cmds.polyCube(name='mdArrayData')[0]
    cmds.polyColorSet(shaded, create=True, colorSet='orangeColors')
    cmds.polyColorPerVertex(shaded + '.vtx[0]', rgb=(1.0, 0.0, 0.0), colorDisplayOption=True)
    cmds.polyUVSet(shaded, create=True, uvSet='orangeDetailUV')
    cmds.polySoftEdge(shaded, angle=180.0, constructionHistory=False)
    source_sel = om.MSelectionList()
    source_sel.add(M._shape(shaded))
    source_fn = om.MFnMesh(source_sel.getDagPath(0))
    source_colors = source_fn.getFaceVertexColors('orangeColors')
    source_normals = [source_fn.getFaceVertexNormals(face, om.MSpace.kObject)
                      for face in range(source_fn.numPolygons)]
    data_node = M.add_array(shaded, 2, 'x')
    result_sel = om.MSelectionList()
    result_sel.add(M._shape(shaded))
    result_fn = om.MFnMesh(result_sel.getDagPath(0))
    result_sets = result_fn.getColorSetNames()
    result_uv_sets = result_fn.getUVSetNames()
    result_colors = result_fn.getFaceVertexColors('orangeColors')
    result_normals = [result_fn.getFaceVertexNormals(face, om.MSpace.kObject)
                      for face in range(result_fn.numPolygons)]
    source_color_count = len(source_colors)
    copied_colors = (len(result_colors) == source_color_count * 2
                     and all(abs(result_colors[i].r - source_colors[i].r) < 1e-6
                             and abs(result_colors[i + source_color_count].r - source_colors[i].r) < 1e-6
                             for i in range(source_color_count)))
    normals_match = (len(result_normals) == len(source_normals) * 2
                     and all(abs(result_normals[i][j].x - source_normals[i % len(source_normals)][j].x) < 1e-5
                             and abs(result_normals[i][j].y - source_normals[i % len(source_normals)][j].y) < 1e-5
                             and abs(result_normals[i][j].z - source_normals[i % len(source_normals)][j].z) < 1e-5
                             for i in range(len(result_normals))
                             for j in range(len(result_normals[i]))))
    ok('Array copies named face-vertex color sets', 'orangeColors' in result_sets and copied_colors)
    ok('Array preserves additional UV set names', 'orangeDetailUV' in result_uv_sets)
    ok('Array copies split face-vertex normals', normals_match)
    cmds.setAttr(data_node + '.nodeState', 1)
    ok('Array bypass returns its source mesh', cmds.polyEvaluate(shaded, face=True) == 6)
    cmds.setAttr(data_node + '.nodeState', 0)
    ok('Array bypass restores the generated copies', cmds.polyEvaluate(shaded, face=True) == 12)

    evaluation_mesh = cmds.polyCube(name='mdArrayEvaluation')[0]
    evaluation_node = M.add_array(evaluation_mesh, 3, 'x')
    evaluation_shape = M._shape(evaluation_mesh)
    original_evaluation_mode = (cmds.evaluationManager(query=True, mode=True) or ['parallel'])[0]
    original_time = cmds.currentTime(query=True)
    evaluation_results = []
    for mode in ('off', 'serial', 'parallel'):
        cmds.evaluationManager(mode=mode)
        cmds.setAttr(evaluation_node + '.constantY', 0.1)
        evaluation_sel = om.MSelectionList()
        evaluation_sel.add(evaluation_shape)
        evaluation_points = om.MFnMesh(evaluation_sel.getDagPath(0)).getPoints(om.MSpace.kObject)
        evaluation_results.append([(round(point.x, 7), round(point.y, 7), round(point.z, 7))
                                   for point in evaluation_points])
    cmds.evaluationManager(mode=original_evaluation_mode)
    cmds.currentTime(original_time)
    ok('Array DG/Serial/Parallel mesh output matches',
       evaluation_results[0] == evaluation_results[1] == evaluation_results[2])

    animated_mesh = cmds.polyCube(name='mdArrayAnimated')[0]
    animated_node = M.add_array(animated_mesh, 2)
    cmds.setKeyframe(animated_node + '.count', time=1, value=2)
    cmds.setKeyframe(animated_node + '.count', time=2, value=3)
    animated_results = []
    for mode in ('off', 'serial', 'parallel'):
        cmds.evaluationManager(mode=mode)
        mode_results = []
        for frame in (1, 2):
            cmds.currentTime(frame)
            mode_results.append(cmds.polyEvaluate(animated_mesh, face=True))
        animated_results.append(mode_results)
    cmds.evaluationManager(mode=original_evaluation_mode)
    cmds.currentTime(original_time)
    ok('Array animated Count is deterministic across evaluation modes',
       animated_results == [[12, 18], [12, 18], [12, 18]])

    material_mesh = cmds.polyCube(name='mdArrayMaterials')[0]
    material_sets = []
    for material_name in ('orangeRed', 'orangeBlue'):
        shader = cmds.shadingNode('lambert', asShader=True, name=material_name)
        shading_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True,
                                  name=material_name + 'SG')
        cmds.connectAttr(shader + '.outColor', shading_group + '.surfaceShader')
        material_sets.append(shading_group)
    cmds.sets(material_mesh + '.f[0:2]', edit=True, forceElement=material_sets[0])
    cmds.sets(material_mesh + '.f[3:5]', edit=True, forceElement=material_sets[1])
    material_shape = M._shape(material_mesh)
    material_sel = om.MSelectionList()
    material_sel.add(material_shape)
    material_fn = om.MFnMesh(material_sel.getDagPath(0))
    source_shading_groups, source_face_groups = material_fn.getConnectedShaders(0)
    material_node = M.add_array(material_mesh, 2)
    cmds.setAttr(material_node + '.mergeCopies', True)
    material_sel = om.MSelectionList()
    material_sel.add(material_shape)
    result_fn = om.MFnMesh(material_sel.getDagPath(0))
    result_shading_groups, result_face_groups = result_fn.getConnectedShaders(0)
    expected_face_groups = list(source_face_groups) * 2
    ok('Array Merge preserves per-face shading-group assignments', len(result_shading_groups) == 2
       and list(result_face_groups) == expected_face_groups)

    old_box = cmds.exactWorldBoundingBox(a)
    cmds.setAttr(arr + '.count', 1)
    ok('Array Count one', cmds.polyEvaluate(shape, face=True) == 6)
    cmds.setAttr(arr + '.count', 3)
    cmds.setAttr(arr + '.relativeX', 0.25)
    cmds.setAttr(arr + '.constantX', 0.0)
    moved_box = cmds.exactWorldBoundingBox(a)
    ok('Array offset updates live', moved_box[3] < old_box[3] - 1.0, moved_box)
    scene_path = os.path.join(tempfile.mkdtemp(prefix='orange_array_scene_'), 'array.ma').replace(os.sep, '/')
    cmds.file(rename=scene_path)
    cmds.file(save=True, type='mayaAscii', force=True)
    cmds.file(new=True, force=True)
    cmds.file(scene_path, open=True, force=True)
    a = 'mdArr'
    arr = next(n for n, kind in M.history_modifiers(a) if kind == 'array')
    ok('Array scene save/reopen retains DG node', cmds.nodeType(arr) == 'orangeArray'
       and cmds.polyEvaluate(a, face=True) == 18)
    uuid = cmds.ls(a, uuid=True)[0]
    bk.undoable(lambda: M.apply_all(a))()
    ok('Apply All bakes Array and preserves transform identity', not M.history_modifiers(a)
       and cmds.polyEvaluate(a, face=True) == 18 and cmds.ls(a, uuid=True)[0] == uuid)
    cmds.undo()
    ok('Array Apply All undo restores live modifier', [kind for _, kind in M.history_modifiers(a)] == ['array']
       and cmds.polyEvaluate(a, face=True) == 18)
    cmds.redo()
    ok('Array Apply All redo bakes again', not M.history_modifiers(a) and cmds.polyEvaluate(a, face=True) == 18)

    prefix_bake = cmds.polyCube(name='mdPrefixApply')[0]
    prefix_subdiv = M.add_subdivision(prefix_bake, 2)
    M.add_array(prefix_bake, 2)
    prefix_faces = cmds.polyEvaluate(prefix_bake, face=True)
    prefix_uuid = cmds.ls(prefix_bake, uuid=True)[0]
    bk.undoable(lambda: M.apply_history_modifier(prefix_bake, prefix_subdiv))()
    ok('Apply card bakes upstream prefix and keeps suffix',
       cmds.polyEvaluate(prefix_bake, face=True) == prefix_faces
       and [kind for _, kind in M.history_modifiers(prefix_bake)] == ['array']
       and M.cage_shape(prefix_bake) and cmds.ls(prefix_bake, uuid=True)[0] == prefix_uuid)
    cmds.undo()
    ok('Apply card undo restores the live prefix',
       [kind for _, kind in M.history_modifiers(prefix_bake)] == ['subdiv', 'array']
       and cmds.polyEvaluate(prefix_bake, face=True) == prefix_faces)
    cmds.redo()
    ok('Apply card redo restores baked prefix and live suffix',
       [kind for _, kind in M.history_modifiers(prefix_bake)] == ['array']
       and cmds.polyEvaluate(prefix_bake, face=True) == prefix_faces)

    h = cmds.polyCube(name='mdHist')[0]
    node = M.add_history_modifier(h, 'bevel')
    ok('bevel modifier node', node and M.kind_of(node) == 'bevel' and M.history_modifiers(h) == [(node, 'bevel')])
    smooth_bevel = cmds.polyCube(name='mdSubdivBevel')[0]
    M.add_subdivision(smooth_bevel, 2)
    bevel_after_subdivision = M.add_history_modifier(smooth_bevel, 'bevel')
    ok('Bevel can be added after Subdivision',
       bevel_after_subdivision and [kind for _, kind in M.history_modifiers(smooth_bevel)] == ['subdiv', 'bevel'])
    for segs, want in ((1, 26), (2, 54), (3, 98)):
        cmds.setAttr(node + '.segments', segs)
        bad = _bevel_shape_problems(h, flat=(segs == 1))
        n_faces = cmds.polyEvaluate(h, face=True)
        ok('bevel %d segments' % segs, not bad and n_faces == want, (n_faces, bad[:5]))
    cmds.setAttr(node + '.segments', 1)
    cmds.setAttr(node + '.roundness', 0.25)
    cmds.setAttr(node + '.mitering', 1)
    cmds.setAttr(node + '.filterEdgesByAngle', False)
    cmds.setAttr(node + '.filterAngle', 45.0)
    ok('Bevel exposes profile, miter and angle-limit controls',
       abs(cmds.getAttr(node + '.roundness') - 0.25) < 1e-6
       and cmds.getAttr(node + '.mitering') == 1
       and not cmds.getAttr(node + '.filterEdgesByAngle')
       and abs(cmds.getAttr(node + '.filterAngle') - 45.0) < 1e-6)
    faces = cmds.polyEvaluate(h, face=True)
    M.set_enabled(node, False)
    ok('history modifier bypass', not M.is_enabled(node) and cmds.polyEvaluate(h, face=True) == 6)
    M.set_enabled(node, True)
    ok('history modifier re-enabled', cmds.polyEvaluate(h, face=True) == faces)
    M.remove_history_modifier(node)
    ok('history modifier removal', cmds.polyEvaluate(h, face=True) == 6 and not M.history_modifiers(h))
    for kind in ('solidify', 'triangulate', 'weld'):
        n = M.add_history_modifier(h, kind)
        ok('%s modifier' % kind, n and M.kind_of(n) == kind)
        if kind == 'solidify':
            cmds.setAttr(n + '.keepFacesTogether', False)
            cmds.setAttr(n + '.reverseAllFaces', False)
            ok('Solidify exposes shell and normal controls',
               not cmds.getAttr(n + '.keepFacesTogether') and not cmds.getAttr(n + '.reverseAllFaces'))
        elif kind == 'weld':
            cmds.setAttr(n + '.alwaysMergeTwoVertices', True)
            cmds.setAttr(n + '.texture', False)
            ok('Weld exposes vertex-count and UV controls',
               cmds.getAttr(n + '.alwaysMergeTwoVertices') and not cmds.getAttr(n + '.texture'))

    full = cmds.polyCube(name='mdAll')[0]
    mir = M.add_mirror(full, 'x')
    mir_y = M.set_mirror_axis(full, 'y', True, node=mir)
    tri = M.add_history_modifier(full, 'triangulate')
    arr = M.add_array(full, 2)
    ok('Mirror/Triangulate/Array unified stack', [kind for _, kind in M.history_modifiers(full)]
       == ['mirror', 'mirror', 'triangulate', 'array'])
    ok('Mirror uses Blender-style object-local axes', cmds.getAttr(mir + '.mirrorAxis') == 1)
    M.set_mirror_group_settings([mir, mir_y], cut=True)
    ok('Mirror cut setting applies to all axes', cmds.getAttr(mir + '.cutMesh')
       and cmds.getAttr(mir_y + '.cutMesh'))
    M.set_mirror_group_settings([mir, mir_y], cut=False)
    M.set_mirror_group_settings([mir, mir_y], direction=1)
    ok('Mirror flip direction applies to all axes', cmds.getAttr(mir + '.axisDirection') == 1
       and cmds.getAttr(mir_y + '.axisDirection') == 1)
    M.set_mirror_group_settings([mir, mir_y], direction=0)
    plane_mesh = cmds.polyCube(name='mdMirrorPlane')[0]
    plane_node = M.add_mirror(plane_mesh, 'x')
    M.set_mirror_plane([plane_node], center=[1.0, 0.0, 0.0], rotation=[0.0, 0.0, 0.0])
    plane_box = cmds.exactWorldBoundingBox(plane_mesh)
    ok('Mirror exposes an editable local plane center and rotation',
       abs(cmds.getAttr(plane_node + '.mirrorPlaneCenterX') - 1.0) < 1e-6
       and abs(cmds.getAttr(plane_node + '.mirrorPlaneRotateZ')) < 1e-6
       and plane_box[3] > 2.4, plane_box)
    ok('reorder across modifier types', M.can_move_history_modifier(full, arr, -1)
       and M.move_history_modifier(full, arr, -1)
       and [kind for _, kind in M.history_modifiers(full)] == ['mirror', 'mirror', 'array', 'triangulate']
       and M._mirror_group_for_node(full, mir) == [mir, mir_y])
    ok('Mirror axis nodes move together as one card', M.can_move_history_modifier(full, mir, 1)
       and M.move_history_modifier(full, mir, 1)
       and [kind for _, kind in M.history_modifiers(full)] == ['array', 'mirror', 'mirror', 'triangulate']
       and M._mirror_group_for_node(full, mir) == [mir, mir_y])
    bk.undoable(lambda: M.move_history_modifier(full, mir, -1))()
    reordered = ['mirror', 'mirror', 'array', 'triangulate']
    cmds.undo()
    ok('stack reorder undo restores connection order', [kind for _, kind in M.history_modifiers(full)]
       == ['array', 'mirror', 'mirror', 'triangulate'])
    cmds.redo()
    ok('stack reorder redo restores connection order', [kind for _, kind in M.history_modifiers(full)] == reordered)
    bk.undoable(lambda: M.move_history_card(full, tri, mir))()
    card_order = [kind for _, kind in M.history_modifiers(full)]
    ok('drag reorder moves across a grouped Mirror card',
       card_order == ['triangulate', 'mirror', 'mirror', 'array']
       and M._mirror_group_for_node(full, mir) == [mir, mir_y])
    cmds.undo()
    ok('drag reorder undo restores card order', [kind for _, kind in M.history_modifiers(full)] == reordered)
    cmds.redo()
    ok('drag reorder redo restores card order', [kind for _, kind in M.history_modifiers(full)] == card_order)
    bk.undoable(lambda: M.move_history_card(full, tri, mir, after=True))()
    after_card_order = [kind for _, kind in M.history_modifiers(full)]
    ok('drag reorder previews/drops after a grouped Mirror card',
       after_card_order == ['mirror', 'mirror', 'triangulate', 'array'])
    cmds.undo()
    ok('drop-after undo restores card order', [kind for _, kind in M.history_modifiers(full)] == card_order)
    cmds.redo()
    ok('drop-after redo restores card order', [kind for _, kind in M.history_modifiers(full)] == after_card_order)
    M.apply_all(full)
    ok('Apply All clears stack', not M.history_modifiers(full) and not M.instance_modifiers(full))

    dynamic = cmds.polyCube(name='mdDynamic')[0]
    dynamic_sub = M.add_subdivision(dynamic, 1)
    dynamic_tri = M.add_history_modifier(dynamic, 'triangulate')
    cmds.setAttr(dynamic_sub + '.divisions', 2)
    ok('Triangulate follows new upstream faces', cmds.getAttr(dynamic_tri + '.inputComponents') == ['f[*]']
       and cmds.polyEvaluate(dynamic, face=True) == 192)
    dynamic_bevel = cmds.polyCube(name='mdDynamicBevel')[0]
    bevel_sub = M.add_subdivision(dynamic_bevel, 1)
    dynamic_bevel_node = M.add_history_modifier(dynamic_bevel, 'bevel')
    bevel_before = cmds.polyEvaluate(dynamic_bevel, face=True)
    cmds.setAttr(bevel_sub + '.divisions', 2)
    ok('Bevel uses current edges, not saved indices',
       cmds.getAttr(dynamic_bevel_node + '.inputComponents') == ['e[*]']
       and cmds.polyEvaluate(dynamic_bevel, face=True) != bevel_before)
    cmds.file(new=True, force=True)


def _bevel_shape_problems(obj, flat=True):
    """Birim kupte bevel sonrasi sorunlar: eski kenar uzerinde kalan nokta, 4'ten cok kenarli yuz,
    flat ise duzlemsel olmayan yuz (cok segmentli yuvarlak kose dortgenleri dogal olarak hafif egik)."""
    import maya.api.OpenMaya as om
    sel = om.MSelectionList()
    sel.add(obj)
    fn = om.MFnMesh(sel.getDagPath(0))
    pts = fn.getPoints(om.MSpace.kObject)
    bad = []
    for i, p in enumerate(pts):
        if sum(1 for c in (p.x, p.y, p.z) if abs(abs(c) - 0.5) < 1e-4) >= 2:
            bad.append(('kenarda nokta', i))
    for f in range(fn.numPolygons):
        ids = list(fn.getPolygonVertices(f))
        if len(ids) > 4:
            bad.append(('n-gon', f))
        if len(ids) < 4 or not flat:
            continue
        n = fn.getPolygonNormal(f, om.MSpace.kObject)
        c = om.MVector()
        for v in ids:
            c += om.MVector(pts[v])
        c /= len(ids)
        if max(abs((om.MVector(pts[v]) - c) * n) for v in ids) > 1e-3:
            bad.append(('duzlemsel degil', f))
    return bad


def test_review_fixes():
    """History'siz mesh'te Array ciktisi ve kafes shading group'ta; Shift+D kopyasinda olu kafes yok;
    Alt+Tab'de fare durumu sifirlanir."""
    M = bk.modifiers
    cmds.file(new=True, force=True)
    mat = cmds.shadingNode('lambert', asShader=True, name='rvMat')
    sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name='rvSG')
    cmds.connectAttr(mat + '.outColor', sg + '.surfaceShader')

    flat = cmds.polyCube(name='rvFlat')[0]          # FBX import / delete history gibi: inMesh bagli degil
    cmds.delete(flat, constructionHistory=True)
    cmds.sets(flat, edit=True, forceElement=sg)
    M.add_array(flat, 2)
    out = M._shape(flat)
    ok('history\'siz mesh: Array ciktisi materyali korur',
       out and sg in (cmds.listConnections(out, type='shadingEngine') or []), out)
    ok('history\'siz mesh: Array 2 kopya uretir', cmds.polyEvaluate(flat, face=True) == 12)

    hist = cmds.polyCube(name='rvHist')[0]          # polyCube1 -> subdiv: kafes createNode ile olusur
    cmds.sets(hist, edit=True, forceElement=sg)
    M.add_subdivision(hist, 1)
    cage = M.cage_shape(hist)
    ok('olusturulan kafes shading group\'ta', cage and sg in (cmds.listConnections(cage, type='shadingEngine') or []), cage)

    dup = cmds.ls(cmds.duplicate(hist, returnRootsOnly=True)[0], long=True)[0]
    ok('Shift+D kopyasinda olu kafes yok', M.cage_shape(dup) is None and M.history_modifiers(dup) == [])
    ok('kopyada Tab gercek mesh\'i duzenler', M.enter_source_edit(dup) is None)
    stale = [s for s in cmds.listRelatives(dup, shapes=True, fullPath=True) or [] if cmds.getAttr(s + '.intermediateObject')]
    ok('kopyadaki yetim kafes silindi', not stale, stale)
    ok('kaynak kafes etkilenmedi', M.cage_shape(hist) == cage)

    class _Filt(object):
        modal = None
    filt = _Filt()
    filt.nav, filt.fwd, filt.eat_release, filt.alt_mmb = (1, 2), None, 1, ((0, 0), 'p')
    original = bk.modal._filter
    bk.modal._filter = lambda: filt
    try:
        bk.modal._on_app_state(Qt.ApplicationState.ApplicationInactive)
    finally:
        bk.modal._filter = original
    ok('Alt+Tab: fare durumu sifirlanir', filt.nav is None and filt.eat_release is None and filt.alt_mmb is None)
    cmds.file(new=True, force=True)


def test_update_fixes():
    """Guncelleme: hazirlik klasoru modules/orange/.update altinda, kaldirma onu da siler; surum kurali;
    hata metinleri cevrilmis."""
    U = bk.update
    tmp = tempfile.mkdtemp(prefix='orange_upd_')
    try:
        modules = os.path.join(tmp, 'modules')
        res = ddi.install(REPO, modules_dir=modules, shelf=False, start_now=False, clean_legacy=False)
        root = res['module_root']
        update_root = U._update_root(modules)
        ok('hazirlik klasoru modul kokunun altinda', update_root == os.path.join(root, '.update'), update_root)
        staging = tempfile.mkdtemp(prefix=U.STAGING_PREFIX, dir=_mkdir(update_root))
        io.open(U._pending_marker(modules), 'w', encoding='utf-8').write(u'{}')
        ok('modules/ klasorune dosya birakilmadi',
           not [f for f in os.listdir(modules) if f.startswith('.orange-update')], os.listdir(modules))
        ok('hazirlik klasoru dogrulanir', U._is_staging_dir(modules, staging)
           and not U._is_staging_dir(modules, os.path.join(modules, 'stage-x')))
        gone = ddi.uninstall(modules_dir=modules, shelf=False, clean_legacy=False)
        ok('kaldirma hazirlik klasorunu ve isareti siler',
           not os.path.exists(staging) and not os.path.exists(U._pending_marker(modules)) and not os.path.exists(root), gone)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        sys.modules.setdefault('blender_kontrol', bk)
    key = U._version_key
    ok('surum kurali: 1.0.0 > rc > beta', key('1.0.0') > key('1.0.0-rc1') > key('1.0.0-beta1') > key('0.9.9'))
    ok('on surum otomatik onerilmez', not U._should_offer('9.0.0-rc1', '0.9.0') and U._should_offer('9.0.0-rc1', '0.9.0', True))
    import urllib.error
    bk.set_setting('language', 'en')
    try:
        msg = U._friendly_error(urllib.error.URLError('getaddrinfo failed'))
        ok('cevrimdisi hata metni yol gosterir', 'internet' in msg.lower() and 'getaddrinfo' not in msg, msg)
    finally:
        bk.set_setting('language', 'auto')
    ok('denetim batch modunda sessiz', U.check_for_updates(force=True) is None and not U._checking)


def _mkdir(path):
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def _array_plugin_is_native():
    for name in cmds.pluginInfo(query=True, listPlugins=True) or []:
        try:
            path = cmds.pluginInfo(name, query=True, path=True) or ''
        except Exception:
            continue
        if 'orangeArray' in path:
            return path.lower().endswith('.mll')
    return False


def _mesh_fn(obj):
    sel = om.MSelectionList()
    sel.add(bk.modifiers._shape(obj))
    return om.MFnMesh(sel.getDagPath(0))


def test_modifier_fixes():
    """Inceleme duzeltmeleri: eski ayarlarla migrasyon, buyuk birlesme mesafesi, duzenlenmis mesh'te kenar
    eslemesi, Object Offset baglantisi, Mirror/Array bypass, grup kimligiyle eksen, UUID'li edit kafesi,
    Apply sonrasi yetim history, edit modunda shape -> transform normalizasyonu, panel scriptJob'lari."""
    M = bk.modifiers
    E = bk.editmode
    cmds.file(new=True, force=True)

    # 3: migrasyon eski merge / threshold degerlerini korur
    legacy = cmds.polyCube(name='fxLegacy')[0]
    M._set_base_value(legacy, M.MIRROR_MERGE_ATTR, False, 'bool')
    M._set_base_value(legacy, M.MIRROR_THRESHOLD_ATTR, 0.25)
    M._instance(legacy, 'mirror:x', [-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
    M.migrate_legacy_instances(legacy)
    migrated = [n for n, kind in M.history_modifiers(legacy) if kind == 'mirror']
    ok('migrasyon eski merge / threshold degerini korur', migrated
       and cmds.getAttr(migrated[0] + '.mergeMode') == M.MIRROR_MERGE_OFF
       and abs(cmds.getAttr(migrated[0] + '.mergeThreshold') - 0.25) < 1e-9,
       [(cmds.getAttr(n + '.mergeMode'), cmds.getAttr(n + '.mergeThreshold')) for n in migrated])

    # 10: baseInverseMatrix yalnizca Object Offset verilince bagli
    arr_base = cmds.polyCube(name='fxArrayOffset')[0]
    arr_node = M.add_array(arr_base, 3, 'x')
    inverse_plug = arr_node + '.baseInverseMatrix'
    ok('Array: ofsetsiz baseInverseMatrix bagli degil', not cmds.listConnections(inverse_plug))
    ok('Array: ofsetsiz 3 kopya uretir', cmds.polyEvaluate(arr_base, face=True) == 18)
    offset_ctrl = cmds.group(empty=True, name='fxOffsetCtrl')
    cmds.setAttr(offset_ctrl + '.translateY', 2.0)
    M.set_array_object_offset(arr_node, arr_base, offset_ctrl)
    ok('Array: ofset verilince baseInverseMatrix bagli',
       cmds.listConnections(inverse_plug) == [arr_base.split('|')[-1]], cmds.listConnections(inverse_plug, plugs=True))
    pts = _mesh_fn(arr_base).getPoints(om.MSpace.kObject)
    ok('Array: ofset dizide uygulanir', abs(pts[8].y - pts[0].y - 2.0) < 1e-6, pts[8].y - pts[0].y)
    M.set_array_object_offset(arr_node, arr_base, None)
    ok('Array: ofset kaldirilinca baseInverseMatrix ayrilir', not cmds.listConnections(inverse_plug)
       and not cmds.getAttr(arr_node + '.useObjectOffset'))
    # Eski sahne: baglanti zaten varken dogru degerlendirme surer
    cmds.connectAttr(arr_base + '.worldInverseMatrix[0]', inverse_plug, force=True)
    cmds.setAttr(arr_base + '.translateX', 5.0)
    ok('Array: eski sahnedeki surekli baglanti sonucu bozmaz', cmds.polyEvaluate(arr_base, face=True) == 18)

    # 15: Mirror grubu ve Array icin bypass (nodeState)
    byp = cmds.polyCube(name='fxBypass')[0]
    mir = M.add_mirror(byp, 'x')
    mir_y = M.set_mirror_axis(byp, 'y', True, node=mir)
    for n in (mir, mir_y):
        M.set_enabled(n, False)
    ok('Mirror grubu bypass: 6 yuz', cmds.polyEvaluate(byp, face=True) == 6 and not M.is_enabled(mir_y))
    for n in (mir, mir_y):
        M.set_enabled(n, True)
    ok('Mirror grubu yeniden acilir: 24 yuz', cmds.polyEvaluate(byp, face=True) == 24)
    byp_arr = M.add_array(byp, 2)
    M.set_enabled(byp_arr, False)
    ok('Array bypass', cmds.polyEvaluate(byp, face=True) == 24)
    M.set_enabled(byp_arr, True)
    ok('Array yeniden acilir', cmds.polyEvaluate(byp, face=True) == 48)

    # 1: eksen kutulari grup kimligiyle calisir; ilk dugum silinse de sonraki eksen degisimi hata vermez
    group_id = M._group_id_of(mir)
    bk.undoable(lambda: M.set_mirror_axis(byp, 'x', False, group_id=group_id))()
    ok('grup kimligiyle X ekseni kapatilir', not cmds.objExists(mir)
       and [cmds.getAttr(n + '.axis') for n in M._mirror_groups(byp).get(group_id, [])] == [1])
    z_node = bk.undoable(lambda: M.set_mirror_axis(byp, 'z', True, group_id=group_id))()
    ok('ilk dugum silindikten sonra ayni karta Z eklenir', z_node and M._group_id_of(z_node) == group_id
       and sorted(cmds.getAttr(n + '.axis') for n in M._mirror_groups(byp)[group_id]) == [1, 2])

    # 6: buyuk birlesme mesafesi hata vermez ve gecerli mesh uretir (Python ve .mll ayni)
    native = _array_plugin_is_native()   # eklenti ilk add_array ile yuklenir
    huge = cmds.polyCube(name='fxHugeMerge')[0]
    huge_node = M.add_array(huge, 3, 'x')
    cmds.setAttr(huge_node + '.mergeCopies', True)
    cmds.setAttr(huge_node + '.mergeDistance', 100.0)
    try:
        huge_faces = cmds.polyEvaluate(huge, face=True)
        huge_verts = cmds.polyEvaluate(huge, vertex=True)
        huge_error = None
    except Exception as exc:
        huge_faces, huge_verts, huge_error = -1, -1, exc
    ok('buyuk birlesme mesafesi hata vermez: bos mesh', huge_error is None and (huge_verts, huge_faces) == (0, 0),
       (huge_verts, huge_faces, huge_error))
    # Kismi cokme: yalnizca bir kenar birlesme mesafesinden kisa -> o dortgen ucgene doner, diger dortgen kalir
    collapse = cmds.polyPlane(name='fxCollapse', subdivisionsX=2, subdivisionsY=1, constructionHistory=False)[0]
    v0 = cmds.xform(collapse + '.vtx[0]', q=True, objectSpace=True, translation=True)
    cmds.xform(collapse + '.vtx[1]', objectSpace=True, translation=[v0[0] + 0.01, v0[1], v0[2]])
    collapse_node = M.add_array(collapse, 1)
    cmds.setAttr(collapse_node + '.mergeCopies', True)
    cmds.setAttr(collapse_node + '.mergeDistance', 0.05)
    try:
        collapse_fn = _mesh_fn(collapse)
        collapse_counts = sorted(collapse_fn.polygonVertexCount(i) for i in range(collapse_fn.numPolygons))
        collapse_verts = collapse_fn.numVertices
        collapse_error = None
    except Exception as exc:
        collapse_counts, collapse_verts, collapse_error = [], -1, exc
    collapse_ok = collapse_error is None and collapse_counts == [3, 4] and collapse_verts == 5
    ok('kisa kenar birlesmesi yuzu ucgene indirger, diger yuz kalir (%s)' % ('mll' if native else 'py'), collapse_ok,
       (collapse_counts, collapse_verts, collapse_error))

    # 5: birlesme kapaliyken duzenlenmis mesh'te kenar yumusakligi kopyalarda korunur
    edited = cmds.polyCube(name='fxEdgeMap')[0]
    cmds.polyExtrudeFacet(edited + '.f[0]', localTranslateZ=0.5)
    cmds.polySoftEdge(edited, angle=0.0, constructionHistory=True)
    cmds.polySoftEdge(edited + '.e[0:3]', angle=180.0, constructionHistory=True)
    src = _mesh_fn(edited)
    src_smooth = {}
    for e in range(src.numEdges):
        a, b = src.getEdgeVertices(e)
        src_smooth[(min(a, b), max(a, b))] = src.isEdgeSmooth(e)
    nv, src_edge_count = src.numVertices, src.numEdges   # add_array ayni shape'i cikti yapar; once oku
    M.add_array(edited, 2, relative=[0.0, 0.0, 0.0], constant=[5.0, 0.0, 0.0])
    out = _mesh_fn(edited)
    mismatches = []
    for e in range(out.numEdges):
        a, b = out.getEdgeVertices(e)
        key = (min(a % nv, b % nv), max(a % nv, b % nv))
        if src_smooth.get(key) != out.isEdgeSmooth(e):
            mismatches.append(e)
    edge_ok = out.numEdges == 2 * src_edge_count and not mismatches
    ok('birlesme kapali: kopyalarda kenar yumusakligi korunur (%s)' % ('mll' if native else 'py'), edge_ok,
       (len(mismatches), out.numEdges))

    # 4: Apply sonrasi eski kafesin ust history'si (polyCube, polyExtrude) yetim kalmaz
    orphan = cmds.polyCube(name='fxOrphan')[0]
    cmds.polyExtrudeFacet(orphan + '.f[1]', localTranslateZ=0.3)
    orphan_sub = M.add_subdivision(orphan, 1)
    M.add_history_modifier(orphan, 'triangulate')
    orphan_cage = M.cage_shape(orphan)
    cage_upstream = [n for n in cmds.listHistory(orphan_cage, pruneDagObjects=True) or [] if n != orphan_cage]
    cage_upstream_types = sorted(cmds.nodeType(n) for n in cage_upstream)
    bk.undoable(lambda: M.apply_history_modifier(orphan, orphan_sub))()
    orphan_history = cmds.listHistory(orphan, pruneDagObjects=True) or []
    ok('Apply: kafesin yetim ust history dugumleri silinir',
       [kind for _, kind in M.history_modifiers(orphan)] == ['triangulate']
       and cage_upstream_types == ['polyCube', 'polyExtrudeFace']
       and not [n for n in cage_upstream if cmds.objExists(n)]
       and 'polyCube' not in [cmds.nodeType(n) for n in orphan_history],
       [n for n in cage_upstream if cmds.objExists(n)])
    cmds.undo()
    ok('Apply yetim temizligi undo ile geri gelir', [kind for _, kind in M.history_modifiers(orphan)] == ['subdiv', 'triangulate']
       and 'polyCube' in [cmds.nodeType(n) for n in cmds.listHistory(orphan, pruneDagObjects=True) or []])

    # 8: edit modunda hilite kafes shape'ini verir; 1/2/3, Ctrl+0..5 ve panel transform'u bulmali
    ed = cmds.polyCube(name='fxEdit')[0]
    M.add_subdivision(ed, 1)
    cmds.select(ed)
    E.enter_edit('vertex')
    hilited = cmds.ls(hilite=True, long=True)
    ok('edit modu: kafes shape hilite', hilited and cmds.nodeType(hilited[0]) == 'mesh', hilited)
    ok('edit modu: edit_targets transform verir', E.edit_targets() == [cmds.ls(ed, long=True)[0]], E.edit_targets())
    ok('edit modu: active_mesh transform verir', M.active_mesh() == cmds.ls(ed, long=True)[0], M.active_mesh())
    E.enter_edit('face')
    ok('edit modu: 3 tusu yuz moduna gecer', E.current_comp() == 'face' and bk.core._state['kinds'] == ['face']
       and cmds.ls(hilite=True, long=True) == hilited, (E.current_comp(), cmds.ls(hilite=True)))
    bk.view.subdiv_level(3)
    ok('edit modu: Ctrl+3 Subdivision seviyesini degistirir', M.subdivision_level(ed) == 3, M.subdivision_level(ed))
    # 7: edit modunda yeniden adlandirma cikis durumunu kaybettirmez (UUID anahtari)
    ed_uuid = cmds.ls(ed, uuid=True)[0]
    renamed = cmds.rename(ed, 'fxEditRenamed')
    ok('edit kafesi UUID ile anahtarli', ed_uuid in M.EDIT_CAGES and len(M.EDIT_CAGES) == 1, list(M.EDIT_CAGES))
    E.exit_edit()
    out_shape = M._shape(renamed)
    ok('yeniden adlandirma sonrasi cikis referans gorunumu geri alir', not M.EDIT_CAGES
       and cmds.getAttr(out_shape + '.overrideDisplayType') == 0 and cmds.getAttr(M.cage_shape(renamed) + '.intermediateObject'))
    cmds.select(renamed)
    E.enter_edit('vertex')
    # mayapy'de scriptJob(event=...) None dondurur (olay dongusu yok); GUI denetimi tools/gui testinde.
    ok('PreFileNewOrOpened scriptJob kurulumu hata vermez', M._EDIT_JOB is None or cmds.scriptJob(exists=M._EDIT_JOB))
    restored = M.exit_all_source_edits()
    ok('exit_all_source_edits tum durumlari geri alir', restored == 1 and not M.EDIT_CAGES
       and cmds.getAttr(out_shape + '.overrideDisplayType') == 0)
    E.exit_edit()

    # 14: surukle-birak on denetimi (panel widget'lari mayapy'de kurulamaz: QGuiApplication; GUI testi ayri)
    dd = cmds.polyCube(name='fxDragDrop')[0]
    dd_sub = M.add_subdivision(dd, 1)
    dd_tri = M.add_history_modifier(dd, 'triangulate')
    dd_arr = M.add_array(dd, 2)
    ok('surukle-birak: bitisik Orange kartlari arasinda gecerli', M.can_move_history_card(dd, dd_arr, dd_sub)
       and M.can_move_history_card(dd, dd_sub, dd_tri, after=True) and not M.can_move_history_card(dd, dd_sub, dd_sub))
    # Orange disi Maya history dugumunu Triangulate ile Array arasina sok: ustunden gecis gecersiz
    foreign = cmds.createNode('polyTriangulate', name='fxForeignTriangulate')
    cmds.disconnectAttr(dd_tri + '.output', dd_arr + '.inputMesh')
    cmds.connectAttr(dd_tri + '.output', foreign + '.inputPolymesh')
    cmds.connectAttr(foreign + '.output', dd_arr + '.inputMesh')
    foreign_between = [n for n, kind in M.history_modifiers(dd)]
    ok('surukle-birak: yabanci Maya history ustunden gecis reddedilir',
       foreign_between == [dd_sub, dd_tri, dd_arr] and not M.can_move_history_card(dd, dd_sub, dd_arr, after=True)
       and M.can_move_history_card(dd, dd_sub, dd_tri))
    ok('close_panels acik panel yokken hata vermez', M.close_panels() is None and not M._open_panels())
    cmds.file(new=True, force=True)


def test_perf_fixes():
    """Performans duzeltmeleri: surukleme toplu nokta yazimi (kenar kaydir, loop cut coklu, kalinlastir) ayni
    geometriyi verir ve tek undo adimidir; bagsiz tuslar panel sorgusu yapmaz; ipucu onbellegi kisitla yenilenir."""
    import math

    class _Stub(object):
        def __init__(self):
            self.calls = {}

        def __getattr__(self, name):
            def hit(*_a, **_k):
                self.calls[name] = self.calls.get(name, 0) + 1
            return hit

    def pos(comp):
        return [round(v, 5) for v in cmds.xform(comp, q=True, ws=True, t=True)]

    stub = _Stub()
    S, L, V, MOD, E = bk.slide, bk.loopcut, bk.valuemodal, bk.modal, bk.events
    saved = (S.hint_bar, L.hint_bar, L.preview_overlay, V.hint_bar, MOD.hint_bar, MOD.preview_overlay, E._context)
    S.hint_bar = L.hint_bar = V.hint_bar = MOD.hint_bar = lambda: stub
    L.preview_overlay = MOD.preview_overlay = lambda: stub
    try:
        cmds.file(new=True, force=True)
        # -- kenar kaydirma: surukleme setPoints ile, bitiste xform (tek undo adimi)
        pl = cmds.polyPlane(name='pfSlide', sx=4, sy=4, w=4, h=4)[0]
        tool = S.EdgeSlide(None, 'edge')
        tool.obj = pl
        tool.fn, _dag = bk._mesh_fn(pl)
        tool.pts = tool.fn.getPoints(om.MSpace.kWorld)
        tool.cur = om.MPointArray(tool.pts)
        start = {v: pos('%s.vtx[%d]' % (pl, v)) for v in (6, 7, 8)}
        want = {6: om.MPoint(-0.7, 0.0, 0.3), 7: om.MPoint(0.1, 0.0, 0.3), 8: om.MPoint(0.9, 0.0, 0.3)}
        cmds.undoInfo(openChunk=True, chunkName='pf_slide')
        tool.chunk_open = True
        tool.undo_prev = cmds.undoInfo(q=True, stateWithoutFlush=True)
        cmds.undoInfo(stateWithoutFlush=False)
        tool._write_points({6: om.MPoint(-0.5, 0.0, 0.1), 7: om.MPoint(0.0, 0.0, 0.2)})   # ara kare
        tool._write_points(want)
        mid = pos(pl + '.vtx[7]')
        ok('kaydirma: surukleme sirasinda setPoints gorunur', mid == [0.1, 0.0, 0.3], mid)
        tool.finish(True)
        got = {v: pos('%s.vtx[%d]' % (pl, v)) for v in want}
        ok('kaydirma: sonuc geometri', all(got[v] == [round(want[v].x, 5), 0.0, round(want[v].z, 5)] for v in want), got)
        cmds.undo()
        ok('kaydirma: undo baslangica doner', {v: pos('%s.vtx[%d]' % (pl, v)) for v in start} == start and cmds.objExists(pl))
        cmds.redo()
        ok('kaydirma: redo sonucu getirir', {v: pos('%s.vtx[%d]' % (pl, v)) for v in want} == got)
        # -- loop cut coklu kesim kaydirma
        strip = cmds.polyPlane(name='pfStrip', sx=4, sy=1, w=4, h=1)[0]
        fn, dag = bk._mesh_fn(strip)
        mesh = {'fn': fn, 'poly': dag, 'matrix': dag.inclusiveMatrix(), 'transform': strip}
        edge = next(e for e in range(fn.numEdges)
                    if abs(fn.getPoint(fn.getEdgeVertices(e)[0]).x - fn.getPoint(fn.getEdgeVertices(e)[1]).x) < 1e-6
                    and fn.getPoint(fn.getEdgeVertices(e)[0]).x < -1.9)
        lc = L.LoopCut(None)
        lc.edge, lc.count = (strip, edge), 3
        pairs, lc.closed = bk._edge_ring_pairs(mesh, edge)
        lc.pairs = [(fn.getPoint(a, om.MSpace.kWorld), fn.getPoint(b, om.MSpace.kWorld)) for a, b in pairs]
        cmds.undoInfo(openChunk=True, chunkName='pf_loopcut')
        lc.chunk_open = True
        lc._cut()
        verts_before = lc.verts_before
        ok('loop cut: coklu kesim hazir', lc._prepare_multi() and len(lc.multi) == 15, len(getattr(lc, 'multi', [])))
        lc._apply_multi(0.05)
        lc._apply_multi(0.1)
        lc.multi_d = 0.1
        expect = {v: (a + (b - a) * (t0 + 0.1)) for v, a, b, t0 in lc.multi}
        lc.finish(True)
        got = all(pos('%s.vtx[%d]' % (strip, v)) == [round(p.x, 5), round(p.y, 5), round(p.z, 5)]
                  for v, p in expect.items())
        ok('loop cut: kaydirilmis kesim geometrisi', got and cmds.polyEvaluate(strip, vertex=True) == verts_before + 15)
        cmds.undo()
        ok('loop cut: undo kesimi kaldirir (tek adim)', cmds.polyEvaluate(strip, vertex=True) == verts_before)
        cmds.redo()
        ok('loop cut: redo kesim + kaydirma', cmds.polyEvaluate(strip, vertex=True) == verts_before + 15
           and pos('%s.vtx[%d]' % (strip, verts_before)) == [round(c, 5) for c in
                                                               (expect[verts_before].x, expect[verts_before].y,
                                                                expect[verts_before].z)])
        # -- kalinlastir / incelt (ValueModal + _set_points)
        cube = cmds.polyCube(name='pfFat')[0]
        cmds.select(cube + '.vtx[*]')
        data = bk.mesh._selected_vertex_data()
        before = {d[1]: pos('%s.vtx[%d]' % (cube, d[1])) for d in data}
        vm = V.ValueModal(None, 'T', lambda v: bk.mesh._set_points(data, [p + n * v for _o, _i, p, n in data]),
                          om.MPoint())
        cmds.undoInfo(openChunk=True, chunkName='pf_value')
        vm.chunk_open = True
        vm.undo_prev = cmds.undoInfo(q=True, stateWithoutFlush=True)
        cmds.undoInfo(stateWithoutFlush=False)
        vm.apply_fn(0.25)
        vm.apply_fn(0.5)
        vm.last_applied = vm.value = 0.5
        ok('kalinlastir: surukleme tek setPoints (xform yok)', data.meshes is not None and
           pos(cube + '.vtx[0]') == [round(c, 5) for c in (data[0][2] + data[0][3] * 0.5)])
        vm.finish(True)
        want = {d[1]: [round(c, 5) for c in (d[2] + d[3] * 0.5)] for d in data}
        ok('kalinlastir: sonuc geometri', {d[1]: pos('%s.vtx[%d]' % (cube, d[1])) for d in data} == want)
        cmds.undo()
        ok('kalinlastir: undo', {d[1]: pos('%s.vtx[%d]' % (cube, d[1])) for d in data} == before)
        cmds.redo()
        ok('kalinlastir: redo', {d[1]: pos('%s.vtx[%d]' % (cube, d[1])) for d in data} == want)
        # -- obje modu: pivot etrafinda yorunge (izlenen pivotlar, mutlak move -rpr)
        a = cmds.polyCube(name='pfOrbitA')[0]
        b = cmds.polyCube(name='pfOrbitB')[0]
        cmds.xform(a, t=(3, 0, 0))
        cmds.xform(b, t=(0, 0, 2))
        cmds.select(a, b)
        m = MOD.Modal('rotate', None)
        m.sel, m.edit, m.pivots, m.constraint = bk._sel(), False, None, None
        m.center = om.MPoint(1, 0, 0)
        m.frames = {'global': [om.MVector(1, 0, 0), om.MVector(0, 1, 0), om.MVector(0, 0, 1)]}
        m.obj_pos = m._object_pivots()
        q = om.MQuaternion(math.radians(90), om.MVector(0, 1, 0))
        m._orbit_objects(m.sel, m.center, rotation=q)
        exp_a = om.MVector(1, 0, 0) + (om.MVector(3, 0, 0) - om.MVector(1, 0, 0)).rotateBy(q)
        exp_b = om.MVector(1, 0, 0) + (om.MVector(0, 0, 2) - om.MVector(1, 0, 0)).rotateBy(q)
        got_a, got_b = cmds.xform(a, q=True, ws=True, rp=True), cmds.xform(b, q=True, ws=True, rp=True)
        ok('obje yorungesi: pivotlar dondurulmus', all(abs(x - y) < 1e-5 for x, y in zip(got_a, exp_a))
           and all(abs(x - y) < 1e-5 for x, y in zip(got_b, exp_b)), (got_a, got_b))
        m._orbit_objects(m.sel, m.center, rotation=q.inverse())
        got_a = cmds.xform(a, q=True, ws=True, rp=True)
        ok('obje yorungesi: ters donusle baslangic', all(abs(x - y) < 1e-5 for x, y in zip(got_a, (3, 0, 0))), got_a)
        # -- soft select kovalari aralik dizgileriyle
        sp = cmds.polyPlane(name='pfSoft', sx=10, sy=10, w=10, h=10)[0]
        cmds.softSelect(edit=True, softSelectEnabled=True, softSelectDistance=0.5)
        cmds.select(sp + '.vtx[44:46]', sp + '.vtx[54:56]')     # agirlik 1.0 kovasi: iki bitisik aralik
        ms = MOD.Modal('move', None)
        ms.edit = True
        buckets = ms._soft_buckets()
        cmds.softSelect(edit=True, softSelectEnabled=False)
        comps = [c for comps, _w in (buckets or []) for c in comps]
        flat = cmds.ls(comps, flatten=True)
        ok('soft select: kovalar aralik dizgisi (vtx[a:b])', buckets and any(':' in c for c in comps)
           and len(flat) == len(set(flat)) and len(flat) > len(comps), (len(comps), len(flat)))
        # -- yuz normali gruplu, normal cercevesi tembel
        cb = cmds.polyCube(name='pfNormal')[0]
        n = bk._face_normal([cb + '.f[0]', cb + '.f[1]', cb + '.f[4]'])
        fnc, _d = bk._mesh_fn(cb)
        brute = sum((fnc.getPolygonNormal(i, om.MSpace.kWorld) for i in (0, 1, 4)), om.MVector()).normal()
        ok('_face_normal gruplu = tek tek', n is not None and (n - brute).length() < 1e-9)
        cmds.select(cb + '.f[1]')
        mn = MOD.Modal('move', None)
        mn.sel, mn.edit, mn.orientation = bk._sel(), True, 'global'
        mn.view_dir, mn.right_dir, mn.up_dir = om.MVector(0, 0, -1), om.MVector(1, 0, 0), om.MVector(0, 1, 0)
        mn.frames = mn._frames()
        ok('normal cercevesi tembel', mn.frames['normal'] is None)
        zf = mn._frame('normal')[2]
        ok('normal cercevesi istenince hesaplanir', mn.frames['normal'] is not None
           and (zf - fnc.getPolygonNormal(1, om.MSpace.kWorld)).length() < 1e-6, zf)
        # -- ipucu onbellegi: kisit degisince yenilenir, degismezse ayni nesne
        mh = MOD.Modal('move', None)
        mh.orientation, mh.edit, mh.soft_on, mh.snap_on = 'global', False, False, False
        mh.pivot_mode, mh.snap_target, mh.last_value, mh.constraint = 'median', 'increment', 'D', None
        k1 = mh._hint_keys()
        ok('ipucu onbellegi: ayni durumda ayni nesne', mh._hint_keys() is k1 and mh._hint_static[0][1] is None)
        mh.constraint = ('x', 'global', False)
        html, _title, _value = mh._hint_html()
        ok('ipucu onbellegi: kisit degisince yenilenir', mh._hint_static[0][1] == ('x', 'global', False)
           and 'X' in html and 'global' in html)
        # -- kisit cizgisi yalniz degisince cizilir
        mh.center, mh.fixed_axis, mh.frames = om.MPoint(), None, {'global': m.frames['global']}
        mh._axis_line = lambda vec: [(0.0, 0.0), (10.0, 10.0)]
        stub.calls.clear()
        for _ in range(5):
            mh._draw_constraint()
        mh.constraint = ('y', 'global', False)
        mh._draw_constraint()
        ok('kisit cizgisi: 6 karede 2 cizim', stub.calls.get('show_lines') == 2, stub.calls)
        # -- bagsiz tus: panel sorgusu yok; bagli tus: var
        calls = []
        E._context = lambda: calls.append(1) or ('other', None)
        filt = E.BlenderFilter()
        T = QtCore.QEvent.Type
        M3 = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier
        unbound = QtGui.QKeyEvent(T.KeyPress, Qt.Key.Key_Y, M3, 0x15, 0, 0, 'y')
        res = filt._key(unbound, T.KeyPress)
        ok('bagsiz tus: _context cagrilmaz, olay Maya\'ya', res is False and not calls, calls)
        filt._key(QtGui.QKeyEvent(T.KeyRelease, Qt.Key.Key_Y, M3, 0x15, 0, 0, 'y'), T.KeyRelease)
        ok('bagsiz tus birakma: _context cagrilmaz', not calls)
        filt._key(QtGui.QKeyEvent(T.KeyPress, Qt.Key.Key_G, Qt.KeyboardModifier.NoModifier, 0x22, 0, 0, 'g'), T.KeyPress)
        ok('bagli tus: _context cagrilir', len(calls) == 1)
        combos = E._bound_combos()
        ok('bagli kume: tablolarin birlesimi', 'g' in combos and 'ctrl+r' in combos and 'alt+v' in combos
           and 'shift+f' in combos and 'ctrl+alt+shift+y' not in combos)
        km = sys.modules['blender_kontrol.keymap']
        orig_path, tmp = km._keymap_path, tempfile.mkdtemp(prefix='bk_perf_keymap_')
        km._keymap_path = lambda: os.path.join(tmp, 'keymap.json')
        try:
            bk._save_overrides({'g': 'ctrl+alt+shift+y'})
            bk._rebuild_keymap()
            ok('bagli kume: tablo yenilenince yenilenir', 'ctrl+alt+shift+y' in E._bound_combos())
        finally:
            km._keymap_path = orig_path
            bk._rebuild_keymap()
            shutil.rmtree(tmp, ignore_errors=True)
        # -- ayar onbellegi
        old = bk.setting('emulate_numpad')
        bk.set_setting('emulate_numpad', 1)
        c1 = bk.cached_setting('emulate_numpad')
        bk.set_setting('emulate_numpad', 0)
        ok('ayar onbellegi set_setting ile yenilenir', c1 == 1 and bk.cached_setting('emulate_numpad') == 0)
        bk.set_setting('emulate_numpad', old)
        # -- mesh grafigi onbellegi: yol basina tek kayit, sahne degisince temiz
        bk.picking._graph_cache.clear()
        gp = cmds.polyPlane(name='pfGraph', sx=2, sy=2)[0]
        gfn, gdag = bk._mesh_fn(gp)
        bk._mesh_graph(gfn, gdag.fullPathName())
        cmds.polyExtrudeFacet(gp + '.f[0]', localTranslateZ=0.2)
        # Topoloji degisti: eski MFnMesh'i kullanmak Maya'yi cokertebiliyor (PolyEngine); uygulama da her islemde
        # yeni MFnMesh alir.
        gfn, gdag = bk._mesh_fn(gp)
        bk._mesh_graph(gfn, gdag.fullPathName())
        ok('mesh grafigi: yol basina tek kayit', len(bk.picking._graph_cache) == 1, len(bk.picking._graph_cache))
        MOD._abort_modal()
        ok('mesh grafigi: sahne olayinda temizlenir', not bk.picking._graph_cache)
        shapes = bk._visible_mesh_shapes()
        ok('_visible_mesh_shapes = _visible_meshes', [t for t, _s in shapes] == bk._visible_meshes()
           and all(cmds.nodeType(s) == 'mesh' and s.startswith(t + '|') for t, s in shapes))
        # -- numpy tembel: compat paket importunda yuklemez
        src = io.open(os.path.join(REPO, 'blender_kontrol', 'compat.py'), encoding='utf-8').read()
        ok('numpy tembel import', 'import numpy' not in src.split('def _numpy')[0] and bk.compat._numpy() is not None)
    finally:
        S.hint_bar, L.hint_bar, L.preview_overlay, V.hint_bar, MOD.hint_bar, MOD.preview_overlay, E._context = saved
        cmds.softSelect(edit=True, softSelectEnabled=False)
        cmds.file(new=True, force=True)


def test_blender_primitives():
    """Shift+A primitifleri Blender varsayilanlariyla: duzlem 4 kose, kure 32x16, silindir / koni 32, torus 48x12."""
    cmds.file(new=True, force=True)
    want = {'plane': (4, 1), 'cube': (8, 6), 'sphere': (32 * 15 + 2, 32 * 16), 'cylinder': (64, 34),
            'cone': (33, 33), 'torus': (48 * 12, 48 * 12)}
    for kind, (verts, faces) in sorted(want.items()):
        node = bk.objects.primitive_fn(kind)()[0]
        got = (cmds.polyEvaluate(node, vertex=True), cmds.polyEvaluate(node, face=True))
        ok('Shift+A %s Blender varsayilani' % kind, got == (verts, faces), got)
    box = cmds.exactWorldBoundingBox(bk.objects.primitive_fn('cube')()[0])
    ok('Shift+A kup 2 birim', [round(v, 4) for v in box] == [-1, -1, -1, 1, 1, 1], box)
    cmds.file(new=True, force=True)


def test_destructive_edit():
    cmds.file(new=True, force=True)
    old = bk.setting('destructive_edit')
    try:
        bk.set_setting('destructive_edit', 1)
        c = cmds.polyCube(name='deCube')[0]
        cmds.delete(c, constructionHistory=True)
        cmds.select(c)
        bk.enter_edit('face')
        bk.undoable(lambda: cmds.polyExtrudeFacet(c + '.f[1]', localTranslateZ=0.5))()
        hist = [n for n in cmds.listHistory(c, pruneDagObjects=True) or [] if cmds.nodeType(n).startswith('poly')]
        ok('gecmis birakma: extrude gecmisi duzlesti', not hist and cmds.polyEvaluate(c, face=True) == 10, hist)
        cmds.undo()
        ok('tek undo adimi (islem + duzlestirme)', cmds.polyEvaluate(c, face=True) == 6, cmds.polyEvaluate(c, face=True))
        node = bk.modifiers.add_history_modifier(c, 'triangulate')
        bk.undoable(lambda: cmds.polyExtrudeFacet(c + '.f[1]', localTranslateZ=0.5))()
        ok('Orange modifier varken duzlestirme yok', cmds.objExists(node))
        bk.exit_edit()
        bk.set_setting('destructive_edit', 0)
        d = cmds.polyCube(name='deOff')[0]
        cmds.select(d)
        bk.enter_edit('face')
        bk.undoable(lambda: cmds.polyExtrudeFacet(d + '.f[1]', localTranslateZ=0.5))()
        ok('ayar kapali: gecmis kalir', cmds.ls(cmds.listHistory(d) or [], type='polyExtrudeFace'))
        bk.exit_edit()
    finally:
        bk.set_setting('destructive_edit', old)
        cmds.file(new=True, force=True)


def test_fbx_roundtrip():
    cmds.file(new=True, force=True)
    c = cmds.polyCube(name='fbxCube', w=2, h=3, d=4)[0]
    cmds.polySoftEdge(c, angle=0)
    cmds.select(c)
    path = os.path.join(tempfile.mkdtemp(prefix='orange_fbx_'), 'to_blender.fbx')
    out = bk.interop.export_for_blender(path)
    ok('FBX disa aktarildi', out and os.path.getsize(out) > 1000, out)
    text = io.open(out, 'rb').read()
    ok('FBX metre birimi (UnitScaleFactor 100)', b'UnitScaleFactor' in text)
    cmds.file(new=True, force=True)
    new = bk.interop.import_from_blender(out)
    ok('FBX ice aktarildi', len(new) == 1, new)
    if new:
        bb = cmds.exactWorldBoundingBox(new[0])
        size = [round(bb[3] - bb[0], 3), round(bb[4] - bb[1], 3), round(bb[5] - bb[2], 3)]
        ok('FBX gidis-donus boyut korunur', size == [2.0, 3.0, 4.0], size)
        fn, _dag = bk._mesh_fn(new[0])
        hard = [e for e in range(fn.numEdges) if not fn.isEdgeSmooth(e)]
        ok('FBX sert kenarlar korunur', len(hard) == 12, len(hard))
    cmds.file(new=True, force=True)


def test_vp2_overlay():
    """orange_overlay eklentisi: dugum sahneyi 'degisti' yapmaz, gizlenince silinir, kayda iz birakmaz."""
    ok('VP2 eklentisi yuklendi', bk.ui.load_overlay_plugin())
    cmds.file(new=True, force=True)
    cmds.file(modified=False)
    ov = bk.ui.Vp2Overlay()
    ov._ensure_node()
    ok('VP2 dugumu, sahne degismedi', cmds.objExists('orangeOverlayShape') and not cmds.file(q=True, modified=True))
    cmds.polyCube(name='vp2Cube')
    ov.hide()
    ok('gizleyince dugum silinir', not cmds.objExists('orangeOverlay'))
    path = os.path.join(tempfile.mkdtemp(prefix='orange_vp2_'), 'scene.ma').replace(os.sep, '/')
    cmds.file(rename=path)
    cmds.file(save=True, type='mayaAscii', force=True)
    text = io.open(path, encoding='utf-8', errors='replace').read()
    ok('kayitta Orange izi yok', 'orange' not in text.lower(), [line for line in text.splitlines() if 'orange' in line.lower()])
    bk.ui.shutdown_overlay()
    ok('kapatinca eklenti bosaltilir', not bk.ui.overlay_plugin_loaded())
    cmds.file(new=True, force=True)


def test_issue_fixes_1_1():
    """1.1.0: #8 bevel koseleri, #6 kamera tabanli secim, #9 proportional / orbit ayarlari."""
    # #8: cok segmentli bevel'de kose tek n-gon olmamali (Maya'nin kendi Bevel'i gibi dortgenlerle kapanir)
    def max_corner(subdivide):
        cmds.file(new=True, force=True)
        cube = cmds.polyCube(name='bevelCube')[0]
        cmds.polyBevel3(cube + '.e[*]', offsetAsFraction=False, offset=0.15, segments=3, mitering=0,
                        chamfer=True, subdivideNgons=subdivide)
        return max(len(cmds.polyInfo(cube + '.f[%d]' % i, faceToVertex=True)[0].split(':')[1].split())
                   for i in range(cmds.polyEvaluate(cube, face=True)))
    ngon, quads = max_corner(False), max_corner(True)
    ok('#8 bevel: subdivideNgons olmadan kose n-gon', ngon > 4, ngon)
    ok('#8 bevel: subdivideNgons ile kose en fazla dortgen', quads <= 4, quads)
    import inspect
    ok('#8 Ctrl+B subdivideNgons kullanir', 'subdivideNgons=True' in inspect.getsource(bk.mesh._bevel_comps))

    # #8 / #9: P profili (depth) geometriyi gercekten degistirir (fareyle ayarlanan ayar olu degil)
    def corner_point(depth):
        cmds.file(new=True, force=True)
        cube = cmds.polyCube(name='profCube')[0]
        node = cmds.polyBevel3(cube + '.e[0]', offsetAsFraction=False, offset=0.3, segments=3, chamfer=True,
                               subdivideNgons=True)[0]
        cmds.setAttr(node + '.depth', depth)
        pts = cmds.xform(cube + '.vtx[*]', q=True, ws=True, t=True)
        return [round(v, 4) for v in pts]
    ok('#9 P profil (depth) sekli degistirir', corner_point(1.0) != corner_point(-1.0))

    # #6: Wireframe / X-Ray'de arkadakiler de secilir, Solid'de yalniz gorunenler
    before = (cmds.selectPref(q=True, useDepth=True), cmds.selectPref(q=True, paintSelectWithDepth=True))
    bk.set_setting('auto_camera_select', 1)
    bk.mayaprefs.sync_camera_selection(True)
    through = (cmds.selectPref(q=True, useDepth=True), cmds.selectPref(q=True, paintSelectWithDepth=True))
    bk.mayaprefs.sync_camera_selection(False)
    solid = (cmds.selectPref(q=True, useDepth=True), cmds.selectPref(q=True, paintSelectWithDepth=True))
    ok('#6 wireframe / x-ray: camera based selection kapali', through == (False, False), through)
    ok('#6 solid: camera based selection acik', solid == (True, True), solid)
    bk.set_setting('auto_camera_select', 0)
    bk.mayaprefs.sync_camera_selection(True)
    ok('#6 ayar kapaliyken dokunulmaz', (cmds.selectPref(q=True, useDepth=True),) == (True,))
    bk.set_setting('auto_camera_select', 1)
    cmds.selectPref(useDepth=before[0], paintSelectWithDepth=before[1])

    # useDepth onceki degeri saklanir ve kaldirinca geri yuklenir (eski kurulumda da bir kez saklanir)
    for var in bk.mayaprefs._PREV_VARS.values():
        if cmds.optionVar(exists=var):
            cmds.optionVar(remove=var)
    cmds.selectPref(useDepth=False)
    bk.mayaprefs._save_maya_defaults()
    cmds.selectPref(useDepth=True)
    bk.mayaprefs._restore_maya_defaults()
    ok('#6 kaldirinca useDepth geri yuklenir', cmds.selectPref(q=True, useDepth=True) is False)
    ok('#6 kaldirinca saklanan degerler silinir',
       not any(cmds.optionVar(exists=v) for v in bk.mayaprefs._PREV_VARS.values()))
    cmds.selectPref(useDepth=before[0], paintSelectWithDepth=before[1])

    # #9: O proportional'i Orange ayari olarak acar; Maya soft select'i (renkli alan) acik birakmaz
    bk.set_setting('proportional', 0)
    cmds.softSelect(edit=True, softSelectEnabled=True)
    bk.mesh.toggle_soft_select()          # Maya'da acik olan durumdan: kapat
    ok('#9 O: Maya soft select acikken kapatir', not bk.setting('proportional')
       and not cmds.softSelect(q=True, softSelectEnabled=True))
    bk.mesh.toggle_soft_select()
    ok('#9 O: proportional acik ama renkli alan gorunmez', bool(bk.setting('proportional'))
       and not cmds.softSelect(q=True, softSelectEnabled=True))
    bk.mesh.toggle_soft_select()
    ok('#9 O: tekrar basinca kapanir', not bk.setting('proportional'))

    # #9: proportional yalniz islem sirasinda acilir ve kapanir (Modal yardimcilari)
    m = bk.Modal('move', 'modelPanel4')
    m.soft_temp = True
    cmds.softSelect(edit=True, softSelectEnabled=True)
    m._end_soft_temp()
    ok('#9 islem bitince gecici soft select kapanir', not cmds.softSelect(q=True, softSelectEnabled=True)
       and not m.soft_temp)

    # #9: Orbit Around Selection = tumble pivot + auto-set pivot (objectTumble degil)
    import inspect as _inspect
    src = _inspect.getsource(bk.mayaprefs._apply_camera_settings)
    ok('#9 orbit: localTumble=0 + autoSetPivot', 'localTumble=0' in src and 'autoSetPivot=True' in src)

    # #9: Ctrl+. origin duzenleme bagli
    ok('#9 Ctrl+. origin duzenle', bk.BINDINGS.get('ctrl+period', {}).get('fn') is bk.objects.toggle_origin_edit)
    cmds.file(new=True, force=True)


def test_issue_fixes_1_2():
    """1.2.0: #11 Array dondurme / olcek, #9 origin noktasi ve obje modunda F."""
    mods = bk.modifiers

    def bbox(node):
        return [round(v, 3) for v in cmds.exactWorldBoundingBox(node)]

    # #11: kopya basina dondurme / olcek gercekten geometriyi degistirir, birim degerde yardimci silinir
    cmds.file(new=True, force=True)
    cube = cmds.polyCube(name='arrCube')[0]
    node = mods.add_array(cube, 4, 'x')
    straight = bbox(cube)
    mods.set_array_step_transform(node, cube, rotation=[0.0, 30.0, 0.0])
    rotated = bbox(cube)
    ok('#11 Array dondurme sekli degistirir', rotated != straight, (straight, rotated))
    ok('#11 dondurme okunur', [round(v, 3) for v in mods.array_step_transform(node)[0]] == [0.0, 30.0, 0.0])
    ok('#11 Object Offset acik', bool(cmds.getAttr(node + '.useObjectOffset')))
    mods.set_array_step_transform(node, cube, scale=[0.8, 0.8, 0.8])
    ok('#11 olcek okunur', [round(v, 3) for v in mods.array_step_transform(node)[1]] == [0.8, 0.8, 0.8])
    ok('#11 olcek sekli degistirir', bbox(cube) != rotated)
    ok('#11 sahnede yeni transform yok', cmds.ls(type='transform') == cmds.ls(['persp', 'top', 'front', 'side', cube],
                                                                          type='transform') or
       not [t for t in cmds.ls(type='transform', long=True) if 'arrCube' not in t and t.split('|')[-1] not in
            ('persp', 'top', 'front', 'side')])

    # kullanicinin ofset objesiyle birlikte
    loc = cmds.spaceLocator(name='arrOffset')[0]
    cmds.setAttr(loc + '.tx', 0.5)
    mods.set_array_object_offset(node, cube, loc)
    compose, transform, mult = mods._array_offset_sources(node)
    ok('#11 ofset objesi + dondurme birlikte (multMatrix)', bool(compose and mult) and transform.endswith('arrOffset'))
    ok('#11 ofset objesi okunur', mods.array_object_offset(node).endswith('arrOffset'))
    mods.set_array_object_offset(node, cube, None)
    compose, transform, mult = mods._array_offset_sources(node)
    ok('#11 ofset objesi kaldirilinca dondurme kalir', bool(compose) and not transform and not mult
       and not cmds.ls(type='multMatrix'))
    mods.set_array_step_transform(node, cube, rotation=[0.0, 0.0, 0.0], scale=[1.0, 1.0, 1.0])
    ok('#11 birim degerde yardimci dugum silinir', not cmds.ls(type='composeMatrix')
       and not cmds.getAttr(node + '.useObjectOffset'))
    ok('#11 birim degerde sekil eskisi gibi', bbox(cube) == straight, (straight, bbox(cube)))
    mods.set_array_step_transform(node, cube, rotation=[0.0, 45.0, 0.0])
    mods.remove_history_modifier(node)
    ok('#11 Array kaldirilinca yardimci dugum kalmaz', not cmds.ls(type='composeMatrix') and not cmds.ls(type='multMatrix'))

    # #9: origin noktasi secili objelerde gorunur, secim kalkinca kapanir; undo / sahne degisti etkilenmez
    cmds.file(new=True, force=True)
    a = cmds.polyCube(name='dotA')[0]
    b = cmds.polyCube(name='dotB')[0]
    cmds.setAttr(b + '.displayRotatePivot', True)       # kullanicinin kendi actigi
    cmds.file(modified=False)
    bk.set_setting('origin_dots', 1)
    cmds.select(a, b)
    bk.cursor.update_origin_dots()
    ok('#9 secili objenin origin noktasi gorunur', cmds.getAttr(a + '.displayRotatePivot'))
    ok('#9 origin noktasi sahneyi degisti yapmaz', not cmds.file(q=True, modified=True))
    cmds.select(clear=True)
    bk.cursor.update_origin_dots()
    ok('#9 secim kalkinca origin noktasi kapanir', not cmds.getAttr(a + '.displayRotatePivot'))
    ok('#9 kullanicinin actigi pivot gostergesine dokunulmaz', cmds.getAttr(b + '.displayRotatePivot'))
    cmds.select(a)
    bk.cursor.update_origin_dots()
    bk.set_setting('origin_dots', 0)
    bk.cursor.update_origin_dots()      # onceki testler modulleri yeniden yukluyor: bu modulun durumuyla calistir
    ok('#9 ayar kapaninca origin noktasi kapanir', not cmds.getAttr(a + '.displayRotatePivot'))
    bk.set_setting('origin_dots', 1)
    bk.cursor.clear_origin_dots()

    # #9: F obje modunda secime odaklanir, edit modunda doldurur
    binding = bk.BINDINGS['f']
    ok('#9 F obje modunda secime odaklan', binding['fn'] is bk.mesh.fill_or_frame and binding['panel'])
    cmds.file(new=True, force=True)


def main():
    for fn in (test_i18n, test_keys, test_parse, test_mesh_helpers, test_selection_ops, test_mesh_ops, test_fill_corner, test_startup_guard, test_update_proxies,
               test_keymap_and_settings, test_grid_fill, test_modifiers, test_review_fixes, test_perf_fixes, test_modifier_fixes, test_update_fixes, test_blender_primitives,
               test_destructive_edit,
               test_fbx_roundtrip,
               test_vp2_overlay,
               test_issue_fixes_1_1,
               test_issue_fixes_1_2,
               test_installer):
        try:
            fn()
        except Exception:
            RESULTS.append((fn.__name__ + ' BEKLENMEYEN HATA', False, traceback.format_exc()[-500:]))
    failed = [r for r in RESULTS if not r[1]]
    for label, passed, detail in RESULTS:
        print(('OK ' if passed else 'XX ') + label + ('' if passed else '  -> ' + detail))
    print('%d test, %d gecti, %d kaldi' % (len(RESULTS), len(RESULTS) - len(failed), len(failed)))
    maya.standalone.uninitialize()
    return len(failed)


if __name__ == '__main__':
    sys.exit(main())
