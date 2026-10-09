# -*- coding: utf-8 -*-
"""Orange viewport overlay: Viewport 2.0 icinde 2D cizgi cizen Maya Python eklentisi (plug-in).

Modal eksen cizgisi ve loop cut onizlemesi, viewport'un ustunde ayri bir Qt penceresi yerine Maya'nin kendi
cizim API'siyle (MUIDrawManager) cizilir: kompozitor gerektirmez (macOS / Linux), DPI ve pencere sirasiyla
ugrasmaz. Bu dosya paketin geri kalanini import etmez; cmds.loadPlugin ile yuklenir (bkz. ui.py).

Sahnede tek bir 'orangeOverlay' dugumu olur: kaydedilmez (doNotWrite), Outliner'da gizli, secilemez, undo'ya
girmez. Maya eklentiyi kendi modul adiyla yukledigi icin cizilecek veri paket ile __main__ uzerindeki ortak
bir sozlukte paylasilir (store()).
"""
import sys

import maya.api.OpenMaya as om
import maya.api.OpenMayaRender as omr
import maya.api.OpenMayaUI as omui


def maya_useNewAPI():
    """Maya'ya Python API 2.0 kullanildigini bildirir."""


NODE_NAME = 'orangeOverlay'
# Yerel gelistirme araligi (0x00000-0x7FFFF, Autodesk dagitilmayan eklentilere ayirir). Autodesk App Store
# icin mayaid.autodesk.io'dan kalici blok alinmali.
NODE_ID = om.MTypeId(0x0007F0A1)
DRAW_CLASSIFICATION = 'drawdb/geometry/orangeOverlay'
DRAW_REGISTRANT = 'orangeOverlayPlugin'
STORE_KEY = '_orange_overlay'


def store():
    """{'camera': kamera dag yolu | None, 'lines': [([(x, y), ...], (r, g, b), genislik)]} (port koordinati)."""
    main = sys.modules['__main__']
    data = getattr(main, STORE_KEY, None)
    if data is None:
        data = {'camera': None, 'lines': []}
        setattr(main, STORE_KEY, data)
    return data


class OverlayNode(omui.MPxLocatorNode):
    @staticmethod
    def creator():
        return OverlayNode()

    @staticmethod
    def initialize():
        pass

    def isBounded(self):
        return False


class OverlayData(om.MUserData):
    def __init__(self):
        om.MUserData.__init__(self, False)
        self.lines = []


class OverlayDrawOverride(omr.MPxDrawOverride):
    @staticmethod
    def creator(obj):
        return OverlayDrawOverride(obj)

    def __init__(self, obj):
        omr.MPxDrawOverride.__init__(self, obj, None, True)   # isAlwaysDirty: her karede yeniden ciz

    def supportedDrawAPIs(self):
        return omr.MRenderer.kAllDevices

    def isBounded(self, obj_path, camera_path):
        return False

    def hasUIDrawables(self):
        return True

    def prepareForDraw(self, obj_path, camera_path, frame_context, old_data):
        data = old_data if isinstance(old_data, OverlayData) else OverlayData()
        shared = store()
        want = shared.get('camera')
        cam = camera_path.fullPathName() if camera_path is not None and camera_path.isValid() else ''
        if want and cam and want not in (cam, cam.rpartition('|')[0]):
            data.lines = []          # baska viewport (quad view): cizme
        else:
            data.lines = list(shared.get('lines') or [])
        return data

    def addUIDrawables(self, obj_path, draw_manager, frame_context, data):
        if not isinstance(data, OverlayData) or not data.lines:
            return
        draw_manager.beginDrawable()
        draw_manager.setDepthPriority(omr.MRenderItem.sActivePointDepthPriority)
        for points, rgb, width in data.lines:
            draw_manager.setColor(om.MColor((rgb[0], rgb[1], rgb[2], 1.0)))
            draw_manager.setLineWidth(width)
            for (x0, y0), (x1, y1) in zip(points[:-1], points[1:]):
                draw_manager.line2d(om.MPoint(x0, y0), om.MPoint(x1, y1))
        draw_manager.endDrawable()


def initializePlugin(obj):
    plugin = om.MFnPlugin(obj, 'Orange', '1.0', 'Any')
    plugin.registerNode(NODE_NAME, NODE_ID, OverlayNode.creator, OverlayNode.initialize,
                        om.MPxNode.kLocatorNode, DRAW_CLASSIFICATION)
    omr.MDrawRegistry.registerDrawOverrideCreator(DRAW_CLASSIFICATION, DRAW_REGISTRANT,
                                                  OverlayDrawOverride.creator)


def uninitializePlugin(obj):
    plugin = om.MFnPlugin(obj)
    omr.MDrawRegistry.deregisterDrawOverrideCreator(DRAW_CLASSIFICATION, DRAW_REGISTRANT)
    plugin.deregisterNode(NODE_ID)
