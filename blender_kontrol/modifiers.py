# -*- coding: utf-8 -*-
"""Blender-style live modifier stack backed by Maya polygon history and an Orange Array DG node.

The input cage is a separate mesh shape in front of Orange's first history node. All seven current
modifier types use native Maya polygon nodes except Array, whose single mesh-input/output node copies
vertices, faces, and UV sets. The panel follows the DG order, and reordering swaps direct adjacent links.
"""
from __future__ import absolute_import, division, print_function

import math
import os
import sys
import uuid

import maya.cmds as cmds
import maya.api.OpenMaya as om

from .compat import Qt, QtCore, QtGui, QtWidgets
from .core import _msg, _state, _warn
from .i18n import _t
from .util import _mesh_fn, _objs, _shape_type, undoable
from .editmode import edit_targets, exit_edit, in_edit

try:
    from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
except ImportError:
    class MayaQWidgetDockableMixin(object):
        """Fallback for Maya builds without the workspace-control mixin."""
        pass

ATTR = 'orangeModifier'      # instance transform'u ya da gecmis dugumu: tur ('mirror:x', 'array', 'bevel' ...)
BASE_ATTR = 'orangeBase'     # instance -> taban obje (message baglantisi)
AXES = 'xyz'
HISTORY_KINDS = ('mirror', 'array', 'subdiv', 'bevel', 'solidify', 'triangulate', 'weld')
MODIFIER_LABELS = {'subdiv': 'Subdivision', 'mirror': 'Mirror', 'array': 'Array', 'bevel': 'Bevel',
                   'solidify': 'Solidify', 'triangulate': 'Triangulate', 'weld': 'Weld'}
ARRAY_ATTRS = ('orangeArrayCount', 'orangeArrayRelativeX', 'orangeArrayRelativeY', 'orangeArrayRelativeZ',
               'orangeArrayConstantX', 'orangeArrayConstantY', 'orangeArrayConstantZ')
MIRROR_MERGE_ATTR = 'orangeMirrorMerge'
MIRROR_THRESHOLD_ATTR = 'orangeMirrorThreshold'
MIRROR_EXISTS_ATTR = 'orangeMirrorExists'
# polyMirror.mergeMode enum: 1 = kenar koselerini birlestir, 2 = kenarlari kopruler, 3 = birlestirme (0 yok: min 1).
MIRROR_MERGE_ON, MIRROR_MERGE_OFF = 1, 3
# Taban UUID -> (kafes UUID, cikti shape UUID, kafes intermediate, kafes visibility, cikti overrideEnabled,
# cikti overrideDisplayType). UUID anahtari: edit modunda yeniden adlandirma / ebeveyn degistirme cikis
# durumunu kaybettirmesin (DAG yolu degisince cikti shape referans gorunumde takili kaliyordu).
EDIT_CAGES = {}
_EDIT_JOB = None
PANEL_NAME = 'BlenderKontrolModifiers'
_UI_SCRIPT = 'import blender_kontrol.modifiers as m; m.restore_panel()'


# ---------------------------------------------------------------- yardimcilar
def active_mesh():
    """Duzenlenen ya da en son secilen mesh transform'u (instance modifier secilmisse tabani)."""
    objs = edit_targets()
    for obj in reversed(objs):
        base = base_of(obj)
        if base:
            return base
        if _shape_type(obj) == 'mesh':
            parents = cmds.listRelatives(obj, parent=True, fullPath=True) or []
            return parents[0] if parents else obj
    return None


def base_of(obj):
    """Instance modifier transform'u ise taban objesi."""
    if not cmds.attributeQuery(BASE_ATTR, node=obj, exists=True):
        return None
    src = cmds.listConnections(obj + '.' + BASE_ATTR, source=True, destination=False) or []
    return cmds.ls(src[0], long=True)[0] if src else None


def _mark(node, kind, owner=None):
    if not cmds.attributeQuery(ATTR, node=node, exists=True):
        cmds.addAttr(node, longName=ATTR, dataType='string')
    cmds.setAttr(node + '.' + ATTR, kind, type='string')
    if owner and not cmds.attributeQuery('orangeOwner', node=node, exists=True):
        cmds.addAttr(node, longName='orangeOwner', attributeType='message')
        cmds.connectAttr(owner + '.message', node + '.orangeOwner', force=True)


def kind_of(node):
    if cmds.attributeQuery(ATTR, node=node, exists=True):
        return cmds.getAttr(node + '.' + ATTR) or ''
    return ''


def owner_of(node):
    if not cmds.objExists(node) or not cmds.attributeQuery('orangeOwner', node=node, exists=True):
        return None
    owners = cmds.listConnections(node + '.orangeOwner', source=True, destination=False) or []
    return (cmds.ls(owners[0], long=True) or owners)[0] if owners else None


def instance_modifiers(base):
    """[(transform, tur)] tabana bagli instance modifier'lar (olusturma sirasinda)."""
    out = []
    for dst in cmds.listConnections(base + '.message', source=False, destination=True, plugs=True) or []:
        node, _, attr = dst.partition('.')
        if attr == BASE_ATTR:
            node = cmds.ls(node, long=True)[0]
            out.append((node, kind_of(node)))
    return out


def history_modifiers(base):
    """[(dugum, tur)] Orange'in DG zincirine ekledigi butun modifier dugumleri."""
    out = []
    for node in cmds.listHistory(base, pruneDagObjects=True) or []:
        k = kind_of(node)
        if k in HISTORY_KINDS:
            out.append((node, k))
    return list(reversed(out))    # olusturma sirasi


def _history_precedes(earlier, later):
    """True when two polygon history nodes are directly adjacent in the DG chain."""
    source = cmds.listConnections(node_input_plug(later), source=True, destination=False, plugs=True) or []
    return source == [node_output_plug(earlier)]


def node_input_plug(node):
    return node + ('.inputMesh' if cmds.nodeType(node) == 'orangeArray' else '.inputPolymesh')


def node_output_plug(node):
    return node + ('.outputMesh' if cmds.nodeType(node) == 'orangeArray' else '.output')


def can_move_history_modifier(base, node, direction, modifiers=None):
    """Only expose reordering where rewiring won't cross an unrelated Maya history node.

    modifiers: history_modifiers(base) sonucu (panel yenilemesi bir kez hesaplayip her karta verir)."""
    if modifiers is None:
        modifiers = history_modifiers(base)
    groups = _mirror_groups(base, modifiers)
    modifiers = [item for item, _kind in modifiers]
    try:
        index = modifiers.index(node)
    except ValueError:
        return False
    group = _mirror_group_for_node(base, node, groups)
    start = modifiers.index(group[0]) if group else index
    end = start + len(group) - 1 if group else start
    target = start - 1 if direction < 0 else end + 1
    if target < 0 or target >= len(modifiers):
        return False
    neighbor = _mirror_group_for_node(base, modifiers[target], groups) or [modifiers[target]]
    moving_group = group or [node]
    chain = neighbor + moving_group if direction < 0 else moving_group + neighbor
    return all(_history_precedes(earlier, later) for earlier, later in zip(chain, chain[1:]))


def can_move_history_card(base, node, target_node, after=False, modifiers=None):
    """Surukle-birak on denetimi: kaynak kart hedefe kadar yalnizca bitisik Orange dugumlerinin uzerinden
    gececekse True (move_history_card ayni zincir uzerinde ardisik guvenli takaslar yapar)."""
    if modifiers is None:
        modifiers = history_modifiers(base)
    groups = _mirror_groups(base, modifiers)
    nodes = [item for item, _kind in modifiers]
    if node == target_node or node not in nodes or target_node not in nodes:
        return False
    source_group = _mirror_group_for_node(base, node, groups) or [node]
    target_group = _mirror_group_for_node(base, target_node, groups) or [target_node]
    if set(source_group) & set(target_group):
        return False
    # Takaslar iki grubun kapsadigi araligin icinde kalir (after=True'da da hedef grubun sonunu gecmez).
    indices = [nodes.index(item) for item in source_group + target_group]
    low, high = min(indices), max(indices)
    return all(_history_precedes(nodes[i], nodes[i + 1]) for i in range(low, high))


def move_history_modifier(base, node, direction):
    """Move one modifier card (all native helper nodes in a Mirror card move together)."""
    modifiers = [item for item, _kind in history_modifiers(base)]
    if node not in modifiers:
        return False
    group = _mirror_group_for_node(base, node) or [node]
    start = modifiers.index(group[0])
    end = start + len(group) - 1
    target = start - 1 if direction < 0 else end + 1
    if target < 0 or target >= len(modifiers):
        return False
    neighbor = _mirror_group_for_node(base, modifiers[target]) or [modifiers[target]]
    left, right = (neighbor, group) if direction < 0 else (group, neighbor)
    chain = left + right
    if any(not _history_precedes(a, b) for a, b in zip(chain, chain[1:])):
        raise RuntimeError(_t('Modifier sadece bitişik Orange modifier\'ları arasında taşınabilir'))
    upstream = cmds.listConnections(node_input_plug(chain[0]), source=True, destination=False, plugs=True) or []
    downstream = cmds.listConnections(node_output_plug(chain[-1]), source=False, destination=True, plugs=True) or []
    if len(upstream) != 1 or len(downstream) != 1:
        raise RuntimeError(_t('Modifier sırası güvenli şekilde değiştirilemedi'))
    upstream, downstream = upstream[0], downstream[0]
    cmds.disconnectAttr(upstream, node_input_plug(chain[0]))
    for earlier, later in zip(chain, chain[1:]):
        cmds.disconnectAttr(node_output_plug(earlier), node_input_plug(later))
    cmds.disconnectAttr(node_output_plug(chain[-1]), downstream)
    reordered = right + left
    cmds.connectAttr(upstream, node_input_plug(reordered[0]), force=True)
    for earlier, later in zip(reordered, reordered[1:]):
        cmds.connectAttr(node_output_plug(earlier), node_input_plug(later), force=True)
    cmds.connectAttr(node_output_plug(reordered[-1]), downstream, force=True)
    return True


def move_history_card(base, node, target_node, after=False):
    """Drag one card before/after another by a sequence of adjacent safe swaps."""
    if node == target_node:
        return False
    nodes = [item for item, _kind in history_modifiers(base)]
    if node not in nodes or target_node not in nodes:
        return False
    source_group = _mirror_group_for_node(base, node) or [node]
    target_group = _mirror_group_for_node(base, target_node) or [target_node]
    if set(source_group) & set(target_group):
        return False
    if after:
        target_end = max(nodes.index(item) for item in target_group)
        next_index = target_end + 1
        if next_index < len(nodes):
            next_group = _mirror_group_for_node(base, nodes[next_index]) or [nodes[next_index]]
            if set(source_group) & set(next_group):
                return False
            target_node = next_group[0]
            target_group = next_group
        else:
            source_end = max(nodes.index(item) for item in source_group)
            moved = False
            while source_end < len(nodes) - 1:
                if not can_move_history_modifier(base, source_group[0], 1):
                    raise RuntimeError(_t("Modifier sadece bitişik Orange modifier'ları arasında taşınabilir"))
                move_history_modifier(base, source_group[0], 1)
                moved = True
                nodes = [item for item, _kind in history_modifiers(base)]
                source_group = _mirror_group_for_node(base, source_group[0]) or source_group
                source_end = max(nodes.index(item) for item in source_group)
            return moved
    source_start = min(nodes.index(item) for item in source_group)
    source_end = max(nodes.index(item) for item in source_group)
    target_start = min(nodes.index(item) for item in target_group)
    moved = False
    while source_end + 1 < target_start:
        if not can_move_history_modifier(base, node, 1):
            raise RuntimeError(_t('Modifier sadece bitişik Orange modifier\'ları arasında taşınabilir'))
        move_history_modifier(base, node, 1)
        moved = True
        nodes = [item for item, _kind in history_modifiers(base)]
        source_start = min(nodes.index(item) for item in source_group)
        source_end = max(nodes.index(item) for item in source_group)
        target_start = min(nodes.index(item) for item in target_group)
    while source_start > target_start:
        if not can_move_history_modifier(base, node, -1):
            raise RuntimeError(_t('Modifier sadece bitişik Orange modifier\'ları arasında taşınabilir'))
        move_history_modifier(base, node, -1)
        moved = True
        nodes = [item for item, _kind in history_modifiers(base)]
        source_start = min(nodes.index(item) for item in source_group)
        source_end = max(nodes.index(item) for item in source_group)
        target_start = min(nodes.index(item) for item in target_group)
    return moved


def _mirror_group_for_node(base, node, groups=None):
    """groups: _mirror_groups(base) sonucu; verilirse history yeniden okunmaz."""
    if kind_of(node) != 'mirror':
        return []
    for nodes in (_mirror_groups(base) if groups is None else groups).values():
        if node in nodes:
            return nodes
    return [node]


def _group_id_of(node):
    return cmds.getAttr(node + '.orangeGroup') if cmds.attributeQuery('orangeGroup', node=node, exists=True) else node


def _shape(base):
    return (cmds.listRelatives(base, shapes=True, type='mesh', noIntermediate=True, fullPath=True) or [None])[0]


def _cage_feeds_orange(shape):
    """Kafesin outMesh'i bir Orange history dugumune gidiyor mu? (Shift+D kopyasinda gitmez: duplicate
    intermediate kafesi kopyalar ama history'yi kopyalamaz; o kafes duzenlenirse gorunen mesh degismez.)"""
    for dst in cmds.listConnections(shape + '.outMesh', source=False, destination=True) or []:
        if kind_of(dst) in HISTORY_KINDS:
            return True
    return False


def cage_shape(base):
    shapes = cmds.listRelatives(base, shapes=True, type='mesh', fullPath=True) or []
    for shape in shapes:
        if (cmds.attributeQuery('orangeCage', node=shape, exists=True) and cmds.getAttr(shape + '.orangeCage')
                and _cage_feeds_orange(shape)):
            return shape
    return None


