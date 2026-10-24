# -*- coding: utf-8 -*-
"""F3 komut arama ve Q favoriler."""
from __future__ import absolute_import, division, print_function

import functools
import json

import maya.cmds as cmds
import maya.mel as mel

from .compat import CTRL_KEY, CTRL, EV_KEY_PRESS, Qt, QtCore, QtGui, QtWidgets, _main_window
from .core import _msg, _search_cache
from .settings import set_setting, setting
from .i18n import _t
from .keys import _combo_label
from .util import _last_view_panel, popup, undoable
from .ui import _clamp_to_screen

_runtime_search_cache = []
_runtime_names_cache = None
_runtime_scan_index = 0


def _search_entries():
    from .keymap import BINDINGS, EXTRA_COMMANDS, _combo_for  # dongusel import: cagri aninda
    if _search_cache:
        return _search_cache + list(_runtime_search_cache)
    entries = []
    for combo, binding in BINDINGS.items():
        if binding.get('title'):
            title = _t(binding['title'])
            if title != binding['title']:
                title += '  /  ' + binding['title']   # iki dilde de aranabilsin
            current = _combo_for(combo)
            entries.append((title, _combo_label(current) if current else '—', ('binding', combo)))
    for title, _fn in EXTRA_COMMANDS:
        shown = _t(title)
        if shown != title:
            shown += '  /  ' + title
        entries.append((shown, '', ('extra', title)))
    # Runtime commands are populated after the palette is visible. Maya can
    # expose thousands of commands and querying each one synchronously from
    # the F3 event freezes Cocoa's UI thread on some macOS installations.
    entries.sort(key=lambda e: e[2][0] == 'runtime')
    _search_cache.extend(entries)
    return entries + list(_runtime_search_cache)


def _runtime_command_names():
    try:
        return cmds.runTimeCommand(q=True, commandArray=True) or []
    except Exception:
        return []


def _runtime_entry(name):
    try:
        cat = cmds.runTimeCommand(name, q=True, category=True) or ''
        if not cat.startswith('Menu items'):
            return None
        ann = cmds.runTimeCommand(name, q=True, annotation=True) or ''
    except Exception:
        return None
    tr = TR_ALIASES.get(name)
    return ('%s  [%s]' % (name, tr) if tr else name, ann, ('runtime', name))


