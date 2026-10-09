# -*- coding: utf-8 -*-
"""Fare altindaki mesh / yuz / kenar / kose ve mesh grafigi (en kisa yol, halka)."""
from __future__ import absolute_import, division, print_function

import math

import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui2

from .compat import QtCore, QtWidgets, _np, wrapInstance
from .util import _objs


# ---------------------------------------------------------------- imlec altindaki bilesen
class Picker(object):
    """Fare altindaki mesh/yuz/kenar/koseyi bulur (secimi degistirmeden)."""

    def __init__(self, panel, meshes=None):
        self.view = omui2.M3dView.getM3dViewFromModelPanel(panel)
        self.widget = wrapInstance(int(self.view.widget()), QtWidgets.QWidget)
        self.meshes = []
        for obj in meshes or cmds.ls(hilite=True, long=True) or _objs():
            for shape in cmds.listRelatives(obj, shapes=True, type='mesh', noIntermediate=True,
                                            fullPath=True) or []:
                self.add_mesh(obj, shape)

    def add_mesh(self, transform, shape):
        sel = om.MSelectionList()
        sel.add(shape)
        dag = sel.getDagPath(0)
        self.meshes.append({'transform': transform, 'fn': om.MFnMesh(dag), 'poly': dag,
                            'matrix': dag.inclusiveMatrix(), 'inverse': dag.inclusiveMatrixInverse(),
                            'bbox': om.MFnDagNode(dag).boundingBox, 'accel': None})

    def port(self, global_pos):
        local = self.widget.mapFromGlobal(QtCore.QPointF(global_pos))
        sx = self.view.portWidth() / float(max(1, self.widget.width()))
        sy = self.view.portHeight() / float(max(1, self.widget.height()))
        return local.x() * sx, self.view.portHeight() - local.y() * sy

    def screen(self, point):
        res = self.view.worldToView(point)
        return float(res[0]), float(res[1])

    def hit(self, global_pos):
        """En yakin yuz: (mesh_bilgisi, yuz_id, dunya_noktasi) veya None."""
        x, y = self.port(global_pos)
        near, far = om.MPoint(), om.MPoint()
        self.view.viewToWorld(int(round(x)), int(round(y)), near, far)
        best = None
        for mesh in self.meshes:
            o = near * mesh['inverse']
            d = om.MVector(far - near) * mesh['inverse']
            if not _ray_hits_box(o, d, mesh['bbox']):
                continue
            if mesh['accel'] is None:
                mesh['accel'] = mesh['fn'].autoUniformGridParams()
            res = mesh['fn'].closestIntersection(om.MFloatPoint(o), om.MFloatVector(d.normal()),
                                                 om.MSpace.kObject, 1e9, False, accelParams=mesh['accel'])
            if res is None or res[2] < 0:
                continue
            world = om.MPoint(res[0]) * mesh['matrix']
            dist = world.distanceTo(near)
            if best is None or dist < best[3]:
                best = (mesh, res[2], world, dist)
        return best[:3] if best else None

    def _world(self, mesh, vid):
        return mesh['fn'].getPoint(vid, om.MSpace.kObject) * mesh['matrix']

    def _face_edges(self, mesh, face):
        it = om.MItMeshPolygon(mesh['poly'])
        it.setIndex(face)
        return list(it.getEdges()), list(it.getVertices())

    def edge(self, global_pos):
        """Fareye en yakin kenar: (mesh, kenar_id, t) ; t = kenar uzerindeki konum 0..1."""
        h = self.hit(global_pos)
        if not h:
            return None
        mesh, face, _ = h
        px, py = self.port(global_pos)
        best = None
        for e in self._face_edges(mesh, face)[0]:
            v0, v1 = mesh['fn'].getEdgeVertices(e)
            a = self.screen(self._world(mesh, v0))
            b = self.screen(self._world(mesh, v1))
            dist, t = _seg_dist(px, py, a, b)
            if best is None or dist < best[0]:
                best = (dist, e, t)
        return (mesh, best[1], best[2]) if best else None

    def vertex(self, global_pos):
        h = self.hit(global_pos)
        if not h:
            return None
        mesh, face, _ = h
        px, py = self.port(global_pos)
        best = None
        for v in self._face_edges(mesh, face)[1]:
            sx, sy = self.screen(self._world(mesh, v))
            d = math.hypot(sx - px, sy - py)
            if best is None or d < best[0]:
                best = (d, v)
        return (mesh, best[1]) if best else None

    def _screen_points(self, mesh):
        """Mesh'in tum koselerinin port koordinatlari (onbellekli; numpy varsa (N,2) dizi)."""
        if 'screen' in mesh:
            return mesh['screen']
        fn = mesh['fn']
        if fn.numVertices > 500000:
            mesh['screen'] = None
            return None
        pts = fn.getPoints(om.MSpace.kWorld)
        if _np is not None:
            arr = _np.array([(p.x, p.y, p.z, 1.0) for p in pts])
            mv = _np.array(list(self.view.modelViewMatrix())).reshape(4, 4)
            pj = _np.array(list(self.view.projectionMatrix())).reshape(4, 4)
            clip = arr @ mv @ pj
            w = clip[:, 3].copy()
            behind = w <= 1e-9
            w[behind] = 1.0
            sx = (clip[:, 0] / w + 1.0) * 0.5 * self.view.portWidth()
            sy = (clip[:, 1] / w + 1.0) * 0.5 * self.view.portHeight()
            res = _np.stack([sx, sy], axis=1)
            res[behind] = 1e9
            mesh['screen'] = res
        else:
            mesh['screen'] = [self.screen(p) for p in pts]
        return mesh['screen']

    def nearest_vertex(self, global_pos, radius=24):
        """Ekran uzayinda fareye en yakin kose (ray gerektirmez, Blender snap gibi): (mesh, vid) ya da None."""
        px, py = self.port(global_pos)
        best = None
        for mesh in self.meshes:
            pts = self._screen_points(mesh)
            if pts is None or len(pts) == 0:
                continue
            if _np is not None:
                d2 = (pts[:, 0] - px) ** 2 + (pts[:, 1] - py) ** 2
                i = int(d2.argmin())
                d = float(d2[i]) ** 0.5
            else:
                i, d = min(((k, math.hypot(x - px, y - py)) for k, (x, y) in enumerate(pts)), key=lambda t: t[1])
            if d <= radius and (best is None or d < best[0]):
                best = (d, mesh, i)
        return (best[1], best[2]) if best else None

    def component(self, global_pos, kind):
        """'mesh.vtx[3]' gibi isim ve (mesh, id)."""
        if kind == 'vertex':
            r = self.vertex(global_pos)
        elif kind == 'edge':
            r = self.edge(global_pos)
        else:
            h = self.hit(global_pos)
            r = (h[0], h[1]) if h else None
        if not r:
            return None
        return r[0], r[1]


