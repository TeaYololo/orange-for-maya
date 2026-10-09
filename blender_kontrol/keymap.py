# -*- coding: utf-8 -*-
"""Tus tablosu ve kullanici kisayollari."""
from __future__ import absolute_import, division, print_function

import functools
import io
import json
import os

import maya.cmds as cmds
import maya.mel as mel

from .core import _search_cache, _state, _warn
from .util import _objs, undoable
from .editmode import in_edit, select_mode, toggle_edit
from .cursor import snap_pie
from .pivot import (orientation_pie, pivot_pie, set_orientation, set_pivot, set_snap_target, snap_target_menu,
    toggle_snap)
from .anim import clear_key, frame_jump, frame_step, key_jump, play_reverse, set_range_end, space_action
from .view import (align_camera_to_view, camera_view, cursor_reset_and_frame, cycle_workspace, frame_all,
    frame_selected, maximize_panel, orbit_step, pan_step, roll_step, set_active_camera, shading_pie, subdiv_level,
    toggle_isolate, toggle_ortho, toggle_overlays, toggle_quad_view, toggle_wireframe, toggle_xray, tool_pie,
    view_axis, view_axis_local, view_opposite, view_pie, walk_navigation, zoom_step)
from .modal import _with_chunk, grab, mirror, rotate, scale
from .loopcut import loop_cut
from .slide import edge_slide
from .selection import (box_select_tool, circle_select_toggle, ctrl_number, cycle_select_tool, deselect_all,
    grow_selection, invert_selection, select_all, select_linked_under_cursor, select_mirror, select_similar_menu,
    shrink_selection)
from . import interop, modifiers
from .mesh import (bevel, bevel_vertices, collapse, connect_verts, crease_edges, delete_by_mode, delete_menu,
    dissolve, edge_menu, extrude, extrude_menu, face_menu, falloff_pie, fill, fill_beauty, inset_or_key, knife,
    limited_dissolve, merge_menu, mesh_mirror_menu, normals_menu, quadrangulate, recalc_normals,
    grid_fill, recalc_normals_inside, rip, separate_by_material, separate_menu, shade_flat, shade_smooth, split_menu,
    split_selection, to_sphere, toggle_soft_connected, toggle_soft_select, triangulate, uv_menu, uv_unwrap,
    vertex_menu)
from .objects import (add_menu, alt_s, apply_menu, batch_rename, boolean, clear_parent_menu, collection_menu,
    ctrl_l, duplicate, hide_selected, hide_unselected, instance, join, new_layer_from_selection, parent_menu,
    rename_active, reset_location, reset_rotation, set_origin, set_origin_menu, transfer_mode, unhide_all)
from .modes import SCULPT_BRUSHES, mode_pie, sculpt_brush, sculpt_radius
from .uv import (uv_pin, uv_select_all, uv_select_linked, uv_select_mode, uv_snap_menu, uv_split, uv_stitch,
    uv_modal, uv_transform_tool)
from .graph import (key_delete, key_extrapolation_menu, key_frame, key_handle_menu, key_interpolation_menu,
    key_move, key_scale, key_select_all, preview_range_menu)
from .adjust import adjust_last
from .helptext import show_help
from .settings_ui import show_settings
from .search import quick_favorites, show_search


