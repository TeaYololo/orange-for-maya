# -*- coding: utf-8 -*-
"""G G kenar kaydirma / Shift+V kose kaydirma."""
from __future__ import absolute_import, division, print_function

import math

import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui2

from .compat import (CTRL, EV_KEY_PRESS, EV_MMOVE, EV_MPRESS, EV_SHORTCUT, LMB, Qt, QtCore, QtGui, QtWidgets, RMB,
    SHIFT, wrapInstance)
from .core import _current_filter_set_modal, _msg, _tip, _warn, run_after_op
from .i18n import _t
from .keys import _phys
from .util import _comps, _last_view_panel, _sel
from .ui import hint_bar
from .editmode import current_comp, in_edit
from .modal import Modal


# ---------------------------------------------------------------- kenar / kose kaydirma (G G, Shift+V)
class EdgeSlide(object):
    """Blender G G. Kenar modunda: secili kenarlarin koseleri komsu kenarlar (ray) boyunca kayar,
    fare bir yone cekince t>0 bir taraf, t<0 diger taraf. Kose modunda: her kose, fare yonune en uygun
    kenar boyunca kayar. Sayi yazilabilir (t), Ctrl adimli, Shift hassas.

    Kenar modunda E: esit mesafe (her kose referans kosenin kaydigi kadar kayar; yeni halka eskisine paralel).
    F: esit modda referansi karsi halkaya cevirir (yeni halka hedef halkaya paralel)."""

    def __init__(self, panel, mode=None):
        self.panel = panel
        self.mode = mode           # 'edge' | 'vertex' | None (secim moduna gore)
        self.timer = None
        self.chunk_open = False
        self.dirty = False
        self.numeric = ''
        self.applied = {}
        self.value = 0.0
        self.even = False
        self.flip = False

    # -- kurulum
    def start(self):
        if not in_edit():
            _msg(_t('Kaydırma için Tab ile edit moduna gir'))
            return False
        if self.mode is None:
            self.mode = 'vertex' if current_comp() == 'vertex' else 'edge'
        if self.mode == 'edge':
            edges = _comps('edge') or cmds.polyListComponentConversion(_comps('face'), toEdge=True) or []
            edges = cmds.ls(edges, flatten=True)
            verts = cmds.ls(cmds.polyListComponentConversion(edges, toVertex=True) or [], flatten=True)
        else:
            edges = []
            verts = cmds.ls(cmds.polyListComponentConversion(_sel(), toVertex=True) or [], flatten=True)
        if not verts:
            _msg(_t('Kaydırmak için kenar ya da köşe seç'))
            return False
        objs = set(v.split('.')[0] for v in verts)
        if len(objs) > 1:
            _msg(_t('Kaydırma tek bir mesh üzerinde çalışır'))
            return False
        self.obj = objs.pop()
        dag = om.MSelectionList().add(self.obj).getDagPath(0)
        try:
            dag.extendToShape()
        except Exception:
            pass
        fn = om.MFnMesh(dag)
        self.pts = fn.getPoints(om.MSpace.kWorld)
        sel = set(int(v.split('[')[-1].rstrip(']')) for v in verts)
        it = om.MItMeshVertex(dag)
        self.rails = {}
        for v in sel:
            it.setIndex(v)
            nbrs = list(it.getConnectedVertices())
            self.rails[v] = [n for n in nbrs if n not in sel] if self.mode == 'edge' else nbrs
        self.verts = [v for v in sel if self.rails[v]]
        if not self.verts:
            _msg(_t('Kayacak kenar bulunamadı (seçimin dışına çıkan kenar yok)'))
            return False
        self.view = omui2.M3dView.getM3dViewFromModelPanel(self.panel)
        self.widget = wrapInstance(int(self.view.widget()), QtWidgets.QWidget)
        self.raw_last = QtGui.QCursor.pos()
        self.eff = QtCore.QPointF(self.raw_last)
        self.start_pos = QtCore.QPointF(self.eff)
        if self.mode == 'edge':
            self._assign_sides(edges)
        cmds.undoInfo(openChunk=True, chunkName='blender_slide')
        self.chunk_open = True
        # surukleme kayitsiz (her karede kose basina bir xform kaydi birikiyordu); sonuc bitiste tek adim
        self.undo_prev = cmds.undoInfo(q=True, stateWithoutFlush=True)
        cmds.undoInfo(stateWithoutFlush=False)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(15)
        self.update(force=True)
        return True

    def _dir(self, a, b):
        d = om.MVector(self.pts[b] - self.pts[a])
        return d.normal() if d.length() > 1e-9 else d

    def _assign_sides(self, edges):
        """Her kose icin A ve B tarafi: secili kenarlar boyunca komsudan komsuya yon tutarliligiyla yay."""
        adj = {}
        for e in edges:
            ends = [int(v.split('[')[-1].rstrip(']'))
                    for v in cmds.ls(cmds.polyListComponentConversion(e, toVertex=True), flatten=True)]
            if len(ends) != 2:
                continue
            a, b = ends
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        mx, my = self._port(self.start_pos)

        def dist2(v):
            sx, sy = self._screen(self.pts[v])
            return (sx - mx) ** 2 + (sy - my) ** 2

        ref = min(self.verts, key=dist2)   # referans: fareye ekranda en yakin kose
        self.side_a, self.side_b = {}, {}
        dir_a, dir_b = {}, {}
        rails = self.rails[ref]
        self.side_a[ref] = rails[0]
        dir_a[ref] = self._dir(ref, rails[0])
        others = sorted(rails[1:], key=lambda n: self._dir(ref, n) * dir_a[ref])
        self.side_b[ref] = others[0] if others else None
        dir_b[ref] = self._dir(ref, others[0]) if others else -dir_a[ref]
        self.ref = ref
        queue, seen = [ref], {ref}
        while queue:
            v = queue.pop(0)
            for w in adj.get(v, ()):
                if w in seen:
                    continue
                seen.add(w)
                queue.append(w)
                self._pick_sides(w, dir_a[v], dir_b[v], dir_a, dir_b)
        for v in self.verts:      # baglantisiz parcalar: referans yonleriyle
            if v not in self.side_a:
                self._pick_sides(v, dir_a[ref], dir_b[ref], dir_a, dir_b)

    def _pick_sides(self, w, pa, pb, dir_a, dir_b):
        rails = self.rails.get(w) or []
        if not rails:
            self.side_a[w] = self.side_b[w] = None
            dir_a[w], dir_b[w] = pa, pb
            return
        a = max(rails, key=lambda n: self._dir(w, n) * pa)
        rest = [n for n in rails if n != a]
        b = max(rest, key=lambda n: self._dir(w, n) * pb) if rest else None
        self.side_a[w], self.side_b[w] = a, b
        dir_a[w] = self._dir(w, a)
        dir_b[w] = self._dir(w, b) if b is not None else -dir_a[w]

    # -- ekran
    def _port(self, global_pos):
        local = self.widget.mapFromGlobal(QtCore.QPointF(global_pos))
        sx = self.view.portWidth() / float(max(1, self.widget.width()))
        sy = self.view.portHeight() / float(max(1, self.widget.height()))
        return local.x() * sx, self.view.portHeight() - local.y() * sy

    def _screen(self, point):
        res = self.view.worldToView(om.MPoint(point))
        return float(res[0]), float(res[1])

    def _update_eff(self):
        raw = QtGui.QCursor.pos()
        d = raw - self.raw_last
        self.raw_last = raw
        factor = 0.1 if (Modal._mods() & SHIFT) else 1.0
        self.eff = QtCore.QPointF(self.eff.x() + d.x() * factor, self.eff.y() + d.y() * factor)
        return d.x() != 0 or d.y() != 0

    # -- hesap
    def _targets(self):
        """{kose: yeni_dunya_noktasi}"""
        num = Modal._parse(self.numeric) if self.numeric else None
        sx, sy = self._port(self.start_pos)
        mx, my = self._port(self.eff)
        dx, dy = mx - sx, my - sy
        ctrl = bool(Modal._mods() & CTRL)
        out = {}
        if self.mode == 'edge':
            if num is not None:
                t = num
            else:
                a = self._screen(self.pts[self.ref])
                b = self._screen(self.pts[self.side_a[self.ref]])
                ax, ay = b[0] - a[0], b[1] - a[1]
                t = (dx * ax + dy * ay) / max(1e-6, ax * ax + ay * ay)
            t = max(-1.0, min(1.0, t))
            if ctrl:
                t = round(t * 10) / 10.0
            self.value = t
            sides = self.side_a if t >= 0 else self.side_b
            ref_len = None
            if self.even and sides.get(self.ref) is not None:
                ref_len = om.MVector(self.pts[sides[self.ref]] - self.pts[self.ref]).length()
            for v in self.verts:
                n = sides.get(v)
                p = om.MPoint(self.pts[v])
                if n is not None:
                    vec = om.MVector(self.pts[n] - self.pts[v])
                    length = vec.length()
                    if ref_len is not None and length > 1e-9:
                        moved = abs(t) * ref_len                     # E: herkes ayni mesafe
                        if self.flip:
                            moved = length - (ref_len - moved)       # F: hedef halkadan ayni uzaklik
                        p = p + vec.normal() * max(0.0, min(length, moved))
                    else:
                        p = p + vec * abs(t)
                out[v] = p
            return out
        length = math.hypot(dx, dy)
        shown = 0.0
        for v in self.verts:
            p = om.MPoint(self.pts[v])
            if length > 2 or num is not None:
                a = self._screen(self.pts[v])
                best, best_cos, best_edge = None, -2.0, None
                for n in self.rails[v]:
                    b = self._screen(self.pts[n])
                    ex, ey = b[0] - a[0], b[1] - a[1]
                    el = math.hypot(ex, ey)
                    if el < 1e-6:
                        continue
                    c = (dx * ex + dy * ey) / (el * max(length, 1e-6))
                    if c > best_cos:
                        best, best_cos, best_edge = n, c, (ex, ey, el)
                if best is not None:
                    ex, ey, el = best_edge
                    f = num if num is not None else (dx * ex + dy * ey) / (el * el)
                    f = max(0.0, min(1.0, f))
                    if ctrl:
                        f = round(f * 10) / 10.0
                    shown = f
                    p = p + om.MVector(self.pts[best] - self.pts[v]) * f
            out[v] = p
        self.value = shown
        return out

    def update(self, force=False):
        moved = self._update_eff()
        if not force and not moved:
            return
        try:
            for v, p in self._targets().items():
                old = self.applied.get(v)
                if old is not None and (old - p).length() < 1e-9:
                    continue
                cmds.xform('%s.vtx[%d]' % (self.obj, v), worldSpace=True, translation=(p.x, p.y, p.z))
                self.applied[v] = p
                self.dirty = True
            self._show()
        except Exception as exc:
            _warn(_t('kaydırma: %s') % exc)
            self.finish(False)

    def _show(self):
        title = _t('KENAR KAYDIR' if self.mode == 'edge' else 'KÖŞE KAYDIR') + '  ·  %.2f' % self.value
        if self.even:
            title += '  ·  ' + (_t('eşit, çevrik') if self.flip else _t('eşit'))
        if self.numeric:
            title += '   [ %s ]' % self.numeric
        keys = [_t('<b>Fare</b> kaydır'), _t('<b>Shift</b> hassas'), _t('<b>Ctrl</b> adımlı'), _t('<b>Sayı</b> yaz')]
        if self.mode == 'edge':
            keys += [_t('<b>E</b> eşit mesafe'), _t('<b>F</b> çevir (eşit modda)')]
        keys += [_t('<b>Sol tık/Enter</b> onay'), _t('<b>Sağ tık/Esc</b> iptal')]
        html = ('<span style="color:#e8a33d; font-weight:bold">%s</span><br>%s'
                % (title, '&nbsp;&nbsp;·&nbsp;&nbsp;'.join(keys)))
        try:
            hint_bar().show(self.widget, html)
        except Exception:
            _tip(title)

    # -- olaylar
    def key(self, ev, etype):
        if etype == EV_SHORTCUT:
            ev.accept()
            return True
        if etype != EV_KEY_PRESS:
            return True
        key = int(ev.key())
        text = ev.text()
        if key in (int(Qt.Key.Key_Return), int(Qt.Key.Key_Enter), int(Qt.Key.Key_Space)):
            self.finish(True)
        elif key == int(Qt.Key.Key_Escape):
            self.finish(False)
        elif key == int(Qt.Key.Key_Backspace):
            self.numeric = '' if ev.modifiers() & CTRL else self.numeric[:-1]
            self.update(force=True)
        elif text and text in '0123456789.,-':
            if text == '-' and self.numeric:
                self.numeric = self.numeric[1:] if self.numeric.startswith('-') else '-' + self.numeric
            else:
                self.numeric += text
            self.update(force=True)
        elif key in (int(Qt.Key.Key_Shift), int(Qt.Key.Key_Control)):
            self.update(force=True)
        elif self.mode == 'edge' and not ev.isAutoRepeat() and _phys(ev)[0] in ('e', 'f'):
            if _phys(ev)[0] == 'e':
                self.even = not self.even
            else:
                self.flip = not self.flip
            self.update(force=True)
        return True

    def mouse(self, ev, etype, obj=None):
        if etype == EV_MPRESS:
            if ev.button() == LMB:
                self.finish(True)
            elif ev.button() == RMB:
                self.finish(False)
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
        prev = getattr(self, 'undo_prev', None)
        if prev is not None:
            final = dict(self.applied) if ok else {}
            for v in list(self.applied):               # baslangica don (kayitsiz)
                p = self.pts[v]
                cmds.xform('%s.vtx[%d]' % (self.obj, v), worldSpace=True, translation=(p.x, p.y, p.z))
            cmds.undoInfo(stateWithoutFlush=prev)
            self.undo_prev = None
            for v, p in final.items():                 # sonuc: tek undo adimi
                cmds.xform('%s.vtx[%d]' % (self.obj, v), worldSpace=True, translation=(p.x, p.y, p.z))
        if ok and self.chunk_open:
            run_after_op()
        if self.chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.chunk_open = False
        cmds.refresh()


def edge_slide(mode=None):
    """G G (edit modu) / Shift+V (kose kaydir) / Ctrl+E > Kenar kaydir."""
    panel = _last_view_panel()
    if not panel:
        return
    tool = EdgeSlide(panel, mode)
    _current_filter_set_modal(tool)
    if not tool.start():
        _current_filter_set_modal(None)
