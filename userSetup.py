# Blender for Maya: Maya acilinca Blender kontrollerini otomatik ac.
# Bu dosyayi Documents/maya/<surum>/scripts/ klasorune koy.
# Orada zaten bir userSetup.py varsa, asagidaki satirlari onun sonuna ekle.
import maya.utils


def _blender_for_maya_startup():
    try:
        import blender_kontrol
        blender_kontrol.install()
    except Exception as exc:
        print("[Blender for Maya] yuklenemedi: %s" % exc)


maya.utils.executeDeferred(_blender_for_maya_startup)
