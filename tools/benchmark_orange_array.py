# -*- coding: utf-8 -*-
"""Repeatable Maya standalone timing for Orange Array DG evaluation.

Run with mayapy tools/benchmark_orange_array.py. This creates temporary in-memory scenes only.
Reports warmed parameter-change evaluation time; set ORANGE_ARRAY_FORCE_PYTHON=1 to compare the
Python fallback with the Maya-version-matched native plugin. This is not viewport or UI timing.
"""
from __future__ import print_function

import os
import statistics
import sys
import time

import maya.standalone


maya.standalone.initialize(name='python')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import maya.cmds as cmds  # noqa: E402
from blender_kontrol.modifiers import add_array, _shape  # noqa: E402


def benchmark(subdivisions, count, repeats=5, merge=False):
    cmds.file(new=True, force=True)
    obj = cmds.polyPlane(name='orangeArrayBench', subdivisionsX=subdivisions,
                         subdivisionsY=subdivisions, constructionHistory=True)[0]
    source_faces = cmds.polyEvaluate(_shape(obj), face=True)
    node = add_array(obj, count=count, relative=[0.0, 0.0, 0.0], constant=[0.0, 0.0, 0.0])
    if merge:
        cmds.setAttr(node + '.mergeCopies', True)
    samples = []
    for index in range(repeats):
        started = time.perf_counter()
        cmds.setAttr(node + '.constantX', 0.0001 * (index + 1))
        result_faces = cmds.polyEvaluate(_shape(obj), face=True)
        samples.append((time.perf_counter() - started) * 1000.0)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    print('faces_in=%d count=%d merge=%s faces_out=%d median_ms=%.3f p95_ms=%.3f samples_ms=%s' % (
        source_faces, count, merge, result_faces, statistics.median(samples), p95,
        ','.join('%.3f' % value for value in samples)))


if __name__ == '__main__':
    benchmark(32, 2)
    benchmark(96, 2)
    benchmark(96, 10)
    benchmark(224, 2)
    benchmark(96, 10, merge=True)
