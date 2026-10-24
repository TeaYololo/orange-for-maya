# -*- coding: utf-8 -*-
"""GitHub Releases kontrolu ve kullanici onayli Orange guncellemesi.

Akis: acilista (ya da menuden) arka plan is parcacigi GitHub'a sorar; sonuc Qt sinyaliyle ana is parcacigina
gelir. Yeni surum varsa acilista yalniz kisa bir inViewMessage gosterilir ve Orange menusunun basina
"... surumune guncelle" ogesi eklenir; pencere (modsuz QDialog) ancak kullanici isteyince acilir. Indirme
ilerleme penceresiyle, iptal edilebilir; paket <modules>/orange/.update/ altina acilir ve Maya'nin sonraki
acilisinda apply_pending_update kurar.

Surum kurali (PEP 440 benzeri): 1.0.0 > 1.0.0-rc1 > 1.0.0-b1 > 1.0.0-a1. GitHub'daki on surum (rc, beta,
alpha) etiketleri kabul edilir ama otomatik denetimde yalniz kurulu surum de on surumse onerilir; elle
denetimde (Guncellemeleri denetle...) her zaman gosterilir.
"""
from __future__ import absolute_import, division, print_function

import json
import os
import re
import shutil
import socket
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from .compat import QtCore, QtGui, QtWidgets, _main_window
from .core import _msg
from .i18n import _t
from .settings import set_setting, setting


REPOSITORY = 'TeaYololo/orange-for-maya'
RELEASES_API = 'https://api.github.com/repos/%s/releases/latest' % REPOSITORY
RELEASES_PAGE = 'https://github.com/%s/releases/latest' % REPOSITORY
MAX_ARCHIVE_SIZE = 100 * 1024 * 1024
UPDATE_DIR = '.update'                 # <modules>/orange/.update: Maya modules/ klasorunu taramasin
STAGING_PREFIX = 'stage-'
PENDING_MARKER = 'pending.json'
DIALOG_NAME = 'BlenderKontrolUpdate'
PROGRESS_NAME = 'BlenderKontrolUpdateProgress'

_bridge = None
_checking = False
_force_wanted = False          # denetim surerken kullanici elle de istedi: sonucu zorlanmis gibi goster
_downloading = False
_cancel_requested = False
_startup_scheduled = False
available_release = None       # bulunan ama henuz kurulmayan surum (menu ogesi icin modul durumu)
_dialog = None
_progress = None


class _Cancelled(Exception):
    pass


def _queued_connection():
    try:
        return QtCore.Qt.QueuedConnection
    except AttributeError:  # PySide6 enum spelling
        return QtCore.Qt.ConnectionType.QueuedConnection


class _UpdateBridge(QtCore.QObject):
    """Is parcacigindan ana is parcacigina sonuc tasir (kuyruklu baglanti)."""
    check_finished = QtCore.Signal(object)
    download_finished = QtCore.Signal(object)
    progress = QtCore.Signal(object, object)

    def __init__(self):
        super(_UpdateBridge, self).__init__()
        queued = _queued_connection()
        self.check_finished.connect(self._on_check_finished, type=queued)
        self.download_finished.connect(self._on_download_finished, type=queued)
        self.progress.connect(self._on_progress, type=queued)

    def _on_check_finished(self, result):
        global _checking, _force_wanted
        _checking = False
        _startup_stage('update check done')
        if _force_wanted:
            result = dict(result, force=True)
        _force_wanted = False
        _handle_check_result(result)

    def _on_download_finished(self, result):
        global _downloading
        _downloading = False
        _handle_download_result(result)

    def _on_progress(self, received, total):
        _update_progress(received, total)


def _get_bridge():
    """Kopru yalniz ana is parcaciginda (Qt nesnesinin yasadigi yerde) olusturulur."""
    global _bridge
    if _bridge is None:
        app = QtWidgets.QApplication.instance()
        if app is None or QtCore.QThread.currentThread() != app.thread():
            raise RuntimeError('Orange update bridge must be created on the main thread')
        _bridge = _UpdateBridge()
    return _bridge