# F3'te tusa bagli olmayan ama aranabilir komutlar: (baslik, fonksiyon)
EXTRA_COMMANDS = [
    ('Yumuşak gölgele (Shade Smooth)', lambda: shade_smooth()),
    ('Düz gölgele (Shade Flat)', lambda: shade_flat()),
    ('Erit (Dissolve)', lambda: dissolve()),
    ('Collapse (kenarları çökert)', lambda: collapse()),
    ('Ayır - Split (taşımadan)', lambda: split_selection()),
    ('Materyale göre ayır (Separate by Material)', lambda: separate_by_material()),
    ('Doldur ve üçgenle (Fill, Alt+F)', lambda: fill_beauty()),
    ('Normalleri içe hesapla', lambda: recalc_normals_inside()),
    ('Layer\'a taşı (Move to Collection)', lambda: collection_menu()),
    ('Pivotu ortala (Origin to Geometry)', lambda: cmds.xform(_objs(), centerPivots=True)),
    ('Mesh aynala (Mirror modifier gibi)', lambda: mesh_mirror_menu()),
    ('Ters oynat (Shift+Ctrl+Space)', lambda: play_reverse()),
    ('Pivot: orta nokta', lambda: set_pivot('median')),
    ('Pivot: sınır kutusu merkezi', lambda: set_pivot('bbox')),
    ('Pivot: 3D imleç', lambda: set_pivot('cursor')),
    ('Pivot: aktif eleman', lambda: set_pivot('active')),
    ('Pivot: tek tek (individual origins)', lambda: set_pivot('individual')),
    ('Oryantasyon: global', lambda: set_orientation('global')),
    ('Oryantasyon: lokal', lambda: set_orientation('local')),
    ('Oryantasyon: normal', lambda: set_orientation('normal')),
    ('Oryantasyon: görünüm', lambda: set_orientation('view')),
    ('Snap hedefi: artım (grid)', lambda: set_snap_target('increment')),
    ('Snap hedefi: köşe', lambda: set_snap_target('vertex')),
    ('Snap hedefi: kenar', lambda: set_snap_target('edge')),
    ('Snap hedefi: yüz', lambda: set_snap_target('face')),
    ('Boolean: birleşim (Union)', lambda: boolean(1)),
    ('Boolean: fark (Difference)', lambda: boolean(2)),
    ('Boolean: kesişim (Intersect)', lambda: boolean(3)),
    ('Sınırlı erit (Limited Dissolve)', lambda: limited_dissolve()),
    ('Geometriyi origin\'e taşı (Geometry to Origin)', lambda: set_origin('geometry_to_origin')),
    ('Origin\'i geometriye taşı (Origin to Geometry)', lambda: set_origin('origin_to_geometry')),
    ('Origin\'i 3D imlece taşı (Origin to 3D Cursor)', lambda: set_origin('origin_to_cursor')),
    ('UV: Unwrap', lambda: uv_unwrap()),
    ('Grid Fill (deliği dörtgen ızgarayla doldur)', lambda: grid_fill()),
    ('Modifier paneli (Properties > Modifiers)', lambda: modifiers.show_panel()),
    ('Blender için FBX dışa aktar (seçim)', lambda: interop.export_for_blender()),
    ('Blender FBX içe aktar', lambda: interop.import_from_blender()),
    ('UV: Maya manipülatörü ile taşı', lambda: uv_transform_tool('move')),
    ('UV: Maya manipülatörü ile döndür', lambda: uv_transform_tool('rotate')),
    ('UV: Maya manipülatörü ile ölçekle', lambda: uv_transform_tool('scale')),
    ('Modifier ekle: Mirror X', lambda: modifiers.add_mirror(modifiers.active_mesh(), 'x')),
    ('Modifier ekle: Subdivision Surface', lambda: modifiers.set_subdivision(modifiers.active_mesh(), 2)),
    ('Modifier ekle: Array', lambda: modifiers.add_array(modifiers.active_mesh(), 3, 'x')),
    ("Modifier'ları uygula (Apply)", lambda: modifiers.apply_all_selected()),
]


# ---------------------------------------------------------------- tus tablosu
V = frozenset(['view'])
VO = frozenset(['view', 'outliner'])
ALL = frozenset(['view', 'outliner', 'other', 'uv', 'graph'])
VT = frozenset(['view', 'other', 'uv', 'graph'])
UV = frozenset(['uv'])
GR = frozenset(['graph'])


