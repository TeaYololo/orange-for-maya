# -*- coding: utf-8 -*-
"""Edit modu (Tab) ve secim modlari (1 / 2 / 3)."""
from __future__ import absolute_import, division, print_function

import maya.cmds as cmds

from .core import _filter, _msg, _state, after_op_hooks
from .settings import setting
from .i18n import _t
from .util import COMP_FILTER, COMP_MASK, COMP_TYPE, _objs, _sel, _shape_type


# ---------------------------------------------------------------- edit modu
def in_edit():
    return bool(cmds.selectMode(q=True, component=True) or cmds.ls(hilite=True))


def current_comp():
    ocm = not cmds.selectMode(q=True, component=True)
    for kind, flag in COMP_TYPE.items():
        try:
            if cmds.selectType(q=True, objectComponent=ocm, **{flag: True}):
                return kind
        except Exception:
            pass
    return _state['comp']


def enter_edit(kind=None):
    kind = kind or _state['comp']
    objs = cmds.ls(hilite=True, long=True) or _objs()
    objs = [o for o in objs if _shape_type(o) in ('mesh', 'nurbsCurve', 'nurbsSurface')]
    if not objs:
        _msg(_t('Önce bir obje seç (sol tık)'))
        return
    _state['comp'] = kind
    mask = COMP_MASK[kind]
    if _shape_type(objs[0]) != 'mesh':
        mask = 'controlVertex'
    keep = _sel() if in_edit() else []
    cmds.select(objs, replace=True)
    cmds.hilite(objs, replace=True)
    # Maya 2027'de dagMenuProc'un doMenuComponentSelectionExt'i maskeleri ayarlamiyor (tiklayinca
    # hicbir sey secilmiyordu); F8 + F9/F10/F11 yolu: bilesen modu + acik maske.
    cmds.selectMode(component=True)
    try:
        cmds.selectType(meshComponents=False)
    except Exception:
        pass
    cmds.selectType(allComponents=False)
    _state['kinds'] = [kind]
    if mask == 'controlVertex':
        cmds.selectType(controlVertex=True)
    else:
        cmds.selectType(**{COMP_TYPE[kind]: True})
    keep = cmds.filterExpand(keep, selectionMask=COMP_FILTER[kind]) if keep else None
    if keep:
        cmds.select(keep, replace=True)
    _msg(_t('Edit modu: %s') % _t({'vertex': 'Köşe (1)', 'edge': 'Kenar (2)', 'face': 'Yüz (3)'}[kind]))


def exit_edit():
    objs = cmds.ls(hilite=True, long=True) or cmds.ls(sl=True, objectsOnly=True, long=True) or []
    try:
        if cmds.selectType(q=True, meshComponents=True):   # coklu bilesen modunu birakma
            cmds.selectType(meshComponents=False)
            cmds.selectType(**{COMP_TYPE[_state['comp']]: True})
    except Exception:
        pass
    cmds.selectMode(object=True)
    if objs:
        cmds.hilite(objs, unHilite=True)
        objs = cmds.ls([cmds.listRelatives(o, parent=True, fullPath=True)[0]
                        if cmds.nodeType(o) != 'transform' else o for o in objs], long=True)
        cmds.select(objs, replace=True)
    _msg(_t('Obje modu'))


_NON_MODELING = ('groupId', 'groupParts', 'tweak', 'shadingEngine', 'objectSet', 'mesh', 'transform')


def finalize_edit():
    """'Edit modunda gecmis birakma' acikken: islemden sonra duzenlenen mesh'lerin modelleme gecmisini
    duzlestir (bakePartialHistory; deformer'lar korunur). Orange gecmis modifier'i (bevel, solidify ...) olan
    mesh'lere dokunulmaz. Modal surerken calismaz; modal bitisinde ayni undo adiminda calisir."""
    if not setting('destructive_edit') or not in_edit():
        return
    filt = _filter()
    if filt is not None and filt.modal is not None:
        return
    for obj in cmds.ls(hilite=True, long=True) or []:
        if _shape_type(obj) != 'mesh':
            continue
        history = cmds.listHistory(obj, pruneDagObjects=True) or []
        modeling = [n for n in history if cmds.nodeType(n) not in _NON_MODELING]
        if not modeling:
            continue
        if any(cmds.attributeQuery('orangeModifier', node=n, exists=True) for n in modeling):
            continue      # canli modifier'i bozma
        cmds.bakePartialHistory(obj, prePostDeformers=True)


after_op_hooks.append(finalize_edit)


def toggle_edit():
    from .modes import _sculpting, exit_sculpt  # dongusel import: cagri aninda
    if _sculpting():
        exit_sculpt()
        enter_edit()
        return
    if in_edit():
        exit_edit()
    else:
        enter_edit()


# ---------------------------------------------------------------- secim modlari (1/2/3, Shift, Ctrl)
KIND_LEVEL = {'vertex': 0, 'edge': 1, 'face': 2}
KIND_NAMES = {'vertex': 'köşe', 'edge': 'kenar', 'face': 'yüz'}


def _active_kinds():
    if cmds.selectType(q=True, meshComponents=True):
        return list(_state.get('kinds') or ['vertex', 'edge', 'face'])
    return [k for k in ('vertex', 'edge', 'face') if cmds.selectType(q=True, **{COMP_TYPE[k]: True})]


def _convert_selection(sel, kind, expand):
    """Blender secim modu gecisi: yukari giderken tamamen secili olanlar (Ctrl: degenler), asagi hepsi."""
    src = current_comp()
    flag = {'vertex': 'toVertex', 'edge': 'toEdge', 'face': 'toFace'}[kind]
    kwargs = {flag: True}
    if KIND_LEVEL[kind] > KIND_LEVEL.get(src, 0) and not expand:
        kwargs['internal'] = True
    return cmds.polyListComponentConversion(sel, **kwargs) or []


def select_mode(kind, extend=False, expand=False):
    """1/2/3: kose/kenar/yuz. Shift: modu ekle/cikar (coklu mod). Ctrl: secimi genisleterek gec."""
    if not in_edit():
        enter_edit(kind)
        return
    if extend:
        kinds = _active_kinds()
        kinds = [k for k in kinds if k != kind] if kind in kinds else kinds + [kind]
        if not kinds:
            return
        kinds = [k for k in ('vertex', 'edge', 'face') if k in kinds]
        _state['comp'], _state['kinds'] = kinds[0], kinds
        if len(kinds) == 1:
            cmds.selectType(meshComponents=False)
            cmds.selectType(allComponents=False)
            cmds.selectType(**{COMP_TYPE[kinds[0]]: True})
            _msg(_t('Seçim modu: %s') % _t(KIND_NAMES[kinds[0]]))
        else:
            # Maya keyfi ikili kombinasyon desteklemiyor: Multi-Component modu kose+kenar+yuz birlikte
            cmds.selectType(polymeshVertex=False, polymeshEdge=False, polymeshFace=False, meshComponents=True)
            _msg(_t('Seçim modu: %s') % ' + '.join(_t(KIND_NAMES[k]) for k in kinds) + '  ' +
                 _t("(Maya'nın çoklu bileşen modu: köşe, kenar ve yüz birlikte seçilebilir)"))
        return
    sel = _sel()
    converted = _convert_selection(sel, kind, expand) if sel else []
    enter_edit(kind)
    if converted:
        cmds.select(converted, replace=True)