def _current_version():
    import sys
    package = sys.modules.get('blender_kontrol')
    return getattr(package, '__version__', '0.0.0')


# ---------------------------------------------------------------- surum karsilastirma
_VERSION_RE = re.compile(r'^[vV]?(\d+)\.(\d+)\.(\d+)(?:[-.]?(a|alpha|b|beta|rc|pre|dev)\.?(\d*))?(?:\+[0-9A-Za-z.-]+)?$')
_PRE_RANK = {'dev': 0, 'a': 1, 'alpha': 1, 'b': 2, 'beta': 2, 'rc': 3, 'pre': 3}


def _version_key(version):
    """(major, minor, patch, is_final, pre_num): 1.0.0 > 1.0.0-rc2 > 1.0.0-rc1 > 1.0.0-beta1; None = taninmadi."""
    match = _VERSION_RE.match(str(version or '').strip())
    if not match:
        return None
    major, minor, patch, kind, number = match.groups()
    if kind is None:
        return (int(major), int(minor), int(patch), 1, 0)
    return (int(major), int(minor), int(patch), 0, _PRE_RANK[kind.lower()] * 1000 + int(number or 0))


def _is_prerelease(version):
    key = _version_key(version)
    return key is not None and key[3] == 0


def _should_offer(latest, current, force=False):
    """Yeni surum onerilsin mi? Daha yeni olmali; on surum (rc / beta) otomatik denetimde yalniz kurulu
    surum de on surumse onerilir, elle denetimde her zaman."""
    latest_key, current_key = _version_key(latest), _version_key(current)
    if latest_key is None or current_key is None or latest_key <= current_key:
        return False
    if _is_prerelease(latest) and not _is_prerelease(current) and not force:
        return False
    return True


# ---------------------------------------------------------------- GitHub
def _request(url, accept=None):
    headers = {'User-Agent': 'Orange-Maya-Updater', 'Accept': accept or 'application/vnd.github+json'}
    return urllib.request.Request(url, headers=headers)


# Guncelleme isteklerinin gidebilecegi sunucular (API, surum sayfasi, indirme yonlendirmeleri)
UPDATE_HOSTS = ('api.github.com', 'github.com', 'objects.githubusercontent.com',
                'release-assets.githubusercontent.com', 'codeload.github.com')


def _main_thread_proxies():
    """Sistem proxy ayarlarini ve proxy'siz gidilecek sunuculari ana is parcaciginda oku: (proxies, bypass).
    macOS'ta urllib ikisini de SystemConfiguration (_scproxy) uzerinden sorar; bu sorgu Maya icinde arka plan is
    parcacigindan yapilinca Maya'yi cokertebiliyor (#4)."""
    try:
        proxies = dict(urllib.request.getproxies())
    except Exception as exc:
        _log('proxy', exc)
        return {}, {}
    bypass = {}
    if proxies:
        for host in UPDATE_HOSTS:
            try:
                bypass[host] = bool(urllib.request.proxy_bypass(host))
            except Exception:
                bypass[host] = False
    return proxies, bypass


class _PresetProxyHandler(urllib.request.ProxyHandler):
    """ProxyHandler, ama proxy_bypass karari onceden (ana is parcaciginda) verilmis: standart proxy_open her istekte
    proxy_bypass(host) cagirir, o da macOS'ta is parcacigi icinden _scproxy'ye gider."""

    def __init__(self, proxies, bypass):
        self._bypass = dict(bypass or {})
        urllib.request.ProxyHandler.__init__(self, proxies)

    def proxy_open(self, req, proxy, type):
        host = (req.host or '').rsplit(':', 1)[0].strip('[]').lower()
        if self._bypass.get(host):
            return None
        orig_type = req.type
        proxy_type, user, password, hostport = urllib.request._parse_proxy(proxy)
        if proxy_type is None:
            proxy_type = orig_type
        if user and password:
            import base64
            creds = base64.b64encode(('%s:%s' % (urllib.parse.unquote(user),
                                                 urllib.parse.unquote(password))).encode()).decode('ascii')
            req.add_header('Proxy-authorization', 'Basic ' + creds)
        req.set_proxy(urllib.parse.unquote(hostport), proxy_type)
        if orig_type == proxy_type or orig_type == 'https':
            return None
        return self.parent.open(req, timeout=req.timeout)


