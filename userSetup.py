# Orange (Maya, the Blender way): Maya acilinca otomatik baslat.
# Start Orange automatically when Maya opens.
#
# Gerek yok / not needed: drag_drop_install.py Orange'i bir Maya modulu olarak kurar ve modul kendi
# userSetup.py dosyasini getirir. Bu dosya yalnizca elle kurulum icindir: blender_kontrol klasorunu
# Documents/maya/<surum>/scripts/ altina kopyaladiysan bu satirlari kendi userSetup.py dosyanin sonuna ekle.
import maya.utils


def _orange_startup():
    try:
        import blender_kontrol
        blender_kontrol.install()
    except Exception as exc:
        print("[Orange] yuklenemedi / could not start: %s" % exc)


maya.utils.executeDeferred(_orange_startup)
