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
                               for f in ('__init__.py', 'i18n_en.py', 'installer.py', 'keymap.py')))
        ok('modul: __pycache__ yok', not os.path.exists(os.path.join(scripts, 'blender_kontrol', '__pycache__')))
        ok('modul: userSetup.py baslatir', 'blender_kontrol.install()' in io.open(os.path.join(scripts, 'userSetup.py'),
                                                                               encoding='utf-8').read())
        ok('modul: ikon', os.path.isfile(os.path.join(root, 'icons', 'orange.png')))
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
    # subdivision: smooth preview -> uygula
    c = cmds.polyCube(name='mdSub')[0]
    M.set_subdivision(c, 2)
    ok('subdiv onizleme topolojiye dokunmaz', M.subdivision_level(c) == 2 and cmds.polyEvaluate(c, face=True) == 6)
    M.apply_subdivision(c)
    ok('subdiv uygula', cmds.polyEvaluate(c, face=True) == 96 and M.subdivision_level(c) == 0, cmds.polyEvaluate(c, face=True))
    # mirror: canli instance, kilitli, secilemez; taban duzenlemesini izler; uygula dikisi kaynar, donusum korunur
    m = cmds.polyCube(name='mdMir', w=1, h=1, d=1)[0]
    cmds.move(0.5, 0, 0, m + '.vtx[*]', relative=True)     # geometri x 0..1: dikis x=0
    seam = [f for f in cmds.ls(m + '.f[*]', flatten=True)
            if all(abs(x) < 1e-6 for x in cmds.xform(f, q=True, os=True, t=True)[0::3])]
    cmds.delete(seam)                                        # yarim mesh: dikiste acik sinir (Blender'daki gibi)
    cmds.xform(m, ws=True, t=(3, 1, 0), ro=(0, 20, 0))
    before = _world_matrix(m)
    inst = M.add_mirror(m, 'x')
    ok('mirror instance', M.instance_modifiers(m) == [(inst, 'mirror:x')] and cmds.getAttr(inst + '.overrideDisplayType') == 2
       and cmds.getAttr(inst + '.tx', lock=True))
    ok('mirror instance aynali (obje uzayi)', round(cmds.exactWorldBoundingBox(inst)[0], 2) != round(cmds.exactWorldBoundingBox(m)[0], 2))
    shape = cmds.listRelatives(m, shapes=True)[0]
    cmds.move(0, 0.25, 0, m + '.vtx[0]', relative=True)
    ok('mirror tabani izler (ortak shape)', cmds.ls(shape, allPaths=True) and len(cmds.ls(shape, allPaths=True)) == 2)
    cmds.select(inst)
    ok('instance secimi -> taban', M.active_mesh() == cmds.ls(m, long=True)[0], M.active_mesh())
    M.apply_mirror(m, inst)
    ok('mirror uygula: dikis kaynadi', cmds.polyEvaluate(m, vertex=True) == 12 and not cmds.objExists(inst),
       cmds.polyEvaluate(m, vertex=True))
    ok('mirror uygula: donusum korundu', _world_matrix(m) == before)
    # array: 3 kopya -> birlestir, donusum / ad korunur
    a = cmds.polyCube(name='mdArr')[0]
    cmds.xform(a, ws=True, t=(0, 0, 5), ro=(0, 45, 0))
    before = _world_matrix(a)
    M.add_array(a, 3, 'x')
    ok('array 2 instance', len([i for i, k in M.instance_modifiers(a) if k == 'array']) == 2)
    res = M.apply_array(a)
    ok('array uygula', cmds.polyEvaluate(res, face=True) == 18 and res.split('|')[-1] == 'mdArr' and _world_matrix(res) == before,
       (cmds.polyEvaluate(res, face=True), res))
    # gecmis modifier'lari
    h = cmds.polyCube(name='mdHist')[0]
    node = M.add_history_modifier(h, 'bevel')
    ok('bevel modifier dugumu', node and M.kind_of(node) == 'bevel' and M.history_modifiers(h) == [(node, 'bevel')])
    # Blender gibi gercek pah: 6 + 12 + 8 kose ucgeni = 26 duzlem yuz; cok segmentte koseler dortgen, eski kenarda nokta yok
    for segs, want in ((1, 26), (2, 54), (3, 98)):
        cmds.setAttr(node + '.segments', segs)
        bad = _bevel_shape_problems(h, flat=(segs == 1))
        n_faces = cmds.polyEvaluate(h, face=True)
        ok('bevel %d segment gercek pah' % segs, not bad and (want is None or n_faces == want), (n_faces, bad[:5]))
    cmds.setAttr(node + '.segments', 1)
    faces = cmds.polyEvaluate(h, face=True)
    M.set_enabled(node, False)
    ok('modifier kapali', not M.is_enabled(node) and cmds.polyEvaluate(h, face=True) == 6, cmds.polyEvaluate(h, face=True))
    M.set_enabled(node, True)
    ok('modifier acik', cmds.polyEvaluate(h, face=True) == faces)
    M.remove_history_modifier(node)
    ok('modifier sil', cmds.polyEvaluate(h, face=True) == 6 and not M.history_modifiers(h))
    for kind in ('solidify', 'triangulate', 'weld'):
        n = M.add_history_modifier(h, kind)
        ok('%s modifier' % kind, n and M.kind_of(n) == kind)
    # hepsini uygula
    full = cmds.polyCube(name='mdAll')[0]
    M.set_subdivision(full, 1)
    M.add_mirror(full, 'z')
    M.add_history_modifier(full, 'triangulate')
    full = M.apply_all(full)
    hist = [n for n in cmds.listHistory(full, pruneDagObjects=True) or [] if cmds.nodeType(n).startswith('poly')]
    ok('hepsini uygula: gecmis ve instance kalmadi', not hist and not M.instance_modifiers(full), hist)
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


def main():
    for fn in (test_i18n, test_keys, test_parse, test_mesh_helpers, test_selection_ops, test_mesh_ops,
               test_keymap_and_settings, test_grid_fill, test_modifiers, test_blender_primitives, test_destructive_edit,
               test_fbx_roundtrip,
               test_vp2_overlay,
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