def _discard_stale_cages(base):
    """Hicbir Orange dugumunu beslemeyen kafes isaretlerini kaldir (baglantisizsa shape'i de sil)."""
    for shape in cmds.listRelatives(base, shapes=True, type='mesh', fullPath=True) or []:
        if not (cmds.attributeQuery('orangeCage', node=shape, exists=True) and cmds.getAttr(shape + '.orangeCage')):
            continue
        if _cage_feeds_orange(shape):
            continue
        if cmds.getAttr(shape + '.intermediateObject') and not cmds.listConnections(
                shape + '.outMesh', source=False, destination=True):
            cmds.delete(shape)
        else:
            cmds.setAttr(shape + '.orangeCage', False)


def _assign_shading(shape, reference):
    """Yeni shape'i referans shape'in shading group'una ekle (yoksa initialShadingGroup); eklenmezse
    Viewport 2.0 yesil/golgesiz cizer. Yuz bazli materyal atamalari tasinmaz, obje materyali korunur."""
    groups = cmds.listConnections(reference, type='shadingEngine') if reference else None
    group = next((g for g in groups or [] if cmds.objExists(g)), 'initialShadingGroup')
    try:
        cmds.sets(shape, edit=True, forceElement=group)
    except Exception:
        cmds.sets(shape, edit=True, forceElement='initialShadingGroup')


def _ensure_cage(base):
    """Insert an editable mesh shape between upstream Maya history and Orange's first node."""
    existing = cage_shape(base)
    if existing:
        return existing
    _discard_stale_cages(base)
    orange_nodes = [node for node, _kind in history_modifiers(base)]
    if not orange_nodes:
        return None
    first = orange_nodes[0]
    input_plug = node_input_plug(first)
    sources = cmds.listConnections(input_plug, source=True, destination=False, plugs=True) or []
    if len(sources) != 1:
        return None
    source_plug = sources[0]
    source_node = source_plug.partition('.')[0]
    if cmds.nodeType(source_node) == 'mesh':
        cage = source_node
    else:
        cage = cmds.createNode('mesh', name=base.split('|')[-1] + 'OrangeCageShape', parent=base)
        cmds.connectAttr(source_plug, cage + '.inMesh', force=True)
        cmds.disconnectAttr(source_plug, input_plug)
        cmds.connectAttr(cage + '.outMesh', input_plug, force=True)
        _assign_shading(cage, _shape(base))
    if not cmds.attributeQuery('orangeCage', node=cage, exists=True):
        cmds.addAttr(cage, longName='orangeCage', attributeType='bool')
    cmds.setAttr(cage + '.orangeCage', True)
    if not cmds.attributeQuery('orangeOwner', node=cage, exists=True):
        cmds.addAttr(cage, longName='orangeOwner', attributeType='message')
        cmds.connectAttr(base + '.message', cage + '.orangeOwner', force=True)
    cmds.setAttr(cage + '.intermediateObject', True)
    cmds.setAttr(cage + '.visibility', False)
    return (cmds.ls(cage, long=True) or [cage])[0]


def _uuid_of(node):
    return (cmds.ls(node, uuid=True) or [None])[0]


def _node_by_uuid(node_uuid):
    return (cmds.ls(node_uuid, long=True) or [None])[0] if node_uuid else None


def _ensure_edit_job():
    """Yeni sahne / sahne acma oncesi edit durumunu temizleyen modul scriptJob'u (bir kez kurulur)."""
    global _EDIT_JOB
    try:
        if _EDIT_JOB is not None and cmds.scriptJob(exists=_EDIT_JOB):
            return
    except Exception:
        pass
    try:
        _EDIT_JOB = cmds.scriptJob(event=['PreFileNewOrOpened', exit_all_source_edits], killWithScene=False)
    except Exception:
        _EDIT_JOB = None


def _kill_edit_job():
    global _EDIT_JOB
    try:
        if _EDIT_JOB is not None and cmds.scriptJob(exists=_EDIT_JOB):
            cmds.scriptJob(kill=_EDIT_JOB, force=True)
    except Exception:
        pass
    _EDIT_JOB = None


def enter_source_edit(base):
    """Show and select the pre-modifier cage while keeping the evaluated output visible as reference."""
    base = (cmds.ls(base, long=True) or [base])[0]
    cage = _ensure_cage(base)
    output = _shape(base)
    if not cage or not output or cage == output:
        return None
    key = _uuid_of(base)
    if key not in EDIT_CAGES:
        EDIT_CAGES[key] = (_uuid_of(cage), _uuid_of(output), cmds.getAttr(cage + '.intermediateObject'),
                           cmds.getAttr(cage + '.visibility'), cmds.getAttr(output + '.overrideEnabled'),
                           cmds.getAttr(output + '.overrideDisplayType'))
    _ensure_edit_job()
    cmds.setAttr(cage + '.intermediateObject', False)
    cmds.setAttr(cage + '.visibility', True)
    cmds.setAttr(output + '.overrideEnabled', True)
    cmds.setAttr(output + '.overrideDisplayType', 2)
    return cage


def _restore_edit_state(state):
    cage_uuid, output_uuid, intermediate, visible, override, display = state
    cage, output = _node_by_uuid(cage_uuid), _node_by_uuid(output_uuid)
    if cage:
        cmds.setAttr(cage + '.intermediateObject', intermediate)
        cmds.setAttr(cage + '.visibility', visible)
    if output:
        cmds.setAttr(output + '.overrideEnabled', override)
        cmds.setAttr(output + '.overrideDisplayType', display)


def exit_source_edit(base_or_cage):
    base = (cmds.ls(base_or_cage, long=True) or [base_or_cage])[0]
    if cmds.nodeType(base) == 'mesh':
        parents = cmds.listRelatives(base, parent=True, fullPath=True) or []
        base = parents[0] if parents else base
    state = EDIT_CAGES.pop(_uuid_of(base), None)
    if not state:
        return False
    _restore_edit_state(state)
    return True


def exit_all_source_edits(*_):
    """Butun kafes duzenleme durumlarini geri al (yeni sahne, sahne acma, yeniden yukleme)."""
    states = list(EDIT_CAGES.values())
    EDIT_CAGES.clear()
    for state in states:
        try:
            _restore_edit_state(state)
        except Exception:
            pass
    return len(states)


def _base_value(base, name, default):
    if cmds.attributeQuery(name, node=base, exists=True):
        return cmds.getAttr('%s.%s' % (base, name))
    return default


def _set_base_value(base, name, value, attr_type='double'):
    if not cmds.attributeQuery(name, node=base, exists=True):
        cmds.addAttr(base, longName=name, attributeType=attr_type)
    cmds.setAttr('%s.%s' % (base, name), value)


def _open_panels():
    """Sahnedeki Orange modifier panelleri (dock icinde oldugunda topLevelWidgets listelemez)."""
    try:
        return [w for w in QtWidgets.QApplication.allWidgets() if w.objectName() == PANEL_NAME]
    except RuntimeError:
        return []


def refresh_open_panels():
    """Refresh Orange modifier panels after a viewport hotkey changes mesh preview state."""
    for widget in _open_panels():
        try:
            widget.refresh()
        except RuntimeError:
            pass


def close_panels():
    """Paneli ve workspaceControl'unu sil (kaldirma / yeniden yukleme); edit kafes durumunu ve modul
    scriptJob'unu da temizler. Yeniden yuklemede eski modulun paneli yeni modulle calisamaz."""
    for widget in _open_panels():
        try:
            widget._kill_jobs()
        except Exception:
            pass
        try:
            QtWidgets.QWidget.setVisible(widget, False)
            widget.setParent(None)
            widget.deleteLater()
        except Exception:
            pass
    control = PANEL_NAME + 'WorkspaceControl'
    try:
        if cmds.workspaceControl(control, query=True, exists=True):
            cmds.deleteUI(control, control=True)
    except Exception:
        pass
    _kill_edit_job()
    exit_all_source_edits()


# ---------------------------------------------------------------- subdivision (smooth mesh preview)
def subdivision_level(base):
    nodes = [n for n, kind in history_modifiers(base) if kind == 'subdiv']
    if nodes:
        node = nodes[-1]
        return int(cmds.getAttr(node + '.divisions')) if is_enabled(node) else 0
    # Legacy scenes use Maya Smooth Mesh Preview; it remains readable until migrated.
    shape = _shape(base)
    if not shape or cmds.getAttr(shape + '.displaySmoothMesh') == 0:
        return 0
    return cmds.getAttr(shape + '.smoothLevel')


def set_subdivision(base, level, render=None):
    nodes = [n for n, kind in history_modifiers(base) if kind == 'subdiv']
    if nodes:
        node = nodes[-1]
    else:
        if not level:
            shape = _shape(base)
            if shape:
                cmds.setAttr(shape + '.displaySmoothMesh', 0)
            return
        node = add_subdivision(base, level)
    if not node:
        return
    cmds.setAttr(node + '.divisions', max(1, int(level or 1)))
    set_enabled(node, bool(level))


def set_subdivision_render(base, use_viewport, level=None):
    # Native polygon history is evaluated identically by viewport and render.
    # Keep legacy preview compatibility; independent Arnold subdivision is a separate adapter.
    shape = _shape(base)
    if shape and cmds.attributeQuery('useSmoothPreviewForRender', node=shape, exists=True):
        cmds.setAttr(shape + '.useSmoothPreviewForRender', bool(use_viewport))
        if level is not None:
            cmds.setAttr(shape + '.renderSmoothLevel', int(level))


def add_subdivision(base, level=2):
    shape = _shape(base)
    if shape and cmds.attributeQuery('displaySmoothMesh', node=shape, exists=True):
        cmds.setAttr(shape + '.displaySmoothMesh', 0)
    node = cmds.polySmooth(base, divisions=max(1, int(level)), constructionHistory=True)[0]
    _set_full_membership(node, 'f[*]')
    _mark(node, 'subdiv', base)
    _ensure_cage(base)
    return node


def apply_subdivision(base):
    nodes = [n for n, kind in history_modifiers(base) if kind == 'subdiv']
    if not nodes:
        return False
    return apply_history_modifier(base, nodes[-1])


# ---------------------------------------------------------------- mesh modifier adapter'lari (mirror, array)
def _instance(base, kind, local_matrix):
    inst = cmds.instance(base, name=base.split('|')[-1] + '_' + kind.replace(':', '_'))[0]
    parent = cmds.listRelatives(base, parent=True, fullPath=True)
    current = cmds.listRelatives(inst, parent=True, fullPath=True)
    if parent and (not current or current[0] != parent[0]):
        inst = cmds.parent(inst, parent[0], relative=True)[0]
    elif not parent and current:
        inst = cmds.parent(inst, world=True, relative=True)[0]
    inst = cmds.ls(inst, long=True)[0]
    cmds.xform(inst, objectSpace=True, matrix=local_matrix)
    cmds.connectAttr(base + '.matrix', inst + '.offsetParentMatrix', force=True)
    cmds.addAttr(inst, longName=BASE_ATTR, attributeType='message')
    cmds.connectAttr(base + '.message', inst + '.' + BASE_ATTR, force=True)
    _mark(inst, kind)
    cmds.setAttr(inst + '.overrideEnabled', 1)
    cmds.setAttr(inst + '.overrideDisplayType', 2)     # reference: viewport'ta secilemez
    for attr in ('t', 'r', 's'):                       # yanlislikla tasinip aynayi bozmasin
        for ax in 'xyz':
            cmds.setAttr('%s.%s%s' % (inst, attr, ax), lock=True)
    return inst


def _create_mirror_axis(base, axis, group_id):
    # Blender's Mirror modifier uses object-local axes; Maya's explicit Object mode matches that default.
    node = cmds.polyMirrorFace(base + '.f[*]', axis=AXES.index(axis), axisDirection=0, mirrorAxis=1,
                               mergeMode=1, mergeThreshold=0.001, constructionHistory=True)[0]
    _set_full_membership(node, 'f[*]')
    _mark(node, 'mirror', base)
    if not cmds.attributeQuery('orangeGroup', node=node, exists=True):
        cmds.addAttr(node, longName='orangeGroup', dataType='string')
    cmds.setAttr(node + '.orangeGroup', group_id, type='string')
    _set_base_value(base, MIRROR_EXISTS_ATTR, True, 'bool')
    _ensure_cage(base)
    return node


def _mirror_groups(base, modifiers=None):
    """{grup kimligi: [polyMirror dugumleri]}. modifiers: history_modifiers(base) sonucu (istege bagli)."""
    groups = {}
    for node, kind in (history_modifiers(base) if modifiers is None else modifiers):
        if kind != 'mirror':
            continue
        groups.setdefault(_group_id_of(node), []).append(node)
    return groups


def add_mirror(base, axis='x'):
    """Add a new logical Mirror card, represented by one native node per active axis."""
    group_id = uuid.uuid4().hex
    return _create_mirror_axis(base, axis, group_id)


def set_mirror_axis(base, axis, enabled, node=None, group_id=None):
    """Bir Mirror kartinin eksenini ac / kapat. Kart, group_id (orangeGroup) ile adreslenir: panelin
    eksen kutulari dugum adini degil grup kimligini tasir, cunku ilk dugum silinince ad gecersiz kalir."""
    groups = _mirror_groups(base)
    if group_id is None and node:
        group_id = _group_id_of(node) if cmds.objExists(node) else None
    if group_id is None:
        if not groups:
            return add_mirror(base, axis) if enabled else None
        group_id = list(groups)[-1]
    nodes = groups.get(group_id, [])
    if not nodes and not enabled:
        return None
    existing = next((n for n in nodes if cmds.getAttr(n + '.axis') == AXES.index(axis)), None)
    if enabled:
        return existing or _create_mirror_axis(base, axis, group_id)
    if existing:
        remove_history_modifier(existing)
    return existing


