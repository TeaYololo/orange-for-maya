# -*- coding: utf-8 -*-
"""docs/cheatsheet_tr.html ve docs/cheatsheet_en.html: varsayilan kisayollarla yazdirilabilir kart.

Maya gerekmez (testlerdeki sahte maya modulleri kullanilir); PySide6 gerekir:
    python tools/build_cheatsheet.py
Maya icinde kullanicinin kendi kisayollariyla: Orange menusu > Kisayol karti.
"""
from __future__ import print_function

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    sys.path.insert(0, os.path.join(ROOT, 'tests'))
    sys.path.insert(0, ROOT)
    import conftest  # noqa: F401  sahte maya modulleri + ekransiz Qt
    import blender_kontrol as bk
    out = []
    for lang in ('tr', 'en'):
        bk.core._state['lang'] = lang
        path = os.path.join(ROOT, 'docs', 'cheatsheet_%s.html' % lang)
        bk.cheatsheet.export(path=path, open_in_browser=False)
        out.append(path)
        print(path)
    bk.core._state['lang'] = None
    return out


if __name__ == '__main__':
    main()
