# -*- coding: utf-8 -*-
"""Blender-style preferences and editable keymap for Maya."""
from __future__ import absolute_import, division, print_function

import functools

import maya.cmds as cmds

from .compat import EV_KEY_PRESS, Qt, QtCore, QtGui, QtWidgets, _main_window
from .core import _state
from .settings import FRAME_NAMES, PIVOT_NAMES, SNAP_NAMES, set_setting, setting
from .i18n import _t
from .keys import _combo, _combo_label, _key_name


class SettingsDialog(QtWidgets.QDialog):
    """Compact Preferences window; settings save as soon as they change."""

    CHOICES = {
        'language': [('auto', 'Auto (system language) / Otomatik'), ('en', 'English'), ('tr', 'Türkçe')],
        'space_action': [('play', 'Oynat / durdur (Blender)'), ('search', 'Arama (F3 gibi)'), ('hotbox', 'Maya hotbox')],
        'pivot': [(k, PIVOT_NAMES[k]) for k in ('median', 'bbox', 'cursor', 'active', 'individual')],
        'orientation': [(k, FRAME_NAMES[k]) for k in ('global', 'local', 'normal', 'view', 'cursor', 'parent')],
        'snap_target': [(k, SNAP_NAMES[k]) for k in ('increment', 'vertex', 'edge', 'face')],
        'cursor_orient': [('none', 'Döndürme (sadece konum)'), ('view', 'Görünüme hizala'),
                          ('surface', 'Yüzey normaline hizala')],
        'overlay': [('qt', 'Qt katmanı (viewport üstünde pencere)'), ('vp2', 'Viewport 2.0 (orange_overlay eklentisi)')],
    }
    LABELS = {
        'language': 'Language / Dil', 'space_action': 'Space tuşu', 'pivot': 'Pivot noktası',
        'orientation': 'Dönüşüm oryantasyonu', 'snap_target': 'Snap hedefi',
        'cursor_orient': '3D imleç yönü (Shift+sağ tık)', 'overlay': 'Önizleme çizimi (eksen, loop cut)',
        'emulate_numpad': 'Emulate Numpad',
        'emulate_3button': 'Emulate 3 Button Mouse',
        'zoom_to_mouse': 'Zoom to Mouse Position',
        'orbit_selection': 'Orbit Around Selection',
        'snap_on': 'Snap açık (Shift+Tab)',
        'destructive_edit': 'Edit modunda geçmiş bırakma (Blender gibi)',
        'auto_camera_select': 'Wireframe / X-Ray\'de arkadakileri de seç',
        'origin_dots': 'Seçili objelerin origin noktasını göster',
    }
    # Onay kutusu etiketi sarmaz: aciklama kutunun altinda soluk satirda ve ipucunda
    NOTES = {
        'emulate_numpad': 'Üst sıradaki rakamlar numpad gibi çalışır (görünümler, 1 / 2 / 3 seçim modları Shift ile).',
        'emulate_3button': 'Alt + sol tık orta tuş gibi davranır (tek tuşlu fare / dokunmatik yüzey).',
        'zoom_to_mouse': 'Tekerlek fare imlecine doğru yakınlaştırır.',
        'orbit_selection': 'Görünüm seçimin etrafında döner.',
        'auto_camera_select': 'Solid görünümde yalnız görünenler seçilir; Wireframe ya da X-Ray açılınca '
                              'arkadakiler de (Maya: camera based selection).',
        'origin_dots': 'Blender gibi seçili objelerin (edit modunda düzenlenen objenin) origin\'i işaretlenir '
                       '(Maya: pivot göstergesi).',
        'destructive_edit': "F9 bu modda çalışmaz; Orange modifier'lı mesh'lere dokunulmaz.",
    }
    PAGE_LABELS = {
        'interface': 'Arayüz', 'modeling': 'Modelleme', 'navigation': 'Gezinme',
        'viewport': 'Görünüm alanı', 'keymap': 'Tuş haritası',
    }
    NAVIGATION = [
        ('interface', ('language', 'space_action'), ('emulate_numpad', 'emulate_3button')),
        ('modeling', ('pivot', 'orientation', 'snap_target'), ('snap_on', 'destructive_edit')),
        ('navigation', ('cursor_orient',), ('zoom_to_mouse', 'orbit_selection')),
        ('viewport', ('overlay',), ('auto_camera_select', 'origin_dots')),
    ]
    GROUPS = ['3D Görünüm', 'Outliner', 'UV Editor', 'Graph Editor', 'Diğer']
    CAPTURE_COLOR = QtGui.QColor(232, 163, 61)

    _STYLE = """
    QDialog#BlenderKontrolSettings { background:#383838; color:#dddddd; }
    QDialog#BlenderKontrolSettings QLabel { color:#dddddd; }
    QDialog#BlenderKontrolSettings QLineEdit,
    QDialog#BlenderKontrolSettings QComboBox,
    QDialog#BlenderKontrolSettings QTreeWidget {
        background:#292929; color:#e2e2e2; border:1px solid #252525; border-radius:2px;
        selection-background-color:#4774a7; selection-color:#ffffff;
    }
    QDialog#BlenderKontrolSettings QLineEdit,
    QDialog#BlenderKontrolSettings QComboBox { min-height:23px; padding:1px 5px; }
    QDialog#BlenderKontrolSettings QTreeWidget { alternate-background-color:#333333; outline:0; }
    QDialog#BlenderKontrolSettings QHeaderView::section {
        background:#303030; color:#c7c7c7; padding:4px 6px; border:0; border-right:1px solid #242424;
        border-bottom:1px solid #202020; font-weight:normal;
    }
    QDialog#BlenderKontrolSettings QTreeWidget::item { min-height:23px; padding:1px 3px; }
    QDialog#BlenderKontrolSettings QPushButton {
        background:#505050; color:#e3e3e3; border:1px solid #252525; border-radius:2px;
        min-height:23px; padding:2px 8px;
    }
    QDialog#BlenderKontrolSettings QPushButton:hover { background:#626262; }
    QDialog#BlenderKontrolSettings QPushButton[nav="true"] {
        text-align:left; background:transparent; border-color:transparent; padding-left:10px;
    }
    QDialog#BlenderKontrolSettings QPushButton[nav="true"]:checked {
        background:#4774a7; border-color:#4774a7; color:#ffffff;
    }
    QDialog#BlenderKontrolSettings QLabel[role="heading"] {
        color:#f0f0f0; font-size:13px; font-weight:500; padding:4px 0 5px;
        border-bottom:1px solid #242424;
    }
    QDialog#BlenderKontrolSettings QLabel[role="muted"] { color:#aaaaaa; }
    QDialog#BlenderKontrolSettings QLabel[role="note"] { color:#9a9a9a; font-size:11px; padding-left:22px; }
    QDialog#BlenderKontrolSettings QGroupBox { border:0; margin-top:6px; padding-top:3px; }
    QDialog#BlenderKontrolSettings QScrollArea { border:0; background:transparent; }
    """

    def __init__(self, page=None, filter_text=None):
        super(SettingsDialog, self).__init__(_main_window())
        self.setObjectName('BlenderKontrolSettings')
        self.setWindowTitle(_t('Orange: ayarlar'))
        self.resize(760, 610)
        self.setMinimumSize(640, 500)
        self.setStyleSheet(self._STYLE)
        self.capture_action = None
        self.current_page = None
        self._filling = False

        shell = QtWidgets.QHBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.nav = QtWidgets.QWidget()
        self.nav.setFixedWidth(148)
        self.nav.setStyleSheet('background:#303030; border-right:1px solid #242424;')
        nav_layout = QtWidgets.QVBoxLayout(self.nav)
        nav_layout.setContentsMargins(8, 10, 8, 8)
        nav_layout.setSpacing(3)
        for i, (page_name, label) in enumerate(self.PAGE_LABELS.items()):
            if page_name == 'keymap':
                line = QtWidgets.QFrame()
                line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
                line.setStyleSheet('color:#222222; margin:5px 2px;')
                nav_layout.addWidget(line)
            button = QtWidgets.QPushButton(_t(label))
            button.setCheckable(True)
            button.setProperty('nav', True)
            button.clicked.connect(functools.partial(self._show_page, page_name))
            nav_layout.addWidget(button)
            setattr(self, '_nav_' + page_name, button)
        nav_layout.addStretch(1)
        shell.addWidget(self.nav)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.setContentsMargins(0, 0, 0, 0)
        self._page_index = {}
        for page_name, choices, checks in self.NAVIGATION:
            self._add_page(page_name, choices, checks)
        self._add_keymap_page()
        shell.addWidget(self.stack, 1)
        if filter_text:
            self.filter_edit.setText(filter_text)
        self._show_page(page if page in self._page_index else 'keymap')

    def _heading(self, text):
        label = QtWidgets.QLabel(_t(text))
        label.setProperty('role', 'heading')
        return label

    def _muted_note(self, text):
        label = QtWidgets.QLabel(_t(text))
        label.setWordWrap(True)
        label.setProperty('role', 'muted')
        return label

    def _add_page(self, page_name, choice_names, check_names):
        page = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(page)
        outer.setContentsMargins(15, 10, 15, 10)
        outer.setSpacing(9)
        outer.addWidget(self._heading(self.PAGE_LABELS[page_name]))
        form = QtWidgets.QFormLayout()
        form.setContentsMargins(2, 4, 2, 2)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(5)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        for key in choice_names:
            box = QtWidgets.QComboBox()
            for value, label in self.CHOICES[key]:
                box.addItem(_t(label), value)
            box.setCurrentIndex(max(0, box.findData(setting(key))))
            box.currentIndexChanged.connect(functools.partial(self._combo_changed, key, box))
            form.addRow(_t(self.LABELS[key]), box)
        for key in check_names:
            check = QtWidgets.QCheckBox(_t(self.LABELS[key]))
            check.setChecked(bool(setting(key)))
            check.toggled.connect(functools.partial(set_setting, key))
            form.addRow('', check)
            if key in self.NOTES:
                check.setToolTip(_t(self.NOTES[key]))
                note = QtWidgets.QLabel(_t(self.NOTES[key]))
                note.setWordWrap(True)
                note.setProperty('role', 'note')
                form.addRow('', note)
        outer.addLayout(form)
        if page_name == 'viewport':
            outer.addSpacing(7)
            outer.addWidget(self._muted_note(
                "Viewport 2.0 çizimi: Linux / macOS'ta önizleme çizgisi siyah kutu olarak görünüyorsa seç. "
                'Maya, güvenilir olmayan klasörden eklenti yüklerken her oturumda bir kez izin sorar; '
                'sormaması için Windows > Settings/Preferences > Preferences > Security bölümünde '
                'Orange klasörünü güvenilir konumlara ekle.'))
        if page_name == 'interface':
            outer.addSpacing(6)
            outer.addWidget(self._muted_note('Dil değişikliği Orange menüsüne ve açık Orange pencerelerine hemen yansır.'))
        outer.addStretch(1)
        self._page_index[page_name] = self.stack.addWidget(page)

    def _combo_changed(self, key, box, *_):
        if key == 'language':
            from .lifecycle import set_language
            set_language(box.currentData())
            return
        set_setting(key, box.currentData())

    @classmethod
    def _context_name(cls, binding):
        contexts = binding.get('ctx', ())
        for key, label in (('view', '3D Görünüm'), ('uv', 'UV Editor'), ('graph', 'Graph Editor'),
                           ('outliner', 'Outliner'), ('other', 'Diğer')):
            if key in contexts:
                return label
        return 'Diğer'

    def _add_keymap_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(13, 9, 13, 8)
        layout.setSpacing(6)

        layout.addWidget(self._heading(self.PAGE_LABELS['keymap']))
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(5)
        self.search_mode = QtWidgets.QComboBox()
        self.search_mode.addItem(_t('Ad'), 'name')
        self.search_mode.addItem(_t('Tuş kombinasyonu'), 'key')
        self.search_mode.setFixedWidth(123)
        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText(_t('Komut ya da kısayol ara...'))
        self.filter_edit.setClearButtonEnabled(True)
        toolbar.addWidget(self.search_mode)
        toolbar.addWidget(self.filter_edit, 1)
        layout.addLayout(toolbar)

        self.table = QtWidgets.QTreeWidget()
        self.table.setColumnCount(3)
        self.table.setHeaderLabels([_t('Komut'), _t('Kısayol'), _t('Varsayılan')])
        self.table.setAlternatingRowColors(True)
        self.table.setRootIsDecorated(True)
        self.table.setUniformRowHeights(True)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setColumnWidth(1, 116)
        self.table.setColumnWidth(2, 116)
        self.table.header().setStretchLastSection(False)
        self.table.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.header().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.setToolTip(_t('Kısayolu değiştirmek için satırdaki Kısayol alanına tıkla.'))
        self.table.itemClicked.connect(self._item_clicked)
        self.table.itemChanged.connect(self._item_changed)
        self.table.installEventFilter(self)
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.search_mode.currentIndexChanged.connect(self._apply_filter)
        layout.addWidget(self.table, 1)

        footer = QtWidgets.QHBoxLayout()
        footer.setSpacing(5)
        self.status = QtWidgets.QLabel(_t('Kısayolu değiştirmek için satırdaki alana tıkla. Esc: vazgeç, Backspace: kaldır.'))
        self.status.setProperty('role', 'muted')
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        for label, fn in ((_t('Değiştir'), self._change_selected),
                          (_t('Seçileni varsayılana döndür'), self._reset_selected),
                          (_t('Hepsini varsayılana döndür'), self._reset_all)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(fn)
            footer.addWidget(button)
        layout.addLayout(footer)
        from .keymap import BINDINGS
        self.ids = [combo for combo, binding in BINDINGS.items() if binding.get('title')]
        self._fill()
        self._page_index['keymap'] = self.stack.addWidget(page)

    # -- tablo
    def _view_state(self):
        """Kaydirma, secili komut ve acik gruplar: _fill tabloyu bastan kurunca geri yuklenir."""
        current = self.table.currentItem()
        expanded = {}
        for index in range(self.table.topLevelItemCount()):
            group = self.table.topLevelItem(index)
            expanded[group.data(0, Qt.ItemDataRole.UserRole + 1)] = group.isExpanded()
        return {
            'scroll': self.table.verticalScrollBar().value(),
            'current': current.data(0, Qt.ItemDataRole.UserRole) if current else None,
            'expanded': expanded,
        }

    def _restore_view_state(self, state):
        if not state:
            return
        for index in range(self.table.topLevelItemCount()):
            group = self.table.topLevelItem(index)
            key = group.data(0, Qt.ItemDataRole.UserRole + 1)
            if key in state['expanded']:
                group.setExpanded(state['expanded'][key])
            if state['current']:
                for row in range(group.childCount()):
                    item = group.child(row)
                    if item.data(0, Qt.ItemDataRole.UserRole) == state['current']:
                        self.table.setCurrentItem(item)
        self.table.verticalScrollBar().setValue(state['scroll'])

    def _fill(self):
        from .keymap import BINDINGS, _combo_for
        state = self._view_state() if self.table.topLevelItemCount() else None
        self._filling = True
        self.table.clear()
        groups = {}
        for label in self.GROUPS:
            item = QtWidgets.QTreeWidgetItem([_t(label), '', ''])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, label)
            item.setFirstColumnSpanned(False)
            item.setExpanded(label != 'Diğer')
            groups[label] = item
        for action in self.ids:
            binding = BINDINGS[action]
            group_name = self._context_name(binding)
            item = QtWidgets.QTreeWidgetItem([
                _t(binding['title']),
                _combo_label(_combo_for(action)) if _combo_for(action) else '—',
                _combo_label(action),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, action)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked if not _combo_for(action) else Qt.CheckState.Checked)
            item.setToolTip(0, action)
            item.setToolTip(1, _t('Kısayolu değiştirmek için tıkla'))
            if _combo_for(action) != action:
                item.setForeground(1, QtGui.QBrush(self.CAPTURE_COLOR))
            item.setForeground(2, QtGui.QBrush(QtGui.QColor(157, 157, 157)))
            groups[group_name].addChild(item)
        for label in self.GROUPS:
            group = groups[label]
            if group.childCount():
                self.table.addTopLevelItem(group)
        self._filling = False
        self._apply_filter(self.filter_edit.text())
        self._restore_view_state(state)

    def _apply_filter(self, *_):
        words = [word for word in self.filter_edit.text().lower().split() if word]
        mode = self.search_mode.currentData()
        for index in range(self.table.topLevelItemCount()):
            group = self.table.topLevelItem(index)
            visible = False
            for row in range(group.childCount()):
                item = group.child(row)
                current = item.text(1).lower()
                default = item.text(2).lower()
                name = item.text(0).lower()
                haystack = ' '.join((current, default)) if mode == 'key' else ' '.join((name, current, default))
                show = all(word in haystack for word in words)
                item.setHidden(not show)
                visible = visible or show
            group.setHidden(not visible)
            if words and visible:
                group.setExpanded(True)

    def _item_clicked(self, item, column):
        if item.data(0, Qt.ItemDataRole.UserRole) and column == 1:
            self._start_capture(item)

    def _item_changed(self, item, column):
        if self._filling or column != 0:
            return
        action = item.data(0, Qt.ItemDataRole.UserRole)
        if not action:
            return
        from .keymap import _rebuild_keymap, _save_overrides
        overrides = dict(_state.get('overrides') or {})
        if item.checkState(0) == Qt.CheckState.Checked:
            overrides.pop(action, None)
        else:
            overrides[action] = ''
        _save_overrides(overrides)
        _rebuild_keymap()
        self._fill()

    def _change_selected(self):
        item = self.table.currentItem()
        if item and item.data(0, Qt.ItemDataRole.UserRole):
            self._start_capture(item)

    # -- tus yakalama
    def _start_capture(self, item):
        action = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not action:
            return
        if self.capture_action is not None:
            self._fill()                  # onceki satirin "Tusa bas" metnini geri al
            item = self._item_for(action) or item
        self.capture_action = action
        _state['capturing'] = True
        self.table.setCurrentItem(item)
        self.table.setFocus()
        self.status.setText(_t('Yeni kısayola bas: %s') % _t(item.text(0)))
        item.setText(1, _t('Tuşa bas…'))
        item.setBackground(1, QtGui.QBrush(self.CAPTURE_COLOR))
        item.setForeground(1, QtGui.QBrush(QtGui.QColor(20, 20, 20)))

    def _item_for(self, action):
        for index in range(self.table.topLevelItemCount()):
            group = self.table.topLevelItem(index)
            for row in range(group.childCount()):
                if group.child(row).data(0, Qt.ItemDataRole.UserRole) == action:
                    return group.child(row)
        return None

    def _stop_capture(self, message=None):
        was_capturing = self.capture_action is not None
        self.capture_action = None
        _state['capturing'] = False
        if was_capturing:
            self._fill()
        if message:
            self.status.setText(message)

    def _cancel_capture(self):
        """Odak baska yere gidince (tiklama, pencere degisimi, gizlenme) yakalama acik kalmasin: aksi halde
        _state['capturing'] True kalir ve butun Orange kisayollari olur."""
        if self.capture_action is not None:
            self._stop_capture(_t('Vazgeçildi'))

    def eventFilter(self, obj, ev):
        from .keymap import BINDINGS, _combo_for, _rebuild_keymap, _save_overrides
        if self.capture_action is None:
            return False
        if ev.type() == QtCore.QEvent.Type.FocusOut:
            self._cancel_capture()
            return False
        if ev.type() != EV_KEY_PRESS:
            return False
        key = int(ev.key())
        if key in (int(Qt.Key.Key_Shift), int(Qt.Key.Key_Control), int(Qt.Key.Key_Alt), int(Qt.Key.Key_Meta)):
            return True
        action = self.capture_action
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
                overrides[other] = ''
                message += '  ·  ' + _t('%s artık kısayolsuz') % _t(BINDINGS[other].get('title') or other)
        if combo == action:
            overrides.pop(action, None)
        else:
            overrides[action] = combo
        _save_overrides(overrides)
        _rebuild_keymap()
        self._stop_capture(message)
        return True

    def event(self, ev):
        if ev.type() == QtCore.QEvent.Type.WindowDeactivate:
            self._cancel_capture()
        return super(SettingsDialog, self).event(ev)

    def hideEvent(self, ev):
        self._cancel_capture()
        super(SettingsDialog, self).hideEvent(ev)

    def _reset_selected(self):
        item = self.table.currentItem()
        action = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not action:
            return
        from .keymap import _rebuild_keymap, _save_overrides
        overrides = dict(_state.get('overrides') or {})
        overrides.pop(action, None)
        _save_overrides(overrides)
        _rebuild_keymap()
        self._fill()

    def _reset_all(self):
        from .keymap import _rebuild_keymap, _save_overrides
        _save_overrides({})
        _rebuild_keymap()
        self._fill()
        self.status.setText(_t('Tüm kısayollar varsayılana döndü'))

    def _show_page(self, page, *_):
        self.current_page = page
        self.stack.setCurrentIndex(self._page_index[page])
        for name in self.PAGE_LABELS:
            getattr(self, '_nav_' + name).setChecked(name == page)

    def reject(self):
        # Esc: QDialog.reject yalniz gizler ve closeEvent calismaz; kapatma temizligi (yakalama, menu) calissin
        self.close()

    def closeEvent(self, ev):
        from .lifecycle import _build_menu
        self.capture_action = None
        _state['capturing'] = False
        cmds.evalDeferred(_build_menu)
        super(SettingsDialog, self).closeEvent(ev)


def show_settings(page=None, filter_text=None):
    """page / filter_text: dil degisince pencere ayni sayfa ve arama metniyle yeniden acilir."""
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == 'BlenderKontrolSettings':
            widget.close()
            widget.deleteLater()
    dialog = SettingsDialog(page=page, filter_text=filter_text)
    dialog.show()
    return dialog
