"""DofusTeam — updater.py
Auto-update via GitHub Releases : vérifie/télécharge/applique une nouvelle
version, sans jamais bloquer l'UI (tout le réseau tourne en QThread, même
pattern que hunt.py).

Windows ne permet pas de remplacer un .exe en cours d'exécution. On télécharge
donc la nouvelle version sous un nom temporaire à côté de l'exe courant, puis
apply_update_and_restart() lance un petit .bat qui attend que l'exe se libère
(boucle de "del" tant que le fichier est verrouillé — il ne l'est plus une
fois ce process terminé), le remplace, relance l'appli et s'auto-supprime.
"""
import hashlib, os, subprocess, sys, time
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

from paths import APP_DIR

REPO = "Ozweego-Dofus/dofusteam-organizer"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAME = "DofusTeam.exe"
SHA_ASSET_NAME = "DofusTeam.exe.sha256"   # empreinte publiée avec la release (absente des anciennes versions)


def parse_version(v):
    """"V1.06" -> (1, 6). Tolérant : ignore tout ce qui n'est pas chiffre/point."""
    v = (v or "").strip().lstrip("Vv")
    parts = []
    for p in v.split("."):
        digits = "".join(c for c in p if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(remote_tag, local_version):
    return parse_version(remote_tag) > parse_version(local_version)


def file_sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def parse_sha_text(text):
    """Premier mot du fichier .sha256 (format « <empreinte>  nom » ou « <empreinte> » seule), en minuscules ; "" si invalide."""
    tok = (text or "").strip().split()
    tok = tok[0].lower() if tok else ""
    return tok if len(tok) == 64 and all(c in "0123456789abcdef" for c in tok) else ""


def can_self_update():
    """True seulement en .exe compilé (PyInstaller frozen) — en dev (python
    main.py), il n'y a pas d'exe à remplacer, on ne fait que signaler."""
    return bool(getattr(sys, "frozen", False))


class UpdateCheckThread(QThread):
    """Émet (tag, download_url, size) si une version plus récente que
    current_version existe sur GitHub Releases, sinon ("", "", 0)."""
    done = pyqtSignal(str, str, int)

    def __init__(self, current_version):
        super().__init__()
        self.current_version = current_version
        self.notes = ""      # notes de version (corps de la release GitHub) — lues après le signal done
        self.sha_url = ""    # URL du fichier d'empreinte SHA-256, si la release en publie un

    def run(self):
        if not REQUESTS_OK:
            self.done.emit("", "", 0); return
        try:
            r = requests.get(API_LATEST, timeout=6,
                              headers={"Accept": "application/vnd.github+json"})
            r.raise_for_status()
            data = r.json()
            tag = data.get("tag_name", "")
            if not tag or not is_newer(tag, self.current_version):
                self.done.emit("", "", 0); return
            self.notes = (data.get("body") or "").strip()
            for asset in data.get("assets", []):
                if asset.get("name", "").lower() == SHA_ASSET_NAME.lower():
                    self.sha_url = asset.get("browser_download_url", "")
            for asset in data.get("assets", []):
                if asset.get("name", "").lower() == ASSET_NAME.lower():
                    self.done.emit(tag, asset.get("browser_download_url", ""), asset.get("size", 0))
                    return
            self.done.emit("", "", 0)
        except Exception:
            self.done.emit("", "", 0)


class UpdateDownloadThread(QThread):
    """Télécharge l'asset vers dest_path (en streaming, avec un .part
    intermédiaire pour ne jamais laisser un fichier à moitié écrit sous le
    nom final)."""
    progress = pyqtSignal(int)
    done = pyqtSignal(bool, str)

    def __init__(self, url, dest_path, sha_url=""):
        super().__init__()
        self.url = url
        self.dest_path = Path(dest_path)
        self.sha_url = sha_url

    @staticmethod
    def _replace_with_retry(src, dest, tries=10):
        """Renomme src -> dest. Sous Windows, l'antivirus scanne souvent le .exe fraîchement écrit et le verrouille
        quelques secondes (WinError 5 / 32) : on réessaie, et on retire d'abord un ancien DofusTeam_new.exe resté là
        d'une tentative précédente (sinon le remplacement est refusé)."""
        for i in range(tries):
            try:
                if dest.exists():
                    try: os.chmod(dest, 0o666)
                    except Exception: pass
                    dest.unlink()
                src.replace(dest)
                return
            except PermissionError:
                if i == tries - 1:
                    raise
                time.sleep(0.5)

    def run(self):
        tmp = self.dest_path.with_suffix(".part")
        try:
            if tmp.exists():
                try: os.chmod(tmp, 0o666)
                except Exception: pass
                tmp.unlink()
            r = requests.get(self.url, stream=True, timeout=15)
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=262144):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        self.progress.emit(int(done * 100 / total))
            if self.sha_url:
                # Intégrité : l'exe téléchargé doit correspondre à l'empreinte publiée avec la release. Si l'empreinte
                # est annoncée mais illisible, on abandonne plutôt que d'installer un fichier non vérifié.
                expected = parse_sha_text(requests.get(self.sha_url, timeout=15).text)
                if not expected or file_sha256(tmp) != expected:
                    raise ValueError("vérification d'intégrité échouée (empreinte SHA-256 différente)")
            self._replace_with_retry(tmp, self.dest_path)
            self.done.emit(True, "")
        except PermissionError:
            try: tmp.unlink(missing_ok=True)
            except Exception: pass
            self.done.emit(False, "accès refusé : ferme les anciennes fenêtres DofusTeam, "
                                  "supprime DofusTeam_new.exe à côté de l'exe, ou mets l'exe dans un dossier non protégé")
        except Exception as e:
            try: tmp.unlink(missing_ok=True)
            except Exception: pass
            self.done.emit(False, str(e))


