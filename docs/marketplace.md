# Autodesk App Store / Marketplace hazırlığı

Bu belge listeleme için hazırlık notudur; gönderim yapılmadı. Gönderim Autodesk hesabıyla elle yapılır.

Kaynak: [Maya publisher guidelines](https://aps.autodesk.com/marketplace/publisher-center/maya-publisher-guidelines), [App Store Maya](https://aps.autodesk.com/app-store/publisher-center/maya), yayıncı sözleşmesi (komisyon %0, ücretsiz uygulamaya izin var).

## Paket

`python tools/build_release.py` → `dist/Orange-<sürüm>-bundle.zip` (`Orange.bundle`):

```
Orange.bundle/
  PackageContents.xml        Maya 2022-2027, win64 | macOS | linux, ComponentEntry ./scripts/userSetup.py
  scripts/blender_kontrol/   paket
  scripts/userSetup.py       otomatik başlatma (modül kurulumuyla aynı metin; değiştirme: Maya hash'ler)
  icons/                     raf ikonu
  Contents/                  kısayol kartları (TR / EN), lisans
```

Elle deneme: `Orange.bundle` klasörünü `%ProgramData%\Autodesk\ApplicationPlugins` (Windows) ya da `/Users/Shared/Autodesk/ApplicationAddins` (macOS) altına kopyala, Maya'yı aç.

## Gönderim kontrol listesi

| Gereklilik | Durum |
|---|---|
| Maya 2027'de çalışır | ✅ (tüm testler 2027 / Windows) |
| 2022-2026 listelenebilir | ◐ kodda destekli, gerçek makinede denenmedi |
| Yükleme mekanizması: `PackageContents.xml` | ✅ topluluk örnekleriyle (AnimMemo, SIWeightEditor) aynı düzen; Autodesk'in kendi kurulum paketini (MSI/PKG) ADN ekibi üretir |
| Raf düğmesi ya da menü | ✅ Orange menüsü; raf düğmesi sürükle-bırak kurulumda |
| Kurulumdan sonra çalışmaya hazır | ✅ `userSetup.py` |
| Özel düğüm kimliği | ⚠️ `orange_overlay` eklentisi yerel geliştirme aralığında `0x0007F0A1` kullanıyor. Listelemeden önce [mayaid.autodesk.io](https://mayaid.autodesk.io) üzerinden kalıcı blok alınmalı ve `orange_overlay.py` içindeki `NODE_ID` değiştirilmeli |
| EULA | Apache-2.0 metni + Autodesk standart EULA'sı |
| Yardım sayfası | `Contents/cheatsheet_en.html` (form da HTML yardım üretiyor) |
| Ekran görüntüleri / video | `docs/media/demo.gif`; 90 sn video senaryosu `docs/duyuru.md` |
| Ad | "Orange" (Blender marka politikası nedeniyle ürün adında "Blender" yok; açıklamada "Blender-style" tanımlayıcı olarak geçebilir) |

## Mağaza metni (taslak, İngilizce)

**Orange: Maya, the Blender way**

Use Maya with the muscle memory you already have from Blender. Orange adds the Blender keymap and mouse navigation, modal G / R / S with axis locking and typed values, Tab edit mode, extrude / inset / bevel / loop cut with live preview, pie menus, a 3D cursor, a modifier panel (Subdivision, Mirror, Array, Bevel, Solidify) and FBX round-trips with Blender.

It never edits Maya's own hotkeys: turn it off from the Orange menu and Maya is back to its defaults. Every Orange command is also available in Maya's Hotkey Editor. Keys are read by physical position, so it works on any keyboard layout. English and Turkish UI.

Free and open source (Apache 2.0), donations welcome on Patreon: https://www.patreon.com/c/Yololo . Source: https://github.com/TeaYololo/orange-for-maya . Not affiliated with the Blender Foundation.
