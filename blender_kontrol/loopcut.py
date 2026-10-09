# -*- coding: utf-8 -*-
"""Ctrl+R loop cut (onizlemeli)."""
from __future__ import absolute_import, division, print_function

import maya.cmds as cmds
import maya.api.OpenMaya as om

from .compat import CTRL, EV_KEY_PRESS, EV_MMOVE, EV_MPRESS, EV_SHORTCUT, EV_WHEEL, LMB, Qt, QtCore, QtGui, RMB
from .core import _current_filter_set_modal, _msg, _warn, run_after_op
from .i18n import _t
from .util import _comp, _last_view_panel, _mesh_fn, _objs, _shape_type
from .ui import hint_bar, preview_overlay
from .picking import Picker, _edge_ring_pairs, _seg_dist
from .editmode import enter_edit, in_edit
from .modal import Modal


class LoopCut(object):
    """Blender Ctrl+R: kenarin uzerine gel (kesilecek halka vurgulanir), tekerlek =
    kesim sayisi, sol tik = kes (tek kesimde kaydir), ikinci sol tik = onay.

    Guvenlik: onizleme icin geometri olusturulmaz/silinmez (onceki surum Maya'yi
    cokertti); halka sadece secimle gosterilir, kesim tiklayinca bir kez yapilir.
    """

    def __init__(self, panel):
        self.panel = panel
        self.pairs = []
        self.closed = False
        self.count = 1
        self.node = None
        self.edge = None          # (transform, kenar_id)
        self.ends = None          # kenarin uc noktalari (dunya), kaydirma icin
        self.edges_before = 0
        self.state = 'hover'
        self.timer = None
        self.chunk_open = False
        self.last_pos = None

    def start(self):
        if not in_edit():
            objs = [o for o in _objs() if _shape_type(o) == 'mesh']
            if not objs:
                _msg(_t('Loop cut için bir mesh seç'))
                return False
            enter_edit('edge')
        self.picker = Picker(self.panel)
        if not self.picker.meshes:
            return False
        cmds.undoInfo(openChunk=True, chunkName='blender_loopcut')
        self.chunk_open = True
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(30)
        self.update(force=True)
        return True

    def _hover(self, pos):
        r = self.picker.edge(pos)
        if not r:
            return
        mesh, edge, _ = r
        key = (mesh['transform'], edge)
        if key == self.edge:
            return
        self.edge = key
        v0, v1 = mesh['fn'].getEdgeVertices(edge)
        self.ends = (self.picker._world(mesh, v0), self.picker._world(mesh, v1))
        pairs, self.closed = _edge_ring_pairs(mesh, edge)
        self.pairs = [(self.picker._world(mesh, a), self.picker._world(mesh, b)) for a, b in pairs]

    def _draw(self):
        """Blender'daki sari onizleme: kesimlerin nereden gececegini ciz."""
        if self.state != 'hover' or not self.pairs:
            preview_overlay().hide()
            return
        lines = []
        for k in range(1, self.count + 1):
            t = k / float(self.count + 1)
            pts = [self.picker.screen(a + (b - a) * t) for a, b in self.pairs]
            if self.closed:
                pts.append(pts[0])
            lines.append(pts)
        preview_overlay().show_lines(self.picker, lines)

    def _cut(self):
        obj, edge = self.edge
        self.edges_before = cmds.polyEvaluate(obj, edge=True)
        self.verts_before = cmds.polyEvaluate(obj, vertex=True)
        multi = self.count > 1
        # polySplitRing tek kenarla bir sey yapmiyor; halkanin tum kenarlari gerekli
        ring = cmds.polySelect(obj, edgeRing=edge, noSelection=True) or [edge]
        self.node = cmds.polySplitRing([_comp(obj, 'edge', e) for e in ring], constructionHistory=True,
                                       splitType=2 if multi else 1, divisions=self.count,
                                       weight=0.5, smoothingAngle=30, rootEdge=edge)[0]

    # -- coklu kesimde kaydirma: polySplitRing coklu modda agirlik kullanmiyor; yeni koseleri halka kenarlarina
    # esleyip hepsini birlikte kaydiriyoruz (Blender: kesimler araliklarini koruyarak birlikte kayar)
    def _prepare_multi(self):
        obj = self.edge[0]
        after = cmds.polyEvaluate(obj, vertex=True)
        if after <= self.verts_before or not self.pairs:
            return False
        fn, _dag = _mesh_fn(obj)
        box = fn.boundingBox
        tol = max(1e-6, max(box.width, box.height, box.depth) * 1e-4)
        n = self.count

        def key(p):
            return (int(round(p.x / tol)), int(round(p.y / tol)), int(round(p.z / tol)))
        lookup = {}
        for a, b in self.pairs:
            for k in range(1, n + 1):
                t0 = k / float(n + 1)
                lookup[key(a + (b - a) * t0)] = (a, b, t0)
        self.multi = []
        for v in range(self.verts_before, after):
            p = fn.getPoint(v, om.MSpace.kWorld)
            kx, ky, kz = key(p)
            hit = None
            for dx in (0, -1, 1):
                for dy in (0, -1, 1):
                    for dz in (0, -1, 1):
                        hit = hit or lookup.get((kx + dx, ky + dy, kz + dz))
            if hit:
                self.multi.append((v, hit[0], hit[1], hit[2]))
        if len(self.multi) < after - self.verts_before:
            return False   # esleme guvenilir degil: kaydirmadan bitir
        self.multi_obj = obj
        self.multi_dmax = 1.0 / (n + 1)
        self.multi_d = 0.0
        self.undo_prev = cmds.undoInfo(q=True, stateWithoutFlush=True)
        cmds.undoInfo(stateWithoutFlush=False)     # surukleme kayitsiz; sonuc finish'te tek adim
        return True

    def _apply_multi(self, d):
        for v, a, b, t0 in self.multi:
            p = a + (b - a) * (t0 + d)
            cmds.xform('%s.vtx[%d]' % (self.multi_obj, v), worldSpace=True, translation=(p.x, p.y, p.z))

    def update(self, force=False):
        pos = QtGui.QCursor.pos()
        if not force and pos == self.last_pos:
            return
        self.last_pos = pos
        try:
            if self.state == 'hover':
                self._hover(pos)
                self._draw()
                self._show()
            elif self.state == 'slide_multi':
                a = self.picker.screen(self.ends[0])
                b = self.picker.screen(self.ends[1])
                px, py = self.picker.port(pos)
                t = max(0.0, min(1.0, _seg_dist(px, py, a, b)[1]))
                f = max(-1.0, min(1.0, (t - 0.5) * 2.0))      # -1..1: dis kesimler kenar uclarina kadar
                if Modal._mods() & CTRL:
                    f = round(f * 10) / 10.0
                d = f * self.multi_dmax
                if abs(d - self.multi_d) > 1e-9:
                    self._apply_multi(d)
                    self.multi_d = d
                self._show('%.2f' % f)
            else:
                a = self.picker.screen(self.ends[0])
                b = self.picker.screen(self.ends[1])
                px, py = self.picker.port(pos)
                t = max(0.0, min(1.0, _seg_dist(px, py, a, b)[1]))
                if Modal._mods() & CTRL:
                    t = round(t * 10) / 10.0
                cmds.setAttr(self.node + '.weight', t)
                self._show('%.2f' % t)
        except Exception as exc:
            _warn(_t('loop cut: %s') % exc)
            self.finish(False)

    def _show(self, value=''):
        if self.state == 'hover':
            title = _t('LOOP CUT  ·  %d kesim') % self.count
            keys = [_t('<b>Kenarın üzerine gel</b> (sarı çizgi = kesim yeri)'),
                    _t('<b>Tekerlek / PageUp</b> kesim sayısı'), _t('<b>Sol tık</b> kes'),
                    _t('<b>Sağ tık/Esc</b> iptal')]
        else:
            title = _t('KAYDIR  ·  %s') % value
            keys = [_t('<b>Fare</b> kaydır'), _t('<b>Ctrl</b> adımlı'), _t('<b>Sol tık/Enter</b> onay'),
                    _t('<b>Sağ tık/Esc</b> ortala')]
        html = ('<span style="color:#e8a33d; font-weight:bold">%s</span><br>%s'
                % (title, '&nbsp;&nbsp;·&nbsp;&nbsp;'.join(keys)))
        hint_bar().show(self.picker.widget, html)

    def _set_count(self, delta):
        self.count = max(1, min(64, self.count + delta))
        self._draw()
        self._show()

    def _click(self):
        if self.timer is None:
            return   # bitmis arac: tekrar kesme
        if self.state == 'hover':
            if not self.edge:
                return
            preview_overlay().hide()
            self._cut()
            if self.count > 1:
                if self._prepare_multi():
                    self.state = 'slide_multi'
                    self.update(force=True)
                else:
                    self.finish(True)
            else:
                self.state = 'slide'
                self.update(force=True)
        else:
            self.finish(True)

    def key(self, ev, etype):
        if etype == EV_SHORTCUT:
            ev.accept()
            return True
        if etype != EV_KEY_PRESS:
            return True
        key = int(ev.key())
        if key in (int(Qt.Key.Key_Return), int(Qt.Key.Key_Enter), int(Qt.Key.Key_Space)):
            self._click()
        elif key == int(Qt.Key.Key_Escape):
            self._cancel()
        elif key in (int(Qt.Key.Key_PageUp), int(Qt.Key.Key_Plus)):
            self._set_count(1)
        elif key in (int(Qt.Key.Key_PageDown), int(Qt.Key.Key_Minus)):
            self._set_count(-1)
        return True

    def _cancel(self):
        if self.state == 'slide':
            cmds.setAttr(self.node + '.weight', 0.5)
            self.finish(True)
        elif self.state == 'slide_multi':
            self._apply_multi(0.0)          # Blender: sag tik = ortada onayla
            self.multi_d = 0.0
            self.finish(True)
        else:
            self.finish(False)

    def mouse(self, ev, etype, obj=None):
        if etype == EV_MPRESS:
            if ev.button() == LMB:
                self._click()
            elif ev.button() == RMB:
                self._cancel()
        elif etype == EV_WHEEL and self.state == 'hover':
            self._set_count(1 if ev.angleDelta().y() > 0 else -1)
        return etype != EV_MMOVE

    def _resume_undo(self):
        """Sahne degisince (_abort_modal) askidaki undo kaydini geri ac."""
        prev = getattr(self, 'undo_prev', None)
        if prev is not None:
            cmds.undoInfo(stateWithoutFlush=prev)
            self.undo_prev = None

    def finish(self, ok):
        if self.timer:
            self.timer.stop()
            self.timer = None
        try:
            hint_bar().hide()
        except Exception:
            pass
        _current_filter_set_modal(None)
        preview_overlay().hide()
        if getattr(self, 'undo_prev', None) is not None:     # coklu kaydirma: baslangica don, sonucu tek adim yaz
            final = self.multi_d if ok else 0.0
            self._apply_multi(0.0)
            cmds.undoInfo(stateWithoutFlush=self.undo_prev)
            self.undo_prev = None
            if abs(final) > 1e-9:
                self._apply_multi(final)
        ok = ok and self.node is not None
        if ok:
            # yeni kenarlari sec (Blender gibi)
            # yeni kenarlardan sadece iki ucu da yeni kose olanlar = yeni loop(lar)
            obj = self.edge[0]
            after = cmds.polyEvaluate(obj, vertex=True)
            if after > self.verts_before:
                new_verts = '%s.vtx[%d:%d]' % (obj, self.verts_before, after - 1)
                loops = cmds.polyListComponentConversion(new_verts, toEdge=True, internal=True)
                cmds.select(loops or new_verts, replace=True)
            if self.chunk_open:
                run_after_op()
        if self.chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.chunk_open = False
            # Bos bir undo adimini geri almak bir onceki islemi silerdi
            if not ok and self.node is not None:
                cmds.undo()


def loop_cut():
    panel = _last_view_panel()
    if not panel:
        return
    tool = LoopCut(panel)
    _current_filter_set_modal(tool)
    if not tool.start():
        _current_filter_set_modal(None)
