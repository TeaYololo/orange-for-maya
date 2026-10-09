# -*- coding: utf-8 -*-
"""Surum paketleri: python tools/build_release.py

dist/Orange-<surum>.zip          GitHub Release: drag_drop_install.py + paket + ikonlar + belgeler.
                                  Kullanici zip'i acip drag_drop_install.py'yi Maya'ya surukler.
dist/Orange-<surum>-bundle.zip   Autodesk App Store / ApplicationPlugins duzeni (Orange.bundle):
                                  PackageContents.xml + scripts/ (paket + userSetup.py) + icons/ + Contents/.
                                  %ProgramData%/Autodesk/ApplicationPlugins altina acilinca Maya yukler.

Ayrica docs/cheatsheet_tr.html ve docs/cheatsheet_en.html yeniden uretilir (tools/build_cheatsheet.py).
"""
from __future__ import print_function

import io
import os
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, 'dist')
PACKAGE = 'blender_kontrol'
IGNORE = shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store', 'Thumbs.db')

PACKAGE_CONTENTS = u'''<?xml version="1.0" encoding="utf-8"?>
<ApplicationPackage SchemaVersion="1.0.0"
    ProductType="Application"
    AutodeskProduct="Maya"
    Name="Orange"
    Description="Orange: Maya, the Blender way. Blender keymap, modal tools, pie menus and 3D cursor for Maya."
    AppVersion="{version}"
    Author="Orange contributors"
    AppNameSpace="com.autodesk.exchange.maya.orange"
    HelpFile="./Contents/cheatsheet_en.html"
    OnlineDocumentation="https://github.com/TeaYololo/orange-for-maya"
    ProductCode="*">
  <CompanyDetails Name="Orange contributors" Url="https://github.com/TeaYololo/orange-for-maya" Email="" Phone=" " />
  <RuntimeRequirements SupportPath="./Contents" OS="win64|macOS|linux" Platform="Maya" SeriesMin="2022" SeriesMax="2027" />
  <Components>
    <RuntimeRequirements SupportPath="./Contents" OS="win64|macOS|linux" Platform="Maya" SeriesMin="2022" SeriesMax="2027" />
    <ComponentEntry ModuleName="./scripts/userSetup.py" />
  </Components>
</ApplicationPackage>
'''


def version():
    text = io.open(os.path.join(ROOT, PACKAGE, '__init__.py'), encoding='utf-8').read()
    return re.search(r"^__version__\s*=\s*'([^']+)'", text, re.M).group(1)


def _zip_dir(folder, out):
    base = os.path.dirname(folder)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirs, files in os.walk(folder):
            for f in sorted(files):
                full = os.path.join(dirpath, f)
                zf.write(full, os.path.relpath(full, base).replace(os.sep, '/'))
    return out


def build_zip(ver):
    stage = os.path.join(DIST, 'Orange-%s' % ver)
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(stage)
    shutil.copytree(os.path.join(ROOT, PACKAGE), os.path.join(stage, PACKAGE), ignore=IGNORE)
    shutil.copytree(os.path.join(ROOT, 'icons'), os.path.join(stage, 'icons'), ignore=IGNORE)
    for f in ('drag_drop_install.py', 'README.md', 'LICENSE', 'CHANGELOG.md'):
        shutil.copy2(os.path.join(ROOT, f), stage)
    docs = os.path.join(stage, 'docs')
    os.makedirs(docs)
    for f in ('cheatsheet_tr.html', 'cheatsheet_en.html'):
        src = os.path.join(ROOT, 'docs', f)
        if os.path.exists(src):
            shutil.copy2(src, docs)
    return _zip_dir(stage, os.path.join(DIST, 'Orange-%s.zip' % ver))


def build_bundle(ver):
    sys.path.insert(0, os.path.join(ROOT, PACKAGE))
    import installer   # bagimsiz modul: MODULE_USERSETUP metni
    bundle = os.path.join(DIST, 'Orange.bundle')
    if os.path.isdir(bundle):
        shutil.rmtree(bundle)
    scripts = os.path.join(bundle, 'scripts')
    os.makedirs(scripts)
    shutil.copytree(os.path.join(ROOT, PACKAGE), os.path.join(scripts, PACKAGE), ignore=IGNORE)
    io.open(os.path.join(scripts, 'userSetup.py'), 'w', encoding='utf-8').write(installer.MODULE_USERSETUP)
    shutil.copytree(os.path.join(ROOT, 'icons'), os.path.join(bundle, 'icons'), ignore=IGNORE)
    contents = os.path.join(bundle, 'Contents')
    os.makedirs(contents)
    for f in ('cheatsheet_tr.html', 'cheatsheet_en.html'):
        src = os.path.join(ROOT, 'docs', f)
        if os.path.exists(src):
            shutil.copy2(src, contents)
    shutil.copy2(os.path.join(ROOT, 'LICENSE'), contents)
    io.open(os.path.join(bundle, 'PackageContents.xml'), 'w', encoding='utf-8').write(
        PACKAGE_CONTENTS.format(version=ver))
    return _zip_dir(bundle, os.path.join(DIST, 'Orange-%s-bundle.zip' % ver))


def main():
    ver = version()
    if not os.path.isdir(DIST):
        os.makedirs(DIST)
    try:
        sys.path.insert(0, os.path.join(ROOT, 'tools'))
        import build_cheatsheet
        build_cheatsheet.main()
    except Exception as exc:   # PySide6 yoksa kart atlanir
        print('cheatsheet skipped: %s' % exc)
    for path in (build_zip(ver), build_bundle(ver)):
        print('%s  (%d KB)' % (path, os.path.getsize(path) // 1024))


if __name__ == '__main__':
    main()