def remove_mirror(base):
    for node, kind in list(history_modifiers(base)):
        if kind == 'mirror':
            remove_history_modifier(node)
    for inst, kind in instance_modifiers(base):
        if kind.startswith('mirror:'):
            remove_instance(inst)
    _set_base_value(base, MIRROR_EXISTS_ATTR, False, 'bool')


def remove_mirror_group(base, node):
    for member in reversed(_mirror_group_for_node(base, node)):
        remove_history_modifier(member)


def _mirror_merge_on(node):
    return cmds.getAttr(node + '.mergeMode') != MIRROR_MERGE_OFF


def mirror_settings(base):
    nodes = [n for n, kind in history_modifiers(base) if kind == 'mirror']
    if nodes:
        node = nodes[-1]
        return _mirror_merge_on(node), float(cmds.getAttr(node + '.mergeThreshold'))
    return bool(_base_value(base, MIRROR_MERGE_ATTR, True)), float(_base_value(base, MIRROR_THRESHOLD_ATTR, 0.001))


def set_mirror_settings(base, merge=None, threshold=None):
    nodes = [n for n, kind in history_modifiers(base) if kind == 'mirror']
    for node in nodes:
        if merge is not None:
            cmds.setAttr(node + '.mergeMode', MIRROR_MERGE_ON if merge else MIRROR_MERGE_OFF)
        if threshold is not None:
            cmds.setAttr(node + '.mergeThreshold', float(threshold))
    if merge is not None:
        _set_base_value(base, MIRROR_MERGE_ATTR, bool(merge), 'bool')
    if threshold is not None:
        _set_base_value(base, MIRROR_THRESHOLD_ATTR, float(threshold))


def array_settings(base):
    nodes = [n for n, kind in history_modifiers(base) if kind == 'array']
    if nodes:
        node = nodes[-1]
        return (cmds.getAttr(node + '.count'),
                [cmds.getAttr(node + '.relative' + a.upper()) for a in AXES],
                [cmds.getAttr(node + '.constant' + a.upper()) for a in AXES])
    count = int(_base_value(base, ARRAY_ATTRS[0], 3))
    relative = [float(_base_value(base, ARRAY_ATTRS[i], 1.0 if i == 1 else 0.0)) for i in range(1, 4)]
    constant = [float(_base_value(base, ARRAY_ATTRS[i], 0.0)) for i in range(4, 7)]
    if not cmds.attributeQuery(ARRAY_ATTRS[0], node=base, exists=True):
        count = len([1 for _inst, kind in instance_modifiers(base) if kind == 'array']) + 1
    return count, relative, constant


def add_array(base, count=3, axis='x', gap=0.0, relative=None, constant=None):
    """Append a live mesh-output Array DG node to the construction-history chain."""
    if relative is None:
        relative = [0.0, 0.0, 0.0]
        relative[AXES.index(axis)] = 1.0
    if constant is None:
        constant = [0.0, 0.0, 0.0]
        constant[AXES.index(axis)] = float(gap)
    relative = [float(v) for v in relative]
    constant = [float(v) for v in constant]
    count = max(1, min(1000, int(count)))
    module_plugin_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'plug-ins')
    module_root_plugin_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                          'plug-ins')
    local_plugin_dir = os.path.dirname(__file__)
    try:
        maya_version = str(cmds.about(version=True))
    except Exception:
        maya_version = ''
    native_name = 'orangeArray.mll' if maya_version.startswith('2027') and os.name == 'nt' else None
    force_python = os.environ.get('ORANGE_ARRAY_FORCE_PYTHON', '').lower() in ('1', 'true', 'yes')
    plugin_candidates = ([os.path.join(module_plugin_dir, native_name),
                          os.path.join(module_root_plugin_dir, native_name),
                          os.path.join(local_plugin_dir, native_name)]
                         if native_name and not force_python else [])
    plugin_candidates.extend([os.path.join(module_plugin_dir, 'orangeArray.py'),
                              os.path.join(module_root_plugin_dir, 'orangeArray.py'),
                              os.path.join(local_plugin_dir, 'orangeArray.py')])
    # Python and C++ builds intentionally share a node type ID. During an in-session
    # upgrade, keep using the already registered implementation instead of attempting
    # to register the competing binary and failing with a duplicate type ID.
    try:
        node_registered = bool(cmds.nodeType('orangeArray', isTypeName=True))
    except Exception:
        node_registered = False
    plugin_path = None if node_registered else next(
        (path for path in plugin_candidates if os.path.isfile(path)), None)
    if not node_registered:
        if plugin_path is None:
            raise RuntimeError(_t('Array: Maya plug-in dosyası bulunamadı'))
        if not cmds.pluginInfo(plugin_path, query=True, loaded=True):
            cmds.loadPlugin(plugin_path, quiet=True)
    shape = _shape(base)
    if not shape:
        raise RuntimeError(_t('Array: mesh shape bulunamadı'))
    input_plug = cmds.listConnections(shape + '.inMesh', source=True, destination=False, plugs=True) or []
    if input_plug:
        source_plug = input_plug[0]
        cmds.disconnectAttr(source_plug, shape + '.inMesh')
    else:
        # Preserve the original mesh as a hidden source shape and create a live result shape.
        source_shape = shape
        out_shape = cmds.createNode('mesh', name=base.split('|')[-1] + 'Shape', parent=base)
        _assign_shading(out_shape, source_shape)
        cmds.setAttr(source_shape + '.intermediateObject', True)
        cmds.setAttr(source_shape + '.visibility', False)
        shape = cmds.ls(out_shape, long=True)[0]
        source_plug = source_shape + '.outMesh'
    node = cmds.createNode('orangeArray', name=base.split('|')[-1] + '_orangeArray')
    cmds.connectAttr(source_plug, node + '.inputMesh', force=True)
    cmds.connectAttr(node + '.outputMesh', shape + '.inMesh', force=True)
    _mark(node, 'array', base)
    for attr, value in [('count', count)] + [('relative' + a.upper(), relative[i]) for i, a in enumerate(AXES)] + \
            [('constant' + a.upper(), constant[i]) for i, a in enumerate(AXES)]:
        cmds.setAttr(node + '.' + attr, value)
    # baseInverseMatrix yalnizca Object Offset verilince baglanir (set_array_object_offset): dugum bu
    # oznitelige bagimli oldugundan surekli baglanti, objeyi tasirken her karede diziyi yeniden hesaplatiyordu.
    _ensure_cage(base)
    return node


def array_object_offset(node):
    """Array dugumune bagli Object Offset transform'u (tam yol) ya da ''."""
    linked = cmds.listConnections(node + '.objectWorldMatrix', source=True, destination=False, plugs=True) or []
    if not linked:
        return ''
    return (cmds.ls(linked[0].split('.worldMatrix', 1)[0], long=True) or [''])[0]


def _disconnect_sources(plug):
    for source in cmds.listConnections(plug, source=True, destination=False, plugs=True) or []:
        cmds.disconnectAttr(source, plug)


def set_array_object_offset(node, base, transform=None):
    """Connect a transform as an animated Blender-style Array Object Offset."""
    base = (cmds.ls(base, long=True) or [base])[0]
    if transform:
        transform = (cmds.ls(transform, long=True) or [None])[0]
        descendants = set(cmds.listRelatives(base, allDescendents=True, fullPath=True) or [])
        if not transform or transform == base or transform in descendants:
            raise RuntimeError(_t('Obje ofseti (Object Offset) farklı ve bu objenin altında olmayan bir transform olmalı'))
        source = transform + '.worldMatrix[0]'
        existing = cmds.listConnections(node + '.objectWorldMatrix', source=True, destination=False, plugs=True) or []
        if existing and existing != [source]:
            cmds.disconnectAttr(existing[0], node + '.objectWorldMatrix')
        if not existing or existing != [source]:
            cmds.connectAttr(source, node + '.objectWorldMatrix', force=True)
        inverse = base + '.worldInverseMatrix[0]'
        if (cmds.listConnections(node + '.baseInverseMatrix', source=True, destination=False, plugs=True) or []) != [inverse]:
            cmds.connectAttr(inverse, node + '.baseInverseMatrix', force=True)
        cmds.setAttr(node + '.useObjectOffset', True)
    else:
        _disconnect_sources(node + '.objectWorldMatrix')
        _disconnect_sources(node + '.baseInverseMatrix')
        cmds.setAttr(node + '.useObjectOffset', False)


def remove_array(base):
    for node, kind in list(history_modifiers(base)):
        if kind == 'array':
            remove_history_modifier(node)
    for inst, k in instance_modifiers(base):
        if k == 'array':
            cmds.delete(inst)
    for name in ARRAY_ATTRS:
        if cmds.attributeQuery(name, node=base, exists=True):
            cmds.deleteAttr(base, attribute=name)


def remove_instance(inst):
    if cmds.objExists(inst):
        cmds.delete(inst)


def migrate_legacy_instances(base):
    """Convert the old instance-based Mirror/Array preview to editable history nodes.

    Legacy Mirror and Array had no recorded relative order. The migration therefore preserves
    their visible settings and appends the corresponding logical cards to the current history.
    Original instances are removed only after every replacement node is created successfully.
    """
    instances = instance_modifiers(base)
    mirrors = [kind.partition(':')[2].lower() for _node, kind in instances
               if kind.startswith('mirror:')]
    arrays = [node for node, kind in instances if kind == 'array']
    if not mirrors and not arrays:
        return False

    # Eski ayarlar taban ozniteliklerinde; yeni dugumler olusunca mirror_settings / array_settings
    # dugumu okur (varsayilan 0.001 / merge acik). Bu yuzden ikisi de dugumler olusturulmadan okunur.
    merge, threshold = mirror_settings(base)
    count, relative, constant = array_settings(base)
    created = []
    try:
        if mirrors:
            group_id = uuid.uuid4().hex
            for axis in AXES:
                if axis in mirrors:
                    created.append(_create_mirror_axis(base, axis, group_id))
            set_mirror_group_settings(created, merge=merge, threshold=threshold)
        if arrays:
            created.append(add_array(base, count=max(1, len(arrays) + 1),
                                     relative=relative, constant=constant))
        for node, _kind in instances:
            remove_instance(node)
        for name in ARRAY_ATTRS + (MIRROR_MERGE_ATTR, MIRROR_THRESHOLD_ATTR, MIRROR_EXISTS_ATTR):
            if cmds.attributeQuery(name, node=base, exists=True):
                cmds.deleteAttr(base, attribute=name)
        return True
    except Exception:
        for node in reversed(created):
            if node and cmds.objExists(node):
                remove_history_modifier(node)
        raise


def apply_mirror(base, inst, threshold=None):
    if cmds.objExists(inst) and cmds.nodeType(inst) == 'polyMirror':
        return apply_history_modifier(base, inst)
    axis = kind_of(inst).partition(':')[2] or 'x'
    cmds.delete(inst)
    remaining = [item for item, kind in instance_modifiers(base) if kind.startswith('mirror:')]
    if not remaining:
        _set_base_value(base, MIRROR_EXISTS_ATTR, False, 'bool')
    merge, stored_threshold = mirror_settings(base)
    threshold = float(threshold if threshold is not None else stored_threshold)
    cmds.polyMirrorFace(base, worldSpace=False, axis=AXES.index(axis), axisDirection=1, mirrorAxis=1,
                        mergeMode=MIRROR_MERGE_ON if merge else MIRROR_MERGE_OFF, mergeThresholdType=1,
                        mergeThreshold=threshold)


def apply_mirrors(base):
    mirrors = [inst for inst, kind in instance_modifiers(base) if kind.startswith('mirror:')]
    for inst in mirrors:
        apply_mirror(base, inst)
    return len(mirrors)


