# -*- coding: utf-8 -*-
"""Blender ile FBX gidis-donus: Blender'in varsayilan FBX ayarlariyla uyumlu disa / ice aktarma.

Disa aktarma: secim, metre (Blender birimi), Y-up (Blender'in FBX iceri aktarmasi varsayilan olarak
'Forward -Z, Up Y' bekler ve Z-up'a kendisi cevirir), smoothing groups acik (Blender'da sert / yumusak kenarlar
korunur), gecmis baglantilari ve smooth mesh onizlemesi disari yazilmaz.
Ice aktarma: Blender'in varsayilan FBX'i (birim olcegi dosyada) sahne birimine cevrilir, sahneye eklenir.
"""
from __future__ import absolute_import, division, print_function

import os

import maya.cmds as cmds
import maya.mel as mel

from .core import _msg, _warn
from .i18n import _t
from .util import _objs

PLUGIN = 'fbxmaya'


def _ensure_plugin():
    if not cmds.pluginInfo(PLUGIN, q=True, loaded=True):
        cmds.loadPlugin(PLUGIN, quiet=True)
    return cmds.pluginInfo(PLUGIN, q=True, loaded=True)


def _mel_path(path):
    return path.replace(os.sep, '/').replace('"', '')


def export_for_blender(path=None, selection=True, triangulate=False):
    """Secili objeleri Blender'a uygun FBX olarak yaz. Donus: dosya yolu ya da None."""
    if selection and not (_objs() or cmds.ls(sl=True)):
        _msg(_t('Önce dışa aktarılacak objeleri seç'))
        return None
    if path is None:
        res = cmds.fileDialog2(fileFilter='FBX (*.fbx)', dialogStyle=2, fileMode=0,
                               caption=_t('Blender için FBX dışa aktar'))
        if not res:
            return None
        path = res[0]
    if not path.lower().endswith('.fbx'):
        path += '.fbx'
    if not _ensure_plugin():
        _warn('FBX plug-in (fbxmaya) yok')
        return None
    for cmd in ('FBXResetExport',
                'FBXExportSmoothingGroups -v true',
                'FBXExportHardEdges -v false',
                'FBXExportTangents -v false',
                'FBXExportSmoothMesh -v false',
                'FBXExportInstances -v false',
                'FBXExportTriangulate -v %s' % ('true' if triangulate else 'false'),
                'FBXExportInputConnections -v false',
                'FBXExportUpAxis y',
                'FBXExportConvertUnitString m',
                'FBXExportCameras -v false',
                'FBXExportLights -v false'):
        try:
            mel.eval(cmd)
        except Exception as exc:
            _warn('%s: %s' % (cmd, exc))
    mel.eval('FBXExport -f "%s"%s' % (_mel_path(path), ' -s' if selection else ''))
    _msg(_t('Blender için FBX yazıldı: %s') % os.path.basename(path))
    return path


def import_from_blender(path=None):
    """Blender'dan gelen FBX'i sahneye ekle. Donus: yeni ust duzey transform'lar."""
    if path is None:
        res = cmds.fileDialog2(fileFilter='FBX (*.fbx)', dialogStyle=2, fileMode=1,
                               caption=_t('Blender FBX içe aktar'))
        if not res:
            return []
        path = res[0]
    if not _ensure_plugin():
        _warn('FBX plug-in (fbxmaya) yok')
        return []
    before = set(cmds.ls(assemblies=True, long=True) or [])
    for cmd in ('FBXResetImport', 'FBXImportMode -v add', 'FBXImportUpAxis y',
                'FBXImportConvertUnitString %s' % cmds.currentUnit(q=True, linear=True)):
        try:
            mel.eval(cmd)
        except Exception as exc:
            _warn('%s: %s' % (cmd, exc))
    mel.eval('FBXImport -f "%s"' % _mel_path(path))
    new = [n for n in (cmds.ls(assemblies=True, long=True) or []) if n not in before]
    if new:
        cmds.select(new, replace=True)
    _msg(_t('Blender FBX içe aktarıldı: %d obje') % len(new))
    return new
