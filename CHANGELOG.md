# Değişiklikler

## 0.9.0 — 2026-10-09 (modifier'lar, UV, Blender ile FBX)

### Modifier'lar (Orange menüsü → Modifier paneli, F3)
- Blender'da edit modu taban mesh'i düzenler, modifier'lar üstte canlı hesaplanır; Maya'da her işlem geçmişin sonuna eklendiği için modifier'lar düzenlemeye uygun Maya yollarıyla kuruldu:
  - **Subdivision Surface**: Smooth Mesh Preview (topolojiye dokunmaz, kafes düzenlenir), seviye; Uygula = `polySmooth`.
  - **Mirror X / Y / Z**: taban mesh'in canlı instance'ı (obje uzayında aynalı, tabana kilitli, viewport'ta seçilemez, dönüşümü kilitli). Taban mesh'i düzenlemeye devam edersin. Uygula = dikişi kaynaklayan `polyMirrorFace`, dönüşüm korunur.
  - **Array**: canlı instance kopyalar (kopya sayısı paneldeki sayıyla). Uygula = birleştir; ad, ebeveyn, dönüşüm ve pivot korunur.
  - **Bevel** (30°'den keskin kenarlar): Blender varsayılanları (0.1, 1 segment, düz pah); paneldeki segment sayısıyla yuvarlak profil, köşeler dörtgenlere bölünür. İlk sürüm pahı kapalı kuruyordu: şekil kesilmiyor, yalnızca destek halkası ekleniyor ve köşelerde eğri altıgenler kalıyordu.
  - **Solidify**, **Triangulate**, **Weld**: geçmiş düğümü; aç / kapa (`nodeState`), ana değeri ayarla, sil.
- **Ctrl+A** menüsü: Modifier'ları uygula (Mirror → Array → Subdivision sırasıyla, tek undo adımı), Geçmişi temizle, Instance'ları gerçek yap.
- Yığın sırasını değiştirme bilinçli olarak yok: düğümlerin bileşen listeleri topoloji indekslerine bağlı, taşımak modeli bozabilir.

### Edit modunda geçmiş bırakma (ayar)
- Ayarlar → **Edit modunda geçmiş bırakma**: açıkken edit modundaki her işlemden sonra modelleme geçmişi `bakePartialHistory` ile düzleşir (deformer'lar korunur), işlemle aynı undo adımında. Orange modifier'ı olan mesh'lere dokunulmaz. Bu modda F9 ayarlanacak düğüm bulamaz.

### UV editörü
- **G / R / S artık fareyle modal** (Blender gibi): X / Y eksen kilidi, sayı yazma (G X 0.25), Ctrl adımlı (1/16, Shift+Ctrl 1/64), Shift hassas, G / R / S arası geçiş, tek undo adımı. Maya UV görünümünün pan / zoom bilgisini vermediği için hareket göreli; tam değer için sayı yazılır. Eski Maya manipülatörü F3'te.

### Blender ile çalışma
- **Blender için FBX dışa aktar** (Orange menüsü, F3): seçim, metre, Y-up (Blender'ın varsayılan içe aktarımı Z-up'a kendisi çevirir), smoothing groups, geçmiş bağlantısız. **Blender FBX içe aktar**: sahne birimine çevirir, ekler. Gidiş-dönüş testinde boyut ve sert kenarlar korunuyor.

### Diğer
- F1 yardımı (TR / EN) yeni özelliklerle güncellendi; kısayol kartları yeniden üretildi.
- Maya 2027 `wrapInstance` önbellek davranışı için regresyon testi.
- `docs/marketplace.md`: Autodesk App Store kontrol listesi ve mağaza metni taslağı (gönderim yapılmadı; `orange_overlay` için kalıcı düğüm kimliği alınması gerekiyor).

## 0.8.0 — 2026-10-09 (çekirdek altyapı)

### Performans ve geri alma
- **G / R / S, extrude, inset, bevel, kenar kaydırma, Alt+S / Shift+Alt+S / Shift+E artık tek undo adımı.** Önceden sürüklemenin her karesi ayrı bir undo kaydıydı; uzun bir sürükleme binlerce kayıt biriktiriyor, geri almak saniyeler sürüyordu (160 bin köşeli mesh'te 2,03 sn). Sürükleme boyunca undo kaydı kapalı, bitişte başlangıca dönülüp sonuç tek işlem olarak kaydediliyor (aynı mesh'te 0,05 sn). Redo sonucu geri getiriyor.
- Değer modallarında (Alt+S, Shift+Alt+S, Shift+E, sculpt F / Shift+F) Esc / sağ tık, boş undo adımı yüzünden kullanıcının **bir önceki işlemini geri alabiliyordu**; düzeltildi.
- Ölçüm: 160 bin köşede sürükleme karesinin ~55 ms'si Maya'nın kendi `move` komutu; Python'dan API ile `setPoints` daha yavaş çıktığı için (76-170 ms) o yol eklenmedi.

### Viewport 2.0 önizleme (isteğe bağlı)
- Eksen çizgisi ve loop cut önizlemesi isteğe bağlı olarak Maya'nın kendi çizim API'siyle (MUIDrawManager, `orange_overlay` eklentisi) viewport içinde çizilebiliyor: kompozitörsüz Linux / macOS'ta siyah kutu riski yok. Ayarlar → **Önizleme çizimi**. Varsayılan Qt katmanı kalıyor, çünkü Maya 2026+ güvenilir olmayan klasörden eklenti yüklerken her oturumda izin soruyor (Orange güvenlik ayarlarını kendiliğinden değiştirmez; ayar penceresi nasıl güvenilir yapılacağını anlatıyor).
- Yardımcı düğüm yalnızca önizleme görünürken var: sahneyi "değişti" yapmıyor, kaydedilen dosyaya `requires` dahil hiçbir iz bırakmıyor; Orange kapatılınca eklenti boşaltılıyor.

### Maya Hotkey Editor
- Her Orange komutu **Hotkey Editor'da "Orange" kategorisinde** (ör. `Orange_LoopCut`). İstersen Maya'nın kendi sistemiyle başka bir tuşa, rafa ya da marking menu'ye bağlarsın; Orange kapalıyken de çalışırlar. Orange etkin hotkey setine dokunmuyor. Komutlar Orange aç / kapa ile silinmiyor (bağladığın tuşlar bozulmasın); yalnızca **Orange'ı kaldır** siliyor.

### Modelleme
- **Grid Fill** (Ctrl+F menüsü, F3): seçili kapalı sınır halkasını Coons yamasıyla dörtgen ızgarayla doldurur; yüz yönü komşularla uyumlu.
- **G G kenar kaydırmada E (eşit mesafe) ve F (çevir)**: E ile her köşe aynı mesafe kayar (yeni halka eskisine paralel), F eşit modda referansı karşı halkaya çevirir.
- **Çoklu loop cut'ta kaydırma**: Ctrl+R ile birden fazla kesimden sonra kesimler aralıklarını koruyarak birlikte kayar (Maya'nın `polySplitRing`'i çoklu modda ağırlık kullanmadığı için yeni köşeler halka kenarlarına eşlenip birlikte taşınıyor); sağ tık ortada onaylar, tek undo adımı.

### Sağlamlık
- Olay filtresi 3 saniyede bir en üste alınıyor: Maya yeni panel açınca kendi filtresini kurup Maya kısayolu olan tuşları (ör. Ctrl+R = Create Reference) Orange'dan önce işleyebiliyordu.
- Sahne değişince (_abort_modal) tüm araçlarda askıdaki undo kaydı mutlaka yeniden açılıyor.

## 0.7.0 — 2026-10-09 (Orange, yayın düzeni, paket yapısı)

### Yeni ad: Orange
- Ürün adı **Orange — Maya, the Blender way** oldu (Blender Foundation marka politikası "Blender" ile başlayan ürün adlarını istemiyor). Menü **Orange**, mesajlar, pencere başlıkları, F1, raf düğmesi ve ikon buna göre güncellendi. Python paket adı `blender_kontrol` kaldı (`import blender_kontrol` aynen çalışır). README'ye "Blender Foundation ile ilişkili değildir" notu eklendi.

### Kurulum: Maya modülü
- Sürükle-bırak kurulum artık Orange'ı **Maya modülü** olarak kurar: `Documents/maya/modules/orange/` (paket, kendi `userSetup.py`'si, ikon) ve `orange.mod`. Kullanıcının kendi `userSetup.py` dosyasına dokunulmaz; 0.6 ve öncesinin scripts klasöründeki kopyası ve `userSetup.py` bloğu otomatik temizlenir. Eski "BL" raf düğmesi Orange ikonlu düğmeyle değiştirilir.
- Kurulum mantığı paket içinde bağımsız `installer.py`; `drag_drop_install.py` onu dosya yolundan yükler (Maya'da eski sürüm yüklüyken de doğru kod çalışır).
- Orange menüsü → **Orange'ı kaldır...** (onaylı): modül, `.mod`, raf düğmesi ve eski kopyalar silinir; ayarlar ve kısayollar kalır.
- `tools/build_release.py`: GitHub sürüm zip'i ve Autodesk ApplicationPlugins / App Store düzeninde `Orange.bundle` (`PackageContents.xml`, Maya 2022-2027).

### Yardım ve geri bildirim
- Orange menüsü → **Tuş testi**: basılan tuşun ham kodlarını ve Orange'ın onu nasıl okuduğunu gösterir (macOS / Linux tablolarını düzeltmek için). Açıkken Orange kısayolları devre dışıdır.
- Orange menüsü → **Sorun bildir**: Maya, Python, Qt, platform, klavye ve ayar bilgilerini panoya kopyalar ve GitHub sorun formunu açar. Telemetri yok; hiçbir şey otomatik gönderilmez.
- Orange menüsü → **Kısayol kartı**: kullanıcının kendi kısayolları ve diliyle yazdırılabilir HTML kart. Varsayılan kartlar depoda: `docs/cheatsheet_en.html`, `docs/cheatsheet_tr.html`.
- GitHub sorun şablonları (hata, eksik Blender özelliği, tuş çalışmıyor), iki dilli.
- README yeniden yazıldı; başına demo GIF'i (`docs/media/demo.gif`, `tools/demo_capture.py` ile Maya içinde gerçek olaylarla çekildi). Duyuru taslakları ve video senaryosu: `docs/duyuru.md`.

### Paket yapısı
- 7.040 satırlık tek `__init__.py` 33 modüle bölündü (`compat`, `keys`, `core`, `settings`, `i18n`, `util`, `ui`, `picking`, `editmode`, `cursor`, `view`, `modal`, `loopcut`, `slide`, `selection`, `mesh`, `objects`, `modes`, `uv`, `graph`, `search`, `keymap`, `events`, `lifecycle` ...). Katman kuralı: alt modül üst modülü modül başında import etmez; test bunu denetler. Bölme kaynak satırları birebir taşıyan bir araçla yapıldı (davranış değişmedi; 286 canlı test geçti).
- **Yeniden yükle** artık paketi tamamen boşaltıp baştan yükler (alt modüllerin birbirine verdiği eski adlar kalmaz).
- Paket adları geriye uyumlu: `blender_kontrol.Modal`, `blender_kontrol.install` vb. çalışmaya devam eder.

### Hata düzeltmeleri
- **Maya açılırken otomatik başlatılınca Tab, Shift+Tab ve Ctrl+Tab çalışmıyordu.** Maya açılışta eklentiden sonra kendi uygulama olay filtresini kuruyor ve Qt en son kurulan filtreyi önce çağırdığı için Tab'ın KeyPress olayı Orange'a hiç ulaşmıyordu (testler eklentiyi geç kurduğu için görünmüyordu). Filtre açılıştan sonra birkaç kez en üste alınıyor; kabul edilen bir kısayolun tuş olayı yine de yutulursa filtre kendini en üste taşıyıp tuşu kendisi işliyor.
- Tuş testinde PySide 6.5+ değiştirici bayrakları `int()` ile okunamıyordu.

### Geliştirme
- `tests/test_pure.py` + `tests/conftest.py`: Maya gerektirmeyen 66 test (tuş tabloları, kısayol tablosu, çeviri kapsamı, ifade ayrıştırma, mesh grafiği algoritmaları, katman kuralı). GitHub Actions: ruff + derleme + bu testler (Windows / macOS / Linux); mayapy testleri isteğe bağlı self-hosted iş.
- `pyproject.toml` (ruff ayarları). Testler artık kullanıcının gerçek kısayol dosyasına yazmaz (`ORANGE_KEYMAP`).

## 0.6.0 — 2026-10-09 (modlar ve diğer editörler + uçtan uca test paketi)

### Yeni
- **Ctrl+Tab mod pie'ı:** köşe / kenar / yüz / obje, Sculpt, Vertex Paint, Weight Paint (skin yoksa uyarır), Texture Paint.
- **Sculpt modu:** F yarıçap, Shift+F güç (fareyle, sayı yazılabilir); V draw, S smooth, P pinch, I inflate, G grab, C clay (wax), Shift+C crease (knife), K snake hook (smear), Shift+T scrape, M mask (freeze); Ctrl+I maskeyi ters çevir, Alt+M temizle; Tab edit moduna. Sculpt'ta yalnız görünüm, oynatma ve genel tuşlar geçerli kalır.
- **UV editörü bağlamı:** 1/2/3/4 UV / kenar / yüz / ada, A / Alt+A / Ctrl+I, L ve Ctrl+L ada, U unwrap menüsü, P / Alt+P pin, V / Y ayır, Alt+V dik, Shift+S / Shift+W hizalama menüsü (U / V hizala, ortala, normalize, paketle). G / R / S Maya'nın UV manipülatörünü açar (Maya UV görünüm dönüşümünü dışarıya vermediği için fareyle modal taşıma yapılamıyor).
- **Graph Editor / Dope Sheet bağlamı:** G anahtarları fareyle taşır (X yalnız zaman, Y yalnız değer, kareye snap, Ctrl serbest, sayı girişi), S zaman ölçeği, T interpolasyon, V tutamak tipi, Shift+E ekstrapolasyon, X / Delete, A / Alt+A, Home / Numpad . odak, P önizleme aralığı. Ctrl+Home / Ctrl+End aralık başı / sonu her yerde.
- **F9 "Son işlemi ayarla" paneli:** son history düğümünün sayısal / bool / enum ayarları yüzen panelde; değiştirince anında ve undo'lu uygulanır; Attribute Editor düğmesi.
- **Yeni 3D imleç:** kırmızı ve beyaz halka + koyu artı; seçilemez (seçime girerse çıkarılır), Outliner'da gizli. Rotasyonu var: ayarlardan Shift+sağ tıkta görünüme ya da yüzey normaline hizalanır; "İmleç" oryantasyonu bunu kullanır; Shift+C rotasyonu da sıfırlar. Eski siyah imleç otomatik dönüştürülür.
- **Q favoriler** (F3'te Ctrl+Enter ile ekle), **Ctrl+PageUp / PageDown** Maya çalışma alanları, **Ctrl+F2** toplu yeniden adlandır (bul / değiştir, önek, sonek, numara), **Shift+`** Walk navigasyonu.

### Uçtan uca testler
- `tests/maya_live_tests.py`: Maya içinde 14 bölüm, 286 test. Gerçek tuş ve fare olaylarını eklentinin filtresinden geçirir; menüleri yakalayıp öğelerini çalıştırır; yalnız `bkt_` önekli objeler kullanır ve kamera, ayarlar, kısayollar, araç ile seçimi geri yükler.
- `tests/headless_tests.py`: mayapy ile 75 test (çeviri kapsamı, platform tuş tabloları, ifade ayrıştırma, mesh grafiği, ışın-kutu, kısayol atama, kurulum, mesh işlemleri).

### Testlerin yakaladığı hatalar (düzeltildi)
- **Menülerde `functools.partial` öğeleri çöküyordu** (Shift+G benzerini seç, snap hedefi ve layer menüleri): undo sarmalayıcısı adı okuyamıyordu.
- **Numpad 0 sahne kamerasından çıkmıyordu:** kamera adı kısa / tam yol karşılaştırması.
- **Numpad + / − yakınlaşırken orbit merkezi kayıyordu:** dolly sonrası "center of interest" güncellenmiyordu.
- **"Aktif eleman" pivotu ilk seçileni kullanıyordu:** Maya tek komutla çoklu seçimde sıralı seçimi ters veriyor; obje modunda `ls -sl` sırası kullanılıyor.
- **↑ / ↓ keyframe atlama hareket etmiyordu:** zaman çubuğu sorgusu geçerli kareyi döndürüyordu; seçili objelerin anahtarları sorgulanıyor.
- **Shift+E ekstrapolasyon etkisizdi:** eğri düğümü adıyla değil, seçili eğrilerle uygulanıyor.
- **Fare altı seçimde hızlandırıcı parametresi yanlış veriliyordu**.

## 0.5.0 — 2026-10-09 (seçim ve edit modu derinliği)

### Seçim
- **Shift+1/2/3** çoklu mod. Maya keyfi ikili kombinasyon desteklemediği için iki ya da daha fazla tür istenince Maya'nın Multi-Component modu açılır (köşe, kenar ve yüz birlikte seçilir); mesaj bunu söyler. **Ctrl+1/2/3** edit modunda seçimi genişleterek mod değiştirir (obje modunda yumuşak önizleme olarak kalır). Düz 1/2/3 artık Blender gibi dönüştürür: yukarı geçişte tamamen seçili olanlar kalır.
- **Shift+G**: edit modunda benzerini seç (yüz: normal, alan, kenar sayısı, materyal, eş düzlemli; kenar: uzunluk, yön, komşu yüz sayısı, sertlik, crease; köşe: normal, komşu yüz, bağlı kenar). Obje modunda grupla seç (çocuklar, doğrudan çocuklar, ebeveyn, kardeşler, tür, layer).
- **Shift+Ctrl+M** ayna seçimi (objenin yerel X'i; köşe, kenar, yüz).
- **Ctrl+sağ sürükle** kement ile ekle, **Shift+Ctrl+sağ** çıkar (geçici olarak Maya'nın kement aracı, bitince önceki araç).
- **B** kutu seçimi, **W** araç döngüsü (kutu / kement / fırça), **C** fırça seçimi; C, sağ tık ya da Esc ile önceki araca dönülür.
- **Alt+tık** sınır kenarında tüm sınırı seçer; **Shift+Alt+tık** zaten seçili loop'u çıkarır.
- **Shift+Ctrl+tık** bölge doldur: son seçilenle tıklanan arasındaki dikdörtgen (yüz ve köşe modu; kenar modunda köşe bölgesinin iç kenarları).

### Edit modu
- **Alt+S** kalınlaştır / incelt (köşe normalleri boyunca; obje modunda ölçeği sıfırla olarak kalır), **Shift+Alt+S** küreye çevir (0..1), **Shift+E** kenar crease (0..1). Hepsi aynı değer modalını kullanır: merkezden uzaklaş / yaklaş, sayı yaz, Ctrl adımlı, Shift hassas.
- **U** UV menüsü: Unwrap (Unfold3D), otomatik projeksiyon, küp / silindir / küre / görünümden projeksiyon, dikiş işaretle / kaldır, sıfırla.
- **X** menüsüne Sınırlı erit (5°), Kenar halkaları ve Collapse eklendi.
- **Shift+A** edit modunda primitifi düzenlenen mesh'e ekler (yeni yüzler seçili kalır).

### Görünüm ve obje
- **Shift+Space** araç pie (kutu, kement, fırça, taşı, döndür, ölçekle, bıçak, Quad Draw), **Ctrl+Alt+Q** dörtlü görünüm, **Shift+Alt+Z** overlay'ler (grid, HUD, kamera/ışık/locator ikonları, manipülatörler; geri alınca eski hali).
- **Z** pie: Rendered (sahne ışıkları + gölge) ve Overlay eklendi; Solid / Material ışık ve gölgeyi sıfırlar.
- **Ctrl+P / Alt+P** artık Blender gibi menü: dönüşümü koru / ters dönüşümsüz; kaldır / dünya dönüşümünü koruyarak kaldır.
- **Ctrl+L** (obje modu) bağla / aktar: materyaller, UV (aynı topoloji), layer. Edit modunda bağlı olanları seç olarak kalır.
- **Ctrl+G** seçimden yeni layer; **Ctrl+Alt+Shift+C** origin ayarla (geometriyi origin'e, origin'i geometriye / 3D imlece / kütle merkezine).
- **Alt+Q** transfer mode: imleç altındaki objeye aynı bileşen modunda geç.
- **Shift+O** falloff pie (yumuşak, küre, kök, keskin, doğrusal, sabit), **Alt+O** sadece bağlı parçalar.
- F3: Boolean birleşim / fark / kesişim (en son seçilen hedef), sınırlı erit, origin komutları, UV unwrap.

### Performans
- Fare altı seçimde sınır kutusu ön elemesi ve Maya'nın hızlandırıcı ızgarası (`accelParams`); en kısa yol / bağlı seçim için mesh grafiği önbelleği.

### Bilinen eksikler
- G G kaydırmada E (eşit mesafe) ve F (yön çevir) yok. Ctrl+F menüsüne Grid Fill eklenmedi (Maya'da doğrudan karşılığı yok).

## 0.4.0 — 2026-10-09 (platform, ayarlar, dil, kurulum)

### Yeni
- **Paket yapısı:** tek `blender_kontrol.py` yerine `blender_kontrol/` paketi (`__init__.py` çekirdek, `i18n_en.py` İngilizce metinler ve yardım). `import blender_kontrol` aynen çalışır. "Yeniden yükle" alt modülleri de yeniler. 0.3'ten yükselten scripts klasöründeki eski `blender_kontrol.py`'yi silmeli (sürükle-bırak kurulum siler).
- **Sürükle-bırak kurulum** (`drag_drop_install.py`): Maya görünümüne bırakınca paketi kullanıcı scripts klasörüne kopyalar, eski tek dosyayı siler, `userSetup.py`'ye işaretli otomatik başlatma bloğunu bir kez ekler (mevcut içerik korunur), seçili rafa **BL** aç/kapa düğmesi koyar ve eklentiyi başlatır. `remove_from_usersetup()` bloğu geri kaldırır.
- **İngilizce arayüz:** tüm mesajlar, menüler, pie'lar, ipucu çubuğu, F3 ve F1 yardımı İngilizce de var (453 metin). Dil ayarı: Otomatik (sistem dili Türkçe ise Türkçe), Türkçe, English. F3 her iki dilde de arar.
- **Ayar penceresi (Ctrl+, ya da Blender menüsü):** dil, Space tuşu, pivot / oryantasyon / snap hedefi varsayılanları, Emulate Numpad, Emulate 3 Button Mouse, Zoom to Mouse, Orbit Around Selection, snap açık.
- **Kısayol düzenleyici:** komut listesi, arama, satıra çift tıkla ve yeni tuşa bas; Esc vazgeç, Backspace kısayolu kaldır; çakışan komutun kısayolu kaldırılır ve bildirilir; seçileni / hepsini varsayılana döndür. Kayıt: `prefs/blender_kontrol_keymap.json`. F3 güncel kısayolları gösterir.
- **macOS ve Linux tuş eşlemesi:** fiziksel tuş artık platforma göre okunuyor. Windows scan code, Linux/X11-Wayland `nativeScanCode - 8` (evdev; numpad `/` = 98), macOS `nativeVirtualKey` (Carbon kVK tablosu; kVK_ANSI_A = 0 belirsizliği ele alındı). Benzetimli tuş olaylarıyla 18 durum test edildi; gerçek macOS / Linux makinede henüz denenmedi.

### Düzeltmeler
- Yardımda köşe extrude hâlâ geçiyordu; kaldırıldı, Ctrl+, eklendi.

## 0.3.0 — 2026-10-08 (dönüşüm modeli)

### Yeni
- **Pivot noktası** (`.` pie): orta nokta, sınır kutusu merkezi, 3D imleç, aktif eleman, tek tek (individual origins). Obje modunda her obje kendi pivotunda; edit modunda her mesh'in seçimi kendi ortasında döner/ölçeklenir.
- **Dönüşüm oryantasyonu** (`,` pie): global, lokal, normal (seçimin ortalama normali), görünüm, imleç, ebeveyn. X/Y/Z ilk basışta oryantasyonun eksenini, ikinci basışta global'i (oryantasyon globalse lokali) kilitler. Sayı girişi ve orta tuş otomatik eksen de oryantasyonu kullanır. Edit modunda ölçekleme keyfi çerçevede `scale -orientAxes` ile yapılır; obje modunda Maya shear üretemediği için lokal eksene düşer.
- **Snap**: Shift+Tab açar/kapar, Ctrl geçici olarak tersine çevirir. Hedef (Shift+Ctrl+Tab ya da Blender menüsü): artım (grid), köşe, kenar, yüz. Köşe/kenar/yüz hedefinde taşıma sırasında seçimin merkezi fare altındaki elemana oturur; düzenlenen mesh'ler hariç tutulur.
- **Alt + orta tuş ile gezinme** modal sırasında (Blender "Transform Navigation with Alt"): Alt+orta orbit, +Shift pan, +Ctrl zoom; işlem kaldığı değerden devam eder.
- **İfade modu** (`=`): sayı girişinde birimler ve fonksiyonlar: `2m`, `10cm`, `3in`, `90d`, `1.5r`, `pi/2`, `sqrt(2)`, `sin(30)`. Uzunluklar sahne birimine çevrilir.
- **Alt+E extrude menüsü**: yüzler, normaller boyunca (`thickness`), tek tek yüzler, kenarlar, köşeler.
- **I I** inset'te tek tek (individual) anahtarı; **Shift+Ctrl+B** köşe bevel; bevel modalında **P** profil, **M** miter, **C** chamfer.
- HintBar başlığında pivot, oryantasyon ve snap durumu görünür.
- **Kısıt ekseni çizgisi**: G/R/S sırasında X/Y/Z basınca pivottan geçen renkli çizgi (X kırmızı, Y yeşil, Z mavi, Blender tema renkleri); Shift+X/Y/Z düzlemde iki çizgi; extrude sırasında normal ekseni. Seçili oryantasyonun eksenlerini izler, işlem bitince kaybolur.

### Maya içinde canlı test sonrası düzeltmeler (2026-10-09, maya-mcp ile)
- Obje modunda orta nokta / imleç / aktif pivot etrafında döndürme ve ölçekleme objeleri yörüngeye sokmuyordu: Maya'nın `rotate/scale -pivot` bayrağı transform'larda konumu `rotatePivot` attribute'larıyla telafi ediyor. Artık obje modunda pivot bayrağı verilmiyor, konum `translate` üzerinden hesaplanıyor (Blender'daki gibi).
- Köşe snap'i ray-cast yerine ekran uzayında en yakın köşeyi arıyor (numpy ile projeksiyon, 24 px yarıçap); siluetteki köşeler de yakalanıyor.
- Loop cut aracı bitince tekrar tıklama ikinci bir kesim yapmıyor.
- **G G çalışmıyordu**: Maya'nın Slide Edge aracını açıyordu, o araç orta tuşla sürüklenir ve orta tuş eklentide orbit. Artık kendi kaydırma modalı: kenar/yüz modunda seçili kenarların köşeleri komşu kenarlar boyunca iki yöne kayar (taraflar halka boyunca tutarlı seçilir), köşe modunda her köşe fare yönündeki kenar boyunca kayar. Sayı girişi, Ctrl adımlı, Shift hassas, Esc/sağ tık iptal. **Shift+V** köşe kaydırma; Ctrl+E menüsündeki 'Kenar kaydır' da bu aracı açar.
- **Köşe modunda E kapatıldı**: uyarı verir. Blender'daki gibi tel kenar Maya mesh'inde olamıyor; Maya'nın köşe extrude'u da üst üste köşe ve sıfır alanlı yüz bırakıyordu. Alt+E menüsünden köşe maddesi kaldırıldı. F, ilk haline döndürüldü.
- **Edit modunda hiçbir bileşen seçilemiyordu** (Tab, 1/2/3 sonrası tıklama boş kalıyordu): Maya 2027'de `doMenuComponentSelectionExt` seçim maskelerini ayarlamıyor. Edit modu artık bileşen modu + açık maske ile giriliyor (F8 + F9/F10/F11 yolu).

## 0.2.0 — 2026-10-08

### Düzeltmeler
- Köşe modunda **E** artık modal taşıma başlatıyor (önce sadece sabit uzunlukta extrude yapıyordu).
- Extrude sırasında **X / Y / Z** eksene kilitliyor, **G** serbest taşımaya geçiyor (önce yok sayılıyordu).
- `uninstall()` artık `trackSelectionOrder`, Dolly "Towards Center" ve Tumble "Tumble on Object" ayarlarını kurulumdan önceki değerlerine geri alıyor.
- Obje modunda **M** merge menüsü yerine "Layer'a taşı" (Blender Move to Collection) menüsünü açıyor.
- Ölü kod kaldırıldı: `snap_menu`, `view_menu`, `shading_menu`. `shade_smooth` / `shade_flat` artık Ctrl+F ve Alt+N menülerinde ve F3'te.
- Tüm tuş bağları F3 aramasında bulunuyor (önce 99 bağın 52'si aranamıyordu). `_b(title=)` ile başlık bağın yanında.
- Emulate 3 Button Mouse açıkken Alt+tık loop seçimini kaybetmemek için **Ctrl + çift tık = ring** (Blender'daki gibi).
- Sayı girişinde **-** işareti çeviriyor, **Tab** sonraki eksene geçiyor (G 1 Tab 2 Enter).
- pyflakes uyarısı (`_edge_ring_pairs` içinde kullanılmayan `e`).

### Yeni kısayollar
- Modal: **C** kısıtı kaldır, **Shift + orta tuş** otomatik düzlem, **Shift + Ctrl** ince adım (0.1 birim / 1° / 0.01).
- Görünüm: **Numpad 9** (180°), **Shift + Numpad 1/3/7** (aktif objenin lokal eksenine göre), **Ctrl + Numpad 2/4/6/8** kaydır, **Shift + Numpad 4/6** yatır, **Alt + orta tık** merkeze al, **Alt + orta sürükle** yöne göre eksen görünümü.
- Mesh: **Alt + F** doldur ve üçgenle, **Alt + M** split menüsü, **Ctrl + X / Ctrl + Delete** dissolve, **Ctrl + Shift + R** ofset kenar halkası, **Shift + Ctrl + N** normalleri içe, **Alt + N** artık normal menüsü, **Ctrl + 4 / 5** subdiv seviyesi.
- Merge menüsü: İmleçte, Collapse, İlk seçilende, Son seçilende. Separate menüsü: Materyale göre.
- Animasyon: **Shift + Ctrl + Space** ters oynat, **Alt + tekerlek** kare kaydır.
- Genel: **F11** render penceresi, **Ctrl + F12** batch render.

### Bilinen eksikler (sonraki fazlar)
- Çoklu loop cut'ta kaydırma aşaması yok (`polySplitRing` çoklu modda `weight` kullanmıyor).
- macOS / Linux tuş eşlemesi, pivot/oryantasyon pie'ları ve vertex snap.

## 0.1.0 — 2026-10-08
- İlk yayın.