def _b(ctx, fn, panel=False, undo=True, raw=False, repeat=False, title=None):
    """title: F3 aramasinda gorunen ad (None = aranamaz)."""
    return {'ctx': ctx, 'fn': fn, 'panel': panel, 'undo': undo and not raw, 'repeat': repeat,
            'title': title}


BINDINGS = {
    # mod / secim
    'tab': _b(V, toggle_edit, title='Edit modu aç/kapa'),
    '1': _b(V, lambda: select_mode('vertex'), title='Köşe modu'),
    '2': _b(V, lambda: select_mode('edge'), title='Kenar modu'),
    '3': _b(V, lambda: select_mode('face'), title='Yüz modu'),
    'shift+1': _b(V, lambda: select_mode('vertex', extend=True), title='Köşe modunu ekle / çıkar (çoklu mod)'),
    'shift+2': _b(V, lambda: select_mode('edge', extend=True), title='Kenar modunu ekle / çıkar (çoklu mod)'),
    'shift+3': _b(V, lambda: select_mode('face', extend=True), title='Yüz modunu ekle / çıkar (çoklu mod)'),
    'shift+g': _b(VO, select_similar_menu, raw=True, title='Benzerini seç / grupla seç'),
    'ctrl+shift+m': _b(V, select_mirror, title='Ayna seçimi (Select Mirror)'),
    'b': _b(V, box_select_tool, undo=False, title='Kutu seçimi'),
    'a': _b(VO, select_all, title='Hepsini seç'),
    'alt+a': _b(VO, deselect_all, title='Seçimi kaldır'),
    'ctrl+i': _b(VO, invert_selection, title='Seçimi ters çevir'),
    'ctrl+l': _b(V, ctrl_l, raw=True, title='Bağlı olanları seç / bağla-aktar (obje)'),
    'w': _b(V, cycle_select_tool, undo=False, title='Seçim aracı döngüsü (kutu / kement / fırça)'),
    'c': _b(V, circle_select_toggle, undo=False, title='Fırça ile seç (Circle select)'),
    # donusum
    'g': _b(V, grab, raw=True, title='Taşı (Grab)'),
    'r': _b(V, rotate, raw=True, title='Döndür (Rotate)'),
    's': _b(V, scale, raw=True, title='Ölçekle (Scale)'),
    'alt+g': _b(V, reset_location, title='Konumu sıfırla'),
    'alt+r': _b(V, reset_rotation, title='Döndürmeyi sıfırla'),
    'alt+s': _b(V, alt_s, raw=True, title='Ölçeği sıfırla / kalınlaştır-incelt (edit)'),
    'alt+shift+s': _b(V, to_sphere, raw=True, title='Küreye çevir (To Sphere)'),
    'shift+e': _b(V, crease_edges, raw=True, title='Kenar crease'),
    'u': _b(V, uv_menu, raw=True, title='UV menüsü'),
    'shift+o': _b(V, falloff_pie, raw=True, title='Proportional falloff pie'),
    'alt+o': _b(V, toggle_soft_connected, title='Proportional: sadece bağlı'),
    'ctrl+a': _b(V, apply_menu, raw=True, title='Uygula (Apply / Freeze)'),
    'shift+s': _b(V, snap_pie, raw=True, title='Hizala (Snap) pie'),
    'o': _b(V, toggle_soft_select, title='Proportional editing (soft select)'),
    # obje
    'x': _b(VO, delete_menu, raw=True, title='Sil (Delete)'),
    'delete': _b(VO, delete_by_mode, title='Sil (menüsüz)'),
    'shift+d': _b(V, duplicate, raw=True, title='Kopyala (Duplicate)'),
    'alt+d': _b(V, instance, raw=True, title='Instance (Duplicate Linked)'),
    'shift+a': _b(V, add_menu, raw=True, title='Ekle (Add)'),
    'ctrl+j': _b(V, join, title='Birleştir (Join objects)'),
    'ctrl+p': _b(VO, parent_menu, raw=True, title='Ebeveyn yap (Parent)'),
    'alt+p': _b(VO, clear_parent_menu, raw=True, title='Ebeveyni kaldır'),
    'ctrl+g': _b(V, new_layer_from_selection, raw=True, title='Yeni layer (New Collection)'),
    'ctrl+alt+shift+c': _b(V, set_origin_menu, raw=True, title='Origin ayarla (Set Origin)'),
    'alt+q': _b(V, transfer_mode, title='Transfer mode (imleç altındaki objeyi düzenle)'),
    'h': _b(VO, hide_selected, title='Gizle'),
    'shift+h': _b(VO, hide_unselected, title='Diğerlerini gizle'),
    'alt+h': _b(VO, unhide_all, title='Hepsini göster'),
    'shift+r': _b(V, lambda: mel.eval('RepeatLast'), undo=False, title='Son işlemi tekrarla'),
    # modelleme
    'e': _b(V, _with_chunk(extrude), raw=True, title='Extrude'),
    'alt+e': _b(V, extrude_menu, raw=True, title='Extrude menüsü (normaller boyunca, tek tek...)'),
    'i': _b(V, _with_chunk(inset_or_key), raw=True, title='Inset / Keyframe ekle'),
    'ctrl+b': _b(V, _with_chunk(bevel), raw=True, title='Bevel'),
    'ctrl+shift+b': _b(V, _with_chunk(bevel_vertices), raw=True, title='Köşe bevel'),
    'period': _b(V, pivot_pie, raw=True, title='Pivot noktası pie'),
    'comma': _b(V, orientation_pie, raw=True, title='Dönüşüm oryantasyonu pie'),
    'shift+tab': _b(V, toggle_snap, undo=False, title='Snap aç/kapa'),
    'ctrl+shift+tab': _b(V, snap_target_menu, raw=True, title='Snap hedefi (artım/köşe/kenar/yüz)'),
    'ctrl+r': _b(V, loop_cut, raw=True, title='Loop cut'),
    'ctrl+shift+r': _b(V, lambda: mel.eval('OffsetEdgeLoopTool'), undo=False, title='Ofset kenar halkası'),
    'k': _b(V, knife, undo=False, title='Bıçak (Knife / Multi-Cut)'),
    'f': _b(V, fill, title='Yüz/kenar doldur (Fill)'),
    'alt+f': _b(V, fill_beauty, title='Doldur ve üçgenle (Fill)'),
    'j': _b(V, connect_verts, title='Köşeleri bağla (Connect)'),
    'l': _b(V, select_linked_under_cursor, title='Bağlı olanları seç (imleç altı)'),
    'shift+l': _b(V, lambda: select_linked_under_cursor(deselect=True), title='Bağlı olanları seçimden çıkar'),
    'v': _b(V, rip, raw=True, title='Rip'),
    'shift+v': _b(V, lambda: edge_slide('vertex'), raw=True, title='Köşe kaydır (Vertex Slide)'),
    'ctrl+m': _b(V, mirror, raw=True, title='Aynala (Mirror)'),
    'ctrl+e': _b(V, edge_menu, raw=True, title='Kenar menüsü (köprü, dikiş, crease, kaydır)'),
    'ctrl+v': _b(V, vertex_menu, raw=True, title='Köşe menüsü'),
    'ctrl+f': _b(V, face_menu, raw=True, title='Yüz menüsü (poke, solidify, mirror)'),
    'ctrl+t': _b(V, triangulate, title='Üçgene çevir (Triangulate)'),
    'alt+j': _b(V, quadrangulate, title='Dörtgene çevir (Tris to Quads)'),
    'm': _b(V, merge_menu, raw=True, title='Birleştir (Merge) / Layer\'a taşı'),
    'alt+m': _b(V, split_menu, raw=True, title='Ayır - Split menüsü'),
    'p': _b(V, separate_menu, raw=True, title='Ayır (Separate)'),
    'ctrl+x': _b(V, lambda: dissolve() if in_edit() else mel.eval('CutSelected'), title='Erit (Dissolve) / Kes'),
    'ctrl+delete': _b(V, dissolve, title='Erit (Dissolve)'),
    'shift+n': _b(V, recalc_normals, title='Normalleri dışa hesapla'),
    'ctrl+shift+n': _b(V, recalc_normals_inside, title='Normalleri içe hesapla'),
    'alt+n': _b(V, normals_menu, raw=True, title='Normal menüsü (çevir, ortala, kilidi aç)'),
    'ctrl+0': _b(V, lambda: subdiv_level(0), title='Yumuşak önizleme kapalı'),
    'ctrl+1': _b(V, lambda: ctrl_number(1), title='Yumuşak önizleme 1 / köşe moduna genişleterek'),
    'ctrl+2': _b(V, lambda: ctrl_number(2), title='Yumuşak önizleme 2 / kenar moduna genişleterek'),
    'ctrl+3': _b(V, lambda: ctrl_number(3), title='Yumuşak önizleme 3 / yüz moduna genişleterek'),
    'ctrl+4': _b(V, lambda: subdiv_level(4), title='Yumuşak önizleme 4'),
    'ctrl+5': _b(V, lambda: subdiv_level(5), title='Yumuşak önizleme 5'),
    # animasyon
    'alt+i': _b(V, clear_key, title='Keyframe sil'),
    'space': _b(VT, space_action, undo=False, title='Oynat / durdur'),
    'ctrl+shift+space': _b(VT, play_reverse, undo=False, title='Ters oynat / durdur'),
    'left': _b(VT, lambda: frame_step(-1), undo=False, repeat=True, title='Önceki kare'),
    'right': _b(VT, lambda: frame_step(1), undo=False, repeat=True, title='Sonraki kare'),
    'shift+left': _b(VT, lambda: frame_jump(False), undo=False, title='Başa git'),
    'shift+right': _b(VT, lambda: frame_jump(True), undo=False, title='Sona git'),
    'up': _b(VT, lambda: key_jump(True), undo=False, repeat=True, title='Sonraki keyframe'),
    'down': _b(VT, lambda: key_jump(False), undo=False, repeat=True, title='Önceki keyframe'),
    # gorunum
    'np1': _b(V, lambda p: view_axis(p, 'front'), panel=True, undo=False, title='Ön görünüm'),
    'ctrl+np1': _b(V, lambda p: view_axis(p, 'back'), panel=True, undo=False, title='Arka görünüm'),
    'np3': _b(V, lambda p: view_axis(p, 'rightSide'), panel=True, undo=False, title='Sağ görünüm'),
    'ctrl+np3': _b(V, lambda p: view_axis(p, 'leftSide'), panel=True, undo=False, title='Sol görünüm'),
    'np7': _b(V, lambda p: view_axis(p, 'top'), panel=True, undo=False, title='Üst görünüm'),
    'ctrl+np7': _b(V, lambda p: view_axis(p, 'bottom'), panel=True, undo=False, title='Alt görünüm'),
    'shift+np1': _b(V, lambda p: view_axis_local(p, 'front'), panel=True, undo=False, title='Ön görünüm (objenin lokal ekseni)'),
    'ctrl+shift+np1': _b(V, lambda p: view_axis_local(p, 'back'), panel=True, undo=False, title='Arka görünüm (lokal)'),
    'shift+np3': _b(V, lambda p: view_axis_local(p, 'rightSide'), panel=True, undo=False, title='Sağ görünüm (lokal)'),
    'ctrl+shift+np3': _b(V, lambda p: view_axis_local(p, 'leftSide'), panel=True, undo=False, title='Sol görünüm (lokal)'),
    'shift+np7': _b(V, lambda p: view_axis_local(p, 'top'), panel=True, undo=False, title='Üst görünüm (lokal)'),
    'ctrl+shift+np7': _b(V, lambda p: view_axis_local(p, 'bottom'), panel=True, undo=False, title='Alt görünüm (lokal)'),
    'np9': _b(V, view_opposite, panel=True, undo=False, title='Görünümü ters çevir (180°)'),
    'np5': _b(V, toggle_ortho, panel=True, undo=False, title='Perspektif / Ortografik'),
    'np0': _b(V, camera_view, panel=True, undo=False, title='Kameradan bak'),
    'ctrl+np0': _b(V, set_active_camera, panel=True, undo=False, title='Seçili kamerayı aktif yap'),
    'ctrl+alt+np0': _b(V, align_camera_to_view, panel=True, title='Kamerayı görünüme hizala'),
    'np.': _b(V, frame_selected, panel=True, undo=False, title='Seçime odaklan'),
    'home': _b(V, frame_all, panel=True, undo=False, title='Hepsini göster (Frame All)'),
    'shift+c': _b(V, cursor_reset_and_frame, panel=True, undo=False, title='İmleci sıfırla ve hepsini göster'),
    'np/': _b(V, toggle_isolate, panel=True, undo=False, title='Local view (isolate)'),
    'np2': _b(V, lambda p: orbit_step(p, 0, -15), panel=True, undo=False, repeat=True, title='Aşağı döndür'),
    'np8': _b(V, lambda p: orbit_step(p, 0, 15), panel=True, undo=False, repeat=True, title='Yukarı döndür'),
    'np4': _b(V, lambda p: orbit_step(p, 15, 0), panel=True, undo=False, repeat=True, title='Sola döndür'),
    'np6': _b(V, lambda p: orbit_step(p, -15, 0), panel=True, undo=False, repeat=True, title='Sağa döndür'),
    'ctrl+np2': _b(V, lambda p: pan_step(p, 0, -1), panel=True, undo=False, repeat=True, title='Aşağı kaydır'),
    'ctrl+np8': _b(V, lambda p: pan_step(p, 0, 1), panel=True, undo=False, repeat=True, title='Yukarı kaydır'),
    'ctrl+np4': _b(V, lambda p: pan_step(p, -1, 0), panel=True, undo=False, repeat=True, title='Sola kaydır'),
    'ctrl+np6': _b(V, lambda p: pan_step(p, 1, 0), panel=True, undo=False, repeat=True, title='Sağa kaydır'),
    'shift+np4': _b(V, lambda p: roll_step(p, 15), panel=True, undo=False, repeat=True, title='Görünümü sola yatır'),
    'shift+np6': _b(V, lambda p: roll_step(p, -15), panel=True, undo=False, repeat=True, title='Görünümü sağa yatır'),
    'np+': _b(V, lambda p: zoom_step(p, 1), panel=True, undo=False, repeat=True, title='Yakınlaş'),
    'np-': _b(V, lambda p: zoom_step(p, -1), panel=True, undo=False, repeat=True, title='Uzaklaş'),
    'ctrl+np+': _b(V, grow_selection, repeat=True, title='Seçimi büyüt'),
    'ctrl+np-': _b(V, shrink_selection, repeat=True, title='Seçimi küçült'),
    'grave': _b(V, view_pie, panel=True, raw=True, title='Görünüm pie'),
    'z': _b(V, shading_pie, panel=True, raw=True, title='Görüntü (shading) pie'),
    'ctrl+tab': _b(V, mode_pie, raw=True, title='Mod pie (seçim, sculpt, boyama)'),
    'q': _b(ALL, quick_favorites, raw=True, title='Favoriler (Quick Favorites)'),
    'ctrl+pgup': _b(ALL, lambda: cycle_workspace(-1), undo=False, title='Önceki çalışma alanı'),
    'ctrl+pgdown': _b(ALL, lambda: cycle_workspace(1), undo=False, title='Sonraki çalışma alanı'),
    'ctrl+f2': _b(VO, batch_rename, raw=True, title='Toplu yeniden adlandır'),
    'shift+grave': _b(V, walk_navigation, undo=False, title='Walk navigasyonu'),
    'ctrl+home': _b(VT, lambda: set_range_end(False), undo=False, title='Aralık başı = geçerli kare'),
    'ctrl+end': _b(VT, lambda: set_range_end(True), undo=False, title='Aralık sonu = geçerli kare'),
    'shift+z': _b(V, toggle_wireframe, panel=True, undo=False, title='Wireframe aç/kapa'),
    'alt+z': _b(V, toggle_xray, panel=True, undo=False, title='X-Ray aç/kapa'),
    'ctrl+space': _b(V, maximize_panel, panel=True, undo=False, title='Paneli büyüt'),
    'shift+space': _b(V, tool_pie, raw=True, title='Araç pie'),
    'ctrl+alt+q': _b(V, toggle_quad_view, panel=True, undo=False, title='Dörtlü görünüm (Quad View)'),
    'alt+shift+z': _b(V, toggle_overlays, panel=True, undo=False, title='Overlay aç/kapa'),
    'n': _b(V, lambda: mel.eval('ToggleChannelsLayers'), undo=False, title='Channel Box aç/kapa'),
    't': _b(V, lambda: mel.eval('ToggleToolbox'), undo=False, title='Araç çubuğu aç/kapa'),
    # genel
    'ctrl+shift+z': _b(ALL, lambda: cmds.redo(), undo=False, repeat=True, title='Yinele (Redo)'),
    'f11': _b(ALL, lambda: mel.eval('RenderViewWindow'), undo=False, title='Render penceresi'),
    'f12': _b(ALL, lambda: mel.eval('RenderIntoNewWindow'), undo=False, title='Render'),
    'ctrl+f12': _b(ALL, lambda: mel.eval('BatchRender'), undo=False, title='Animasyonu render et (batch)'),
    'f1': _b(ALL, lambda: show_help(), undo=False, title='Kısayol listesi'),
    'f2': _b(VO, rename_active, raw=True, title='Yeniden adlandır'),
    'f3': _b(ALL, lambda: show_search(), raw=True, title='Komut ara'),
    'f9': _b(V, adjust_last, raw=True, title='Son işlemi ayarla'),
    'ctrl+comma': _b(ALL, lambda: show_settings(), raw=True, title='Ayarlar ve kısayollar'),
}
for _combo_id, _binding in BINDINGS.items():
    _binding['id'] = _combo_id     # varsayilan kombinasyon = komutun kalici kimligi