def _opener(config=None):
    """Proxy ayari onceden verilmis acici: is parcacigi icinde sistem proxy sorgusu yapilmaz.
    config: _main_thread_proxies() sonucu (proxies, bypass) ya da None (proxy yok)."""
    proxies, bypass = config if isinstance(config, tuple) else (config or {}, {})
    return urllib.request.build_opener(_PresetProxyHandler(proxies, bypass))


def _read_latest_release(proxies=None):
    with _opener(proxies).open(_request(RELEASES_API), timeout=6) as response:
        data = json.loads(response.read().decode('utf-8'))
    tag = data.get('tag_name', '')
    if _version_key(tag) is None:
        raise ValueError('Release tag is not a semantic version: %r' % tag)
    version = tag.strip().lstrip('vV')
    expected_asset = 'Orange-%s.zip' % version
    asset_url = None
    for asset in data.get('assets', []):
        if asset.get('name') == expected_asset:
            candidate = asset.get('browser_download_url', '')
            if candidate.startswith('https://github.com/%s/releases/download/' % REPOSITORY):
                asset_url = candidate
                break
    page_url = data.get('html_url', RELEASES_PAGE)
    if not page_url.startswith('https://github.com/%s/releases/' % REPOSITORY):
        page_url = RELEASES_PAGE
    return {
        'version': version,
        'asset_url': asset_url,
        'page_url': page_url,
        'name': data.get('name') or ('Orange %s' % version),
        'body': data.get('body') or '',
    }


