# -*- coding: utf-8 -*-
"""F1 kisayol listesi."""
from __future__ import absolute_import, division, print_function

from .compat import QtWidgets, _main_window
from . import i18n
from .i18n import _lang, _t


HELP = u"""
<h2>Orange · Maya, Blender gibi</h2>
<p>Maya'da artık Blender gibi çalışabilirsin. Üstteki <b>Orange</b> menüsünden açıp kapatabilirsin.
Tuşlar imleç <b>3D görünümün üzerindeyken</b> çalışır.</p>
<h3>Fare</h3>
<table>
<tr><td><b>Orta tuş sürükle</b></td><td>Etrafında dön (orbit)</td></tr>
<tr><td><b>Shift + orta tuş</b></td><td>Kaydır (pan)</td></tr>
<tr><td><b>Ctrl + orta tuş</b> / tekerlek</td><td>Yakınlaş / uzaklaş</td></tr>
<tr><td><b>Alt + orta tık</b> / Alt + orta sürükle</td><td>Fare altındaki noktayı merkeze al / sürükleme yönüne göre eksen görünümü</td></tr>
<tr><td><b>Alt + tekerlek</b></td><td>Kare kaydır (animasyon)</td></tr>
<tr><td><b>Sol tık</b></td><td>Seç (Shift: ekle/çıkar, boşluğa sürükle: kutu seçimi)</td></tr>
<tr><td><b>Alt + sol tık</b> (edit modu)</td><td>Loop seç (sınır kenarında tüm sınır; Shift ile ekle, zaten seçiliyse çıkar)</td></tr>
<tr><td><b>Ctrl + Alt + sol tık</b></td><td>Ring seç</td></tr>
<tr><td><b>Çift tık</b> / Ctrl + çift tık</td><td>Loop / ring (Emulate 3 Button Mouse açıkken Alt+tık yerine)</td></tr>
<tr><td><b>Ctrl + sol tık</b> / Shift + Ctrl + sol tık</td><td>En kısa yol / bölge doldur (son seçilenle tıklanan arası dikdörtgen)</td></tr>
<tr><td><b>Ctrl + sağ sürükle</b> / Shift + Ctrl + sağ sürükle</td><td>Kement ile seçime ekle / çıkar</td></tr>
<tr><td><b>Sağ tık</b></td><td>Maya bağlam menüsü</td></tr>
<tr><td><b>Shift + sağ tık</b></td><td>3D imleci koy (yüzeye ya da imleç düzlemine)</td></tr>
</table>
<h3>Görünüm</h3>
<table>
<tr><td><b>Numpad 1 / 3 / 7</b></td><td>Ön / sağ / üst (Ctrl ile ters taraf, Shift ile aktif objenin lokal eksenine göre)</td></tr>
<tr><td><b>Numpad 9</b></td><td>Görünümü 180° çevir</td></tr>
<tr><td><b>Numpad 5</b></td><td>Perspektif / ortografik</td></tr>
<tr><td><b>Numpad 0</b></td><td>Kameradan bak (Ctrl: seçili kamerayı aktif yap, Ctrl+Alt: kamerayı görünüme hizala)</td></tr>
<tr><td><b>Numpad . </b></td><td>Seçime odaklan</td></tr>
<tr><td><b>Home</b> / Shift+C</td><td>Hepsini göster</td></tr>
<tr><td><b>Numpad 2 4 6 8</b></td><td>Adım adım döndür (Ctrl: kaydır, Shift+4/6: yatır)</td></tr>
<tr><td><b>Numpad + / -</b></td><td>Yakınlaş / uzaklaş</td></tr>
<tr><td><b>Numpad /</b></td><td>Local view (sadece seçili)</td></tr>
<tr><td><b>1'in solundaki tuş (")</b></td><td>Görünüm pie menüsü (numpad yoksa)</td></tr>
<tr><td><b>Z</b> / Shift+Z / Alt+Z</td><td>Görüntü pie (wireframe / solid / material / rendered) / wireframe / X-ray</td></tr>
<tr><td colspan="2" style="color:gray">Pie menü: tuşa bas-bırak sonra tıkla, ya da basılı tutup yöne çek ve bırak.</td></tr>
<tr><td><b>Ctrl + Space</b></td><td>Paneli büyüt</td></tr>
<tr><td><b>N</b> / <b>T</b></td><td>Channel Box / araç çubuğu</td></tr>
<tr><td><b>Shift + Space</b></td><td>Araç pie (kutu, kement, fırça, taşı, döndür, ölçekle, bıçak, Quad Draw)</td></tr>
<tr><td><b>Ctrl + Alt + Q</b> / Shift + Alt + Z</td><td>Dörtlü görünüm / overlay'leri gizle-göster (grid, HUD, ikonlar)</td></tr>
</table>
<h3>Obje modu</h3>
<table>
<tr><td><b>Tab</b></td><td>Edit moduna gir / çık</td></tr>
<tr><td><b>G / R / S</b></td><td>Taşı / döndür / ölçekle. İşlem sırasında:<br>
X/Y/Z eksen (2. kez global/lokal, 3. kez kapalı) · Shift+X/Y/Z düzlem · C kısıtı kaldır · orta tuş otomatik eksen (Shift: düzlem) ·
Alt + orta tuş ile gezin · Shift hassas · Ctrl snap (Shift+Ctrl ince) · Shift+Tab snap aç/kapa · G/R/S arası geçiş · G G kaydır (edit modu) · R R serbest döndür ·
tekerlek/PageUp proportional alanı · sayı ya da işlem yaz (ör. 2*3), - işaret çevirir, Tab sonraki eksen (G 1 Tab 2 Enter), = ifade modu (2m, 90d, pi/2)</td></tr>
<tr><td><b>.</b> / <b>,</b></td><td>Pivot pie (orta nokta / sınır kutusu / 3D imleç / aktif / tek tek) / oryantasyon pie (global / lokal / normal / görünüm / imleç / ebeveyn)</td></tr>
<tr><td><b>Shift + Tab</b> / Shift + Ctrl + Tab</td><td>Snap aç/kapa / snap hedefi (artım, köşe, kenar, yüz). İşlem sırasında Ctrl geçici olarak tersine çevirir</td></tr>
<tr><td><b>Alt + G / R / S</b></td><td>Konum / döndürme / ölçeği sıfırla</td></tr>
<tr><td><b>Ctrl + A</b></td><td>Uygula (freeze), modifier'ları uygula, geçmişi temizle, instance'ları gerçek yap</td></tr>
<tr><td><b>Shift + A</b></td><td>Ekle (küp, küre, kamera, ışık...)</td></tr>
<tr><td><b>Shift + D</b> / Alt + D</td><td>Kopyala / instance</td></tr>
<tr><td><b>X</b> / Delete</td><td>Sil</td></tr>
<tr><td><b>A</b> / Alt + A / Ctrl + I</td><td>Hepsini seç / seçimi kaldır / ters çevir</td></tr>
<tr><td><b>H</b> / Shift + H / Alt + H</td><td>Gizle / diğerlerini gizle / hepsini göster</td></tr>
<tr><td><b>Ctrl + J</b></td><td>Birleştir (join)</td></tr>
<tr><td><b>Ctrl + P</b> / Alt + P</td><td>Ebeveyn yap menüsü (dönüşümü koru / ters dönüşümsüz) / ebeveyni kaldır menüsü</td></tr>
<tr><td><b>Ctrl + L</b></td><td>Bağla / aktar: materyal, UV (aynı topoloji), layer (aktif = en son seçilen)</td></tr>
<tr><td><b>Ctrl + G</b> / M</td><td>Seçimden yeni layer / layer'a taşı (Blender: collection)</td></tr>
<tr><td><b>Ctrl + Alt + Shift + C</b></td><td>Origin ayarla: geometriyi origin'e, origin'i geometriye / 3D imlece / kütle merkezine</td></tr>
<tr><td><b>Shift + G</b></td><td>Grupla seç (çocuklar, ebeveyn, kardeşler, tür, layer); edit modunda benzerini seç</td></tr>
<tr><td><b>Shift + S</b></td><td>Hizala pie: imleç/seçim → seçim/imleç/grid/orijin/aktif, pivot → imleç</td></tr>
<tr><td><b>Shift + A</b> (3D imleç)</td><td>Yeni objeler 3D imlecin olduğu yere eklenir (Shift+C: imleci sıfırla)</td></tr>
<tr><td><b>Ctrl + 0..5</b></td><td>Yumuşak önizleme (subdivision) seviyesi</td></tr>
<tr><td><b>M</b></td><td>Layer'a taşı (Blender: Move to Collection)</td></tr>
<tr><td><b>O</b> / Shift + O / Alt + O</td><td>Proportional editing / falloff pie / sadece bağlı parçalar</td></tr>
<tr><td><b>B</b> / <b>W</b> / <b>C</b></td><td>Kutu seçimi / seçim aracı döngüsü (kutu, kement, fırça) / fırça ile seçim (C, sağ tık ya da Esc ile çık)</td></tr>
<tr><td><b>Shift + R</b></td><td>Son işlemi tekrarla</td></tr>
</table>
<h3>Edit modu (Tab)</h3>
<table>
<tr><td><b>1 / 2 / 3</b></td><td>Köşe / kenar / yüz (Shift: çoklu mod, Maya'da üçü birlikte; Ctrl: seçimi genişleterek geç)</td></tr>
<tr><td><b>Shift + G</b> / Shift + Ctrl + M</td><td>Benzerini seç (normal, alan, kenar sayısı, materyal, uzunluk, yön...) / ayna seçimi (X)</td></tr>
<tr><td><b>Alt + S</b> / Shift + Alt + S / Shift + E</td><td>Kalınlaştır-incelt (normal boyunca) / küreye çevir / kenar crease. Sayı yaz, Ctrl adımlı</td></tr>
<tr><td><b>U</b></td><td>UV menüsü (unwrap, otomatik, küp / silindir / küre / görünüm projeksiyonu, dikiş, sıfırla)</td></tr>
<tr><td><b>Alt + Q</b></td><td>İmleç altındaki objeyi aynı modda düzenle (transfer mode)</td></tr>
<tr><td><b>Shift + A</b> (edit modu)</td><td>Primitifi düzenlenen mesh'e ekle</td></tr>
<tr><td><b>E</b> / Alt + E</td><td>Kenar ya da yüz extrude (yüz: normal boyunca; X/Y/Z eksene kilitle, G serbest taşı) / extrude menüsü (normaller boyunca, tek tek, kenar). Köşe extrude yok: Maya mesh'inde yüzü olmayan kenar olamaz</td></tr>
<tr><td><b>I</b></td><td>Inset (I tekrar: tek tek)</td></tr>
<tr><td><b>Ctrl + B</b> / Shift + Ctrl + B</td><td>Bevel / köşe bevel (tekerlek: segment, P profil, M miter, C chamfer)</td></tr>
<tr><td><b>Ctrl + R</b> / Ctrl + Shift + R</td><td>Loop cut: kenarın üzerine gel, tekerlek kesim sayısı, tıkla, kaydır (birden çok kesim birlikte kayar), tıkla / ofset kenar halkası</td></tr>
<tr><td><b>V</b></td><td>Rip (ayır ve taşı)</td></tr>
<tr><td><b>G G</b> / Shift + V</td><td>Kenar kaydır (kenar/yüz modu: komşu kenarlar boyunca, iki yöne; E eşit mesafe, F çevir) / köşe kaydır (fare yönündeki kenar boyunca). Sayı yaz, Ctrl adımlı, Shift hassas</td></tr>
<tr><td><b>Ctrl + M</b></td><td>Aynala (X/Y/Z seç, Enter)</td></tr>
<tr><td><b>Ctrl + E / V / F</b></td><td>Kenar / köşe / yüz menüsü (köprü, dikiş, crease, poke, Grid Fill, mirror...)</td></tr>
<tr><td><b>Ctrl + T</b> / Alt + J</td><td>Üçgene / dörtgene çevir</td></tr>
<tr><td><b>L</b> / Shift + L</td><td>İmlecin altındaki parçayı seç / çıkar</td></tr>
<tr><td><b>H</b> / Shift + H / Alt + H</td><td>Seçili yüzleri gizle / diğerlerini gizle / göster</td></tr>
<tr><td><b>K</b></td><td>Bıçak (Multi-Cut)</td></tr>
<tr><td><b>F</b> / Alt + F / <b>J</b></td><td>Yüz / kenar doldur, üçgenleyerek doldur, köşeleri bağla</td></tr>
<tr><td><b>M</b></td><td>Birleştir (merkezde / imleçte / collapse / ilk-son seçilende / mesafeye göre)</td></tr>
<tr><td><b>Alt + M</b></td><td>Ayır - Split (taşımadan; kenarlardan / köşelerden)</td></tr>
<tr><td><b>P</b></td><td>Ayır (seçim / materyale göre / gevşek parçalar)</td></tr>
<tr><td><b>X</b> / Ctrl + X</td><td>Sil menüsü (köşe / kenar / yüz / erit / sınırlı erit / kenar halkaları / collapse) / erit</td></tr>
<tr><td><b>Ctrl + L</b> / Ctrl + Numpad +/-</td><td>Bağlı olanları seç / seçimi büyüt-küçült</td></tr>
<tr><td><b>Shift + N</b> / Shift + Ctrl + N / Alt + N</td><td>Normalleri dışa / içe hesapla / normal menüsü (çevir, ortala, kilidi aç, shade smooth/flat)</td></tr>
</table>
<h3>Modlar, UV ve Graph Editor</h3>
<table>
<tr><td><b>Ctrl + Tab</b></td><td>Mod pie: köşe / kenar / yüz / obje, Sculpt, Vertex Paint, Weight Paint, Texture Paint</td></tr>
<tr><td><b>Sculpt modu</b></td><td>F yarıçap, Shift+F güç (fareyle), V draw, S smooth, P pinch, I inflate, G grab, C clay (wax), Shift+C crease (knife), K snake hook (smear), Shift+T scrape, M mask (freeze), Ctrl+I maskeyi ters çevir, Alt+M maskeyi temizle, Tab edit modu. Ctrl ters, Shift yumuşat (Maya)</td></tr>
<tr><td><b>UV editörü</b></td><td>1/2/3/4 UV / kenar / yüz / ada, A / Alt+A / Ctrl+I, L ya da Ctrl+L ada seç, G / R / S fareyle taşı / döndür / ölçekle (X / Y eksen, sayı yaz), U unwrap menüsü, P / Alt+P pin, V ya da Y ayır, Alt+V dik (stitch), Shift+S ya da Shift+W hizala menüsü</td></tr>
<tr><td><b>Graph Editor / Dope Sheet</b></td><td>G anahtarları fareyle taşı (X sadece zaman, Y sadece değer, kareye snap, Ctrl serbest), S zaman ölçekle, T interpolasyon, V tutamak tipi, Shift+E ekstrapolasyon, X / Delete sil, A / Alt+A, Home / Numpad . odakla, P önizleme aralığı</td></tr>
<tr><td><b>Ctrl + Home</b> / Ctrl + End</td><td>Oynatma aralığının başı / sonu = geçerli kare</td></tr>
<tr><td><b>F9</b></td><td>Son işlemi ayarla: son history düğümünün sayısal ayarları yüzen panelde, değiştirince anında uygulanır</td></tr>
<tr><td><b>Modifier'lar</b></td><td>Orange menüsü → Modifier paneli: Subdivision (smooth preview), Mirror ve Array (canlı instance), Bevel, Solidify, Triangulate, Weld; aç / kapa, ayarla, uygula. Ctrl+A ile hepsini uygula</td></tr>
<tr><td><b>Blender ile FBX</b></td><td>Orange menüsü / F3: Blender için FBX dışa aktar (metre, smoothing) ve Blender FBX içe aktar</td></tr>
<tr><td><b>Hotkey Editor</b></td><td>Her Orange komutu Maya Hotkey Editor'da "Orange" kategorisinde: istersen Maya'nın kendi tuşlarına, rafa ya da marking menu'ye bağla</td></tr>
<tr><td><b>Q</b></td><td>Favoriler; eklemek için F3'te bir komut seçip Ctrl+Enter</td></tr>
<tr><td><b>Ctrl + PageUp / PageDown</b></td><td>Önceki / sonraki Maya çalışma alanı</td></tr>
<tr><td><b>Ctrl + F2</b></td><td>Toplu yeniden adlandır (bul / değiştir, önek, sonek, numara)</td></tr>
<tr><td><b>Shift + `</b></td><td>Walk navigasyonu (Maya Walk Tool)</td></tr>
<tr><td colspan="2" style="color:gray">3D imleç kırmızı-beyaz halkalıdır ve seçilemez. Ayarlardan Shift+sağ tıkta görünüme ya da yüzey normaline hizalanabilir; "İmleç" oryantasyonu bu yönü kullanır.</td></tr>
</table>
<h3>Animasyon ve genel</h3>
<table>
<tr><td><b>I</b> (obje modu) / Alt + I</td><td>Keyframe ekle / sil</td></tr>
<tr><td><b>Space</b> / Shift + Ctrl + Space</td><td>Oynat / ters oynat / durdur</td></tr>
<tr><td><b>← / →</b></td><td>Bir kare geri / ileri (Shift: başa / sona; Alt + tekerlek de kaydırır)</td></tr>
<tr><td><b>↑ / ↓</b></td><td>Sonraki / önceki keyframe</td></tr>
<tr><td><b>Ctrl+Z</b> / Ctrl+Shift+Z</td><td>Geri al / yinele</td></tr>
<tr><td><b>Ctrl+S</b></td><td>Kaydet</td></tr>
<tr><td><b>F12</b> / F11 / Ctrl + F12</td><td>Render / render penceresi / animasyonu render et</td></tr>
<tr><td><b>F1</b></td><td>Bu liste</td></tr>
<tr><td><b>F2</b></td><td>Yeniden adlandır</td></tr>
<tr><td><b>F3</b></td><td>Komut ara (Blender ve Maya menü komutları)</td></tr>
<tr><td><b>Ctrl + ,</b></td><td>Ayarlar ve kısayol düzenleyici (Orange menüsünden de açılır)</td></tr>
</table>
<p style="color:gray">Blender'dan farkı: Maya'da her işlem "geçmiş" (history) bırakır; işin bitince
Ctrl+A &gt; Geçmişi temizle. Maya'nın kendi menüleri ve Channel Box'ı (sağda) her zaman kullanılabilir.</p>
"""


def show_help():
    name = 'BlenderKontrolHelp'
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.objectName() == name:
            w.close()
            w.deleteLater()
    dlg = QtWidgets.QDialog(_main_window())
    dlg.setObjectName(name)
    dlg.setWindowTitle(_t('Orange kısayolları'))
    dlg.resize(620, 760)
    layout = QtWidgets.QVBoxLayout(dlg)
    text = QtWidgets.QTextBrowser()
    text.setHtml((i18n.HELP_EN if _lang() == 'en' and i18n.HELP_EN else HELP).replace('<table>', '<table cellpadding="3">'))
    layout.addWidget(text)
    dlg.show()
