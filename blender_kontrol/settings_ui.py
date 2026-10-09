# -*- coding: utf-8 -*-
"""Ayar penceresi ve kisayol duzenleyici (Ctrl+,)."""
from __future__ import absolute_import, division, print_function

import functools

import maya.cmds as cmds

from .compat import EV_KEY_PRESS, Qt, QtGui, QtWidgets, _main_window
from .core import _state
from .settings import FRAME_NAMES, PIVOT_NAMES, SNAP_NAMES, set_setting, setting
from .i18n import _t
from .keys import _combo, _combo_label, _key_name


# ---------------------------------------------------------------- ayar penceresi (Ctrl+,)
class SettingsDialog(QtWidgets.QDialog):
    """Genel ayarlar + kisayol duzenleyici. Degisiklikler aninda uygulanir ve kaydedilir."""

    CHOICES = {
        'language': [('auto', 'Otomatik (sistem dili)'), ('tr', 'Türkçe'), ('en', 'English')],
        'space_action': [('play', 'Oynat / durdur (Blender)'), ('search', 'Arama (F3 gibi)'), ('hotbox', 'Maya hotbox')],
        'pivot': [(k, PIVOT_NAMES[k]) for k in ('median', 'bbox', 'cursor', 'active', 'individual')],
        'orientation': [(k, FRAME_NAMES[k]) for k in ('global', 'local', 'normal', 'view', 'cursor', 'parent')],
        'snap_target': [(k, SNAP_NAMES[k]) for k in ('increment', 'vertex', 'edge', 'face')],
        'cursor_orient': [('none', 'Döndürme (sadece konum)'), ('view', 'Görünüme hizala'),
                          ('surface', 'Yüzey normaline hizala')],
        'overlay': [('qt', 'Qt katmanı (viewport üstünde pencere)'), ('vp2', 'Viewport 2.0 (orange_overlay eklentisi)')],
    }
    CHECKS = [('emulate_numpad', 'Emulate Numpad (üst sıradaki rakamlar = numpad)'),
              ('emulate_3button', 'Emulate 3 Button Mouse (Alt + sol tık = orta tuş)'),
              ('zoom_to_mouse', 'Zoom to Mouse Position (tekerlek fareye doğru)'),
              ('orbit_selection', 'Orbit Around Selection (seçimin etrafında dön)'),
              ('snap_on', 'Snap açık (Shift+Tab)'),
              ('destructive_edit', "Edit modunda geçmiş bırakma (Blender gibi; F9 bu modda çalışmaz, "
                                   "Orange modifier'lı mesh'lere dokunulmaz)")]
    LABELS = {'language': 'Dil', 'space_action': 'Space tuşu', 'pivot': 'Pivot noktası',
              'orientation': 'Dönüşüm oryantasyonu', 'snap_target': 'Snap hedefi',
              'cursor_orient': '3D imleç yönü (Shift+sağ tık)', 'overlay': 'Önizleme çizimi (eksen, loop cut)'}

    def __init__(self):
        super(SettingsDialog, self).__init__(_main_window())
        self.setObjectName('BlenderKontrolSettings')
        self.setWindowTitle(_t('Orange: ayarlar'))
        self.resize(640, 640)
        self.capture_row = None
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._general_tab(), _t('Genel'))
        tabs.addTab(self._keymap_tab(), _t('Kısayollar'))
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(tabs)
        close = QtWidgets.QPushButton(_t('Kapat'))
        close.clicked.connect(self.close)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)

    # -- genel
    def _general_tab(self):
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        for key in ('language', 'space_action', 'pivot', 'orientation', 'snap_target', 'cursor_orient', 'overlay'):
            box = QtWidgets.QComboBox()
            for value, label in self.CHOICES[key]:
                box.addItem(_t(label) if key != 'language' else label, value)
            box.setCurrentIndex(max(0, box.findData(setting(key))))
            box.currentIndexChanged.connect(functools.partial(self._combo_changed, key, box))
            form.addRow(_t(self.LABELS[key]), box)
        for key, label in self.CHECKS:
            check = QtWidgets.QCheckBox(_t(label))
            check.setChecked(bool(setting(key)))
            check.toggled.connect(functools.partial(set_setting, key))
            form.addRow('', check)
        vp2 = QtWidgets.QLabel(_t("Viewport 2.0 çizimi: Linux / macOS'ta önizleme çizgisi siyah kutu olarak görünüyorsa seç. "
                                  'Maya, güvenilir olmayan klasörden eklenti yüklerken her oturumda bir kez izin sorar; '
                                  'sormaması için Windows > Settings/Preferences > Preferences > Security bölümünde '
                                  'Orange klasörünü güvenilir konumlara ekle.'))
        vp2.setWordWrap(True)
        vp2.setStyleSheet('color: gray')
        form.addRow('', vp2)
        note = QtWidgets.QLabel(_t('Dil değişikliği menüye ve bu pencereye yeniden açılınca yansır.'))
        note.setStyleSheet('color: gray')
        form.addRow('', note)
        return page

    def _combo_changed(self, key, box, *_):
        set_setting(key, box.currentData())

    # -- kisayollar
    def _keymap_tab(self):
        from .keymap import BINDINGS  # dongusel import: cagri aninda
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText(_t('Komut ya da kısayol ara...'))
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit)
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([_t('Komut'), _t('Kısayol'), _t('Varsayılan')])
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.cellDoubleClicked.connect(lambda row, _col: self._start_capture(row))
        layout.addWidget(self.table)
        self.status = QtWidgets.QLabel(_t('Kısayolu değiştirmek için satıra çift tıkla, sonra yeni tuşa bas. '
                                          'Esc: vazgeç, Backspace: kısayolu kaldır.'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QtWidgets.QHBoxLayout()
        for label, fn in ((_t('Değiştir'), lambda: self._start_capture(self.table.currentRow())),
                          (_t('Seçileni varsayılana döndür'), self._reset_selected),
                          (_t('Hepsini varsayılana döndür'), self._reset_all)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(fn)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.ids = [c for c, b in BINDINGS.items() if b.get('title')]
        self._fill()
        self.table.installEventFilter(self)
        return page

    def _fill(self):
        from .keymap import BINDINGS, _combo_for  # dongusel import: cagri aninda
        self.table.setRowCount(len(self.ids))
        for row, action in enumerate(self.ids):
            current = _combo_for(action)
            cells = (_t(BINDINGS[action]['title']), _combo_label(current) if current else '—', _combo_label(action))
            for col, text in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                if col == 1 and current != action:
                    item.setForeground(QtGui.QBrush(QtGui.QColor(232, 163, 61)))   # degistirilmis
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self._apply_filter(self.filter_edit.text())

    def _apply_filter(self, text):
        from .keymap import BINDINGS  # dongusel import: cagri aninda
        words = [w for w in text.lower().split() if w]
        for row in range(self.table.rowCount()):
            hay = ' '.join(self.table.item(row, c).text() for c in range(3)).lower()
            hay += ' ' + BINDINGS[self.ids[row]]['title'].lower()
            self.table.setRowHidden(row, not all(w in hay for w in words))

    def _start_capture(self, row):
        from .keymap import BINDINGS  # dongusel import: cagri aninda
        if row is None or row < 0:
            return
        self.capture_row = row
        _state['capturing'] = True
        self.table.setFocus()
        self.status.setText(_t('Yeni kısayola bas: %s') % _t(BINDINGS[self.ids[row]]['title']))
        self.table.item(row, 1).setText('...')

    def _stop_capture(self, message=None):
        self.capture_row = None
        _state['capturing'] = False
        self._fill()
        if message:
            self.status.setText(message)

    def eventFilter(self, obj, ev):
        from .keymap import BINDINGS, _combo_for, _rebuild_keymap, _save_overrides  # dongusel import: cagri aninda
        if self.capture_row is None or ev.type() != EV_KEY_PRESS:
            return False
        key = int(ev.key())
        if key in (int(Qt.Key.Key_Shift), int(Qt.Key.Key_Control), int(Qt.Key.Key_Alt), int(Qt.Key.Key_Meta)):
            return True
        action = self.ids[self.capture_row]
        if key == int(Qt.Key.Key_Escape):
            self._stop_capture(_t('Vazgeçildi'))
            return True
        overrides = dict(_state.get('overrides') or {})
        if key in (int(Qt.Key.Key_Backspace), int(Qt.Key.Key_Delete)) and not ev.modifiers():
            overrides[action] = ''
            _save_overrides(overrides)
            _rebuild_keymap()
            self._stop_capture(_t('Kısayol kaldırıldı: %s') % _t(BINDINGS[action]['title']))
            return True
        name = _key_name(ev)
        if not name:
            self.status.setText(_t('Bu tuş tanınmadı, başka bir tuş dene'))
            return True
        combo = _combo(ev, name)
        message = _t('%s → %s') % (_t(BINDINGS[action]['title']), _combo_label(combo))
        for other in BINDINGS:
            if other != action and _combo_for(other) == combo:
                overrides[other] = ''     # cakisan komutun kisayolu kaldirilir
                message += '  ·  ' + _t('%s artık kısayolsuz') % _t(BINDINGS[other].get('title') or other)
        if combo == action:
            overrides.pop(action, None)
        else:
            overrides[action] = combo
        _save_overrides(overrides)
        _rebuild_keymap()
        self._stop_capture(message)
        return True

    def _reset_selected(self):
        from .keymap import _rebuild_keymap, _save_overrides  # dongusel import: cagri aninda
        row = self.table.currentRow()
        if row < 0:
            return
        overrides = dict(_state.get('overrides') or {})
        overrides.pop(self.ids[row], None)
        _save_overrides(overrides)
        _rebuild_keymap()
        self._fill()

    def _reset_all(self):
        from .keymap import _rebuild_keymap, _save_overrides  # dongusel import: cagri aninda
        _save_overrides({})
        _rebuild_keymap()
        self._fill()
        self.status.setText(_t('Tüm kısayollar varsayılana döndü'))

    def closeEvent(self, ev):
        from .lifecycle import _build_menu  # dongusel import: cagri aninda
        _state['capturing'] = False
        cmds.evalDeferred(_build_menu)    # menudeki onay kutulari guncellensin
        super(SettingsDialog, self).closeEvent(ev)


def show_settings():
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.objectName() == 'BlenderKontrolSettings':
            w.close()
            w.deleteLater()
    dlg = SettingsDialog()
    dlg.show()
    return dlg