def _ray_hits_box(origin, direction, box):
    """Isin (nesne uzayi) sinir kutusuna degiyor mu (slab testi, %1 pay)."""
    lo, hi = box.min, box.max
    pad = 0.01 * max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z, 1e-6)
    t0, t1 = -1e30, 1e30
    for o, d, a, b in ((origin.x, direction.x, lo.x, hi.x), (origin.y, direction.y, lo.y, hi.y),
                       (origin.z, direction.z, lo.z, hi.z)):
        a, b = a - pad, b + pad
        if abs(d) < 1e-12:
            if o < a or o > b:
                return False
            continue
        ta, tb = (a - o) / d, (b - o) / d
        if ta > tb:
            ta, tb = tb, ta
        t0, t1 = max(t0, ta), min(t1, tb)
        if t0 > t1:
            return False
    return t1 >= 0


def _seg_dist(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 < 1e-9 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / length2))
    cx, cy = a[0] + dx * t, a[1] + dy * t
    return math.hypot(px - cx, py - cy), t


class MeshGraph(object):
    """En kisa yol icin mesh komsuluk grafigi (Dijkstra)."""

    def __init__(self, fn):
        self.fn = fn
        pts = fn.getPoints(om.MSpace.kObject)
        self.pts = pts
        n_edges = fn.numEdges
        self.edge_verts = [fn.getEdgeVertices(e) for e in range(n_edges)]
        self.vadj = [[] for _ in range(fn.numVertices)]
        for e, (a, b) in enumerate(self.edge_verts):
            d = pts[a].distanceTo(pts[b])
            self.vadj[a].append((b, e, d))
            self.vadj[b].append((a, e, d))
        self._fadj = None

    @staticmethod
    def _dijkstra(sources, targets, neighbors):
        import heapq
        targets = set(targets)
        dist = {s: 0.0 for s in sources}
        prev = {}
        heap = [(0.0, s) for s in sources]
        heapq.heapify(heap)
        while heap:
            d, node = heapq.heappop(heap)
            if node in targets:
                path, links = [node], []
                while node in prev:
                    node, link = prev[node]
                    path.append(node)
                    links.append(link)
                return path[::-1], links[::-1]
            if d > dist.get(node, 1e30):
                continue
            for other, link, w in neighbors(node):
                nd = d + w
                if nd < dist.get(other, 1e30):
                    dist[other] = nd
                    prev[other] = (node, link)
                    heapq.heappush(heap, (nd, other))
        return [], []

    def vertex_path(self, sources, targets):
        """(kose_listesi, kenar_listesi)"""
        return self._dijkstra(list(sources), list(targets), lambda v: self.vadj[v])

    def face_path(self, a, b):
        if self._fadj is None:
            centers = []
            edge_faces = {}
            for f in range(self.fn.numPolygons):
                verts = self.fn.getPolygonVertices(f)
                c = om.MVector()
                for v in verts:
                    c += om.MVector(self.pts[v])
                centers.append(c / len(verts))
                for i in range(len(verts)):
                    key = tuple(sorted((verts[i], verts[(i + 1) % len(verts)])))
                    edge_faces.setdefault(key, []).append(f)
            self._fadj = [[] for _ in range(self.fn.numPolygons)]
            for faces in edge_faces.values():
                for f in faces:
                    for g in faces:
                        if f != g:
                            self._fadj[f].append((g, None, (centers[f] - centers[g]).length()))
        return self._dijkstra([a], [b], lambda f: self._fadj[f])[0]

    def shell(self, face):
        """Bagli tum yuzler (L / Ctrl+L)."""
        self.face_path(face, -1)  # komsulugu kur
        seen, stack = {face}, [face]
        while stack:
            f = stack.pop()
            for g, _, _ in self._fadj[f]:
                if g not in seen:
                    seen.add(g)
                    stack.append(g)
        return sorted(seen)