def _friendly_error(exc):
    """Ag / HTTP / paket hatasini kullaniciya soylenecek cevrilmis metne cevir (ayrinti Script Editor'a)."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (403, 429):
            return _t("GitHub istek sınırına ulaşıldı; bir süre sonra tekrar dene")
        if exc.code == 404:
            return _t("Sürüm bilgisi GitHub'da bulunamadı")
        return _t('GitHub yanıt vermedi (HTTP %d); daha sonra tekrar dene') % exc.code
    if isinstance(exc, (urllib.error.URLError, socket.timeout)) or (
            isinstance(exc, OSError) and not getattr(exc, 'filename', None)):
        return _t("İnternet bağlantısı yok ya da GitHub'a ulaşılamıyor; daha sonra tekrar dene")
    if isinstance(exc, OSError):
        return _t('Dosya yazılamadı: %s') % exc
    if isinstance(exc, (ValueError, zipfile.BadZipFile)):
        return _t('Güncelleme paketi geçersiz: %s') % exc
    return str(exc)


def _startup_stage(stage):
    """Acilis korumasi: Maya bu adimda coker ise bir sonraki acilista hangi adim oldugu bilinsin."""
    try:
        from .lifecycle import startup_stage   # dongusel import: cagri aninda
        startup_stage(stage)
    except Exception:
        pass


def _log(label, exc):
    print('[Orange] update %s: %s: %s' % (label, type(exc).__name__, exc))


# ---------------------------------------------------------------- denetim
def _in_batch():
    try:
        import maya.cmds as cmds
        return bool(cmds.about(batch=True))
    except Exception:
        return True


def check_for_updates(force=False):
    """GitHub kontrolunu ana arayuzu bloklamadan baslat. force: menuden; sonuc her durumda gosterilir."""
    global _checking, _force_wanted
    if not force and not setting('auto_update_check'):
        return
    if _in_batch():
        return
    if force:
        _msg(_t('Güncellemeler denetleniyor…'))
    if _checking:
        if force:
            _force_wanted = True      # suren denetimin sonucu zorlanmis gibi gosterilecek
        return
    _checking = True
    _force_wanted = False
    bridge = _get_bridge()
    proxies = _main_thread_proxies()
    _startup_stage('update check')
    thread = threading.Thread(target=_check_worker, args=(bool(force), bridge, proxies),
                              name='OrangeUpdateCheck')
    thread.daemon = True
    thread.start()


def _check_worker(force, bridge, proxies=None):
    try:
        release = _read_latest_release(proxies)
        result = {'ok': True, 'force': force, 'release': release}
    except Exception as exc:
        result = {'ok': False, 'force': force, 'error': str(exc), 'exc': exc}
    try:
        bridge.check_finished.emit(result)
    except RuntimeError:
        pass  # Maya kapandiysa arayuz nesnesi silinmis olabilir.


def _info(message):
    import maya.cmds as cmds
    cmds.confirmDialog(title='Orange', message=message, button=[_t('Tamam')])


def _release_summary(body, limit=350):
    body = re.sub(r'[`*_>#]', '', body or '')
    body = ' '.join(body.split())
    if len(body) > limit:
        body = body[:limit - 3].rstrip() + '...'
    return body


def _rebuild_menu():
    try:
        import maya.cmds as cmds
        from .lifecycle import _build_menu
        cmds.evalDeferred(_build_menu)
    except Exception:
        pass


def _set_available(release):
    global available_release
    if (available_release or {}).get('version') != (release or {}).get('version'):
        available_release = release
        _rebuild_menu()
    else:
        available_release = release


def _handle_check_result(result):
    force = result.get('force', False)
    if not result.get('ok'):
        exc = result.get('exc')
        _log('check', exc if exc is not None else RuntimeError(result.get('error', '')))
        if force:
            _info(_t('Güncelleme denetlenemedi: %s') % _friendly_error(exc))
        return

    release = result['release']
    current = _current_version()
    latest = release['version']
    if _version_key(latest) is None or _version_key(current) is None:
        if force:
            _info(_t('Güncelleme denetlenemedi: %s') % _t('Sürüm bilgisi okunamadı'))
        return
    if not _should_offer(latest, current, force):
        if force:
            _info(_t('Güncel sürümü kullanıyorsun (%s).') % current)
        return
    if not force and setting('skip_update_version') == latest:
        return

    _set_available(release)
    if force:
        show_update_dialog(release)
    else:
        # Acilista modsuz: kisa bildirim + Orange menusunun basindaki "guncelle" ogesi (pencere istenince acilir)
        try:
            import maya.cmds as cmds
            cmds.inViewMessage(assistMessage=_t('Orange %s hazır: Orange menüsü → Güncelle') % latest,
                               position='topCenter', fade=True, fadeStayTime=5000)
        except Exception:
            pass


def _open_url(url):
    try:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))
    except Exception:
        pass


def set_auto_check(enabled):
    set_setting('auto_update_check', bool(enabled))
    _rebuild_menu()
    if enabled:
        schedule_startup_check(delay=250)


def schedule_startup_check(delay=7000):
    """Maya arayuzu acildiktan sonra bir kez kontrol et."""
    global _startup_scheduled
    if _startup_scheduled or not setting('auto_update_check') or _in_batch():
        return
    _startup_scheduled = True

    def run_check():
        global _startup_scheduled
        _startup_scheduled = False
        check_for_updates()

    QtCore.QTimer.singleShot(int(delay), run_check)


# ---------------------------------------------------------------- guncelleme penceresi (modsuz)
class UpdateDialog(QtWidgets.QDialog):
    """Yeni surum penceresi: ozet notlar; Indir / Surum notlari (pencere acik kalir) / Bu surumu atla /
    Bir daha sorma / Daha sonra."""

    def __init__(self, release):
        super(UpdateDialog, self).__init__(_main_window())
        self.release = release
        self.setObjectName(DIALOG_NAME)
        self.setWindowTitle(_t('Orange güncellemesi'))
        self.setMinimumWidth(460)
        layout = QtWidgets.QVBoxLayout(self)
        found = _t('Orange için yeni bir sürüm bulundu: %s (kurulu sürüm: %s).') % (release['version'], _current_version())
        title = QtWidgets.QLabel('<b>%s</b>' % found)
        title.setWordWrap(True)
        layout.addWidget(title)
        name = release.get('name') or ''
        if name and name != 'Orange %s' % release['version']:
            layout.addWidget(QtWidgets.QLabel(name))
        notes = QtWidgets.QPlainTextEdit()
        notes.setReadOnly(True)
        notes.setPlainText(_release_summary(release.get('body'), limit=1500) or _t('Sürüm notu yok'))
        notes.setMinimumHeight(140)
        layout.addWidget(notes, 1)
        if not release.get('asset_url'):
            hint = QtWidgets.QLabel(_t('Bu sürümün indirilebilir paketi yok; sürüm sayfasından kur.'))
            hint.setWordWrap(True)
            layout.addWidget(hint)
        buttons = QtWidgets.QHBoxLayout()
        download = QtWidgets.QPushButton(_t('Şimdi indir') if release.get('asset_url') else _t('Sürüm sayfasını aç'))
        download.setDefault(True)
        download.clicked.connect(self._download)
        buttons.addWidget(download)
        notes_button = QtWidgets.QPushButton(_t('Sürüm notları'))
        notes_button.clicked.connect(lambda: _open_url(self.release['page_url']))   # pencere acik kalir
        buttons.addWidget(notes_button)
        buttons.addStretch(1)
        for label, fn in ((_t('Bu sürümü atla'), self._skip), (_t('Bir daha sorma'), self._disable),
                          (_t('Daha sonra'), self.close)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(fn)
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def _download(self):
        if self.release.get('asset_url'):
            _start_download(self.release)
        else:
            _open_url(self.release['page_url'])
        self.close()

    def _skip(self):
        set_setting('skip_update_version', self.release['version'])
        _set_available(None)
        self.close()

    def _disable(self):
        set_auto_check(False)
        self.close()

    def reject(self):
        self.close()


def _close_dialog():
    global _dialog
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == DIALOG_NAME:
            widget.close()
            widget.deleteLater()
    _dialog = None


def show_update_dialog(release=None):
    """Menuden: bilinen surum varsa pencereyi ac, yoksa elle denetim baslat."""
    global _dialog
    release = release or available_release
    if release is None:
        check_for_updates(force=True)
        return None
    _close_dialog()
    _dialog = UpdateDialog(release)
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()
    return _dialog


# ---------------------------------------------------------------- indirme
def _modules_dir():
    from . import installer
    return installer.default_modules_dir()


def _update_root(modules_dir):
    from . import installer
    return os.path.join(modules_dir, installer.MODULE_DIR, UPDATE_DIR)


def _pending_marker(modules_dir):
    return os.path.join(_update_root(modules_dir), PENDING_MARKER)


def _start_download(release):
    global _downloading, _cancel_requested, _progress
    if _downloading:
        _msg(_t('Güncelleme zaten indiriliyor'))
        return
    try:
        modules_dir = _modules_dir()
        update_root = _update_root(modules_dir)
        if not os.path.isdir(update_root):
            os.makedirs(update_root)
        if os.path.isfile(_pending_marker(modules_dir)):
            _info(_t('Bir güncelleme kurulmayı bekliyor. Maya\'yı yeniden başlat.'))
            return
        staging_dir = tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=update_root)
    except Exception as exc:
        _log('download', exc)
        _info(_t('Güncelleme indirilemedi: %s') % _friendly_error(exc))
        return
    _downloading = True
    _cancel_requested = False
    bridge = _get_bridge()
    _close_progress()
    _progress = QtWidgets.QProgressDialog(_t('Orange %s indiriliyor...') % release['version'], _t('Vazgeç'),
                                          0, 0, _main_window())
    _progress.setObjectName(PROGRESS_NAME)
    _progress.setWindowTitle(_t('Orange güncellemesi'))
    _progress.setWindowModality(QtCore.Qt.WindowModality.NonModal)
    _progress.setMinimumDuration(0)
    _progress.setAutoClose(False)
    _progress.setAutoReset(False)
    _progress.canceled.connect(_cancel_download)
    _progress.show()
    proxies = _main_thread_proxies()
    thread = threading.Thread(target=_download_worker, args=(release, modules_dir, staging_dir, bridge, proxies),
                              name='OrangeUpdateDownload')
    thread.daemon = True
    thread.start()


def _cancel_download():
    global _cancel_requested
    _cancel_requested = True
    if _progress is not None:
        try:
            _progress.setLabelText(_t('İndirme iptal ediliyor...'))
        except RuntimeError:
            pass


def _close_progress():
    global _progress
    if _progress is not None:
        try:
            _progress.canceled.disconnect(_cancel_download)
        except (RuntimeError, TypeError):
            pass
        try:
            _progress.close()
            _progress.deleteLater()
        except RuntimeError:
            pass
    _progress = None


def _update_progress(received, total):
    if _progress is None or _cancel_requested:
        return
    try:
        if total:
            _progress.setRange(0, 100)
            _progress.setValue(int(min(received, total) * 100 // total))
        else:
            _progress.setRange(0, 0)
            _progress.setLabelText(_t('İndiriliyor: %.1f MB') % (received / (1024.0 * 1024.0)))
    except RuntimeError:
        pass


def _safe_extract(archive_path, staging_dir):
    root = os.path.normcase(os.path.abspath(staging_dir))
    with zipfile.ZipFile(archive_path, 'r') as archive:
        expanded_size = sum(member.file_size for member in archive.infolist())
        if expanded_size > MAX_ARCHIVE_SIZE:
            raise ValueError('Expanded update archive is too large')
        for member in archive.infolist():
            name = member.filename.replace('\\', '/')
            pieces = name.split('/')
            if name.startswith('/') or re.match(r'^[A-Za-z]:', name) or '..' in pieces:
                raise ValueError('Unsafe path in update archive')
            target = os.path.normcase(os.path.abspath(os.path.join(staging_dir, *pieces)))
            if os.path.commonpath([root, target]) != root:
                raise ValueError('Unsafe path in update archive')
        archive.extractall(staging_dir)


def _find_release_root(staging_dir):
    for root, dirs, files in os.walk(staging_dir):
        dirs[:] = [name for name in dirs if name != '__pycache__']
        package = os.path.join(root, 'blender_kontrol')
        if os.path.isfile(os.path.join(package, '__init__.py')) and os.path.isdir(os.path.join(root, 'icons')):
            return root
    raise ValueError('Release archive does not contain the Orange installer package')


def _write_pending_update(modules_dir, staging_dir, source_dir, version):
    marker = _pending_marker(modules_dir)
    temporary = marker + '.tmp'
    payload = {'version': version, 'staging_dir': staging_dir, 'source_dir': source_dir}
    with open(temporary, 'w') as fh:
        json.dump(payload, fh)
    os.replace(temporary, marker)


def _download_worker(release, modules_dir, staging_dir, bridge, proxies=None):
    try:
        archive_path = os.path.join(staging_dir, 'release.zip')
        request = _request(release['asset_url'], accept='application/octet-stream')
        with _opener(proxies).open(request, timeout=20) as response:
            length = response.headers.get('Content-Length')
            total = int(length) if length and length.isdigit() else 0
            if total > MAX_ARCHIVE_SIZE:
                raise ValueError('Update archive is too large')
            size = 0
            with open(archive_path, 'wb') as output:
                while True:
                    if _cancel_requested:
                        raise _Cancelled()
                    block = response.read(1024 * 128)
                    if not block:
                        break
                    size += len(block)
                    if size > MAX_ARCHIVE_SIZE:
                        raise ValueError('Update archive is too large')
                    output.write(block)
                    try:
                        bridge.progress.emit(size, total)
                    except RuntimeError:
                        raise _Cancelled()
        if _cancel_requested:
            raise _Cancelled()
        _safe_extract(archive_path, staging_dir)
        source_dir = _find_release_root(staging_dir)
        from . import installer
        source_version = installer.source_version(source_dir)
        if source_version != release['version']:
            raise ValueError('Downloaded package version does not match the release')
        os.remove(archive_path)
        _write_pending_update(modules_dir, staging_dir, source_dir, release['version'])
        result = {'ok': True, 'version': release['version'], 'staging_dir': staging_dir}
    except _Cancelled:
        shutil.rmtree(staging_dir, ignore_errors=True)
        result = {'ok': False, 'cancelled': True}
    except Exception as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        result = {'ok': False, 'error': str(exc), 'exc': exc}
    try:
        bridge.download_finished.emit(result)
    except RuntimeError:
        if result.get('ok'):
            shutil.rmtree(staging_dir, ignore_errors=True)


def _handle_download_result(result):
    _close_progress()
    if result.get('cancelled'):
        _msg(_t('İndirme iptal edildi'))
        return
    if result.get('ok'):
        _set_available(None)      # menudeki "guncelle" ogesi kalksin: kurulum yeniden baslatinca
        _info(_t('%s indirildi. Kurulumu tamamlamak için Maya\'yı yeniden başlat.') % result['version'])
        return
    exc = result.get('exc')
    _log('download', exc if exc is not None else RuntimeError(result.get('error', '')))
    _info(_t('Güncelleme indirilemedi: %s') % _friendly_error(exc))


# ---------------------------------------------------------------- bekleyen kurulum (Maya acilisi)
def _is_within(parent, child):
    parent = os.path.normcase(os.path.abspath(parent))
    child = os.path.normcase(os.path.abspath(child))
    try:
        return os.path.commonpath([parent, child]) == parent
    except ValueError:
        return False


def _is_staging_dir(modules_dir, staging_dir):
    return (bool(staging_dir) and os.path.basename(staging_dir).startswith(STAGING_PREFIX)
            and _is_within(_update_root(modules_dir), staging_dir))


def _clear_pending(modules_dir, staging_dir=None):
    try:
        os.remove(_pending_marker(modules_dir))
    except OSError:
        pass
    if _is_staging_dir(modules_dir, staging_dir):
        shutil.rmtree(staging_dir, ignore_errors=True)


def apply_pending_update():
    """Bekleyen kurulumu Maya acilisinda uygula; basariliysa guncel paket zaten baslatilmistir."""
    modules_dir = None
    staging_dir = None
    try:
        modules_dir = _modules_dir()
        marker = _pending_marker(modules_dir)
        if not os.path.isfile(marker):
            return False        # olagan acilis: bekleyen guncelleme yok
        try:
            with open(marker, 'r') as fh:
                pending = json.load(fh)
        except (IOError, OSError, ValueError):
            _clear_pending(modules_dir)       # bozuk / okunamayan isaret: sessizce temizle
            return False
        staging_dir = pending.get('staging_dir', '')
        source_dir = pending.get('source_dir', '')
        version = pending.get('version', '')
        if not _is_staging_dir(modules_dir, staging_dir) or not _is_within(staging_dir, source_dir):
            raise ValueError('Invalid staged update location')
        from . import installer
        if installer.source_version(source_dir) != version:
            raise ValueError('Staged update version does not match its package')
        current_key = _version_key(_current_version())
        target_key = _version_key(version)
        if current_key is None or target_key is None or target_key <= current_key:
            _clear_pending(modules_dir, staging_dir)
            return False
        installer.install(source_dir, modules_dir=modules_dir, start_now=True)
        _clear_pending(modules_dir, staging_dir)
        return True
    except Exception as exc:
        # Kurulum hatalari (izin, kilitli .mll, disk) dahil her sey kullaniciya soylenir; copy_package
        # atomik oldugu icin eski surum yerinde kalir ve asagida normal yoldan baslatilir.
        try:
            import maya.cmds as cmds
            cmds.warning('[Orange] ' + _t('Orange güncellemesi kurulamadı: %s') % exc)
        except Exception:
            print('[Orange] ' + _t('Orange güncellemesi kurulamadı: %s') % exc)
        try:
            _clear_pending(modules_dir, staging_dir)
        except Exception:
            pass
        return False
