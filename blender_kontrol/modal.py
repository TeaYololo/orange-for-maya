# -*- coding: utf-8 -*-
"""Modal G / R / S / extrude / inset / bevel (Blender transform modali)."""
from __future__ import absolute_import, division, print_function

import math
import re

import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui2

from .compat import (ALT, CTRL, EV_KEY_PRESS, EV_KEY_RELEASE, EV_MMOVE, EV_MPRESS, EV_MRELEASE, EV_SHORTCUT,
    EV_WHEEL, LMB, MMB, NOBTN, Qt, QtCore, QtGui, QtWidgets, RMB, SHIFT, wrapInstance)
from .core import _current_filter_set_modal, _filter, _msg, _tip, _warn, run_after_op
from .settings import FRAME_NAMES, PIVOT_NAMES, SNAP_NAMES, set_setting, setting
from .i18n import _t
from .keys import QT_KEYS, _phys
from .util import _face_normal, _last_view_panel, _sel, _visible_meshes
from .ui import AXIS_COLORS, NORMAL_COLOR, _hint_bar, _overlay, hint_bar, preview_overlay
from .picking import Picker
from .editmode import in_edit
from .cursor import cursor_node, cursor_pos


TRANSFORMS = ('move', 'rotate', 'scale', 'trackball')


