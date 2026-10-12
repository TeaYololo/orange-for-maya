# -*- coding: utf-8 -*-
"""Standalone regression check for Array face material assignments.

Run with mayapy tests/array_materials_smoke.py. Set ORANGE_ARRAY_FORCE_PYTHON=1 to
exercise the compatibility plug-in instead of the Maya 2027 Windows native module.
"""
from __future__ import print_function

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import maya.standalone
maya.standalone.initialize(name='python')
import maya.cmds as cmds
import maya.api.OpenMaya as om

if os.environ.get('ORANGE_ARRAY_FORCE_PYTHON', '').lower() in ('1', 'true', 'yes'):
    cmds.loadPlugin(os.path.join(ROOT, 'blender_kontrol', 'orangeArray.py'), quiet=True)

from blender_kontrol.modifiers import add_array, _shape

obj = cmds.polyCube(name='orangeArrayMaterialSmoke')[0]
shading_groups = []
for name in ('orangeArrayRed', 'orangeArrayBlue'):
    shader = cmds.shadingNode('lambert', asShader=True, name=name)
    shading_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + 'SG')
    cmds.connectAttr(shader + '.outColor', shading_group + '.surfaceShader')
    shading_groups.append(shading_group)
cmds.sets(obj + '.f[0:2]', edit=True, forceElement=shading_groups[0])
cmds.sets(obj + '.f[3:5]', edit=True, forceElement=shading_groups[1])
shape = _shape(obj)

selection = om.MSelectionList()
selection.add(shape)
mesh = om.MFnMesh(selection.getDagPath(0))
source_groups, source_assignments = mesh.getConnectedShaders(0)
add_array(obj, 2)

selection = om.MSelectionList()
selection.add(shape)
mesh = om.MFnMesh(selection.getDagPath(0))
result_groups, result_assignments = mesh.getConnectedShaders(0)
expected = list(source_assignments) * 2
actual = list(result_assignments)
if len(result_groups) != len(source_groups) or actual != expected:
    raise AssertionError('Expected %r, got %r (shader groups: %d -> %d)' % (
        expected, actual, len(source_groups), len(result_groups)))
print('Array duplicated %d face material assignments across both copies.' % len(actual))