class SearchPalette(QtWidgets.QDialog):
    """F3: Blender'daki menu arama. Blender komutlari + Maya menu komutlari."""

    def __init__(self):
        # Qt.Popup grabs input on Cocoa; a non-modal tool window avoids
        # Maya becoming unresponsive when F3 is opened on macOS.
        super(SearchPalette, self).__init__(_main_window(), Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(520, 380)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText(_t('Ara... (ör. extrude, bevel, mirror, köprü)  ·  Ctrl+Enter: favorilere ekle (Q)'))
        self.edit.setStyleSheet('QLineEdit { padding: 6px; font-size: 13px; border: 2px solid #e8a33d; }')
        self.list = QtWidgets.QListWidget()
        layout.addWidget(self.edit)
        layout.addWidget(self.list)
        self.entries = _search_entries()
        self._runtime_names = _runtime_names_cache
        self._runtime_index = _runtime_scan_index
        self._runtime_loading = False
        self.edit.textChanged.connect(self._filter)
        self.edit.returnPressed.connect(self._run_current)
        self.list.itemActivated.connect(lambda _item: self._run_current())
        self.edit.installEventFilter(self)
        self._filter('')

    def showEvent(self, ev):
        super(SearchPalette, self).showEvent(ev)
        if self._runtime_names is None or self._runtime_index < len(self._runtime_names):
            self._runtime_loading = True
            QtCore.QTimer.singleShot(1, self._load_runtime_batch)

    def _load_runtime_batch(self):
        global _runtime_names_cache, _runtime_scan_index
        if not self._runtime_loading:
            return
        if self._runtime_names is None:
            if _runtime_names_cache is None:
                _runtime_names_cache = _runtime_command_names()
            self._runtime_names = _runtime_names_cache
        end = min(self._runtime_index + 30, len(self._runtime_names))
        for name in self._runtime_names[self._runtime_index:end]:
            entry = _runtime_entry(name)
            if entry:
                self.entries.append(entry)
                _runtime_search_cache.append(entry)
        self._runtime_index = end
        _runtime_scan_index = end
        self._filter(self.edit.text())
        if end < len(self._runtime_names):
            QtCore.QTimer.singleShot(1, self._load_runtime_batch)
        else:
            self._runtime_loading = False

    def closeEvent(self, ev):
        self._runtime_loading = False
        super(SearchPalette, self).closeEvent(ev)

    def event(self, ev):
        # Arac penceresi (Popup degil): disari tiklaninca kendiliginden kapanmaz; odak gidince kapat
        if ev.type() == QtCore.QEvent.Type.WindowDeactivate and self.isVisible():
            QtCore.QTimer.singleShot(0, self.close)
        return super(SearchPalette, self).event(ev)

    def reject(self):
        """Esc: QDialog.reject yalniz gizler; WA_DeleteOnClose icin kapatmak gerekir (her F3+Esc sizmasin)."""
        self.close()

    def _filter(self, text):
        words = [w for w in text.lower().split() if w]
        self.list.clear()
        shown = 0
        for title, detail, action in self.entries:
            hay = (title + ' ' + detail).lower()
            if all(w in hay for w in words):
                item = QtWidgets.QListWidgetItem('%s    —  %s' % (title, detail) if detail else title)
                item.setData(Qt.ItemDataRole.UserRole, action)
                self.list.addItem(item)
                shown += 1
                if shown >= 200:
                    break
        if self.list.count():
            self.list.setCurrentRow(0)

    def eventFilter(self, obj, ev):
        if (ev.type() == EV_KEY_PRESS and int(ev.key()) in (int(Qt.Key.Key_Return), int(Qt.Key.Key_Enter))
                and ev.modifiers() & CTRL_KEY):
            item = self.list.currentItem()
            if item:
                add_favorite(*item.data(Qt.ItemDataRole.UserRole))
            return True
        if ev.type() == EV_KEY_PRESS and int(ev.key()) in (int(Qt.Key.Key_Down), int(Qt.Key.Key_Up)):
            row = self.list.currentRow() + (1 if int(ev.key()) == int(Qt.Key.Key_Down) else -1)
            self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
            return True
        return False

    def _run_current(self):
        from .keymap import BINDINGS, EXTRA_COMMANDS, _run_binding  # dongusel import: cagri aninda
        item = self.list.currentItem()
        self.close()
        if not item:
            return
        kind, name = item.data(Qt.ItemDataRole.UserRole)
        if kind == 'binding':
            QtCore.QTimer.singleShot(0, functools.partial(_run_binding, BINDINGS[name], _last_view_panel()))
        elif kind == 'extra':
            fn = dict(EXTRA_COMMANDS)[name]
            QtCore.QTimer.singleShot(0, undoable(fn))
        else:
            QtCore.QTimer.singleShot(0, lambda: mel.eval(name))


_palette = []    # acik F3 penceresi (her F3 yeni pencere biriktirmesin)


def show_search():
    for old in _palette:
        try:
            old.close()
        except RuntimeError:
            pass        # Qt nesnesi zaten silinmis
    del _palette[:]
    dlg = SearchPalette()
    _palette.append(dlg)
    pos = QtGui.QCursor.pos()
    dlg.move(_clamp_to_screen(pos - QtCore.QPoint(260, 20), dlg.size(), pos))
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    dlg.edit.setFocus()


# F3 aramasinda Turkce kelimeyle bulunabilsin diye sik Maya komutlarinin karsiliklari
TR_ALIASES = {
    'BridgeEdge': 'köprü', 'MirrorPolygonGeometry': 'aynala simetri', 'SmoothPolygon': 'yumuşat pürüzsüz subdivision',
    'CombinePolygons': 'birleştir join', 'SeparatePolygon': 'ayır parçala', 'FillHole': 'delik doldur',
    'PolyExtrude': 'extrude çıkart', 'BevelPolygon': 'bevel pah', 'InsertEdgeLoopTool': 'loop cut kenar halkası',
    'MultiCutTool': 'bıçak kes knife', 'MergeVertices': 'birleştir merge köşe', 'DeleteHistory': 'geçmişi sil history',
    'FreezeTransformations': 'uygula apply freeze dondur', 'CenterPivot': 'pivot ortala origin',
    'Triangulate': 'üçgen', 'Quadrangulate': 'dörtgen quad', 'ReversePolygonNormals': 'normal çevir flip',
    'ConformPolygonNormals': 'normal düzelt', 'SoftPolyEdgeElements': 'yumuşak gölgele shade smooth',
    'HardPolyEdgeElements': 'sert gölgele shade flat', 'PolygonBooleanUnion': 'boolean birleşim',
    'PolygonBooleanDifference': 'boolean fark çıkar', 'PolygonBooleanIntersection': 'boolean kesişim',
    'CreatePolygonType': 'yazı metin text', 'UVEditor': 'uv editör', 'HypershadeWindow': 'malzeme shader material',
    'RenderViewWindow': 'render görüntü', 'GraphEditor': 'animasyon eğri graph', 'OutlinerWindow': 'outliner sahne listesi',
    'DuplicateSpecial': 'kopyala özel instance', 'GroupSelected': 'grupla', 'ParentSelected': 'ebeveyn parent',
    'SlideEdgeTool': 'kaydır slide', 'OffsetEdgeLoopTool': 'ofset kenar', 'DetachComponent': 'rip ayır',
    'ExtractFace': 'yüz ayır extract', 'DuplicateFace': 'yüz kopyala', 'PokePolygon': 'poke üçgen merkez',
    'CreaseTool': 'crease kenar sertliği', 'TargetWeldTool': 'kaynak birleştir weld',
    'polyRetopo': 'retopo yeniden topoloji', 'ReduceEditor': 'azalt decimate reduce',
}


# ---------------------------------------------------------------- Q favoriler, calisma alanlari, toplu ad, walk
def _favorites():
    try:
        data = json.loads(setting('favorites') or '[]')
        return [tuple(x) for x in data if isinstance(x, list) and len(x) == 2]
    except Exception:
        return []


def add_favorite(kind, name):
    favs = _favorites()
    if (kind, name) not in favs:
        favs.append((kind, name))
        set_setting('favorites', json.dumps([list(x) for x in favs]))
    _msg(_t('Favorilere eklendi (Q)'))


def _favorite_label(kind, name):
    from .keymap import BINDINGS, _combo_for  # dongusel import: cagri aninda
    if kind == 'binding' and name in BINDINGS:
        combo = _combo_for(name)
        return '%s    %s' % (_t(BINDINGS[name]['title']), _combo_label(combo) if combo else '')
    return _t(name)


def _run_favorite(kind, name):
    from .keymap import BINDINGS, EXTRA_COMMANDS, _run_binding  # dongusel import: cagri aninda
    if kind == 'binding' and name in BINDINGS:
        _run_binding(BINDINGS[name], _last_view_panel())
    elif kind == 'extra':
        fn = dict(EXTRA_COMMANDS).get(name)
        if fn:
            undoable(fn)()
    else:
        mel.eval(name)


def quick_favorites():
    """Q: Blender Quick Favorites. Eklemek icin F3'te Ctrl+Enter."""
    favs = _favorites()
    items = [(_favorite_label(k, n), functools.partial(_run_favorite, k, n)) for k, n in favs]
    if items:
        items.append(None)
        items.append((_t('Favorileri temizle'), lambda: set_setting('favorites', '[]')))
    else:
        items.append((_t('Favori yok: F3\'te bir komut seçip Ctrl+Enter'), lambda: show_search()))
    popup(_t('Favoriler (Q)'), items)
