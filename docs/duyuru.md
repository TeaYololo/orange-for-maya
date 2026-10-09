# Duyuru taslakları ve video senaryosu (v0.7)

Bu dosya yayın için hazırlık notudur; hiçbir yere gönderilmedi. Gönderiler sürüm (GitHub Release) yayınlandıktan ve depo yeni adına taşındıktan sonra paylaşılmalı. Her gönderide test edilen ortamı açık yaz ve macOS / Linux denemesi iste.

---

## 1. Polycount, Technical Talk (İngilizce)

**Başlık:** Orange: Blender keymap, modal G/R/S and pie menus inside Maya (free, open source)

> I switched between Blender and Maya for years and kept pressing G-X-2 in Maya. So I built **Orange**, a free Maya add-on (Apache 2.0) that brings the Blender way of working into Maya without touching Maya's own hotkeys:
>
> - modal G / R / S with X / Y / Z, typed values and expressions (`2m`, `90d`), Ctrl snap, Shift precision
> - Tab edit mode, 1 / 2 / 3, E / I / Ctrl+B / Ctrl+R with live preview, G G edge slide, K, F, J, M, P, V
> - MMB orbit, numpad views, pie menus (Z, `, ., ,), 3D cursor, F3 search, F9 adjust last operation
> - Sculpt, UV Editor and Graph Editor contexts; a shortcut editor; English and Turkish UI
>
> It reads keys by physical position, so it works on any keyboard layout. Turn it off from the Orange menu and Maya is back to its defaults.
>
> Tested on Maya 2027 / Windows. **I'm looking for macOS and Linux testers**: the key tables are there but untested on real machines. Orange menu → Key test shows exactly what to report.
>
> Download and GIF: https://github.com/TeaYololo/orange-for-maya
> Feedback, especially "this key doesn't do what Blender does", is very welcome.

## 2. Reddit r/Maya (Self-Promotion flair) (İngilizce)

**Başlık:** I made a free add-on that lets Blender users use their Blender shortcuts in Maya (modal G/R/S, Tab edit mode, pie menus)

> Coming from Blender, the hardest part of Maya for me was muscle memory: G X 2, Tab, E, Ctrl+R. Orange is a free, open-source add-on that adds the Blender keymap and modal tools on top of Maya without changing Maya's hotkeys. GIF and install (drag and drop one file): https://github.com/TeaYololo/orange-for-maya
>
> Tested on Maya 2027 / Windows. Mac and Linux users: I'd love a quick test.

## 3. Autodesk Maya forumu, "Maya Programming" ya da "Maya Shared Area" (İngilizce)

Kısa sürüm (2. ile aynı metin) + teknik not:

> Technical notes for the curious: it's a QApplication event filter plus modal tools written with maya.api and Qt; keys are read via native scan codes; everything is undoable and it restores the Maya preferences it touches when turned off.

## 4. Blender Artists, "Maya'ya geçenler" iplikleri (İngilizce)

Eski ipliklere (2012-2019 "I want Blender hotkeys in Maya") cevap olarak:

> In case anyone still lands here: there is now a free add-on that does this, including modal G/R/S with typed values, Tab edit mode, loop cut with preview and pie menus: https://github.com/TeaYololo/orange-for-maya

## 5. YouTube kanallarına kısa not (Abe Leal 3D, On Mars 3D)

> Hi! Your "Learning Maya as a Blender user" video is great. I built a free add-on that brings the Blender keymap and modal tools into Maya, in case it's useful for a follow-up: https://github.com/TeaYololo/orange-for-maya. No strings attached.

---

## 90 saniyelik video senaryosu

| Süre | Görüntü | Ses / yazı |
|---|---|---|
| 0-5 sn | Maya açık, kullanıcı G'ye basar, hiçbir şey olmaz | "Blender'dan Maya'ya geçince en zor şey kas hafızası." |
| 5-12 sn | Rafta Orange düğmesi, tıkla; "Orange ON" mesajı | "Orange ile Blender tuşların Maya'da çalışır." |
| 12-25 sn | Küp: Tab, 3, yüz seç, E, fareyle çek, 1.5 yaz, Enter | Modal extrude, sayı girişi |
| 25-35 sn | Ctrl+R: sarı önizleme, tekerlek 3 kesim, tık | Loop cut önizlemeli |
| 35-45 sn | Tab, G X 2 Enter, R Z 90, S 0.5 | Modal dönüşüm, eksen çizgisi |
| 45-55 sn | Z pie, ` pie, . pivot pie | Pie menüler |
| 55-65 sn | Shift+sağ tık 3D imleç, Shift+A küp imlece | 3D imleç |
| 65-75 sn | F3 "bevel" ara, F9 son işlemi ayarla | Arama ve F9 |
| 75-85 sn | Ctrl+, kısayol düzenleyici, bir tuşu değiştir | Kendi kısayolların |
| 85-90 sn | Orange menüsü, logo, depo adresi | "Ücretsiz, açık kaynak. Maya, the Blender way." |

Çekim için: `tools/demo_capture.py` aynı adımların bir kısmını otomatik oynatıyor; ekran kaydı (OBS) ile birlikte kullanılabilir.