def apply_array(base):
    """Array kopyalarini taban objeyle birlestir; obje donusumu, pivotu, adi ve ebeveyni korunur."""
    nodes = [n for n, k in history_modifiers(base) if k == 'array']
    if nodes:
        return apply_history_modifier(base, nodes[-1])
    insts = [i for i, k in instance_modifiers(base) if k == 'array']
    if not insts:
        return base
    name = base.split('|')[-1]
    parent = cmds.listRelatives(base, parent=True, fullPath=True)
    rp = cmds.xform(base, q=True, objectSpace=True, rotatePivot=True)
    sp = cmds.xform(base, q=True, objectSpace=True, scalePivot=True)
    world = cmds.xform(base, q=True, worldSpace=True, matrix=True)
    if parent:
        base = cmds.parent(base, world=True)[0]
        for inst, _k in instance_modifiers(base):     # kopyalar da tabanin obje uzayinda kalsin
            cmds.parent(inst, world=True, relative=True)
    base = cmds.ls(base, long=True)[0]
    cmds.xform(base, worldSpace=True, matrix=[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
    copies = []
    for inst in instance_modifiers(base):
        if inst[1] != 'array':
            continue
        dup = cmds.duplicate(inst[0])[0]
        for attr in (ATTR, BASE_ATTR):
            if cmds.attributeQuery(attr, node=dup, exists=True):
                cmds.deleteAttr(dup, attribute=attr)
        cmds.setAttr(dup + '.overrideEnabled', 0)
        for attr in ('t', 'r', 's'):
            for ax in 'xyz':
                cmds.setAttr('%s.%s%s' % (dup, attr, ax), lock=False)
        copies.append(dup)
    for inst in insts:
        cmds.delete(inst)
    keep = instance_modifiers(base)      # mirror instance'lari: birlesimden sonra yeniden kur
    keep_kinds = [k for _i, k in keep]
    for inst, _k in keep:
        cmds.delete(inst)
    result = cmds.polyUnite([base] + copies, constructionHistory=True, mergeUVSets=1)[0]
    cmds.delete(result, constructionHistory=True)
    for o in [base] + copies:
        if cmds.objExists(o) and not cmds.listRelatives(o, children=True):
            cmds.delete(o)
    result = cmds.rename(result, name)
    cmds.xform(result, worldSpace=True, matrix=world)
    cmds.xform(result, objectSpace=True, rotatePivot=rp, scalePivot=sp)
    if parent:
        result = cmds.parent(result, parent[0])[0]
    result = cmds.ls(result, long=True)[0]
    for attr in ARRAY_ATTRS:
        if cmds.attributeQuery(attr, node=result, exists=True):
            cmds.deleteAttr(result, attribute=attr)
    for k in keep_kinds:
        if k.startswith('mirror:'):
            add_mirror(result, k.partition(':')[2])
    cmds.select(result, replace=True)
    return result


# ---------------------------------------------------------------- gecmis modifier'lari
def _all_edges_sharper_than(base, angle):
    fn, dag = _mesh_fn(base)
    it = om.MItMeshEdge(dag)
    cos_tol = math.cos(math.radians(angle))
    out = []
    while not it.isDone():
        faces = list(it.getConnectedFaces())
        if len(faces) == 2:
            a = fn.getPolygonNormal(faces[0], om.MSpace.kObject)
            b = fn.getPolygonNormal(faces[1], om.MSpace.kObject)
            if a * b < cos_tol:
                out.append(it.index())
        it.next()
    return out


def add_history_modifier(base, kind, value=None):
    """Tabanin tum mesh'ine gecmis dugumu ekle. Donus: dugum ya da None."""
    if kind == 'bevel':
        # Always create the live modifier. Upstream Subdivision can smooth every
        # evaluated edge below the default 30-degree cutoff, but the Bevel card
        # must still be addable and remain adjustable in the stack.
        # Blender Bevel modifier varsayilanlari: 0.1 m, 1 segment, duz pah. chamfer=False Maya'da sekli kesmez,
        # yalnizca destek halkasi ekler (kose yuzleri duzlemsel olmaz); depth=1 cok segmentte yuvarlak profil;
        # subdivideNgons kose n-gon'larini Blender gibi dortgenlere boler.
        node = cmds.polyBevel3(base + '.e[*]', offset=value or 0.1, segments=1, offsetAsFraction=False,
                               mitering=0, chamfer=True, depth=1.0, roundness=0.5, autoFit=False,
                               filterEdgesByAngle=True, filterAngle=30.0, subdivideNgons=True)[0]
        # Maya's polyBevel3 command may retain its autoFit default on some versions;
        # roundness only acts as the Blender-style profile when autoFit is off.
        cmds.setAttr(node + '.autoFit', False)
    elif kind == 'solidify':
        node = cmds.polyExtrudeFacet(base + '.f[*]', keepFacesTogether=True, thickness=value or 0.1)[0]
    elif kind == 'triangulate':
        node = cmds.polyTriangulate(base + '.f[*]')[0]
    elif kind == 'weld':
        node = cmds.polyMergeVertex(base + '.vtx[*]', distance=value or 0.001)[0]
    else:
        return None
    component = {'bevel': 'e[*]', 'solidify': 'f[*]', 'triangulate': 'f[*]', 'weld': 'vtx[*]'}[kind]
    _set_full_membership(node, component)
    _mark(node, kind, base)
    _ensure_cage(base)
    return node


def _set_full_membership(node, components):
    """Store a wildcard component list so newly generated upstream topology is included."""
    if cmds.attributeQuery('inputComponents', node=node, exists=True):
        cmds.setAttr(node + '.inputComponents', 1, components, type='componentList')


MAIN_ATTR = {'bevel': 'offset', 'solidify': 'thickness', 'weld': 'distance'}
INT_ATTRS = {'bevel': [('segments', 1, 12)], 'solidify': [('divisions', 1, 12)]}
BOOL_ATTRS = {
    'bevel': [('filterEdgesByAngle', 'Açı sınırla'), ('mergeVertices', 'Köşeleri birleştir'),
              ('subdivideNgons', 'N-gonları böl')],
    'solidify': [('keepFacesTogether', 'Yüzleri birlikte tut'), ('reverseAllFaces', 'Normalleri ters çevir')],
    'weld': [('alwaysMergeTwoVertices', 'İki köşeyi daima birleştir'), ('texture', 'UV’leri birleştir')],
}
FLOAT_ATTRS = {
    'bevel': [('roundness', 'Profil', 0.0, 1.0), ('filterAngle', 'Açı', 0.0, 180.0),
              ('mergeVertexTolerance', 'Köşe toleransı', 0.0, 1e6)],
}
ENUM_ATTRS = {
    'bevel': [('mitering', 'Miter', ['Otomatik', 'Uniform', 'Patch', 'Radial', 'Yok'])],
}


def set_enabled(node, on):
    cmds.setAttr(node + '.nodeState', 0 if on else 1)      # 1 = HasNoEffect


def is_enabled(node):
    return cmds.getAttr(node + '.nodeState') == 0


def remove_history_modifier(node):
    if cmds.objExists(node):
        upstream = cmds.listConnections(node_input_plug(node), source=True, destination=False, plugs=True) or []
        downstream = cmds.listConnections(node_output_plug(node), source=False, destination=True, plugs=True) or []
        if len(upstream) == 1 and len(downstream) == 1:
            cmds.disconnectAttr(upstream[0], node_input_plug(node))
            cmds.disconnectAttr(node_output_plug(node), downstream[0])
            cmds.connectAttr(upstream[0], downstream[0], force=True)
            cmds.delete(node)
        else:
            cmds.delete(node)


def apply_history_modifier(base, node=None):
    """Bake the selected card and every upstream Orange card into a new editable source mesh."""
    if node is None:
        node = base
        base = owner_of(node)
    else:
        base = (cmds.ls(base, long=True) or [base])[0]
    if not cmds.objExists(node) or kind_of(node) not in HISTORY_KINDS:
        return False
    if not base:
        raise RuntimeError(_t('Modifier sahibi obje bulunamadı'))
    if in_edit():
        exit_edit()
    stack = [item for item, _kind in history_modifiers(base)]
    if node not in stack:
        return False
    mirror_group = _mirror_group_for_node(base, node)
    last_index = max(stack.index(item) for item in mirror_group) if mirror_group else stack.index(node)
    prefix, suffix = stack[:last_index + 1], stack[last_index + 1:]
    if not suffix:
        return apply_all(base)

    expected_upstream = node_output_plug(prefix[-1])
    actual_upstream = cmds.listConnections(node_input_plug(suffix[0]), source=True,
                                            destination=False, plugs=True) or []
    if actual_upstream != [expected_upstream]:
        raise RuntimeError(_t('Yalnızca bitişik Orange modifier öneki güvenle uygulanabilir'))
    history = list(reversed(cmds.listHistory(base, pruneDagObjects=True) or []))
    prefix_position = history.index(prefix[-1])
    suffix_position = history.index(suffix[0])
    foreign = [item for item in history[prefix_position + 1:suffix_position]
               if item not in prefix + suffix and kind_of(item) not in HISTORY_KINDS
               and cmds.nodeType(item) not in _NON_MODELING_HISTORY_TYPES]
    if foreign:
        raise RuntimeError(_t('Bitişik olmayan Maya history düğümleri arasından modifier uygulanamıyor'))
    if not confirm_apply_prefix(base):
        return False

    states = [(item, cmds.getAttr(item + '.nodeState')) for item in suffix]
    old_cage = cage_shape(base)
    # Kafes silinince ust gecmisi (polyCube1, kullanicinin polyExtrude'u, groupParts/groupId) yetim kalir;
    # kafesle birlikte silmek icin once toplanir (silmeden sonra listHistory kafesi bulamaz).
    cage_history = [item for item in (cmds.listHistory(old_cage, pruneDagObjects=True) or [])
                    if item != old_cage] if old_cage else []
    duplicate = None
    try:
        # Bypass only the downstream Orange nodes, then duplicate Maya's evaluated mesh without history.
        for item, _state in states:
            cmds.setAttr(item + '.nodeState', 1)
        duplicate = cmds.duplicate(base, upstreamNodes=False, inputConnections=False)[0]
        duplicate_shapes = cmds.listRelatives(duplicate, shapes=True, type='mesh',
                                              noIntermediate=True, fullPath=True) or []
        if len(duplicate_shapes) != 1:
            raise RuntimeError(_t('Modifier sonucu mesh kopyalanamadı'))
        duplicate_shape = duplicate_shapes[0]
        if any(kind_of(item) for item in cmds.listHistory(duplicate, pruneDagObjects=True) or []):
            raise RuntimeError(_t('Modifier sonucu history olmadan kopyalanamadı'))
        baked_shape = cmds.parent(duplicate_shape, base, shape=True, relative=True)[0]
        cmds.delete(duplicate)
        duplicate = None

        cmds.connectAttr(baked_shape + '.outMesh', node_input_plug(suffix[0]), force=True)
        cmds.delete(prefix)
        if old_cage and cmds.objExists(old_cage) and old_cage != baked_shape:
            cmds.delete(old_cage)
            _delete_orphaned_history(cage_history)
        if not cmds.attributeQuery('orangeCage', node=baked_shape, exists=True):
            cmds.addAttr(baked_shape, longName='orangeCage', attributeType='bool')
        cmds.setAttr(baked_shape + '.orangeCage', True)
        cmds.setAttr(baked_shape + '.intermediateObject', True)
        cmds.setAttr(baked_shape + '.visibility', False)
        for item, state in states:
            if cmds.objExists(item):
                cmds.setAttr(item + '.nodeState', state)
        cmds.select(base, replace=True)
        return base
    finally:
        if duplicate and cmds.objExists(duplicate):
            cmds.delete(duplicate)
        for item, state in states:
            if cmds.objExists(item) and cmds.getAttr(item + '.nodeState') != state:
                cmds.setAttr(item + '.nodeState', state)


def _delete_orphaned_history(nodes):
    """Baska hicbir seyi beslemeyen (yalnizca birbirine ya da silinmis dugumlere bagli) DG dugumlerini sil.
    DAG, varsayilan ve referans dugumlere dokunulmaz; zincir cozulene kadar yinelenir."""
    remaining = []
    for node in nodes:
        if not cmds.objExists(node) or cmds.ls(node, type='dagNode') or cmds.ls(node, defaultNodes=True):
            continue
        try:
            if cmds.referenceQuery(node, isNodeReferenced=True):
                continue
        except Exception:
            pass
        remaining.append(node)
    changed = True
    while changed and remaining:
        changed = False
        alive = set(remaining)
        for node in list(remaining):
            outputs = set(cmds.listConnections(node, source=False, destination=True) or [])
            if outputs - alive:
                continue
            try:
                cmds.delete(node)
            except Exception:
                continue
            remaining.remove(node)
            alive.discard(node)
            changed = True


def set_mirror_group_settings(nodes, merge=None, threshold=None, cut=None, direction=None):
    for node in nodes:
        if merge is not None:
            cmds.setAttr(node + '.mergeMode', MIRROR_MERGE_ON if merge else MIRROR_MERGE_OFF)
        if threshold is not None:
            cmds.setAttr(node + '.mergeThreshold', float(threshold))
        if cut is not None and cmds.attributeQuery('cutMesh', node=node, exists=True):
            cmds.setAttr(node + '.cutMesh', bool(cut))
        if direction is not None and cmds.attributeQuery('axisDirection', node=node, exists=True):
            cmds.setAttr(node + '.axisDirection', int(direction))


def set_mirror_plane(nodes, center=None, rotation=None):
    """Set one custom object-local mirror plane across all axis nodes in a card."""
    for node in nodes:
        if center is not None:
            cmds.setAttr(node + '.mirrorPlaneCenter', *[float(v) for v in center], type='double3')
        if rotation is not None:
            cmds.setAttr(node + '.mirrorPlaneRotate', *[float(v) for v in rotation], type='double3')


# ---------------------------------------------------------------- hepsini uygula (Ctrl+A)
_NON_MODELING_HISTORY_TYPES = frozenset(('groupParts', 'groupId', 'tweak', 'mesh', 'transform'))


def foreign_history_nodes(base):
    """Return user-visible Maya history that Apply All will also delete."""
    orange_nodes = {node for node, _kind in history_modifiers(base)}
    return [node for node in (cmds.listHistory(base, pruneDagObjects=True) or [])
            if node not in orange_nodes and kind_of(node) not in HISTORY_KINDS
            and cmds.nodeType(node) not in _NON_MODELING_HISTORY_TYPES]


def confirm_apply_all(base):
    """Warn before Apply All removes native Maya history outside Orange's stack."""
    foreign = foreign_history_nodes(base)
    if not foreign or cmds.about(batch=True):
        return True
    details = '\n'.join('%s  (%s)' % (node, cmds.nodeType(node)) for node in foreign[:12])
    if len(foreign) > 12:
        details += '\n… %d more' % (len(foreign) - 12)
    response = cmds.confirmDialog(
        title=_t('Maya geçmişini uygula'),
        message=_t('Apply All, Orange modifier’larının yanında aşağıdaki Maya history düğümlerini de silecek. Devam edilsin mi?')
                + '\n\n' + details,
        button=[_t('Devam et'), _t('İptal')], defaultButton=_t('İptal'),
        cancelButton=_t('İptal'), dismissString=_t('İptal'))
    return response == _t('Devam et')


def confirm_apply_prefix(base):
    """Warn that prefix Apply disconnects upstream Maya history while keeping the downstream stack."""
    foreign = foreign_history_nodes(base)
    if not foreign or cmds.about(batch=True):
        return True
    details = '\n'.join('%s  (%s)' % (node, cmds.nodeType(node)) for node in foreign[:12])
    if len(foreign) > 12:
        details += '\n… %d more' % (len(foreign) - 12)
    response = cmds.confirmDialog(
        title=_t('Modifier önekini uygula'),
        message=_t('Seçili modifier ve öncesi kafese uygulanacak. Aşağıdaki Maya history düğümleri de bake edilecek '
                   've kafes kaynağından ayrılacak.')
                + '\n\n' + details,
        button=[_t('Devam et'), _t('İptal')], defaultButton=_t('İptal'),
        cancelButton=_t('İptal'), dismissString=_t('İptal'))
    return response == _t('Devam et')


def apply_all(base, confirmed=False):
    """Bake the live stack and legacy instance/preview modifiers while preserving the object transform."""
    if not confirmed and not confirm_apply_all(base):
        return False
    if in_edit():
        exit_edit()
    # Migrate legacy instances into real history before Maya bakes the evaluated result.
    for inst, k in instance_modifiers(base):
        if k.startswith('mirror:'):
            apply_mirror(base, inst)
    if any(kind == 'array' for _inst, kind in instance_modifiers(base)):
        base = apply_array(base)
    # Old Orange scenes used shape Smooth Mesh Preview instead of a history node.
    if not any(kind == 'subdiv' for _node, kind in history_modifiers(base)):
        shape = _shape(base)
        if shape and cmds.getAttr(shape + '.displaySmoothMesh'):
            level = cmds.getAttr(shape + '.smoothLevel')
            cmds.setAttr(shape + '.displaySmoothMesh', 0)
            if level:
                cmds.polySmooth(base, divisions=level, constructionHistory=True)
    cmds.delete(base, constructionHistory=True)
    cmds.select(base, replace=True)
    return base


def apply_all_selected():
    bases = []
    for obj in _objs() or cmds.ls(hilite=True, long=True):
        base = base_of(obj) or (obj if _shape_type(obj) == 'mesh' else None)
        if base and base not in bases:
            bases.append(base)
    if not bases:
        _msg(_t('Önce bir mesh seç'))
        return
    if not cmds.about(batch=True) and any(foreign_history_nodes(base) for base in bases):
        all_foreign = []
        for base in bases:
            all_foreign.extend(foreign_history_nodes(base))
        details = '\n'.join('%s  (%s)' % (node, cmds.nodeType(node)) for node in all_foreign[:12])
        response = cmds.confirmDialog(
            title=_t('Maya geçmişini uygula'),
            message=_t('Apply All, Orange modifier’larının yanında aşağıdaki Maya history düğümlerini de silecek. Devam edilsin mi?')
                    + '\n\n' + details,
            button=[_t('Devam et'), _t('İptal')], defaultButton=_t('İptal'),
            cancelButton=_t('İptal'), dismissString=_t('İptal'))
        if response != _t('Devam et'):
            return
    for base in bases:
        apply_all(base, confirmed=True)
    _msg(_t('Modifier\'lar uygulandı: %d obje') % len(bases))


# ---------------------------------------------------------------- panel
_MODIFIER_MIME = 'application/x-orange-modifier-node'


def _modifier_type_icon(kind):
    """Small monochrome topology glyphs for modifier headers, in the Blender Properties style."""
    size = 18
    pixmap = QtGui.QPixmap(size, size)
    global_color = getattr(QtCore.Qt, 'GlobalColor', QtCore.Qt)
    pixmap.fill(global_color.transparent)
    painter = QtGui.QPainter(pixmap)
    try:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    except AttributeError:  # PySide2
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    painter.setPen(QtGui.QPen(QtGui.QColor('#c5cbd2'), 1.25))
    painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 0)))
    if kind == 'subdiv':
        painter.drawRect(3, 3, 12, 12)
        painter.drawLine(7, 3, 7, 15)
        painter.drawLine(11, 3, 11, 15)
        painter.drawLine(3, 7, 15, 7)
        painter.drawLine(3, 11, 15, 11)
    elif kind == 'mirror':
        painter.drawRect(3, 4, 12, 10)
        painter.drawLine(9, 2, 9, 16)
        painter.drawLine(5, 8, 7, 8)
        painter.drawLine(11, 10, 13, 10)
    elif kind == 'array':
        painter.drawRect(2, 5, 7, 9)
        painter.drawRect(6, 3, 7, 9)
        painter.drawRect(10, 5, 6, 9)
    elif kind == 'bevel':
        painter.drawLine(4, 2, 13, 2)
        painter.drawLine(13, 2, 16, 5)
        painter.drawLine(16, 5, 16, 14)
        painter.drawLine(16, 14, 13, 16)
        painter.drawLine(13, 16, 4, 16)
        painter.drawLine(4, 16, 2, 14)
        painter.drawLine(2, 14, 2, 4)
        painter.drawLine(2, 4, 4, 2)
    elif kind == 'solidify':
        painter.drawRect(2, 4, 10, 10)
        painter.drawRect(6, 2, 10, 10)
        painter.drawLine(2, 4, 6, 2)
        painter.drawLine(12, 4, 16, 2)
        painter.drawLine(12, 14, 16, 12)
    elif kind == 'triangulate':
        painter.drawRect(2, 3, 14, 12)
        painter.drawLine(2, 3, 16, 15)
        painter.drawLine(2, 15, 16, 3)
    elif kind == 'weld':
        painter.drawEllipse(2, 5, 6, 6)
        painter.drawEllipse(10, 5, 6, 6)
        painter.drawLine(6, 8, 12, 8)
        painter.drawEllipse(7, 6, 4, 4)
    painter.end()
    return QtGui.QIcon(pixmap)