def build_update_bat(old_exe, new_exe):
    """Contenu du .bat de remplacement : attend que l'ancien exe se libère, le remplace, puis RELANCE l'appli.

    Relance : un exe PyInstaller « onefile » lancé par un process qui est lui-même un exe PyInstaller hérite de ses
    variables d'environnement internes (_MEIPASS2, _PYI_*) et croit être son enfant : il cherche alors le dossier
    d'extraction de l'ancien process, déjà supprimé, et échoue (« Security Validation failure »). On les vide donc avant
    le `start` et on pose PYINSTALLER_RESET_ENVIRONMENT=1 (variable prévue par PyInstaller pour se relancer soi-même).
    La relance n'a lieu que si le remplacement a réussi (jamais après un abandon)."""
    old_exe, new_exe = Path(old_exe), Path(new_exe)
    return (
        "@echo off\r\n"
        "set tries=0\r\n"
        ":wait\r\n"
        f'del /f /q "{old_exe}" >nul 2>&1\r\n'
        f'if exist "{old_exe}" (\r\n'
        "    set /a tries+=1\r\n"
        # Limite à 30 tentatives (~1 minute) : si l'ancien exe reste verrouillé au-delà (antivirus, sync cloud...), on
        # abandonne plutôt que de boucler. "ping" (et non "timeout") car "timeout" échoue sans console interactive.
        "    if %tries% GEQ 30 goto giveup\r\n"
        "    ping -n 2 127.0.0.1 >nul\r\n"
        "    goto wait\r\n"
        ")\r\n"
        f'ren "{new_exe}" "{old_exe.name}"\r\n'
        "set PYINSTALLER_RESET_ENVIRONMENT=1\r\n"
        "set _MEIPASS2=\r\n"
        "set _PYI_ARCHIVE_FILE=\r\n"
        "set _PYI_APPLICATION_HOME_DIR=\r\n"
        "set _PYI_PARENT_PROCESS_LEVEL=\r\n"
        "ping -n 3 127.0.0.1 >nul\r\n"
        f'start "" "{old_exe}"\r\n'
        ":giveup\r\n"
        'del /f /q "%~f0"\r\n'
    )


def apply_update_and_restart(new_exe_path):
    """Écrit et lance le .bat de remplacement (voir build_update_bat) puis quitte immédiatement ce process (os._exit)
    pour libérer le verrou sur l'exe courant ; le .bat remplace l'exe et relance l'appli. Ne retourne jamais en cas de
    succès."""
    if not can_self_update():
        return False
    old_exe = Path(sys.executable)
    new_exe = Path(new_exe_path)
    bat_path = APP_DIR / "_dofusteam_update.bat"
    bat_content = build_update_bat(old_exe, new_exe)
    bat_path.write_text(bat_content, encoding="utf-8")
    # Le .bat est lancé via un wrapper WScript.Shell (windowstyle=0) : CREATE_NO_WINDOW seul ne cachait pas sa fenêtre
    # sur certaines configs (Windows Terminal en terminal par défaut) pendant la boucle d'attente.
    vbs_path = APP_DIR / "_dofusteam_update.vbs"
    vbs_content = (
        'Set s = CreateObject("WScript.Shell")\r\n'
        f's.Run """{bat_path}""", 0, False\r\n'
    )
    vbs_path.write_text(vbs_content, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "_MEIPASS2" and not k.startswith("_PYI_")}   # cf. build_update_bat
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen(
        ["wscript", "//B", str(vbs_path)],
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        cwd=str(APP_DIR),
    )
    os._exit(0)
