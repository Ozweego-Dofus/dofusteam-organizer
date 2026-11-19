"""Champ de saisie de raccourci clavier : on clique, on appuie sur la touche (ou la combinaison), le nom est écrit tout seul.

Avant, les raccourcis se tapaient à la main (« ctrl+F1 », « < », « tab »…) : une faute, un nom en français ou une touche
exotique (², Verr Num, pavé numérique…) et la lib `keyboard` ne la reconnaissait pas, sans aucun signal. Ici le nom vient
de la lib elle-même via read_hotkey(), donc il est reconnu par construction ; un nom tapé à la main est validé et le
champ passe en rouge s'il est inconnu. Sans la lib `keyboard` (Mac, dev), le champ reste un QLineEdit normal.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QLineEdit

try:
    import keyboard
    KEYBOARD_OK = True
except Exception:  # noqa: BLE001 — absente/inutilisable : pas de capture, saisie libre
    keyboard = None
    KEYBOARD_OK = False

_ALIASES = {"maj": "shift", "majuscule": "shift", "échap": "esc", "echap": "esc", "escape": "esc", "espace": "space",
            "entrée": "enter", "entree": "enter", "retour": "backspace", "suppr": "delete", "supprimer": "delete",
            "contrôle": "ctrl", "controle": "ctrl", "control": "ctrl", "tabulation": "tab", "verr maj": "caps lock"}


def normalize_hotkey(text: str) -> str:
    """« Ctrl + Maj + F1 » → « ctrl+shift+f1 » : minuscules, espaces autour des « + » retirés, noms français usuels convertis."""
    text = (text or "").strip()
    if not text:
        return ""
    parts = [p.strip().lower() for p in text.split("+")] if text != "+" else ["+"]
    return "+".join(_ALIASES.get(p, p) for p in parts if p)


def is_valid_hotkey(text: str) -> bool:
    """Vrai si la lib `keyboard` saura enregistrer ce raccourci (vide = valide : champ non utilisé)."""
    text = normalize_hotkey(text)
    if not text or not KEYBOARD_OK:
        return True
    try:
        keyboard.parse_hotkey(text)
        return True
    except Exception:  # noqa: BLE001
        return False


class KeyCaptureEdit(QLineEdit):
    _captured = pyqtSignal(int, str)

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._capturing = False
        self._token = 0
        self._captured.connect(self._on_captured)
        self.editingFinished.connect(self._normalize)
        self.textChanged.connect(lambda _t: self.update())
        if KEYBOARD_OK:
            self.setToolTip("Clique puis appuie sur la touche (ou la combinaison) à utiliser")

    # ── capture ────────────────────────────────────────────────────────────────
    def focusInEvent(self, e):
        super().focusInEvent(e)
        if KEYBOARD_OK and not self.isReadOnly():
            self._start()

    def focusOutEvent(self, e):
        self._token += 1            # une capture en cours devient caduque
        self._stop()
        super().focusOutEvent(e)

    def keyPressEvent(self, e):
        if self._capturing:
            e.accept()              # la touche appartient à la capture (hook global), pas au champ de texte
            return
        super().keyPressEvent(e)

    def focusNextPrevChild(self, nxt):
        return False if self._capturing else super().focusNextPrevChild(nxt)   # Tab doit pouvoir être capturé

    def _start(self):
        self._capturing = True; self._token += 1
        self._prev_placeholder = self.placeholderText()
        self.setPlaceholderText("Appuie sur une touche…")
        self.selectAll(); self.update()
        token = self._token

        def _wait():
            try:
                combo = keyboard.read_hotkey(suppress=False)
            except Exception:  # noqa: BLE001
                combo = ""
            self._captured.emit(token, combo)
        threading.Thread(target=_wait, daemon=True).start()

    def _stop(self):
        if self._capturing:
            self._capturing = False
            self.setPlaceholderText(getattr(self, "_prev_placeholder", "—"))
            self.update()

    def _on_captured(self, token, combo):
        if token != self._token or not self._capturing:
            return                  # champ quitté entre-temps
        self._stop()
        combo = normalize_hotkey(combo)
        if combo and combo != "esc":       # Échap seul = annuler, on garde l'ancienne touche
            self.setText(combo)
        self.clearFocus()           # déclenche editingFinished → l'appli recharge les raccourcis

    def _normalize(self):
        t = normalize_hotkey(self.text())
        if t != self.text():
            self.setText(t)
        self.update()

    # ── rendu : cadre citron pendant la capture, rouge si la touche est inconnue ─
    def paintEvent(self, e):
        super().paintEvent(e)
        bad = not is_valid_hotkey(self.text())
        if not (self._capturing or bad):
            return
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#e05c5c" if bad and not self._capturing else "#c8f135"), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 5, 5)
        if bad and not self._capturing:
            self.setToolTip("Touche non reconnue : clique et appuie sur la touche voulue")