# ---------------------------------------------------------------- loop cut (Ctrl+R)
def _edge_ring_pairs(mesh, edge):
    """Kenar halkasini dortgenler uzerinden yuru.

    Donus: ([(kose_a, kose_b), ...], kapali_mi). Tum ciftler ayni yone bakar
    (a'lar halkanin bir tarafinda), boylece t oranindaki noktalar kesim cizgisini verir.
    """
    fn = mesh['fn']
    it_edge = om.MItMeshEdge(mesh['poly'])
    it_poly = om.MItMeshPolygon(mesh['poly'])

    def faces_of(e):
        it_edge.setIndex(e)
        return list(it_edge.getConnectedFaces())

    def step(face, a, b):
        """Dortgende (a,b) kenarinin karsisindaki kenar: (a'ya komsu, b'ye komsu, kenar_id)."""
        verts = list(fn.getPolygonVertices(face))
        if len(verts) != 4 or a not in verts or b not in verts:
            return None
        i, j = verts.index(a), verts.index(b)
        na = verts[(i - 1) % 4] if verts[(i + 1) % 4] == b else verts[(i + 1) % 4]
        nb = verts[(j - 1) % 4] if verts[(j + 1) % 4] == a else verts[(j + 1) % 4]
        it_poly.setIndex(face)
        for e in it_poly.getEdges():
            if set(fn.getEdgeVertices(e)) == {na, nb}:
                return na, nb, e
        return None

    def walk(face):
        out, cur, prev = [], (v0, v1), None
        while face is not None and len(out) < 100000:
            res = step(face, cur[0], cur[1])
            if not res:
                return out, False
            na, nb, ne = res
            if ne == edge:
                return out, True
            out.append((na, nb))
            cur, prev = (na, nb), face
            nxt = [f for f in faces_of(ne) if f != prev]
            face = nxt[0] if nxt else None
        return out, False

    v0, v1 = fn.getEdgeVertices(edge)
    faces = faces_of(edge)
    fwd, closed = walk(faces[0]) if faces else ([], False)
    back = []
    if not closed and len(faces) > 1:
        back, _ = walk(faces[1])
    return list(reversed(back)) + [(v0, v1)] + fwd, closed


_graph_cache = {}


def _mesh_graph(fn, path):
    """MeshGraph onbellegi: topoloji ve ilk/son nokta ayniysa yeniden kurma (P3)."""
    pts = (fn.getPoint(0), fn.getPoint(fn.numVertices - 1)) if fn.numVertices else ()
    key = (path, fn.numVertices, fn.numEdges, fn.numPolygons,
           tuple(round(c, 5) for p in pts for c in (p.x, p.y, p.z)))
    graph = _graph_cache.get(key)
    if graph is None:
        if len(_graph_cache) > 8:
            _graph_cache.clear()
        graph = _graph_cache[key] = MeshGraph(fn)
    return graph


def _hops(start, neighbors):
    """Agirliksiz BFS: {dugum: adim}"""
    dist, queue = {start: 0}, [start]
    i = 0
    while i < len(queue):
        n = queue[i]
        i += 1
        for m in neighbors(n):
            if m not in dist:
                dist[m] = dist[n] + 1
                queue.append(m)
    return dist
