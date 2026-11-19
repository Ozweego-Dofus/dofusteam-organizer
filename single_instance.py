"""Une seule instance de DofusTeam à la fois.

Deux instances lanceraient deux jeux de raccourcis globaux, deux barres flottantes et écriraient chacune settings.json :
les raccourcis se déclencheraient en double et la dernière à se fermer écraserait les réglages de l'autre.
Verrou par fichier (QLockFile) : si le process meurt (crash, kill), Qt détecte le verrou périmé et le libère tout seul.
"""
from __future__ import annotations

from PyQt6.QtCore import QDir, QLockFile

_lock = None   # gardé vivant pour toute la durée du process


def acquire(name: str = "dofusteam_organizer") -> bool:
    """True si on est la seule instance (le verrou est alors tenu jusqu'à la fin du process), False sinon."""
    global _lock
    lock = QLockFile(QDir.temp().filePath(f"{name}.lock"))
    if lock.tryLock(0):
        _lock = lock
        return True
    return False


def release() -> None:
    global _lock
    if _lock is not None:
        _lock.unlock()
        _lock = None