class Modal(object):
    """Blender'daki G/R/S/E/I/Ctrl+B gibi fareyle calisan islemler.

    Pivot (orta nokta / sinir kutusu / imlec / aktif / tek tek) ve oryantasyon
    (global / lokal / normal / gorunum / imlec / ebeveyn) ayarlardan okunur;
    '.' ve ',' pie'lari ile degistirilir. Snap: Shift+Tab acar, Ctrl tersine cevirir.
    """

    TITLES = {
        'move': 'TAŞI',
        'rotate': 'DÖNDÜR',
        'trackball': 'SERBEST DÖNDÜR',
        'scale': 'ÖLÇEKLE',
        'attr_axis': 'EXTRUDE',
        'attr_dist': 'AYARLA',
    }
    UNIT_CM = {'mm': 0.1, 'cm': 1.0, 'm': 100.0, 'km': 100000.0, 'in': 2.54, 'ft': 30.48, 'yd': 91.44,
               'mi': 160934.4}

    def __init__(self, kind, panel, nodes=None, attr=None, axis=None, wheel_attr=None,
                 keep_undo=False, keys=None, key_hints=None):
        self.kind = kind
        self.panel = panel
        self.nodes = nodes or []
        self.attr = attr
        self.fixed_axis = axis
        self.wheel_attr = wheel_attr
        self.keys = keys or {}              # ek tuslar: ad -> fonksiyon(dugum)
        self.key_hints = key_hints or []    # HintBar'da gosterilecek aciklamalar
        self.constraint = None      # (eksen, cerceve_adi, duzlem_mi)
        self.numeric = ''
        self.expr_mode = False      # '=' ile ifade modu: harfler sayiya gider (pi, 2m, 90d...)
        self.applied = None
        self.prev_angle = None
        self.total_angle = 0.0
        self.track = []             # serbest dondurme adimlari (geri almak icin)
        self.auto_start = None      # orta tusla otomatik eksen
        self.auto_plane = False     # Shift+orta tus: otomatik duzlem
        self.fields = None          # Tab ile eksen eksen sayi girisi: ['1', '', '2']
        self.field_axis = 0
        self.timer = None
        self.chunk_open = keep_undo
        self.dirty = keep_undo      # geri alinacak bir sey var mi (bos undo onceki islemi siler)
        self.last_value = ''
        self.nav = None             # Alt+orta tusla gezinme surerken (kaynak, hedef)
        self.base_move = om.MVector()   # gezinme sonrasi kaldigi yerden devam icin
        self.base_angle = 0.0
        self.base_scale = 1.0
        self.base_dist = 0.0
        self.snap_picker = None
        self.pivots = None          # 'individual': [(bilesenler, MPoint)]
        self.frames = None

    # -- kurulum
    def start(self):
        self.sel = _sel()
        if not self.sel and not self.nodes:
            _msg(_t('Önce bir şey seç'))
            return False
        self.edit = in_edit()
        self.view = omui2.M3dView.getM3dViewFromModelPanel(self.panel)
        self.widget = wrapInstance(int(self.view.widget()), QtWidgets.QWidget)
        self._read_camera()
        self.pivot_mode = setting('pivot')
        self.orientation = setting('orientation')
        self.snap_on = bool(setting('snap_on'))
        self.snap_target = setting('snap_target')
        self.center, self.pivots = self._compute_pivot()
        self.frames = self._frames()
        self.buckets = self._soft_buckets() if self.kind in TRANSFORMS else None
        self.raw_last = QtGui.QCursor.pos()
        self.eff = QtCore.QPointF(self.raw_last)
        self.start_pos = QtCore.QPointF(self.eff)
        self.pivot_2d = self._to_screen(self.center)
        if self.kind in TRANSFORMS:
            self._reset_applied()
        if not self.chunk_open:
            cmds.undoInfo(openChunk=True, chunkName='blender_modal')
            self.chunk_open = True
        # Surukleme boyunca undo kaydi kapali: her karedeki move/rotate/setAttr ayri kayit olunca uzun bir
        # surukleme binlerce kayit biriktiriyor, geri alma saniyeler suruyordu. Bitiste baslangica donulur ve
        # toplam degisiklik tek islem olarak kaydedilir (bkz. finish / _commit).
        self.recorded = self.dirty          # chunk'ta modal oncesi kayitli islem var (extrude dugumu, rip ...)
        self.attr_start = _snapshot_attrs(self.nodes)
        self._suspend_undo()
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(15)
        self.update(force=True)
        return True

    # -- undo: surukleme kayitsiz, sonuc tek islem
    def _suspend_undo(self):
        self.undo_prev = cmds.undoInfo(q=True, stateWithoutFlush=True)
        cmds.undoInfo(stateWithoutFlush=False)

    def _resume_undo(self):
        prev = getattr(self, 'undo_prev', None)
        if prev is not None:
            cmds.undoInfo(stateWithoutFlush=prev)
            self.undo_prev = None

    def _final_state(self):
        applied = self.applied
        if isinstance(applied, om.MVector):
            applied = om.MVector(applied)
        return {'kind': self.kind, 'applied': applied, 'track': list(self.track),
                'attrs': dict((plug, cmds.getAttr(plug)) for plug in self.attr_start)}

    def _revert_all(self):
        """Undo kapaliyken: modal boyunca yapilan her seyi geri al (baslangic durumu)."""
        if self.kind in TRANSFORMS:
            self._revert()
        for plug, value in self.attr_start.items():
            try:
                if cmds.getAttr(plug) != value:
                    cmds.setAttr(plug, value)
            except Exception:
                pass

    def _commit(self, final):
        """Undo acikken: sonucu tek seferde uygula (geri al tek adim)."""
        for plug, value in final['attrs'].items():
            if value != self.attr_start.get(plug):
                cmds.setAttr(plug, value)
        kind, applied = final['kind'], final['applied']
        if kind == 'move' and applied is not None and applied.length() > 1e-9:
            self._do_move(applied)
        elif kind == 'rotate' and applied and abs(applied) > 1e-9:
            self._rotate_about(self._rotation_axis()[0], applied)
        elif kind == 'scale' and applied is not None and abs(applied - 1.0) > 1e-9:
            self._do_scale(1.0, applied)
        elif kind == 'trackball' and final['track']:
            q = om.MQuaternion()
            for axis, angle in final['track']:
                q = q * om.MQuaternion(angle, axis)      # q1 * q2: once q1, sonra q2
            axis, angle = q.asAxisAngle()
            self._rotate_about(axis, angle)

    def _read_camera(self):
        cam = om.MFnCamera(self.view.getCamera())
        self.view_dir = cam.viewDirection(om.MSpace.kWorld).normal()
        self.right_dir = cam.rightDirection(om.MSpace.kWorld).normal()
        self.up_dir = cam.upDirection(om.MSpace.kWorld).normal()

    # -- pivot
    def _points(self):
        """Secimin dunya noktalari (duz x,y,z,x,y,z... listesi)."""
        if self.kind in ('attr_axis', 'attr_dist') or self.edit:
            verts = cmds.polyListComponentConversion(self.sel, toVertex=True) or self.sel
            return cmds.xform(verts, q=True, worldSpace=True, translation=True) or [0, 0, 0]
        pts = []
        for obj in cmds.ls(self.sel, type='transform', long=True) or self.sel:
            pts += cmds.xform(obj, q=True, worldSpace=True, rotatePivot=True)
        return pts or [0, 0, 0]

    @staticmethod
    def _median(pts):
        n = max(1, len(pts) // 3)
        return om.MPoint(sum(pts[0::3]) / n, sum(pts[1::3]) / n, sum(pts[2::3]) / n)

    def _compute_pivot(self):
        mode = self.pivot_mode if self.kind in TRANSFORMS else 'median'
        pts = self._points()
        center = self._median(pts)
        pivots = None
        if mode == 'bbox':
            center = om.MPoint((min(pts[0::3]) + max(pts[0::3])) / 2.0,
                               (min(pts[1::3]) + max(pts[1::3])) / 2.0,
                               (min(pts[2::3]) + max(pts[2::3])) / 2.0)
        elif mode == 'cursor':
            center = cursor_pos()
        elif mode == 'active':
            p = self._active_point()
            if p is not None:
                center = p
        elif mode == 'individual':
            pivots = self._individual_pivots()
        return center, pivots

    def _active_point(self):
        if not self.edit:
            # obje modu: ls -sl sirasi (tek komutla coklu secimde orderedSelection ters donuyor)
            objs = cmds.ls(self.sel, type='transform', long=True) or []
            if not objs:
                return None
            return om.MPoint(*cmds.xform(objs[-1], q=True, worldSpace=True, rotatePivot=True))
        ordered = cmds.ls(orderedSelection=True, flatten=True, long=True) or []
        if not ordered:
            return None
        last = ordered[-1]
        if self.edit:
            verts = cmds.polyListComponentConversion(last, toVertex=True) or [last]
            pts = cmds.xform(verts, q=True, worldSpace=True, translation=True) or []
            return self._median(pts) if pts else None
        objs = cmds.ls(last, objectsOnly=True, long=True) or [last]
        return om.MPoint(*cmds.xform(objs[0], q=True, worldSpace=True, rotatePivot=True))

    def _individual_pivots(self):
        """Obje modu: her obje kendi pivotunda. Edit modu: her mesh'in secimi kendi ortasinda."""
        groups = []
        if self.edit:
            by_obj = {}
            for c in cmds.ls(self.sel, flatten=True, long=True) or []:
                by_obj.setdefault(c.split('.')[0], []).append(c)
            for comps in by_obj.values():
                verts = cmds.polyListComponentConversion(comps, toVertex=True) or comps
                pts = cmds.xform(verts, q=True, worldSpace=True, translation=True) or [0, 0, 0]
                groups.append((comps, self._median(pts)))
        else:
            for obj in cmds.ls(self.sel, type='transform', long=True) or []:
                groups.append(([obj], om.MPoint(*cmds.xform(obj, q=True, worldSpace=True, rotatePivot=True))))
        return groups or None

    # -- cerceveler (oryantasyon)
    def _local_axes(self):
        objs = cmds.ls(hilite=True, long=True) or cmds.ls(self.sel, objectsOnly=True, long=True) or []
        unit = [om.MVector(1, 0, 0), om.MVector(0, 1, 0), om.MVector(0, 0, 1)]
        if not objs:
            return unit
        obj = objs[-1]
        if cmds.nodeType(obj) != 'transform':
            obj = (cmds.listRelatives(obj, parent=True, fullPath=True) or [obj])[0]
        return self._matrix_axes(obj) or unit

    @staticmethod
    def _matrix_axes(node):
        try:
            m = cmds.xform(node, q=True, worldSpace=True, matrix=True)
        except Exception:
            return None
        return [om.MVector(m[0], m[1], m[2]).normal(), om.MVector(m[4], m[5], m[6]).normal(),
                om.MVector(m[8], m[9], m[10]).normal()]

    def _selection_normal(self):
        """Edit modunda secimin ortalama normali (dunya)."""
        faces = cmds.polyListComponentConversion(self.sel, toFace=True, internal=True) or []
        if faces:
            n = _face_normal(faces)
            if n is not None:
                return n
        verts = cmds.ls(cmds.polyListComponentConversion(self.sel, toVertex=True) or [], flatten=True, long=True)
        total = om.MVector()
        fns = {}
        for v in verts[:2000]:
            obj, idx = v.split('.vtx[')
            if obj not in fns:
                sl = om.MSelectionList()
                sl.add(obj)
                dag = sl.getDagPath(0)
                try:
                    dag.extendToShape()
                except Exception:
                    pass
                fns[obj] = om.MFnMesh(dag)
            total += fns[obj].getVertexNormal(int(idx.rstrip(']')), True, om.MSpace.kWorld)
        return total.normal() if total.length() > 1e-6 else None

    def _frames(self):
        unit = [om.MVector(1, 0, 0), om.MVector(0, 1, 0), om.MVector(0, 0, 1)]
        local = self._local_axes()
        view = [om.MVector(self.right_dir), om.MVector(self.up_dir), -om.MVector(self.view_dir)]
        normal = list(local)
        if self.edit:
            try:
                n = self._selection_normal()
            except Exception:
                n = None
            if n is not None:
                t = self.right_dir - n * (self.right_dir * n)
                if t.length() < 1e-6:
                    t = self.up_dir - n * (self.up_dir * n)
                x = t.normal()
                normal = [x, (n ^ x).normal(), om.MVector(n)]
        cursor = unit
        node = cursor_node(create=False)
        if node:
            cursor = self._matrix_axes(node) or unit
        parent = list(unit)
        objs = cmds.ls(hilite=True, long=True) or cmds.ls(self.sel, objectsOnly=True, long=True) or []
        if objs:
            obj = objs[-1]
            if cmds.nodeType(obj) != 'transform':
                obj = (cmds.listRelatives(obj, parent=True, fullPath=True) or [obj])[0]
            par = cmds.listRelatives(obj, parent=True, fullPath=True)
            if par:
                parent = self._matrix_axes(par[0]) or unit
        return {'global': unit, 'local': local, 'normal': normal, 'view': view,
                'cursor': cursor, 'parent': parent}

    def _frame(self, name=None):
        return self.frames.get(name or self.orientation) or self.frames['global']

    def _frame_euler(self, name):
        x, y, z = self._frame(name)
        m = om.MMatrix([x.x, x.y, x.z, 0, y.x, y.y, y.z, 0, z.x, z.y, z.z, 0, 0, 0, 0, 1])
        e = om.MTransformationMatrix(m).rotation(asQuaternion=False)
        return (math.degrees(e.x), math.degrees(e.y), math.degrees(e.z))

    def _soft_buckets(self):
        """Soft select acikken koseleri agirliklarina gore grupla.

        Maya'nin move/rotate/scale komutlari soft select'i uygulamiyor; her
        agirlik grubunu kendi oraninda donusturerek Blender'daki proportional
        editing'i taklit ediyoruz.
        """
        if not (self.edit and cmds.softSelect(q=True, softSelectEnabled=True)):
            return None
        suffix = {om.MFn.kMeshVertComponent: 'vtx', om.MFn.kMeshEdgeComponent: 'e',
                  om.MFn.kMeshPolygonComponent: 'f', om.MFn.kCurveCVComponent: 'cv'}
        groups = {}
        sel = om.MGlobal.getRichSelection().getSelection()
        for i in range(sel.length()):
            try:
                dag, comp = sel.getComponent(i)
            except Exception:
                continue
            if comp.isNull() or comp.apiType() not in suffix:
                continue
            fn = om.MFnSingleIndexedComponent(comp)
            path = dag.fullPathName()
            name = suffix[comp.apiType()]
            for k, idx in enumerate(fn.getElements()):
                w = fn.weight(k).influence if fn.hasWeights else 1.0
                if w < 1e-3:
                    continue
                groups.setdefault(round(w * 32) / 32.0, []).append('%s.%s[%d]' % (path, name, idx))
        return [(comps, w) for w, comps in sorted(groups.items())] or None

    def _targets(self):
        """[(bilesenler, agirlik, pivot)]"""
        if self.pivots:
            return [(comps, 1.0, piv) for comps, piv in self.pivots]
        return [(comps, w, self.center) for comps, w in (self.buckets or [(self.sel, 1.0)])]

    def _do_move(self, d):
        self.dirty = True
        for comps, w, _piv in self._targets():
            cmds.move(d.x * w, d.y * w, d.z * w, comps, relative=True, worldSpace=True)

    def _do_scale(self, old, new):
        self.dirty = True
        for comps, w, piv in self._targets():
            f = (1.0 + (new - 1.0) * w) / (1.0 + (old - 1.0) * w)
            if abs(f - 1.0) > 1e-9:
                cmds.scale(*self._scale_vector(f) + [comps], **self._scale_kwargs(piv))
                self._orbit_objects(comps, piv, scale=f)

    def _orbit_objects(self, comps, piv, scale=None, rotation=None):
        """Maya'nin rotate/scale -pivot bayragi transform'larda etkisiz (bilesenlerde calisir);
        obje modunda objenin pivotunu secilen pivot etrafinda kendimiz yorungeye sokariz."""
        if self.edit:
            return
        for obj in cmds.ls(comps, type='transform', long=True) or []:
            p = om.MVector(*cmds.xform(obj, q=True, worldSpace=True, rotatePivot=True))
            d = p - om.MVector(piv)
            if rotation is not None:
                d = d.rotateBy(rotation)
            else:
                sv = self._scale_vector(scale)
                axes = self._frame(self.constraint[1]) if self.constraint else self.frames['global']
                d = sum((axes[i] * ((d * axes[i]) * sv[i]) for i in range(3)), om.MVector())
            new = om.MVector(piv) + d
            if (new - p).length() > 1e-9:
                cmds.move(new.x - p.x, new.y - p.y, new.z - p.z, obj, relative=True, worldSpace=True)

    def _reset_applied(self):
        self.applied = {'move': om.MVector(), 'rotate': 0.0, 'scale': 1.0,
                        'trackball': None}.get(self.kind)
        self.base_move, self.base_angle, self.base_scale, self.base_dist = om.MVector(), 0.0, 1.0, 0.0
        self.prev_angle = None
        self.total_angle = 0.0
        self.track = []
        self.tb_last = QtCore.QPointF(self.eff) if hasattr(self, 'eff') else None

    # -- ekran / dunya donusumleri
    def _port(self, global_pos):
        local = self.widget.mapFromGlobal(QtCore.QPointF(global_pos))
        sx = self.view.portWidth() / float(max(1, self.widget.width()))
        sy = self.view.portHeight() / float(max(1, self.widget.height()))
        return local.x() * sx, self.view.portHeight() - local.y() * sy

    def _to_screen(self, point):
        res = self.view.worldToView(point)
        return float(res[0]), float(res[1])

    def _ray(self, global_pos):
        x, y = self._port(global_pos)
        near, far = om.MPoint(), om.MPoint()
        self.view.viewToWorld(int(round(x)), int(round(y)), near, far)
        return near, om.MVector(far - near).normal()

    def _plane_hit(self, global_pos, normal):
        origin, direction = self._ray(global_pos)
        denom = direction * normal
        if abs(denom) < 1e-8:
            return None
        t = (om.MVector(self.center - origin) * normal) / denom
        return origin + direction * t

    def _axis_vector(self):
        if self.fixed_axis is not None:
            return self.fixed_axis
        if self.constraint is None:
            return None
        axis, frame, _plane = self.constraint
        return om.MVector(self._frame(frame)['xyz'.index(axis)])

    def _plane(self):
        return bool(self.constraint and self.constraint[2])

    def _pixels_per_unit(self):
        a = self._to_screen(self.center)
        b = self._to_screen(self.center + self.right_dir)
        return max(1e-3, math.hypot(b[0] - a[0], b[1] - a[1]))

    # -- sayi girisi
    @classmethod
    def _parse(cls, text):
        """'2*3', '-1.5', '90d', '2m', '10cm', 'pi/2', 'sqrt(2)' -> float (sahne birimi / derece)."""
        expr = text.replace(',', '.').replace('°', 'd').strip().lower()
        if not expr:
            return None

        def unit_sub(mt):
            value, unit = float(mt.group(1)), mt.group(2)
            if unit in ('d', 'deg'):
                return repr(value)
            if unit in ('r', 'rad'):
                return repr(math.degrees(value))
            try:
                scene = cls.UNIT_CM.get(cmds.currentUnit(q=True, linear=True), 1.0)
            except Exception:
                scene = 1.0
            return repr(value * cls.UNIT_CM[unit] / scene)

        expr = re.sub(r'(\d+(?:\.\d+)?)\s*(mm|cm|km|mi|m|in|ft|yd|deg|rad|d|r)(?![a-z])', unit_sub, expr)
        if not re.match(r'^[0-9.+\-*/()\s a-z]+$', expr) or '__' in expr:
            return None
        names = {'pi': math.pi, 'e': math.e, 'sin': lambda a: math.sin(math.radians(a)),
                 'cos': lambda a: math.cos(math.radians(a)), 'tan': lambda a: math.tan(math.radians(a)),
                 'sqrt': math.sqrt, 'abs': abs}
        try:
            return float(eval(expr, {'__builtins__': {}}, names))
        except Exception:
            return None

    def _number(self):
        return self._parse(self.numeric)

    def _number_vector(self):
        """Tab ile girilen eksen bazli degerler (G 1 Tab 2 Enter) -> MVector ya da None."""
        if not self.fields:
            return None
        vals = [self._parse(f) or 0.0 for f in self.fields]
        axes = self._frame(self.constraint[1] if self.constraint else None)
        return axes[0] * vals[0] + axes[1] * vals[1] + axes[2] * vals[2]

    @staticmethod
    def _mods():
        return QtWidgets.QApplication.keyboardModifiers()

    def _ctrl(self):
        return bool(self._mods() & CTRL)

    def _fine(self):
        """Shift+Ctrl: ince adim (Blender: 0.1 birim / 1 derece / 0.01)."""
        return bool(self._mods() & SHIFT)

    def _snapping(self):
        """Snap acik mi: ayar XOR Ctrl (Blender: Ctrl gecici olarak tersine cevirir)."""
        return bool(self.snap_on) != self._ctrl()

    @staticmethod
    def _grid_step():
        try:
            return cmds.grid(q=True, spacing=True) / max(1, cmds.grid(q=True, divisions=True))
        except Exception:
            return 1.0

    def _snap_point(self, pos):
        """Snap hedefi kose/kenar/yuz: fare altindaki noktayi (dunya) dondur."""
        if self.snap_picker is None:
            if self.edit:
                excluded = set(cmds.ls(hilite=True, long=True) or [])
            else:
                excluded = set(cmds.ls(self.sel, type='transform', long=True) or [])
            meshes = [m for m in _visible_meshes() if m not in excluded]
            self.snap_picker = Picker(self.panel, meshes=meshes)
        pk = self.snap_picker
        if not pk.meshes:
            return None
        if self.snap_target == 'vertex':
            r = pk.nearest_vertex(pos)   # ekran uzayinda; kose siluette olsa da yakalar
            return pk._world(r[0], r[1]) if r else None
        if self.snap_target == 'edge':
            r = pk.edge(pos)
            if not r:
                return None
            mesh, e, t = r
            v0, v1 = mesh['fn'].getEdgeVertices(e)
            a, b = pk._world(mesh, v0), pk._world(mesh, v1)
            return a + (b - a) * t
        h = pk.hit(pos)
        return h[2] if h else None

    def _free_move(self):
        """Extrude sirasinda X/Y/Z ya da G: normal boyunca kilidi birak, serbest tasimaya gec."""
        for node in self.nodes:
            try:
                cmds.setAttr('%s.%s' % (node, self.attr), 0)
            except Exception:
                pass
        self.kind = 'move'
        self.nodes, self.attr, self.fixed_axis = [], None, None
        self.keys, self.key_hints = {}, []
        self.sel = _sel()
        self.edit = in_edit()
        self.center, self.pivots = self._compute_pivot()
        self.frames = self._frames()
        self.buckets = None
        self.numeric, self.fields, self.field_axis = '', None, 0
        self.start_pos = QtCore.QPointF(self.eff)
        self.pivot_2d = self._to_screen(self.center)
        self._reset_applied()

    # -- hesaplama
    def _move_value(self, pos):
        axis = self._axis_vector()
        plane = self._plane()
        vec = self._number_vector()
        if vec is not None:
            return vec
        num = self._number()
        if num is not None:
            frame = self._frame(self.constraint[1] if self.constraint else None)
            if axis is None:
                return frame[0] * num
            if plane:
                others = [frame[j] for j in range(3) if j != 'xyz'.index(self.constraint[0])]
                return (others[0] + others[1]) * num
            return axis * num
        if self.kind == 'move' and self.snap_target != 'increment' and self._snapping():
            p = self._snap_point(pos)
            if p is not None:
                delta = om.MVector(p - self.center)
                if axis is not None and not plane:
                    return axis * (delta * axis)
                if plane:
                    return delta - axis * (delta * axis)
                return delta
        if axis is None:
            normal = self.view_dir
        elif plane:
            normal = axis if abs(axis * self.view_dir) > 0.05 else self.view_dir
        else:
            normal = axis ^ (self.view_dir ^ axis)
            normal = normal.normal() if normal.length() > 1e-6 else self.view_dir
        a = self._plane_hit(self.start_pos, normal)
        b = self._plane_hit(pos, normal)
        if a is None or b is None:
            return None
        delta = om.MVector(b - a) + self.base_move
        if axis is not None and not plane:
            amount = delta * axis
            if self._snapping():
                step = self._grid_step() * (0.1 if self._fine() else 1.0)
                amount = round(amount / step) * step
            return axis * amount
        if plane:
            delta = delta - axis * (delta * axis)
        if self._snapping():
            step = self._grid_step() * (0.1 if self._fine() else 1.0)
            delta = om.MVector(*[round(v / step) * step for v in (delta.x, delta.y, delta.z)])
        return delta

    def _rotate_value(self, pos):
        """Eksen etrafinda uygulanacak isaretli aci (radyan)."""
        num = self._number()
        if num is not None:
            return math.radians(num)
        value = self.base_angle + self._mouse_angle(pos) * self._rotation_axis()[1]
        if self._snapping():
            step = 1.0 if self._fine() else 5.0
            value = math.radians(round(math.degrees(value) / step) * step)
        return value

    def _mouse_angle(self, pos):
        x, y = self._port(pos)
        angle = math.atan2(y - self.pivot_2d[1], x - self.pivot_2d[0])
        if self.prev_angle is None:
            sx, sy = self._port(self.start_pos)
            self.prev_angle = math.atan2(sy - self.pivot_2d[1], sx - self.pivot_2d[0])
        diff = (angle - self.prev_angle + math.pi) % (2 * math.pi) - math.pi
        self.prev_angle = angle
        self.total_angle += diff
        return self.total_angle

    def _rotation_axis(self):
        to_viewer = -self.view_dir
        axis = self._axis_vector()
        if axis is None:
            return to_viewer, 1.0
        return axis, (1.0 if axis * to_viewer >= 0 else -1.0)

    def _scale_value(self, pos):
        num = self._number()
        if num is not None:
            return num if abs(num) > 1e-4 else 1e-4
        sx, sy = self._port(self.start_pos)
        x, y = self._port(pos)
        d0 = max(1.0, math.hypot(sx - self.pivot_2d[0], sy - self.pivot_2d[1]))
        value = self.base_scale * math.hypot(x - self.pivot_2d[0], y - self.pivot_2d[1]) / d0
        if self._snapping():
            q = 100.0 if self._fine() else 10.0
            value = round(value * q) / q
        return max(0.001, value)

    def _dist_value(self, pos):
        num = self._number()
        if num is not None:
            return max(0.0, num)
        sx, sy = self._port(self.start_pos)
        x, y = self._port(pos)
        d0 = math.hypot(sx - self.pivot_2d[0], sy - self.pivot_2d[1])
        d1 = math.hypot(x - self.pivot_2d[0], y - self.pivot_2d[1])
        value = self.base_dist + abs(d1 - d0) / self._pixels_per_unit()
        if self._snapping():
            q = 100.0 if self._fine() else 10.0
            value = round(value * q) / q
        return value

    # -- uygulama
    def _scale_vector(self, factor):
        if self.constraint is None:
            return [factor] * 3
        idx = 'xyz'.index(self.constraint[0])
        if self._plane():
            return [1.0 if i == idx else factor for i in range(3)]
        return [factor if i == idx else 1.0 for i in range(3)]

    def _scale_kwargs(self, pivot):
        kwargs = {'relative': True}
        if self.edit:
            # obje modunda pivot verilmez: Maya onu scalePivotTranslate ile telafi eder,
            # biz konumu _orbit_objects ile translate uzerinden degistiriyoruz (Blender gibi)
            kwargs['pivot'] = (pivot.x, pivot.y, pivot.z)
        if self.constraint is None:
            return kwargs
        frame = self.constraint[1]
        if frame == 'global' and self.edit:
            kwargs['worldSpace'] = True
        elif frame == 'local' or not self.edit:
            kwargs['objectSpace'] = True   # Maya transform'u dunya ekseninde olceklenemez (shear yok)
        else:
            kwargs['worldSpace'] = True
            kwargs['orientAxes'] = self._frame_euler(frame)
        return kwargs

    def _rotate_about(self, axis, angle):
        if abs(angle) < 1e-9:
            return
        self.dirty = True
        for comps, w, piv in self._targets():
            q = om.MQuaternion(angle * w, axis)
            euler = q.asEulerRotation()
            kwargs = {'relative': True, 'worldSpace': True}
            if self.edit:
                kwargs['pivot'] = (piv.x, piv.y, piv.z)   # obje modunda: bkz. _orbit_objects
            cmds.rotate(math.degrees(euler.x), math.degrees(euler.y), math.degrees(euler.z), comps, **kwargs)
            self._orbit_objects(comps, piv, rotation=q)

    def _update_eff(self):
        """Shift basiliyken fare 10 kat yavas etki eder (hassas mod)."""
        raw = QtGui.QCursor.pos()
        d = raw - self.raw_last
        self.raw_last = raw
        factor = 0.1 if (self._mods() & SHIFT) else 1.0
        self.eff = QtCore.QPointF(self.eff.x() + d.x() * factor, self.eff.y() + d.y() * factor)
        return d.x() != 0 or d.y() != 0

    def _auto_constraint(self):
        """Orta tusla surukleyince fareye en uygun ekseni sec (Shift ile: o eksen haric duzlem)."""
        dx = self.eff.x() - self.auto_start.x()
        dy = -(self.eff.y() - self.auto_start.y())
        length = math.hypot(dx, dy)
        if length < 12:
            return
        frame = self.constraint[1] if self.constraint else self.orientation
        axes = self._frame(frame)
        best, best_score = None, -1.0
        scores = {}
        for i, axis in enumerate('xyz'):
            a = self._to_screen(self.center)
            b = self._to_screen(self.center + axes[i])
            sx, sy = b[0] - a[0], b[1] - a[1]
            slen = math.hypot(sx, sy)
            if slen < 1e-6:
                continue
            if self.kind == 'move':
                score = abs(sx * dx + sy * dy) / (slen * length)
            else:  # dondurmede ekrana en dik eksen
                score = 1.0 - slen / max(1e-6, self._pixels_per_unit())
            scores[axis] = score
            if score > best_score:
                best, best_score = axis, score
        if self.auto_plane and scores:
            best = min(scores, key=scores.get)   # fareye en az uyan eksen haric tutulur
        if best and (not self.constraint or self.constraint[0] != best or self.constraint[2] != self.auto_plane):
            self._revert()
            self.constraint = (best, frame, self.auto_plane)

    def update(self, force=False):
        if self.nav is not None:
            return
        moved = self._update_eff()
        if not force and not moved:
            return
        pos = self.eff
        try:
            if self.auto_start is not None and self.kind in TRANSFORMS:
                self._auto_constraint()
            if self.kind == 'move':
                value = self._move_value(pos)
                if value is None:
                    return
                d = value - self.applied
                if d.length() > 1e-9:
                    self._do_move(d)
                    self.applied = value
                self.last_value = 'D: %.3f  %.3f  %.3f' % (value.x, value.y, value.z)
            elif self.kind == 'rotate':
                value = self._rotate_value(pos)
                self._rotate_about(self._rotation_axis()[0], value - self.applied)
                self.applied = value
                self.last_value = '%.1f°' % math.degrees(value)
            elif self.kind == 'trackball':
                dx = pos.x() - self.tb_last.x()
                dy = -(pos.y() - self.tb_last.y())
                self.tb_last = QtCore.QPointF(pos)
                for axis, angle in ((self.up_dir, dx * 0.01), (self.right_dir, -dy * 0.01)):
                    if abs(angle) > 1e-9:
                        self._rotate_about(axis, angle)
                        self.track.append((axis, angle))
                self.last_value = ''
            elif self.kind == 'scale':
                value = self._scale_value(pos)
                if abs(value - self.applied) > 1e-9:
                    self._do_scale(self.applied, value)
                    self.applied = value
                self.last_value = '%.3f' % value
            elif self.kind == 'attr_axis':
                value = self._move_value(pos)
                if value is None:
                    return
                amount = value * self.fixed_axis
                for node in self.nodes:
                    cmds.setAttr('%s.%s' % (node, self.attr), amount)
                self.last_amount = amount
                self.last_value = '%.3f' % amount
            elif self.kind == 'attr_dist':
                value = self._dist_value(pos)
                for node in self.nodes:
                    cmds.setAttr('%s.%s' % (node, self.attr), value)
                self.last_amount = value
                self.last_value = '%.3f' % value
            self._show()
        except Exception as exc:
            _warn(_t('modal: %s') % exc)
            self.finish(False)

    def _revert(self):
        """Eksen/mod degisince o ana kadar yapilani geri al."""
        if self.kind == 'rotate':
            self._rotate_about(self._rotation_axis()[0], -self.applied)
        elif self.kind == 'trackball':
            for axis, angle in reversed(self.track):
                self._rotate_about(axis, -angle)
        elif self.kind == 'scale' and abs(self.applied - 1.0) > 1e-9:
            self._do_scale(self.applied, 1.0)
        elif self.kind == 'move' and self.applied.length() > 1e-9:
            self._do_move(-self.applied)
        self._reset_applied()

    def _after_nav(self):
        """Alt+orta tusla gezinme bitti: kamera degisti, kaldigi degerden devam et."""
        self._read_camera()
        if self.frames is not None:
            self.frames['view'] = [om.MVector(self.right_dir), om.MVector(self.up_dir), -om.MVector(self.view_dir)]
        self.raw_last = QtGui.QCursor.pos()
        self.eff = QtCore.QPointF(self.raw_last)
        self.start_pos = QtCore.QPointF(self.eff)
        self.tb_last = QtCore.QPointF(self.eff)
        self.pivot_2d = self._to_screen(self.center)
        self.prev_angle = None
        self.total_angle = 0.0
        if self.kind == 'move':
            self.base_move = om.MVector(self.applied)
        elif self.kind == 'rotate':
            self.base_angle = self.applied
        elif self.kind == 'scale':
            self.base_scale = self.applied
        elif self.kind == 'attr_axis':
            self.base_move = om.MVector(self.fixed_axis) * getattr(self, 'last_amount', 0.0)
        elif self.kind == 'attr_dist':
            self.base_dist = getattr(self, 'last_amount', 0.0)
        self.snap_picker = None
        self._show()

    # -- kisit ekseni cizgisi (Blender: secili eksen viewport'ta renkli cizgi)
    def _axis_line(self, vec):
        """Pivottan gecen, vec yonunde, viewport'u boydan boya kesen ekran cizgisi (port koordinati)."""
        a = self._to_screen(self.center)
        step = 50.0 / self._pixels_per_unit()      # ~50 piksellik dunya uzunlugu
        b = self._to_screen(self.center + vec * step)
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1e-3:
            return None      # eksen ekrana dik: cizgi nokta olur
        far = 2.0 * (self.view.portWidth() + self.view.portHeight())
        dx, dy = dx / length * far, dy / length * far
        return [(a[0] - dx, a[1] - dy), (a[0] + dx, a[1] + dy)]

    def _draw_constraint(self):
        lines, colors = [], []
        if self.constraint is not None and self.kind != 'trackball':
            axis, frame, plane = self.constraint
            axes = self._frame(frame)
            names = [n for n in 'xyz' if n != axis] if plane else [axis]
            for n in names:
                line = self._axis_line(om.MVector(axes['xyz'.index(n)]))
                if line:
                    lines.append(line)
                    colors.append(AXIS_COLORS[n])
        elif self.kind == 'attr_axis' and self.fixed_axis is not None:
            line = self._axis_line(om.MVector(self.fixed_axis))
            if line:
                lines.append(line)
                colors.append(NORMAL_COLOR)
        try:
            if lines:
                preview_overlay().show_lines(self, lines, colors)
            else:
                preview_overlay().hide()
        except Exception:
            pass

    # -- ipucu
    def _show(self):
        self._draw_constraint()
        title = _t(self.TITLES[self.kind])
        if self.constraint:
            axis, frame, plane = self.constraint
            what = (_t('%s hariç düzlem') if plane else _t('%s ekseni')) % axis.upper()
            title += '  ·  %s (%s)' % (what, _t(FRAME_NAMES.get(frame, frame)))
        if self.kind in TRANSFORMS:
            title += '  ·  pivot: %s' % _t(PIVOT_NAMES.get(self.pivot_mode, self.pivot_mode))
            if self.snap_on:
                title += '  ·  snap: %s' % _t(SNAP_NAMES.get(self.snap_target, self.snap_target))
        value = self.last_value
        if self.fields:
            shown = []
            for i, f in enumerate(self.fields):
                cell = f or '0'
                shown.append('<u>%s</u>' % cell if i == self.field_axis else cell)
            value = '[ X %s | Y %s | Z %s ]   %s' % (shown[0], shown[1], shown[2], value)
        elif self.numeric or self.expr_mode:
            value = '[%s %s ]   %s' % ('=' if self.expr_mode else '', self.numeric, value)
        if self._mods() & SHIFT:
            title += '  ·  ' + _t('hassas')
        keys = []
        if self.kind in TRANSFORMS:
            keys += [_t('<b>X Y Z</b> eksen (2. kez: %s)') % _t('global' if self.orientation != 'global' else 'lokal'),
                     _t('<b>Shift+X</b> düzlem'), _t('<b>C</b> kısıt kaldır'),
                     _t('<b>Orta tuş</b> otomatik eksen (Shift: düzlem)'), _t('<b>Alt+orta tuş</b> gezin'),
                     _t('<b>Shift</b> hassas'), _t('<b>Ctrl</b> snap (Shift+Ctrl: ince)'), _t('<b>Shift+Tab</b> snap aç/kapa'),
                     _t('<b>G R S</b> değiştir')]
            if self.kind == 'move':
                keys.append(_t('<b>Tab</b> sonraki eksen (sayı girerken)'))
            if self.kind == 'move' and self.edit:
                keys.append(_t('<b>G G</b> kaydır (slide)'))
            if self.kind == 'rotate':
                keys.append(_t('<b>R R</b> serbest'))
            if cmds.softSelect(q=True, softSelectEnabled=True):
                keys.append(_t('<b>Tekerlek</b> proportional alanı'))
        elif self.kind == 'attr_axis':
            keys += [_t('<b>X Y Z</b> eksene kilitle'), _t('<b>G</b> serbest taşı'), _t('<b>Ctrl</b> adımlı')]
        else:
            keys += [_t('<b>Ctrl</b> adımlı')]
        keys += [_t(k) for k in self.key_hints]
        if self.wheel_attr:
            keys.append(_t('<b>Tekerlek</b> segment'))
        keys += [_t('<b>Sayı</b> yaz (<b>=</b> ifade: 2m, 90d, pi)'), _t('<b>Sol tık/Enter</b> onay'), _t('<b>Sağ tık/Esc</b> iptal')]
        html = ('<span style="color:#e8a33d; font-weight:bold">%s</span>'
                '&nbsp;&nbsp;&nbsp;<span style="color:#ffffff">%s</span><br>%s'
                % (title, value, '&nbsp;&nbsp;·&nbsp;&nbsp;'.join(keys)))
        try:
            hint_bar().show(self.widget, html)
        except Exception:
            _tip(_t('%s  %s') % (title, value))

    # -- olaylar
    def _switch(self, name):
        from .slide import edge_slide  # dongusel import: cagri aninda
        target = {'g': 'move', 'r': 'rotate', 's': 'scale'}[name]
        if target == self.kind:
            if name == 'g' and self.edit:
                # Blender G G: kenar / kose kaydirma (kendi modalimiz; Maya'nin Slide Edge araci
                # orta tusla calisiyor ve orta tus bizde orbit)
                self.finish(False)
                QtCore.QTimer.singleShot(0, edge_slide)
                return
            if name == 'r':
                self._revert()
                self.kind = 'trackball'
                self._reset_applied()
                self.update(force=True)
            return
        self._revert()
        self.kind = target
        self.numeric, self.fields, self.field_axis = '', None, 0
        self.start_pos = QtCore.QPointF(self.eff)
        self.pivot_2d = self._to_screen(self.center)
        self._reset_applied()
        self.update(force=True)

    def _set_constraint(self, axis, plane):
        """Blender: 1. basis oryantasyon ekseni, 2. basis global (oryantasyon globalse lokal), 3. kapali."""
        self._revert()
        first = self.orientation
        second = 'global' if first != 'global' else 'local'
        c = self.constraint
        if c is None or c[0] != axis or c[2] != plane:
            self.constraint = (axis, first, plane)
        elif c[1] == first:
            self.constraint = (axis, second, plane)
        else:
            self.constraint = None
        self.update(force=True)

    def _toggle_snap(self):
        self.snap_on = not self.snap_on
        set_setting('snap_on', self.snap_on)
        self.update(force=True)
        self._show()

    def _wheel(self, up):
        if self.wheel_attr:
            for node in self.nodes:
                plug = '%s.%s' % (node, self.wheel_attr)
                cmds.setAttr(plug, max(1, cmds.getAttr(plug) + (1 if up else -1)))
            self.last_value = 'Segment: %d' % cmds.getAttr('%s.%s' % (self.nodes[0], self.wheel_attr))
            self._show()
        elif self.kind in TRANSFORMS and cmds.softSelect(q=True, softSelectEnabled=True):
            self._revert()
            dist = cmds.softSelect(q=True, softSelectDistance=True)
            cmds.softSelect(edit=True, softSelectDistance=dist * (1.15 if up else 1 / 1.15))
            self.buckets = self._soft_buckets()
            self.last_value = _t('Proportional alan: %.2f') % cmds.softSelect(q=True, softSelectDistance=True)
            self.update(force=True)

    def key(self, ev, etype):
        if etype == EV_SHORTCUT:
            ev.accept()
            return True
        key = int(ev.key())
        if etype == EV_KEY_RELEASE:
            if key == int(Qt.Key.Key_Shift):
                self._show()
            return True
        if etype != EV_KEY_PRESS:
            return True
        phys, numpad = _phys(ev)
        name = (None if numpad else phys) or QT_KEYS.get(key)
        text = ev.text()
        mods = ev.modifiers()
        if key in (int(Qt.Key.Key_Return), int(Qt.Key.Key_Enter)) or (key == int(Qt.Key.Key_Space) and not self.expr_mode):
            self.finish(True)
        elif key == int(Qt.Key.Key_Escape):
            self.finish(False)
        elif text == '=':
            self.expr_mode = not self.expr_mode   # Blender: = ile ifade modu (harfler sayiya)
            self._show()
        elif key == int(Qt.Key.Key_Backtab) or (key == int(Qt.Key.Key_Tab) and mods & SHIFT):
            if self.kind in TRANSFORMS:
                self._toggle_snap()
        elif self.expr_mode and text and (text.isalnum() or text in '.,+-*/() °'):
            self.numeric += text
            self._revert_for_numeric()
        elif key == int(Qt.Key.Key_Shift):
            self._show()
        elif name in self.keys and self.nodes:
            for node in self.nodes:
                try:
                    self.keys[name](node)
                except Exception as exc:
                    _warn(str(exc))
            self.update(force=True)
        elif name in ('x', 'y', 'z') and self.kind in TRANSFORMS and self.kind != 'trackball':
            self._set_constraint(name, bool(mods & SHIFT))
        elif name in ('x', 'y', 'z') and self.kind == 'attr_axis':
            self._free_move()   # extrude: eksene kilitle (Blender E sonra X)
            self._set_constraint(name, bool(mods & SHIFT))
        elif name == 'g' and self.kind == 'attr_axis' and not ev.isAutoRepeat():
            self._free_move()   # extrude: serbest tasi
            self.update(force=True)
        elif name == 'c' and self.kind in TRANSFORMS and self.constraint is not None:
            self._revert()
            self.constraint = None
            self.update(force=True)
        elif name in ('g', 'r', 's') and self.kind in TRANSFORMS and not ev.isAutoRepeat():
            self._switch(name)
        elif key in (int(Qt.Key.Key_PageUp), int(Qt.Key.Key_PageDown)):
            self._wheel(key == int(Qt.Key.Key_PageUp))
        elif key == int(Qt.Key.Key_Tab) and self.kind == 'move':
            # Blender: G 1 Tab 2 Tab 3 -> eksen eksen deger (Ctrl+Tab: onceki eksen)
            if self.fields is None:
                self.fields = ['', '', '']
            self.fields[self.field_axis] = self.numeric
            self.field_axis = (self.field_axis + (-1 if mods & CTRL else 1)) % 3
            self.numeric = self.fields[self.field_axis]
            self._revert_for_numeric()
        elif key == int(Qt.Key.Key_Backspace):
            if mods & CTRL or not self.numeric:
                self.numeric, self.fields, self.field_axis = '', None, 0
            else:
                self.numeric = self.numeric[:-1]
            self._revert_for_numeric()
        elif text == '-' and self.numeric and self.numeric[-1] not in '+-*/(':
            # Blender: - isareti cevirir
            self.numeric = self.numeric[1:] if self.numeric.startswith('-') else '-' + self.numeric
            self._revert_for_numeric()
        elif text and text in '0123456789.,+-*/()':
            self.numeric += text
            self._revert_for_numeric()
        return True

    def _revert_for_numeric(self):
        if self.fields is not None:
            self.fields[self.field_axis] = self.numeric
        if self.kind == 'trackball':
            return
        self.update(force=True)

    def mouse(self, ev, etype, obj=None):
        mods = ev.modifiers()
        filt = _filter()
        if self.nav is not None:
            source, target = self.nav
            if filt is None or obj is None:
                self.nav = None
                return True
            if etype == EV_MMOVE:
                filt._send(obj, ev, etype, NOBTN, target, ALT)
            elif etype == EV_MRELEASE and ev.button() == source:
                filt._send(obj, ev, etype, target, NOBTN, ALT)
                self.nav = None
                self._after_nav()
            return True
        if etype == EV_MPRESS:
            if ev.button() == MMB and mods & ALT and filt is not None and obj is not None:
                # Blender "Transform Navigation with Alt": Alt+orta = orbit, +Shift pan, +Ctrl zoom
                target = MMB if mods & SHIFT else (RMB if mods & CTRL else LMB)
                self.nav = (MMB, target)
                filt._send(obj, ev, etype, target, target, ALT)
                return True
            if ev.button() == LMB:
                self.finish(True)
            elif ev.button() == RMB:
                self.finish(False)
            elif ev.button() == MMB and self.kind in TRANSFORMS and self.kind != 'trackball':
                self.auto_start = QtCore.QPointF(self.eff)
                self.auto_plane = bool(mods & SHIFT) and self.kind != 'rotate'
        elif etype == EV_MRELEASE and ev.button() == MMB:
            self.auto_start = None
            self.auto_plane = False
            self._show()
        elif etype == EV_WHEEL:
            self._wheel(ev.angleDelta().y() > 0)
        return etype != EV_MMOVE

    def finish(self, ok):
        if self.timer:
            self.timer.stop()
            self.timer = None
        try:
            hint_bar().hide()
        except Exception:
            pass
        QtWidgets.QToolTip.hideText()
        try:
            preview_overlay().hide()
        except Exception:
            pass
        _current_filter_set_modal(None)
        self.snap_picker = None
        if getattr(self, 'undo_prev', None) is not None:
            final = None
            try:
                if ok:
                    final = self._final_state()
                self._revert_all()
            except Exception as exc:
                _warn(_t('modal: %s') % exc)
            self._resume_undo()
            if final is not None:
                try:
                    self._commit(final)
                except Exception as exc:
                    _warn(_t('modal: %s') % exc)
        if ok and self.chunk_open:
            run_after_op()      # ayni undo adiminda (ornegin edit modunda gecmisi duzlestir)
        if self.chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.chunk_open = False
            if not ok and getattr(self, 'recorded', self.dirty):
                cmds.undo()     # modal oncesi kaydedilen olusturma (extrude dugumu vb.) da geri alinsin
        cmds.refresh()


def _snapshot_attrs(nodes):
    """{dugum.attr: deger} - modalin degistirebilecegi sayisal / bool / enum ayarlar."""
    out = {}
    skip = ('caching', 'frozen', 'nodeState', 'isHistoricallyInteresting')
    for node in nodes or []:
        for attr in cmds.listAttr(node, scalar=True, settable=True) or []:
            if '.' in attr or attr in skip:
                continue
            plug = '%s.%s' % (node, attr)
            try:
                if cmds.getAttr(plug, type=True) in ('double', 'float', 'doubleLinear', 'doubleAngle', 'long',
                                                     'short', 'byte', 'bool', 'enum'):
                    out[plug] = cmds.getAttr(plug)
            except Exception:
                pass
    return out


def _abort_modal(*_):
    """Suren G/R/S, loop cut vb. islemi geri alma yapmadan kapat (sahne degistiyse undo tehlikeli)."""
    filt = _filter()
    modal = filt.modal if filt else None
    if modal is None:
        return
    if getattr(modal, 'timer', None):
        modal.timer.stop()
        modal.timer = None
    for holder in (_overlay, _hint_bar):
        for w in holder:
            try:
                w.hide()
            except Exception:
                pass
    QtWidgets.QToolTip.hideText()
    filt.modal = None
    resume = getattr(modal, '_resume_undo', None)
    if resume is not None:
        try:
            resume()    # sahne degisti: geri alma yok ama undo kaydi mutlaka yeniden acilsin
        except Exception:
            pass
    if getattr(modal, 'chunk_open', False):
        try:
            cmds.undoInfo(closeChunk=True)
        except Exception:
            pass
        modal.chunk_open = False


def _on_app_state(state):
    """Maya arka plana gecerse (Alt+Tab) suren islemi o anki haliyle onayla, yuzen pencereleri gizle."""
    if state == Qt.ApplicationState.ApplicationActive:
        return
    filt = _filter()
    if filt and filt.modal:
        try:
            filt.modal.finish(True)
        except Exception:
            _abort_modal()


def start_modal(kind, panel=None, keep_undo=False, **kwargs):
    panel = panel or _last_view_panel()
    if not panel:
        return
    modal = Modal(kind, panel, keep_undo=keep_undo, **kwargs)
    if kind in ('attr_axis', 'attr_dist'):
        modal.chunk_open = True  # olusturma da ayni undo adiminda
        modal.dirty = True
    _current_filter_set_modal(modal)
    if not modal.start():
        _current_filter_set_modal(None)


def grab():
    start_modal('move')


def rotate():
    start_modal('rotate')


def scale():
    start_modal('scale')


def _with_chunk(fn):
    """Extrude/inset/bevel: olusturma + modal tek undo adimi olsun."""
    def run():
        cmds.undoInfo(openChunk=True, chunkName='blender_' + fn.__name__)
        filt = _filter()
        try:
            fn()
        except Exception as exc:
            _warn(_t('%s: %s') % (fn.__name__, exc))
        if not (filt and filt.modal):
            cmds.undoInfo(closeChunk=True)
    return run


def mirror():
    """Ctrl+M: secilen eksende aynala (X/Y/Z ile degistir, Enter onay)."""
    start_modal('scale')
    filt = _filter()
    m = filt.modal if filt else None
    if isinstance(m, Modal):
        m.constraint = ('x', 'global', False)
        m.numeric = '-1'
        m.TITLES = dict(Modal.TITLES, scale='AYNALA')
        m.update(force=True)