# ---------------------------------------------------------------- kullanici kisayollari
def _keymap_path():
    """Kullanici kisayol dosyasi. ORANGE_KEYMAP ortam degiskeni (testler) baska bir dosya gosterebilir."""
    override = os.environ.get('ORANGE_KEYMAP')
    if override:
        return override
    try:
        base = cmds.internalVar(userPrefDir=True)
    except Exception:
        base = os.path.expanduser('~')
    return os.path.join(base, 'blender_kontrol_keymap.json')


def _load_overrides():
    """{varsayilan_kombinasyon: yeni_kombinasyon ('' = kapali)}"""
    try:
        with io.open(_keymap_path(), 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return {k: v for k, v in data.items() if k in BINDINGS and isinstance(v, str)}
    except Exception:
        return {}


def _save_overrides(overrides):
    with io.open(_keymap_path(), 'w', encoding='utf-8') as fh:
        json.dump(overrides, fh, indent=1, sort_keys=True)


def _rebuild_keymap():
    """Varsayilan tablo + kullanici degisiklikleri -> etkin tablo. Cakismada kullanicinin atamasi kazanir."""
    overrides = _load_overrides()
    active = {}
    for combo, binding in BINDINGS.items():
        if combo not in overrides:
            active[combo] = binding
    for default, new in overrides.items():
        if new:
            active[new] = BINDINGS[default]
    _state['active_bindings'] = active
    _state['overrides'] = overrides
    del _search_cache[:]
    return active


def _active_bindings():
    return _state.get('active_bindings') or _rebuild_keymap()


def _combo_for(action_id):
    """Komutun su anki kisayolu ('' = kapali)."""
    overrides = _state.get('overrides')
    if overrides is None:
        _rebuild_keymap()
        overrides = _state['overrides']
    if action_id in overrides:
        return overrides[action_id]
    active = _active_bindings()
    return action_id if active.get(action_id) is BINDINGS.get(action_id) else ''


# ---------------------------------------------------------------- baglama ozel tus tablolari (sculpt, UV, Graph)
SCULPT_KEYMAP = dict((combo, _b(V, functools.partial(sculpt_brush, combo), undo=False))
                     for combo, brush in SCULPT_BRUSHES.items() if brush)
SCULPT_KEYMAP.update({
    'f': _b(V, lambda: sculpt_radius(False), raw=True),
    'shift+f': _b(V, lambda: sculpt_radius(True), raw=True),
    'ctrl+i': _b(V, lambda: mel.eval('SculptMeshInvertFreeze'), undo=False),
    'alt+m': _b(V, lambda: mel.eval('SculptMeshUnfreezeAll'), undo=False),
    'tab': _b(V, toggle_edit),
})

CONTEXT_KEYMAPS = {
    'uv': {
        'g': _b(UV, lambda p: uv_modal(p, 'move'), panel=True, raw=True),
        'r': _b(UV, lambda p: uv_modal(p, 'rotate'), panel=True, raw=True),
        's': _b(UV, lambda p: uv_modal(p, 'scale'), panel=True, raw=True),
        'a': _b(UV, uv_select_all),
        'alt+a': _b(UV, deselect_all),
        'ctrl+i': _b(UV, invert_selection),
        '1': _b(UV, lambda: uv_select_mode('vertex'), undo=False),
        '2': _b(UV, lambda: uv_select_mode('edge'), undo=False),
        '3': _b(UV, lambda: uv_select_mode('face'), undo=False),
        '4': _b(UV, lambda: uv_select_mode('island'), undo=False),
        'l': _b(UV, uv_select_linked),
        'ctrl+l': _b(UV, uv_select_linked),
        'u': _b(UV, uv_menu, raw=True),
        'p': _b(UV, lambda: uv_pin(1)),
        'alt+p': _b(UV, lambda: uv_pin(0)),
        'v': _b(UV, uv_split),
        'y': _b(UV, uv_split),
        'alt+v': _b(UV, uv_stitch),
        'shift+s': _b(UV, uv_snap_menu, raw=True),
        'shift+w': _b(UV, uv_snap_menu, raw=True),
    },
    'graph': {
        'g': _b(GR, key_move, panel=True, raw=True),
        's': _b(GR, key_scale, raw=True),
        't': _b(GR, key_interpolation_menu, raw=True),
        'v': _b(GR, key_handle_menu, raw=True),
        'shift+e': _b(GR, key_extrapolation_menu, raw=True),
        'x': _b(GR, key_delete),
        'delete': _b(GR, key_delete),
        'a': _b(GR, lambda p: key_select_all(p, True), panel=True),
        'alt+a': _b(GR, lambda p: key_select_all(p, False), panel=True),
        'home': _b(GR, lambda p: key_frame(p, False), panel=True, undo=False),
        'np.': _b(GR, lambda p: key_frame(p, True), panel=True, undo=False),
        'p': _b(GR, preview_range_menu, raw=True),
    },
}


def _run_binding(binding, panel):
    fn = binding['fn']
    call = (lambda: fn(panel)) if binding['panel'] else fn
    if binding['undo']:
        undoable(call)()
        return
    try:
        call()
    except Exception as exc:
        _warn(str(exc))