def _modifier_header_icon(kind, expanded):
    pixmap = QtGui.QPixmap(34, 18)
    global_color = getattr(QtCore.Qt, 'GlobalColor', QtCore.Qt)
    pixmap.fill(global_color.transparent)
    painter = QtGui.QPainter(pixmap)
    try:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    except AttributeError:  # PySide2
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    painter.setPen(QtGui.QPen(QtGui.QColor('#b9bdc2'), 1.5))
    if expanded:
        painter.drawLine(3, 5, 11, 5)
        painter.drawLine(11, 5, 7, 10)
        painter.drawLine(7, 10, 3, 5)
    else:
        painter.drawLine(5, 3, 5, 11)
        painter.drawLine(5, 11, 10, 7)
        painter.drawLine(10, 7, 5, 3)
    painter.drawPixmap(16, 1, _modifier_type_icon(kind).pixmap(16, 16))
    painter.end()
    return QtGui.QIcon(pixmap)


class _ModifierCardHeader(QtWidgets.QToolButton):
    """Kart basligi. Tek tiklama karti etkinlestirir (secer); daraltma / genisletme yalnizca soldaki ok
    simgesinden ya da cift tiklamayla (Blender'daki gibi baslik tiklamasi karti kapatmaz)."""
    ARROW_WIDTH = 24     # ok simgesinin bulundugu sol bolge (padding 7 + ok 14)

    def __init__(self, node, panel, icon_key=None, parent=None):
        super(_ModifierCardHeader, self).__init__(parent)
        self._node = node
        self._panel = panel
        self._icon_key = icon_key or ''
        self._expanded = True
        self.on_activate = None
        self.on_toggle = None
        self.setIcon(_modifier_header_icon(self._icon_key, True))
        self.setArrowType(Qt.ArrowType.NoArrow)
        self.setIconSize(QtCore.QSize(34, 18))
        self._press_pos = None
        self._drag_started = False

    def is_expanded(self):
        return self._expanded

    def set_expanded(self, expanded):
        self._expanded = bool(expanded)
        self.setIcon(_modifier_header_icon(self._icon_key, self._expanded))
        if self.on_toggle is not None:
            self.on_toggle(self._expanded)

    def _click(self, pos):
        if pos.x() <= self.ARROW_WIDTH:
            self.set_expanded(not self._expanded)
        if self.on_activate is not None:
            self.on_activate()

    def mouseDoubleClickEvent(self, event):
        self.set_expanded(not self._expanded)
        if self.on_activate is not None:
            self.on_activate()
        event.accept()

    def mousePressEvent(self, event):
        self._press_pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        super(_ModifierCardHeader, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._node and self._press_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            current = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            if (current - self._press_pos).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
                drag = QtGui.QDrag(self)
                mime = QtCore.QMimeData()
                mime.setData(_MODIFIER_MIME, QtCore.QByteArray(self._node.encode('utf-8')))
                drag.setMimeData(mime)
                drag.setPixmap(self.grab())
                drag.setHotSpot(self._press_pos)
                self._drag_started = True
                self._panel._drag_source_node = self._node
                try:
                    drag.exec(Qt.DropAction.MoveAction)
                except AttributeError:  # PySide2
                    drag.exec_(Qt.MoveAction)
                self._panel._clear_drag_preview(clear_source=True)
                self._press_pos = None
                _run_pending_move(self._panel)
                return
        super(_ModifierCardHeader, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_started:
            self._drag_started = False
            event.accept()
            return
        pressed = self._press_pos
        self._press_pos = None
        super(_ModifierCardHeader, self).mouseReleaseEvent(event)
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        if pressed is not None and event.button() == Qt.MouseButton.LeftButton and self.rect().contains(pos):
            self._click(pos)


class _ModifierDragHandle(QtWidgets.QToolButton):
    def __init__(self, node, panel, header, parent=None):
        super(_ModifierDragHandle, self).__init__(parent)
        self._node = node
        self._panel = panel
        self._header = header
        self._press_pos = None
        self._drag_started = False
        self.setObjectName('ModifierDragHandle')
        self.setText('⠿')
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(_t('Kartı buradan sürükleyerek sırala'))

    def mousePressEvent(self, event):
        self._press_pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        super(_ModifierDragHandle, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        if self._press_pos is not None and event.buttons() & Qt.MouseButton.LeftButton and \
                (pos - self._press_pos).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
            drag = QtGui.QDrag(self)
            mime = QtCore.QMimeData()
            mime.setData(_MODIFIER_MIME, QtCore.QByteArray(self._node.encode('utf-8')))
            drag.setMimeData(mime)
            drag.setPixmap(self._header.grab())
            drag.setHotSpot(QtCore.QPoint(18, 10))
            self._drag_started = True
            self._panel._drag_source_node = self._node
            try:
                drag.exec(Qt.DropAction.MoveAction)
            except AttributeError:  # PySide2
                drag.exec_(Qt.MoveAction)
            self._panel._clear_drag_preview(clear_source=True)
            self._press_pos = None
            _run_pending_move(self._panel)
            return
        super(_ModifierDragHandle, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_started:
            self._drag_started = False
            event.accept()
            return
        self._press_pos = None
        super(_ModifierDragHandle, self).mouseReleaseEvent(event)


class _ModifierCardFrame(QtWidgets.QFrame):
    def __init__(self, panel, target_node, parent=None):
        super(_ModifierCardFrame, self).__init__(parent)
        self._panel = panel
        self._target_node = target_node
        self.setAcceptDrops(bool(target_node))

    def _source_node(self, event):
        payload = event.mimeData().data(_MODIFIER_MIME)
        raw = payload.data() if hasattr(payload, 'data') else bytes(payload)
        return raw.decode('utf-8')

    def _can_drop(self, event, after):
        return self._panel.can_drop_card(self._source_node(event), self._target_node, after)

    def dragEnterEvent(self, event):
        # Girişte kabul edilmezse Qt dragMove olaylarini hic gondermez; konum bazli denetim dragMove'da.
        if event.mimeData().hasFormat(_MODIFIER_MIME) and (
                self._can_drop(event, False) or self._can_drop(event, True)):
            self._update_drop_preview(event)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(_MODIFIER_MIME):
            self._update_drop_preview(event)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._panel._clear_drag_preview()
        super(_ModifierCardFrame, self).dragLeaveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(_MODIFIER_MIME):
            event.ignore()
            return
        source_node = self._source_node(event)
        target_node = self._target_node
        panel = self._panel
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        after = pos.y() >= self.height() / 2
        if not self._can_drop(event, after):
            event.ignore()
            panel._clear_drag_preview(clear_source=True)
            return
        event.acceptProposedAction()
        # Tasima, surukleme dongusu (drag.exec) bittikten sonra kaynak karttan baslatilir: macOS'ta birakma
        # Qt'nin ic dongusunde gelir ve oradaki zamanlayici kartlari kaynak kartin olayi bitmeden silebiliyordu.
        panel._pending_move = (source_node, target_node, after)
        panel._clear_drag_preview(clear_source=True)

    def _update_drop_preview(self, event):
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        after = pos.y() >= self.height() / 2
        if self._can_drop(event, after):
            event.acceptProposedAction()
            self._panel._set_drag_preview(self, after)
        else:
            # Gecersiz hedef: mavi cizgi yok, Qt yasak imlecini gosterir.
            event.ignore()
            self._panel._clear_drag_preview()


class ModifierPanel(MayaQWidgetDockableMixin, QtWidgets.QDialog):
    """Blender Properties > Modifiers karsiligi: secili mesh'in modifier'lari."""

    def __init__(self):
        # Maya's dockable mixin requires parent=None for main-window children and forwards
        # extra positional arguments into MayaQWidgetBaseMixin, which duplicates parent.
        super(ModifierPanel, self).__init__(parent=None)
        self.setObjectName('BlenderKontrolModifiers')
        self.setWindowTitle(_t('Orange: modifier\'lar'))
        self.resize(420, 760)
        self.setMinimumSize(360, 460)
        panel_font = self.font()
        if sys.platform == 'win32':
            panel_font.setFamily('Segoe UI')    # macOS'ta yok: Qt font takma adlarini tararken arayuz takiliyordu
        panel_font.setPointSizeF(9.5)
        self.setFont(panel_font)
        check_icon = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'check_white.svg')
        check_icon = check_icon.replace('\\', '/')
        self.setStyleSheet("""
        QDialog#BlenderKontrolModifiers { background:#303030; color:#e6e6e6; }
        QDialog#BlenderKontrolModifiers QLabel { color:#d5d5d5; }
        QDialog#BlenderKontrolModifiers QLabel[role="muted"] { color:#a5a5a5; }
        QDialog#BlenderKontrolModifiers QComboBox,
        QDialog#BlenderKontrolModifiers QSpinBox,
        QDialog#BlenderKontrolModifiers QDoubleSpinBox {
            background:#292929; color:#e3e3e3; border:1px solid #222222; border-radius:3px;
            min-height:22px; padding:1px 5px; selection-background-color:#568bd2;
        }
        QDialog#BlenderKontrolModifiers QComboBox:hover,
        QDialog#BlenderKontrolModifiers QSpinBox:hover,
        QDialog#BlenderKontrolModifiers QDoubleSpinBox:hover { background:#333333; }
        QDialog#BlenderKontrolModifiers QComboBox:focus,
        QDialog#BlenderKontrolModifiers QSpinBox:focus,
        QDialog#BlenderKontrolModifiers QDoubleSpinBox:focus { border:1px solid #568bd2; }
        QDialog#BlenderKontrolModifiers QComboBox::drop-down {
            border:0; border-left:1px solid #202020; width:19px;
        }
        QDialog#BlenderKontrolModifiers QComboBox QAbstractItemView {
            background:#353535; color:#e3e3e3; border:1px solid #202020;
            selection-background-color:#568bd2; outline:0;
        }
        QDialog#BlenderKontrolModifiers QPushButton {
            background:#484848; color:#e3e3e3; border:1px solid #292929; border-radius:3px;
            min-height:22px; padding:2px 8px;
        }
        QDialog#BlenderKontrolModifiers QPushButton:hover { background:#555555; }
        QDialog#BlenderKontrolModifiers QPushButton:pressed { background:#3b3b3b; }
        QDialog#BlenderKontrolModifiers QPushButton:disabled { color:#7c7c7c; background:#383838; }
        QDialog#BlenderKontrolModifiers QCheckBox { spacing:5px; color:#d5d5d5; }
        QDialog#BlenderKontrolModifiers QCheckBox::indicator {
            width:13px; height:13px; background:#292929; border:1px solid #1e1e1e; border-radius:2px;
        }
        QDialog#BlenderKontrolModifiers QCheckBox::indicator:hover { border-color:#777777; }
        QDialog#BlenderKontrolModifiers QCheckBox::indicator:checked {
            background:#568bd2; border-color:#568bd2;
            image:url("%s");
        }
        QDialog#BlenderKontrolModifiers QToolButton {
            background:#414141; color:#e5e5e5; border:0; text-align:left; padding:5px 7px;
            font-weight:600; min-height:23px;
        }
        QDialog#BlenderKontrolModifiers QToolButton:hover { background:#4a4a4a; }
        QDialog#BlenderKontrolModifiers QToolButton:checked { background:#454545; }
        QDialog#BlenderKontrolModifiers QToolButton#AddModifierButton {
            background:#454545; border:1px solid #282828; border-radius:3px;
            text-align:center; padding:5px 8px; font-weight:600;
        }
        QDialog#BlenderKontrolModifiers QToolButton#AddModifierButton:hover { background:#505050; }
        QDialog#BlenderKontrolModifiers QToolButton#ModifierDragHandle {
            background:transparent; color:#a7adb5; border:0; padding:0; min-width:20px;
        }
        QDialog#BlenderKontrolModifiers QToolButton#ModifierDragHandle:hover { color:#ffffff; background:#4a4a4a; }
        QDialog#BlenderKontrolModifiers QMenu {
            background:#353535; color:#e3e3e3; border:1px solid #202020; padding:3px;
        }
        QDialog#BlenderKontrolModifiers QMenu::item { padding:5px 22px 5px 8px; }
        QDialog#BlenderKontrolModifiers QMenu::item:selected { background:#568bd2; color:#ffffff; }
        QDialog#BlenderKontrolModifiers QScrollArea { border:0; background:#303030; }
        QDialog#BlenderKontrolModifiers QFrame[role="modifier"] {
            background:#383838; border:1px solid #272727; border-radius:3px;
        }
        QDialog#BlenderKontrolModifiers QFrame[role="modifier"][dropPosition="before"] {
            border-top:3px solid #70a5e8;
        }
        QDialog#BlenderKontrolModifiers QFrame[role="modifier"][dropPosition="after"] {
            border-bottom:3px solid #70a5e8;
        }
        QDialog#BlenderKontrolModifiers QFrame[role="modifier"][active="true"] {
            border-color:#568bd2;
        }
        QDialog#BlenderKontrolModifiers QScrollBar:vertical {
            background:#2d2d2d; width:11px; margin:0; border:0;
        }
        QDialog#BlenderKontrolModifiers QScrollBar::handle:vertical {
            background:#555555; min-height:28px; border-radius:4px; margin:2px;
        }
        QDialog#BlenderKontrolModifiers QScrollBar::handle:vertical:hover { background:#6a6a6a; }
        QDialog#BlenderKontrolModifiers QScrollBar::add-line:vertical,
        QDialog#BlenderKontrolModifiers QScrollBar::sub-line:vertical { height:0; }
        """ % check_icon)
        self.base = None
        self.array_timer = None
        self._mutating = False
        self._row_expanded = {}
        self._drag_source_node = None
        self._drag_preview_frame = None
        self._active_card_key = None
        self._stale = True
        self.layout_ = QtWidgets.QVBoxLayout(self)
        self.layout_.setContentsMargins(8, 8, 8, 8)
        self.layout_.setSpacing(6)
        self.head = QtWidgets.QLabel()
        self.head.setTextFormat(Qt.TextFormat.RichText)
        self.head.setMinimumHeight(24)
        self.layout_.addWidget(self.head)
        self.add_button = QtWidgets.QToolButton()
        self.add_button.setObjectName('AddModifierButton')
        self.add_button.setText(_t('Modifier ekle'))
        self.add_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.add_button.setCheckable(True)
        self.add_button.setArrowType(Qt.ArrowType.DownArrow)
        self.add_picker = QtWidgets.QWidget()
        add_grid = QtWidgets.QGridLayout(self.add_picker)
        add_grid.setContentsMargins(2, 2, 2, 4)
        add_grid.setHorizontalSpacing(4)
        add_grid.setVerticalSpacing(4)
        for index, (key, label) in enumerate(self.ADD):
            choice = QtWidgets.QPushButton(_t(label))
            choice.setObjectName('AddModifierChoice')
            choice.clicked.connect(lambda _checked=False, k=key: self._select_add(k))
            add_grid.addWidget(choice, index // 2, index % 2)
        add_grid.setColumnStretch(0, 1)
        add_grid.setColumnStretch(1, 1)
        self.add_picker.setVisible(False)
        self.add_button.toggled.connect(self.add_picker.setVisible)
        size_policy = getattr(QtWidgets.QSizePolicy, 'Policy', QtWidgets.QSizePolicy)
        self.add_button.setSizePolicy(size_policy.Expanding, size_policy.Fixed)
        self.layout_.addWidget(self.add_button)
        self.layout_.addWidget(self.add_picker)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.stack_widget = QtWidgets.QWidget()
        self.body = QtWidgets.QVBoxLayout(self.stack_widget)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(4)
        self.scroll.setWidget(self.stack_widget)
        self.layout_.addWidget(self.scroll, 1)
        bottom = QtWidgets.QHBoxLayout()
        apply_all_btn = QtWidgets.QPushButton(_t('Hepsini uygula (Ctrl+A)'))
        apply_all_btn.clicked.connect(lambda: self._run(lambda: apply_all(self.base, confirmed=True)
                                                        if confirm_apply_all(self.base) else False))
        bottom.addWidget(apply_all_btn)
        self.layout_.addLayout(bottom)
        # Kisa omurlu hata satiri: _run'daki hata yalnizca Script Editor'e degil panele de yazilir.
        self.status = QtWidgets.QLabel()
        self.status.setObjectName('ModifierStatus')
        self.status.setWordWrap(True)
        self.status.setStyleSheet('color:#f0b36a; padding:2px 4px;')
        self.status.setVisible(False)
        self.layout_.addWidget(self.status)
        self.status_timer = QtCore.QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(lambda: self.status.setVisible(False))
        self.jobs = []
        self._ensure_jobs()
        self.refresh()

    ADD = [('subdiv', 'Subdivision Surface'), ('mirror', 'Mirror'), ('array', 'Array'), ('bevel', 'Bevel (30° kenarlar)'),
           ('solidify', 'Solidify (kalınlık)'), ('triangulate', 'Triangulate'), ('weld', 'Weld (mesafeye göre birleştir)')]
    STATUS_MS = 4000

    def show_status(self, text):
        try:
            self.status.setText(text)
            self.status.setVisible(True)
            self.status_timer.start(self.STATUS_MS)
        except RuntimeError:
            pass

    def _run(self, fn, refresh=True):
        if not self.base or not cmds.objExists(self.base):
            return
        result = None
        errors = []

        def guarded():
            # undoable() hatayi yutup cmds.warning verir; panel icin ayrica yakalanir.
            try:
                return fn()
            except Exception as exc:
                errors.append(exc)
                raise
        self._mutating = True
        try:
            result = undoable(guarded)()
        except Exception as exc:
            errors.append(exc)
            _warn(str(exc))
        finally:
            # Attribute edits must not steal object/component selection or keyboard focus.
            try:
                if isinstance(result, str) and cmds.objExists(result) and cmds.nodeType(result) == 'transform':
                    self.base = (cmds.ls(result, long=True) or [result])[0]
            finally:
                self._mutating = False
        if errors:
            self.show_status(str(errors[0]))
        if refresh:
            self.refresh()

    def can_drop_card(self, source_node, target_node, after):
        try:
            return bool(self.base and can_move_history_card(self.base, source_node, target_node, after=after))
        except Exception:
            return False

    _JOB_EVENTS = ('SelectionChanged', 'Undo', 'Redo', 'SceneOpened', 'NewSceneOpened')

    def _ensure_jobs(self):
        """Secim, undo/redo ve sahne degisiminde yenile (dugumler disaridan degisince kartlar bayatlamasin)."""
        alive = []
        for job in self.jobs:
            try:
                if cmds.scriptJob(exists=job):
                    alive.append(job)
            except Exception:
                pass
        if len(alive) == len(self._JOB_EVENTS):
            self.jobs = alive
            return
        self._kill_jobs()
        for event in self._JOB_EVENTS:
            try:
                self.jobs.append(cmds.scriptJob(event=[event, self.refresh], killWithScene=False))
            except Exception:
                pass   # bu Maya surumunde olmayan olay

    def _kill_jobs(self):
        for job in self.jobs:
            try:
                if cmds.scriptJob(exists=job):
                    cmds.scriptJob(kill=job, force=True)
            except Exception:
                pass
        self.jobs = []

    def _add(self, key):
        base = self.base
        if not base or not cmds.objExists(base):
            return

        def run():
            if key == 'subdiv':
                set_subdivision(base, max(1, subdivision_level(base) or 2))
            elif key == 'mirror':
                add_mirror(base, 'x')
                set_mirror_settings(base, merge=True, threshold=0.001)
            elif key == 'array':
                add_array(base, 3, 'x')
            else:
                add_history_modifier(base, key)
            cmds.select(base, replace=True)
        self._run(run)
        # New cards are appended at the end of the stack. Move the panel viewport
        # to that card so the result of a menu choice is immediately visible in
        # the modifier panel instead of appearing to have opened a separate UI.
        QtCore.QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def _select_add(self, key):
        self.add_button.setChecked(False)
        self._add(key)

    def _clear(self):
        self._clear_drag_preview(clear_source=True)
        if self.array_timer is not None:
            self.array_timer.stop()
            self.array_timer = None
        while self.body.count():
            item = self.body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _row(self, title, widgets, reorder=None, state_key=None, icon_key=None):
        drag_node = reorder[0] if reorder else None
        apply_button = None
        remove_button = None
        if reorder:
            apply_button = next((w for w in widgets if isinstance(w, QtWidgets.QPushButton)
                                 and w.text() == _t('Uygula')), None)
            remove_button = next((w for w in widgets if isinstance(w, QtWidgets.QPushButton)
                                  and w.text() == '✕'), None)
            for button in (apply_button, remove_button):
                if button is not None:
                    widgets.remove(button)
        visibility_toggle = next((w for w in widgets if isinstance(w, QtWidgets.QCheckBox)
                                  and w.text() == _t('Açık')), None)
        if visibility_toggle is not None:
            widgets.remove(visibility_toggle)
            visibility_toggle.setToolTip(_t('Modifier görünürlüğünü değiştir'))
            visibility_toggle.setAccessibleName(_t('Modifier görünürlüğü'))
            visibility_toggle.setText('')
        box = _ModifierCardFrame(self, drag_node)
        box.setProperty('role', 'modifier')
        outer = QtWidgets.QVBoxLayout(box)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        header = _ModifierCardHeader(drag_node, self, icon_key)
        header.setText(title)
        header.setToolTip(_t('Tıkla: kartı seç · Ok simgesi / çift tıkla: daralt-genişlet')
                          + ('\n' + _t('Kartı başlığından sürükleyerek sırala') if drag_node else ''))
        state_key = state_key or title
        box.setProperty('active', state_key == self._active_card_key)
        header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        content = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(content)
        lay.setContentsMargins(8, 6, 8, 7)
        lay.setSpacing(5)
        if apply_button is not None:
            size_policy = getattr(QtWidgets.QSizePolicy, 'Policy', QtWidgets.QSizePolicy)
            apply_button.setSizePolicy(size_policy.Expanding, size_policy.Fixed)
            lay.addWidget(apply_button)
        actions = QtWidgets.QHBoxLayout()
        actions.addStretch(1)
        for w in widgets:
            if isinstance(w, QtWidgets.QPushButton):
                actions.addWidget(w)
            else:
                lay.addWidget(w)
        if actions.count() > 1:
            lay.addLayout(actions)
        expanded = self._row_expanded.get(state_key, True)
        content.setVisible(expanded)
        header.on_toggle = lambda opened, body=content, key=state_key: (
            self._row_expanded.__setitem__(key, opened), body.setVisible(opened))
        header.on_activate = lambda key=state_key, card=box: self._activate_card(key, card)
        header.set_expanded(expanded)
        title_row = QtWidgets.QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(2)
        title_row.addWidget(header, 1)
        if visibility_toggle is not None:
            title_row.addWidget(visibility_toggle)
        if reorder:
            if remove_button is not None:
                remove_button.setFixedSize(24, 23)
                remove_button.setToolTip(_t('Modifier kaldır'))
                title_row.addWidget(remove_button)
            grip = _ModifierDragHandle(drag_node, self, header)
            title_row.addWidget(grip)
        outer.addLayout(title_row)
        outer.addWidget(content)
        self.body.addWidget(box)

    def _button(self, text, fn):
        b = QtWidgets.QPushButton(text)
        b.clicked.connect(lambda *_: self._run(fn))
        return b

    def _set_drag_preview(self, frame, after):
        if frame._target_node == self._drag_source_node:
            self._clear_drag_preview()
            return
        if self._drag_preview_frame is not frame:
            self._clear_drag_preview()
            self._drag_preview_frame = frame
        frame.setProperty('dropPosition', 'after' if after else 'before')
        frame.style().unpolish(frame)
        frame.style().polish(frame)
        frame.update()

    def _clear_drag_preview(self, clear_source=False):
        frame = self._drag_preview_frame
        self._drag_preview_frame = None
        if clear_source:
            self._drag_source_node = None
        if frame is not None:
            frame.setProperty('dropPosition', '')
            frame.style().unpolish(frame)
            frame.style().polish(frame)
            frame.update()

    def _activate_card(self, key, card):
        self._active_card_key = key
        for frame in self.stack_widget.findChildren(_ModifierCardFrame):
            frame.setProperty('active', frame is card)
            frame.style().unpolish(frame)
            frame.style().polish(frame)
            frame.update()

    def _form(self, rows):
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)
        form.setContentsMargins(7, 4, 7, 6)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(4)
        try:
            wrap_policy = QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows
        except AttributeError:  # PySide2 / older Maya
            wrap_policy = QtWidgets.QFormLayout.WrapLongRows
        form.setRowWrapPolicy(wrap_policy)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        for label, field in rows:
            form.addRow(_t(label), field)
        return widget

    def _spin(self, value, low, high, decimals=0, step=1.0, prefix=''):
        spin = QtWidgets.QDoubleSpinBox() if decimals else QtWidgets.QSpinBox()
        spin.setRange(low, high)
        if decimals:
            spin.setDecimals(decimals)
        spin.setSingleStep(step)
        # "10" yazarken once 1 uygulanmasin ve her tus icin ayri undo adimi olusmasin: deger Enter / odak
        # kaybinda ya da ok tuslariyla uygulanir.
        spin.setKeyboardTracking(False)
        spin.setValue(value)
        if prefix:
            spin.setPrefix(prefix)
        return spin

    def _triple(self, values, changed, low=-1e6, high=1e6):
        widget = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        for axis, value in zip(AXES, values):
            spin = self._spin(value, low, high, decimals=3, step=0.1)
            spin.setMinimumWidth(62)
            spin.setMaximumWidth(74)
            spin.valueChanged.connect(lambda _v, w=widget, fn=changed: fn(
                [child.value() for child in w.findChildren(QtWidgets.QDoubleSpinBox)]))
            row.addWidget(QtWidgets.QLabel(axis.upper()))
            row.addWidget(spin)
        widget.setMinimumWidth(0)
        return widget

    def _set_array_vector(self, node, prefix, values):
        def update():
            for axis, value in zip(AXES, values):
                cmds.setAttr(node + '.' + prefix + axis.upper(), value)
        self._run(update, False)

    def _use_selected_offset(self, node, base):
        """Secili transform'lardan tabani ve altindakileri disarida birakarak ilkini Object Offset yap.
        Kullanim: once ofset objesi, sonra (Shift ile) bu mesh secilir; panel son secileni gosterir."""
        try:
            selected = cmds.ls(orderedSelection=True, long=True, type='transform') or []
        except Exception:
            selected = []
        selected = selected or cmds.ls(selection=True, long=True, type='transform') or []
        excluded = set(cmds.listRelatives(base, allDescendents=True, fullPath=True) or [])
        excluded.add(base)
        candidate = next((item for item in selected if item not in excluded), None)
        if not candidate:
            self.show_status(_t('Önce ofset objesini, sonra Shift ile bu mesh\'i seç'))
            return
        self._run(lambda: set_array_object_offset(node, base, candidate))

    def refresh(self, *_):
        if self._mutating:
            return
        # Kapali (retain ile gizlenmis) dock'u ya da gizli kayan pencereyi yenilemek bosa; show_panel /
        # showEvent gorununce yeniler (_stale). Mixin isVisible: dock'ta workspaceControl'un acik olmasi
        # (Qt gorunurlugu dock yerlesiminde guvenilir degil), kayan pencerede QWidget gorunurlugu.
        if not self._panel_visible():
            self._stale = True
            return
        self._stale = False
        try:
            self.base = active_mesh()
        except Exception:
            self.base = None
        self._clear()
        if not self.base:
            self.head.setText(_t("Modifier'lar"))
            empty = QtWidgets.QLabel(_t('Modifier listesini görmek için bir mesh seçin'))
            empty.setProperty('role', 'muted')
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(100)
            self.body.addWidget(empty)
            self.body.addStretch(1)
            return
        base = self.base
        self.head.setText('<b>%s</b><span style="color:#aaaaaa">  ·  %s</span>'
                          % (_t("Modifier'lar"), base.split('|')[-1]))
        # History bir kez okunur; kart basina yeniden hesaplanmaz (uzun yiginlarda O(n^2) oluyordu).
        ordered = history_modifiers(base)
        groups = _mirror_groups(base, ordered)
        drawn_mirror_groups = set()
        for node, kind in ordered:
            widgets = []
            if kind == 'mirror':
                group = _mirror_group_for_node(base, node, groups)
                group_id = _group_id_of(group[0])
                if group_id in drawn_mirror_groups:
                    continue
                drawn_mirror_groups.add(group_id)
                enabled = QtWidgets.QCheckBox(_t('Açık'))
                enabled.setChecked(is_enabled(group[0]))
                enabled.toggled.connect(lambda value, ns=tuple(group): self._run(
                    lambda: [set_enabled(n, value) for n in ns], False))
                widgets.append(enabled)
                axes = QtWidgets.QWidget()
                axes_row = QtWidgets.QHBoxLayout(axes)
                axes_row.setContentsMargins(0, 0, 0, 0)
                axes_row.setSpacing(8)
                enabled_axes = {AXES[cmds.getAttr(member + '.axis')] for member in group}
                for letter in AXES:
                    check = QtWidgets.QCheckBox(letter.upper())
                    check.setChecked(letter in enabled_axes)
                    # Grup kimligiyle adreslenir ve kart yenilenir: ilk dugum silinince eski ad gecersizdi
                    # (RuntimeError, kart donuyordu).
                    check.toggled.connect(lambda value, g=group_id, a=letter: self._run(
                        lambda: set_mirror_axis(base, a, value, group_id=g)))
                    axes_row.addWidget(check)
                merge = QtWidgets.QCheckBox(_t('Birleştir (Merge)'))
                merge.setChecked(_mirror_merge_on(group[0]))
                merge.toggled.connect(lambda value, ns=tuple(group): self._run(
                    lambda: set_mirror_group_settings(ns, merge=value), False))
                threshold = self._spin(cmds.getAttr(group[0] + '.mergeThreshold'), 0.0, 1e6,
                                       decimals=5, step=0.001)
                threshold.setEnabled(merge.isChecked())
                merge.toggled.connect(threshold.setEnabled)
                threshold.valueChanged.connect(lambda value, ns=tuple(group): self._run(
                    lambda: set_mirror_group_settings(ns, threshold=value), False))
                cut = QtWidgets.QCheckBox(_t('Ayna düzleminde kes'))
                cut.setChecked(bool(cmds.getAttr(group[0] + '.cutMesh')))
                cut.toggled.connect(lambda value, ns=tuple(group): self._run(
                    lambda: set_mirror_group_settings(ns, cut=value), False))
                flip = QtWidgets.QCheckBox(_t('Yönü ters çevir'))
                flip.setChecked(bool(cmds.getAttr(group[0] + '.axisDirection')))
                flip.toggled.connect(lambda value, ns=tuple(group): self._run(
                    lambda: set_mirror_group_settings(ns, direction=1 if value else 0), False))
                plane_center = self._triple(cmds.getAttr(group[0] + '.mirrorPlaneCenter')[0],
                    lambda values, ns=tuple(group): self._run(
                        lambda: set_mirror_plane(ns, center=values), False))
                plane_rotation = self._triple(cmds.getAttr(group[0] + '.mirrorPlaneRotate')[0],
                    lambda values, ns=tuple(group): self._run(
                        lambda: set_mirror_plane(ns, rotation=values), False))
                widgets.append(self._form([(_t('Eksen'), axes), (_t('Birleştir (Merge)'), merge),
                                           (_t('Birleştirme mesafesi (Merge Distance)'), threshold)]))
                widgets.extend([cut, flip])
                widgets.append(self._form([(_t('Ayna düzlemi merkezi'), plane_center),
                                           (_t('Ayna düzlemi dönüşü'), plane_rotation)]))
                row_node = group[0]
            elif kind == 'array':
                enabled = QtWidgets.QCheckBox(_t('Açık'))
                enabled.setChecked(is_enabled(node))
                enabled.toggled.connect(lambda value, n=node: self._run(
                    lambda: set_enabled(n, value), False))
                widgets.append(enabled)
                count = self._spin(cmds.getAttr(node + '.count'), 1, 1000)
                count.valueChanged.connect(lambda value, n=node: self._run(
                    lambda: cmds.setAttr(n + '.count', value), False))
                relative = self._triple([cmds.getAttr(node + '.relative' + a.upper()) for a in AXES],
                                        lambda vals, n=node: self._set_array_vector(n, 'relative', vals))
                constant = self._triple([cmds.getAttr(node + '.constant' + a.upper()) for a in AXES],
                                        lambda vals, n=node: self._set_array_vector(n, 'constant', vals))
                # Object Offset: sahnedeki tum transform'lari listeleyen combo yerine (buyuk sahnede O(n^2))
                # salt okunur ad + "Seçiliyi kullan" + temizle.
                offset = QtWidgets.QWidget()
                offset_row = QtWidgets.QHBoxLayout(offset)
                offset_row.setContentsMargins(0, 0, 0, 0)
                offset_row.setSpacing(3)
                linked_transform = array_object_offset(node)
                offset_name = QtWidgets.QLineEdit(linked_transform.rsplit('|', 1)[-1] if linked_transform else '')
                offset_name.setReadOnly(True)
                offset_name.setPlaceholderText(_t('Yok'))
                offset_name.setToolTip(linked_transform or _t('Yok'))
                offset_name.setStyleSheet('background:#292929; color:#e3e3e3; border:1px solid #222222; '
                                          'border-radius:3px; min-height:22px; padding:1px 5px;')
                use_selected = QtWidgets.QPushButton(_t('Seçiliyi kullan'))
                use_selected.setToolTip(_t('Önce ofset objesini, sonra Shift ile bu mesh\'i seç'))
                use_selected.clicked.connect(lambda _checked=False, n=node, b=base: self._use_selected_offset(n, b))
                clear_offset = QtWidgets.QPushButton('✕')
                clear_offset.setFixedWidth(26)
                clear_offset.setToolTip(_t('Obje ofsetini (Object Offset) kaldır'))
                clear_offset.setEnabled(bool(linked_transform))
                clear_offset.clicked.connect(lambda _checked=False, n=node, b=base: self._run(
                    lambda: set_array_object_offset(n, b, None)))
                offset_row.addWidget(offset_name, 1)
                offset_row.addWidget(use_selected)
                offset_row.addWidget(clear_offset)
                merge = QtWidgets.QCheckBox(_t('Kopyaları birleştir (Merge Copies)'))
                merge.setChecked(bool(cmds.getAttr(node + '.mergeCopies')))
                merge.toggled.connect(lambda value, n=node: self._run(
                    lambda: cmds.setAttr(n + '.mergeCopies', value), False))
                merge_distance = self._spin(cmds.getAttr(node + '.mergeDistance'), 0.0, 1e6,
                                            decimals=6, step=0.001)
                merge_distance.setEnabled(merge.isChecked())
                merge.toggled.connect(merge_distance.setEnabled)
                merge_distance.valueChanged.connect(lambda value, n=node: self._run(
                    lambda: cmds.setAttr(n + '.mergeDistance', value), False))
                widgets.append(self._form([(_t('Kopya Sayısı'), count), (_t('Göreli Konum'), relative),
                                           (_t('Sabit Konum'), constant), (_t('Obje ofseti (Object Offset)'), offset),
                                           (_t('Birleştirme mesafesi (Merge Distance)'), merge_distance)]))
                widgets.append(merge)
                row_node = node
            elif kind == 'subdiv':
                enabled = QtWidgets.QCheckBox(_t('Açık'))
                enabled.setChecked(is_enabled(node))
                enabled.toggled.connect(lambda value, n=node: self._run(
                    lambda: set_enabled(n, value), False))
                level = self._spin(cmds.getAttr(node + '.divisions'), 1, 6)
                level.valueChanged.connect(lambda value, n=node: self._run(
                    lambda: cmds.setAttr(n + '.divisions', value), False))
                scheme = QtWidgets.QComboBox()
                scheme.addItem(_t('Catmull-Clark'), 0)
                scheme.addItem(_t('Linear'), 1)
                scheme.setCurrentIndex(int(cmds.getAttr(node + '.method')))
                scheme.currentIndexChanged.connect(lambda index, n=node: self._run(
                    lambda: cmds.setAttr(n + '.method', index), False))
                keep_border = QtWidgets.QCheckBox(_t('Sınırı koru'))
                keep_border.setChecked(bool(cmds.getAttr(node + '.keepBorder')))
                keep_border.toggled.connect(lambda value, n=node: self._run(
                    lambda: cmds.setAttr(n + '.keepBorder', value), False))
                smooth_uvs = QtWidgets.QCheckBox(_t('UV’leri yumuşat'))
                smooth_uvs.setChecked(bool(cmds.getAttr(node + '.smoothUVs')))
                smooth_uvs.toggled.connect(lambda value, n=node: self._run(
                    lambda: cmds.setAttr(n + '.smoothUVs', value), False))
                widgets.extend([enabled, self._form([(_t('Seviye'), level), (_t('Yöntem'), scheme)]),
                                smooth_uvs, keep_border])
                row_node = node
            else:
                enabled = QtWidgets.QCheckBox(_t('Açık'))
                enabled.setChecked(is_enabled(node))
                enabled.toggled.connect(lambda value, n=node: self._run(
                    lambda: set_enabled(n, value), False))
                widgets.append(enabled)
                fields = []
                attr = MAIN_ATTR.get(kind)
                if attr:
                    spin = self._spin(cmds.getAttr('%s.%s' % (node, attr)), 0.0, 1e6,
                                      decimals=4, step=0.01)
                    spin.valueChanged.connect(lambda value, plug='%s.%s' % (node, attr): self._run(
                        lambda: cmds.setAttr(plug, value), False))
                    fields.append((_t({'bevel': 'Genişlik (Width)', 'solidify': 'Kalınlık (Thickness)',
                                       'weld': 'Birleştirme mesafesi (Merge Distance)'}[kind]), spin))
                for attr_name, low, high in INT_ATTRS.get(kind, []):
                    spin = self._spin(cmds.getAttr('%s.%s' % (node, attr_name)), low, high)
                    spin.valueChanged.connect(lambda value, plug='%s.%s' % (node, attr_name): self._run(
                        lambda: cmds.setAttr(plug, value), False))
                    fields.append((_t('Segment sayısı (Segments)' if attr_name == 'segments'
                                      else 'Bölme sayısı (Divisions)'), spin))
                for attr_name, label in BOOL_ATTRS.get(kind, []):
                    if not cmds.attributeQuery(attr_name, node=node, exists=True):
                        continue
                    checkbox = QtWidgets.QCheckBox(_t(label))
                    checkbox.setChecked(bool(cmds.getAttr('%s.%s' % (node, attr_name))))
                    checkbox.toggled.connect(lambda value, plug='%s.%s' % (node, attr_name): self._run(
                        lambda: cmds.setAttr(plug, value), False))
                    widgets.append(checkbox)
                for attr_name, label, low, high in FLOAT_ATTRS.get(kind, []):
                    if not cmds.attributeQuery(attr_name, node=node, exists=True):
                        continue
                    spin = self._spin(cmds.getAttr('%s.%s' % (node, attr_name)), low, high,
                                      decimals=3, step=0.05)
                    spin.valueChanged.connect(lambda value, plug='%s.%s' % (node, attr_name): self._run(
                        lambda: cmds.setAttr(plug, value), False))
                    spin.setEnabled(bool(cmds.getAttr(node + '.filterEdgesByAngle'))
                                    if attr_name == 'filterAngle' else
                                    bool(cmds.getAttr(node + '.mergeVertices'))
                                    if attr_name == 'mergeVertexTolerance' else True)
                    fields.append((_t(label), spin))
                    if attr_name == 'filterAngle':
                        limit = next((w for w in widgets if isinstance(w, QtWidgets.QCheckBox)
                                      and w.text() == _t('Açı sınırla')), None)
                        if limit:
                            limit.toggled.connect(spin.setEnabled)
                    elif attr_name == 'mergeVertexTolerance':
                        merge_corners = next((w for w in widgets if isinstance(w, QtWidgets.QCheckBox)
                                              and w.text() == _t('Köşeleri birleştir')), None)
                        if merge_corners:
                            merge_corners.toggled.connect(spin.setEnabled)
                for attr_name, label, options in ENUM_ATTRS.get(kind, []):
                    if not cmds.attributeQuery(attr_name, node=node, exists=True):
                        continue
                    combo = QtWidgets.QComboBox()
                    for value, option in enumerate(options):
                        combo.addItem(_t(option), value)
                    combo.setCurrentIndex(int(cmds.getAttr('%s.%s' % (node, attr_name))))
                    combo.currentIndexChanged.connect(lambda value, plug='%s.%s' % (node, attr_name): self._run(
                        lambda: cmds.setAttr(plug, value), False))
                    fields.append((_t(label), combo))
                if fields:
                    widgets.append(self._form(fields))
                row_node = node
            remove_fn = (lambda n=row_node: remove_mirror_group(base, n)) if kind == 'mirror' else \
                (lambda n=node: remove_history_modifier(n))
            widgets.append(self._button(_t('Uygula'),
                                        lambda n=row_node, b=base:
                                        self._run(lambda: apply_history_modifier(b, n))))
            widgets.append(self._button('✕', lambda fn=remove_fn: self._run(fn)))
            stable_id = group_id if kind == 'mirror' else (cmds.ls(node, uuid=True) or [node])[0]
            self._row(_t(MODIFIER_LABELS.get(kind, kind.capitalize())), widgets, reorder=(
                row_node, can_move_history_modifier(base, row_node, -1, ordered),
                can_move_history_modifier(base, row_node, 1, ordered)),
                state_key='%s:%s' % (kind, stable_id), icon_key=kind)

        legacy_instances = instance_modifiers(base)
        migration_added = False
        for inst, kind in legacy_instances:
            axis = kind.partition(':')[2].upper() if kind.startswith('mirror:') else ''
            apply_fn = (lambda i=inst: apply_mirror(base, i)) if kind.startswith('mirror:') else \
                (lambda: apply_array(base))
            actions = [QtWidgets.QLabel(_t('Eski sahne modifieri; sıralamak için yığına dönüştür'))]
            if not migration_added:
                actions.append(self._button(_t('Yığına dönüştür'),
                                            lambda b=base: self._run(lambda: migrate_legacy_instances(b))))
                migration_added = True
            actions.extend([self._button(_t('Uygula'), apply_fn),
                            self._button('✕', lambda i=inst: self._run(lambda: remove_instance(i)))])
            self._row((_t('Mirror') + ' ' + axis) if axis else _t('Array') + ' (legacy)', actions,
                      state_key='legacy:%s' % ((cmds.ls(inst, uuid=True) or [inst])[0]),
                      icon_key='mirror' if kind.startswith('mirror:') else 'array')
        if not ordered and not legacy_instances:
            empty = QtWidgets.QLabel(_t('Henüz modifier yok'))
            empty.setProperty('role', 'muted')
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(84)
            self.body.addWidget(empty)
        self.body.addStretch(1)
        return

    def _panel_visible(self):
        try:
            return bool(self.isVisible())
        except Exception:
            return bool(QtWidgets.QWidget.isVisible(self))

    # Kapanma yollari: closeEvent (kayan pencere X), reject (Esc), dock'un X'i (dockCloseEventTriggered),
    # kayan pencerenin gizlenmesi. Hepsi scriptJob'lari oldurur; show_panel / showEvent yeniden kurar.
    # Dock yerlesiminde Qt hide/show olaylari guvenilir degil (dock'a alinirken hideEvent gelir, showEvent
    # gelmeyebilir); bu yuzden dock'taki panel icin joblar yalnizca dock kapatilinca olur.
    def closeEvent(self, ev):
        self._kill_jobs()
        super(ModifierPanel, self).closeEvent(ev)

    def reject(self):
        self.close()

    def dockCloseEventTriggered(self):
        self._kill_jobs()
        try:
            super(ModifierPanel, self).dockCloseEventTriggered()
        except AttributeError:
            pass

    def hideEvent(self, ev):
        try:
            docked = self.isDockable()
        except Exception:
            docked = False
        if not docked:
            self._kill_jobs()
        super(ModifierPanel, self).hideEvent(ev)

    def showEvent(self, ev):
        super(ModifierPanel, self).showEvent(ev)
        self._ensure_jobs()
        if self._stale:
            QtCore.QTimer.singleShot(0, self.refresh)


def _adopt_workspace_control(panel, control_name):
    """Var olan (Maya acilisinda uiScript ile geri yuklenen ya da onceki denemeden kalan bos) workspaceControl'un
    icine paneli yerlestir: mixin ayni adla yeni kontrol kurmaya kalkip 'name is not unique' veriyordu."""
    try:
        import maya.OpenMayaUI as omui
        from maya.app.general import mayaMixin
        control = omui.MQtUtil.findControl(control_name)
        widget = omui.MQtUtil.findControl(panel.objectName())
        if not control or not widget:
            return False
        omui.MQtUtil.addWidgetToMayaLayout(int(widget), int(control))
        if not panel.isDockable():
            return False
        mayaMixin.mixinWorkspaceControls[control_name] = panel
        cmds.workspaceControl(control_name, edit=True, uiScript=_UI_SCRIPT, label=panel.windowTitle())
        panel.show()
        return True
    except Exception:
        return False


def _show_dockable_panel(panel):
    """Show an existing panel without asking Maya to create its workspaceControl twice."""
    control_name = panel.objectName() + 'WorkspaceControl'
    try:
        if panel.isDockable():
            # MayaQWidgetDockableMixin.show(dockable=True) creates a new workspaceControl.
            # For a widget already hosted there, call its plain show() to restore that dock.
            panel.show()
            return True

        if cmds.workspaceControl(control_name, query=True, exists=True):
            if _adopt_workspace_control(panel, control_name):
                return True
            cmds.deleteUI(control_name, control=True)
        # uiScript: Maya yeniden acildiginda dock'u bos gri kontrol yerine paneli kurarak geri yukler.
        panel.show(dockable=True, floating=False, area='right', retain=True, width=420, uiScript=_UI_SCRIPT)
        try:
            cmds.workspaceControl(control_name, edit=True, uiScript=_UI_SCRIPT)
        except Exception:
            pass
        return True
    except Exception as dock_error:  # Maya workspace-control failures vary by version and saved UI state.
        # Avoid leaving a duplicate control behind if Maya failed after creating its shell.
        try:
            if (not panel.isDockable()
                    and cmds.workspaceControl(control_name, query=True, exists=True)):
                cmds.deleteUI(control_name, control=True)
        except Exception:
            pass
        _msg(_t('Dockable modifier paneli açılamadı; kayan pencere olarak açılıyor: %s') % dock_error)
        panel.show()
        return False


def restore_panel():
    """workspaceControl uiScript'i: Maya acilista dock'u geri yuklerken cagirir. O anda paneli kurmak (scriptJob,
    sahne sorgusu, gerekirse ayni kontrolu silip yeniden kurmak) Maya'yi her acilista cokertebilir ve Orange'in
    baslatma korumasinin disinda kalir; panel Maya acilisi ve Orange baslatmasi bittikten sonra kurulur."""
    if os.environ.get('ORANGE_DISABLE'):
        return
    cmds.evalDeferred(_restore_deferred, lowestPriority=True)


def _restore_deferred():
    try:
        from .lifecycle import startup_blocked   # dongusel import: cagri aninda
        if startup_blocked():
            return      # onceki acilis yarida kaldi: paneli de kurma
    except Exception:
        pass
    try:
        show_panel()
    except Exception as exc:
        _warn('modifier panel: %s' % exc)


def _run_pending_move(panel):
    """Surukleme dongusu bittikten sonra (kaynak kart artik olay icinde degil) bekleyen tasimayi yap."""
    pending = getattr(panel, '_pending_move', None)
    panel._pending_move = None
    if pending:
        source_node, target_node, after = pending
        QtCore.QTimer.singleShot(0, lambda: panel._run(
            lambda: move_history_card(panel.base, source_node, target_node, after=after)))


def show_panel():
    if not _state.get('maya_started') and not cmds.about(batch=True):
        # Eski surumlerin kaydettigi uiScript (m.show_panel()) Maya acilisinda da buraya gelir
        restore_panel()
        return None
    for w in _open_panels():
        if type(w).__module__ != __name__:
            # Yeniden yuklemeden kalan eski modul paneli: yeni modulle calisamaz, sil ve yeniden kur.
            try:
                w._kill_jobs()
                QtWidgets.QWidget.setVisible(w, False)
                w.setParent(None)
                w.deleteLater()
            except Exception:
                pass
            continue
        w._ensure_jobs()
        _show_dockable_panel(w)
        w.refresh()
        if hasattr(w, 'raise_'):
            w.raise_()
        return w
    panel = ModifierPanel()
    _show_dockable_panel(panel)
    panel._ensure_jobs()     # dock'a alinirken gelen hideEvent joblari oldurmus olabilir
    panel.refresh()
    panel.raise_()
    panel.activateWindow()
    return panel
