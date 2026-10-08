# Blender for Maya

Autodesk Maya'yı **Blender gibi** kullan: aynı kısayollar, aynı fare navigasyonu, G/R/S ile fareyle taşı-döndür-ölçekle, pie menüler, 3D imleç, loop cut ve daha fazlası.

Blender'dan gelip Maya'ya geçenler için yazıldı. Tek bir Python dosyası; Maya'nın kendi kısayollarını **değiştirmez**. Üstteki **Blender** menüsünden tek tıkla kapatınca her şey Maya varsayılanına döner.

> 🇬🇧 English summary is [at the bottom](#english).

---

## Özellikler

- **Blender navigasyonu:** orta tuş = orbit, Shift + orta tuş = pan, Ctrl + orta tuş / tekerlek = zoom
- **Modal G / R / S:** fareyle taşı, döndür, ölçekle
  - X / Y / Z ile eksen kilitle (2. basış lokal eksen), Shift + X/Y/Z ile düzlem
  - Sayı ya da işlem yaz (`2*3` gibi), Ctrl adımlı, Shift hassas
  - Orta tuşla otomatik eksen, R R serbest döndürme, G G kenar kaydırma
  - Proportional editing (soft select) desteği, tekerlekle alan ayarı
- **Edit modu:** Tab, 1 / 2 / 3 ile köşe / kenar / yüz
- **Modelleme:** E extrude, I inset, Ctrl+B bevel (tekerlek: segment), **Ctrl+R loop cut** (sarı önizleme çizgisiyle), K bıçak, F doldur, J bağla, M birleştir, P ayır, V rip, Ctrl+M aynala
- **Seçim:** Alt + tık loop, Ctrl + Alt + tık ring, Ctrl + tık en kısa yol, L / Ctrl+L bağlı parçayı seç
- **Pie menüler:** Z görüntü, ` (1'in solundaki tuş) görünüm, Ctrl+Tab seçim modu, Shift+S hizala
- **3D imleç:** Shift + sağ tık ile koy, Shift+A ile eklenen objeler imlecin yerine gelir
- **Menüler:** Shift+A ekle, X sil, Ctrl+A uygula (freeze), Ctrl+E / Ctrl+V / Ctrl+F kenar / köşe / yüz menüleri
- **F2** yeniden adlandır, **F3** komut ara (Türkçe kelimelerle de bulur), **F9** son işlemi ayarla
- **Animasyon:** I keyframe, Alt+I sil, Space oynat, ok tuşlarıyla kare / keyframe arası gezin
- **Klavye dilinden bağımsız:** tuşlar fiziksel konumdan okunur, Türkçe Q klavyede de Blender'daki yerlerinde çalışır
- **Blender tercihleri:** Emulate Numpad, Emulate 3 Button Mouse, Zoom to Mouse Position, Orbit Around Selection (Maya kapanınca da hatırlanır)

Tam kısayol listesi Maya içinde **F1** ile açılır.

## Kurulum

1. `blender_kontrol.py` dosyasını Maya'nın scripts klasörüne kopyala:
   - Windows: `Belgeler\maya\<sürüm>\scripts\`  (ör. `Documents\maya\2027\scripts\`)
2. Maya her açıldığında otomatik başlasın istiyorsan `userSetup.py` dosyasını da aynı klasöre koy.
   Orada zaten bir `userSetup.py` varsa, bu dosyadaki satırları onun sonuna ekle.
3. Maya'yı yeniden başlat. Üst menüde **Blender** menüsü görünür.

Otomatik başlatma istemiyorsan Script Editor'ün **Python** sekmesinde şunu çalıştırman yeterli:

```python
import blender_kontrol
blender_kontrol.install()
```

## Kullanım

- Kısayollar fare **3D görünümün üzerindeyken** çalışır. Outliner, Channel Box ve diğer pencerelerde Maya normal davranır.
- **Blender** menüsü:
  - **Blender kontrolleri**: aç / kapat
  - **Kısayol listesi (F1)**
  - Ayarlar: Emulate Numpad, Emulate 3 Button Mouse, Space tuşu (oynat / ara / Maya hotbox), Zoom to Mouse Position, Orbit Around Selection
  - **Yeniden yükle**: dosyayı güncelledikten sonra Maya'yı kapatmadan yeni sürümü yükler

Python'dan:

```python
import blender_kontrol
blender_kontrol.install()     # aç
blender_kontrol.uninstall()   # kapat (Maya varsayılanına dön)
blender_kontrol.show_help()   # kısayol listesi
```

## Blender'dan farklar

- Maya'da her işlem **geçmiş (history)** bırakır. İşin bitince **Ctrl+A → Geçmişi temizle**.
- 3D imleç sahnede `blenderCursor` adlı bir locator'dır; Outliner'da gizlidir ve tıklayınca seçilmez.
- Maya'nın kendi menüleri, Channel Box ve Attribute Editor her zaman kullanılabilir.

## Uyumluluk

- **Maya 2027 / Windows** üzerinde geliştirildi ve test edildi.
- Maya 2024 ve öncesi için PySide2 desteği kodda var ama test edilmedi.
- Tuşlar Windows scan code'larıyla okunuyor; **macOS ve Linux'ta test edilmedi**, kısayollar yanlış tuşlara denk gelebilir.

## Kaldırma

Blender menüsünden kontrolleri kapat, ya da `blender_kontrol.py` ve `userSetup.py`'deki ilgili satırları sil ve Maya'yı yeniden başlat.

## Lisans

[Apache License 2.0](LICENSE)

---

<a name="english"></a>
## English

**Blender for Maya** makes Autodesk Maya behave like Blender: Blender keymap and mouse navigation, modal G/R/S transforms with axis locking and numeric input, Tab edit mode, extrude / inset / bevel / loop cut (with live preview), loop / ring / shortest-path selection, pie menus, a 3D cursor, F2 / F3 / F9 and Blender-style preferences.

It is a single Python file and does **not** modify Maya's own hotkeys. Turn it off from the **Blender** menu and Maya is back to its defaults. Keys are read by physical position, so it works on non-US keyboard layouts too. The UI text is in Turkish.

**Install:** copy `blender_kontrol.py` (and optionally `userSetup.py` for auto-start) into `Documents/maya/<version>/scripts/` and restart Maya, or run `import blender_kontrol; blender_kontrol.install()` in the Script Editor. Press **F1** in the viewport for the full shortcut list.

Developed and tested on Maya 2027 / Windows. Older Maya versions (PySide2) and macOS / Linux are untested.

Licensed under the [Apache License 2.0](LICENSE).
