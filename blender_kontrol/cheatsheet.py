# -*- coding: utf-8 -*-
"""Yazdirilabilir kisayol karti (HTML). Kullanicinin kendi kisayollari ve diliyle uretilir.

Kategori, komutun tanimlandigi modulden cikarilir (lambda ise cagirdigi ilk fonksiyonun modulu); yeni bir
kisayol eklenince kart elle guncellenmez.
"""
from __future__ import absolute_import, division, print_function

import io
import os
import sys
import tempfile

from .compat import QtCore, QtGui
from .i18n import _lang, _t
from .keys import _combo_label
from .keymap import BINDINGS, CONTEXT_KEYMAPS, SCULPT_KEYMAP, _combo_for

# (modul, baslik) - siralama karttaki siradir
CATEGORIES = [
    ('editmode', 'Modlar ve seçim'), ('selection', 'Modlar ve seçim'),
    ('modal', 'Dönüşüm (G / R / S)'), ('pivot', 'Dönüşüm (G / R / S)'), ('cursor', 'Dönüşüm (G / R / S)'),
    ('mesh', 'Edit modu (mesh)'), ('loopcut', 'Edit modu (mesh)'), ('slide', 'Edit modu (mesh)'),
    ('valuemodal', 'Edit modu (mesh)'),
    ('objects', 'Obje modu'),
    ('view', 'Görünüm'),
    ('anim', 'Animasyon'),
    ('modes', 'Sculpt ve boyama'),
]
GENERAL = 'Genel'
ORDER = []
for _m, _title in CATEGORIES:
    if _title not in ORDER:
        ORDER.append(_title)
ORDER.append(GENERAL)
del _m, _title


def _owner_module(fn):
    """Komutun ait oldugu alt modul adi ('mesh', 'view' ...)."""
    fn = getattr(fn, 'func', fn)                      # functools.partial
    name = getattr(fn, '__module__', '') or ''
    short = name.rpartition('.')[2]
    if short == 'keymap' and hasattr(fn, '__code__'):
        package = sys.modules[__name__.rpartition('.')[0]]
        for global_name in fn.__code__.co_names:     # lambda: cagirdigi ilk paket fonksiyonu
            target = getattr(package, global_name, None)
            module = getattr(target, '__module__', '') or ''
            if module.startswith(package.__name__ + '.'):
                return module.rpartition('.')[2]
    return short


def category(binding):
    owner = _owner_module(binding['fn'])
    for module, title in CATEGORIES:
        if module == owner:
            return title
    return GENERAL


def rows():
    """{kategori: [(kisayol_etiketi, baslik)]} - kullanicinin guncel kisayollariyla."""
    out = dict((title, []) for title in ORDER)
    for action, binding in BINDINGS.items():
        if not binding.get('title'):
            continue
        combo = _combo_for(action)
        if not combo:
            continue
        out[category(binding)].append((_combo_label(combo), _t(binding['title'])))
    return out


CSS = '''
:root { --accent: #e8730c; --ink: #1d1d1f; --muted: #6b6b70; --line: #e4e4e7; --bg: #ffffff; --kbd: #f4f4f5; }
@media (prefers-color-scheme: dark) {
  :root { --ink: #ececef; --muted: #a1a1aa; --line: #34343a; --bg: #18181b; --kbd: #27272a; }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 16px; background: var(--bg); color: var(--ink);
       font: 13px/1.4 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; border-bottom: 3px solid var(--accent);
         padding-bottom: 8px; margin-bottom: 16px; }
h1 { margin: 0; font-size: 22px; } h1 span { color: var(--accent); }
.tag { color: var(--muted); }
main { columns: 3 300px; column-gap: 24px; }
section { break-inside: avoid; margin: 0 0 18px; }
h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: var(--accent); margin: 0 0 6px; }
table { width: 100%; border-collapse: collapse; }
td { padding: 3px 0; border-bottom: 1px solid var(--line); vertical-align: top; }
td.k { white-space: nowrap; padding-right: 10px; width: 1%; }
kbd { font: 11px/1 ui-monospace, Consolas, monospace; background: var(--kbd); border: 1px solid var(--line);
      border-bottom-width: 2px; border-radius: 4px; padding: 2px 5px; }
footer { color: var(--muted); margin-top: 8px; font-size: 11px; }
@media print { body { padding: 0; } main { columns: 3; } }
'''


def _esc(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _kbd(label):
    return '+'.join('<kbd>%s</kbd>' % _esc(part) for part in label.split('+')) if label != '+' else '<kbd>+</kbd>'


def html():
    from . import __version__, TAGLINE   # dongusel import: cagri aninda
    sections = []
    data = rows()
    for title in ORDER:
        items = data[title]
        if not items:
            continue
        body = '\n'.join('<tr><td class="k">%s</td><td>%s</td></tr>' % (_kbd(k), _esc(t)) for k, t in items)
        sections.append('<section><h2>%s</h2><table>%s</table></section>' % (_esc(_t(title)), body))
    extra = [
        (_t('Sculpt modu'), sorted(k for k in SCULPT_KEYMAP)),
        (_t('UV editörü'), sorted(CONTEXT_KEYMAPS['uv'])),
        (_t('Graph Editor / Dope Sheet'), sorted(CONTEXT_KEYMAPS['graph'])),
    ]
    for title, combos in extra:
        sections.append('<section><h2>%s</h2><p>%s</p></section>' % (
            _esc(title), ' '.join(_kbd(_combo_label(c)) for c in combos)))
    return ('<!doctype html><html lang="%s"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Orange %s</title><style>%s</style></head><body>'
            '<header><h1><span>Orange</span> %s</h1><span class="tag">%s · v%s</span></header>'
            '<main>%s</main><footer>%s</footer></body></html>') % (
        _lang(), _esc(_t('kısayol kartı')), CSS, _esc(_t('kısayol kartı')), _esc(TAGLINE), __version__,
        '\n'.join(sections),
        _esc(_t('Fare 3D görünümün üzerindeyken çalışır. F1: ayrıntılı liste, F3: komut ara, Ctrl+,: ayarlar.')))


def export(path=None, open_in_browser=True):
    path = path or os.path.join(tempfile.gettempdir(), 'orange_cheatsheet_%s.html' % _lang())
    with io.open(path, 'w', encoding='utf-8') as fh:
        fh.write(html())
    if open_in_browser:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))
    return path
