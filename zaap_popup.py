"""Fenêtre rapide « Zaap » de la barre flottante : tous les zaaps, barre de recherche, favoris en tête.

Clic (ou Entrée) sur un zaap -> `on_pick(nom, x, y)` (la barre envoie alors /zaap x y). Les favoris (étoile) sont
toujours affichés en premier, dans l'ordre où ils ont été ajoutés ; la recherche filtre l'ensemble de la liste
(insensible aux accents et à la casse, sur le nom, la région ou les coordonnées).
"""
import unicodedata

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                             QLabel)

from theme import ACC, GOLD, MUT, TEXT
from zaap_data import ZAAPS, get_favorites


def _norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def ordered_zaaps(favs, query=""):
    """[(zaap, est_favori)] : favoris d'abord (ordre d'ajout), puis le reste par ordre alphabétique ; filtré par `query`."""
    q = _norm(query.strip())
    fav_rank = {n: i for i, n in enumerate(favs)}

    def match(z):
        if not q: return True
        hay = _norm(f"{z['name']} {z['region']} {z['coords'][0]},{z['coords'][1]} {z['coords'][0]} {z['coords'][1]}")
        return all(part in hay for part in q.split())

    zs = [z for z in ZAAPS if match(z)]
    zs.sort(key=lambda z: (0, fav_rank[z["name"]]) if z["name"] in fav_rank else (1, _norm(z["name"])))
    return [(z, z["name"] in fav_rank) for z in zs]


class ZaapQuickPopup(QFrame):
    WIDTH, HEIGHT = 330, 420

    def __init__(self, config, on_pick, on_manage, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.config, self.on_pick, self.on_manage = config, on_pick, on_manage
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setStyleSheet(
            "ZaapQuickPopup{background:#161b22;border:1px solid rgba(255,255,255,0.14);border-radius:12px;}"
            f"QLabel{{background:transparent;color:{MUT};font-size:11px;}}"
            f"QLineEdit{{background:#0d1117;color:{TEXT};border:1px solid rgba(255,255,255,0.12);border-radius:8px;"
            "padding:7px 10px;font-size:13px;}"
            f"QLineEdit:focus{{border-color:{ACC};}}"
            f"QListWidget{{background:transparent;border:none;outline:0;color:{TEXT};font-size:13px;}}"
            "QListWidget::item{padding:7px 10px;border-radius:7px;}"
            "QListWidget::item:hover,QListWidget::item:selected{background:rgba(255,138,30,0.12);color:#e8e9ed;}"
            "QScrollBar:vertical{background:transparent;width:8px;margin:2px;}"
            "QScrollBar::handle:vertical{background:rgba(255,255,255,0.22);border-radius:3px;min-height:30px;}"
            "QScrollBar::handle:vertical:hover{background:rgba(255,138,30,0.6);}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical,QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:none;height:0;}"
            f"QPushButton{{background:transparent;color:{MUT};border:none;font-size:11px;padding:4px 8px;}}"
            f"QPushButton:hover{{color:{ACC};}}")
        lay = QVBoxLayout(self); lay.setContentsMargins(10, 10, 10, 8); lay.setSpacing(8)

        self.search = QLineEdit(); self.search.setPlaceholderText("Rechercher un zaap, une région…")
        self.search.setClearButtonEnabled(True); self.search.textChanged.connect(self._fill)
        lay.addWidget(self.search)

        self.list = QListWidget(); self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(self._pick)
        lay.addWidget(self.list, 1)

        foot = QHBoxLayout(); foot.setContentsMargins(0, 0, 0, 0)
        self.count = QLabel(""); foot.addWidget(self.count); foot.addStretch()
        manage = QPushButton("⭐  Gérer les favoris"); manage.setCursor(Qt.CursorShape.PointingHandCursor)
        manage.clicked.connect(lambda: (self.close(), self.on_manage()))
        foot.addWidget(manage)
        lay.addLayout(foot)
        self.search.installEventFilter(self)
        self._fill()

    def eventFilter(self, obj, ev):
        # Flèches / Entrée dans la barre de recherche pilotent la liste sans quitter le champ.
        if obj is self.search and ev.type() == ev.Type.KeyPress:
            k = ev.key()
            if k in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                n = self.list.count()
                if n:
                    r = self.list.currentRow()
                    self.list.setCurrentRow(max(0, min(n - 1, (r + 1) if k == Qt.Key.Key_Down else (r - 1))))
                return True
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                it = self.list.currentItem() or (self.list.item(0) if self.list.count() else None)
                if it: self._pick(it)
                return True
        return super().eventFilter(obj, ev)

    def _fill(self, *_):
        favs = get_favorites(self.config)
        rows = ordered_zaaps(favs, self.search.text())
        self.list.clear()
        sep_done = False
        for i, (z, is_fav) in enumerate(rows):
            if not is_fav and not sep_done and i > 0 and rows[0][1]:
                sep = QListWidgetItem("— Tous les zaaps —"); sep.setFlags(Qt.ItemFlag.NoItemFlags)
                sep.setForeground(Qt.GlobalColor.gray); self.list.addItem(sep)
            if not is_fav: sep_done = True
            x, y = z["coords"]
            it = QListWidgetItem(f"{'★  ' if is_fav else '     '}{z['name']}      [{x}, {y}]")
            it.setData(Qt.ItemDataRole.UserRole, (z["name"], x, y))
            it.setToolTip(z["region"])
            if is_fav: it.setForeground(self._gold())
            self.list.addItem(it)
        for r in range(self.list.count()):
            if self.list.item(r).data(Qt.ItemDataRole.UserRole): self.list.setCurrentRow(r); break
        self.count.setText(f"{len(rows)} zaap{'s' if len(rows) > 1 else ''}" if rows else "Aucun résultat")

    @staticmethod
    def _gold():
        from PyQt6.QtGui import QColor
        return QColor(GOLD).lighter(125)

    def _pick(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data: return
        self.close(); self.on_pick(*data)

    def popup_at(self, anchor_widget, vertical=False):
        """Ouvre la fenêtre contre `anchor_widget` (à droite si la barre est verticale, sinon dessous ou dessus selon la
        place), sans jamais sortir de l'écran."""
        r = anchor_widget.rect()
        scr = QGuiApplication.screenAt(anchor_widget.mapToGlobal(r.center())) or QGuiApplication.primaryScreen()
        sg = scr.availableGeometry()
        if vertical:
            p = anchor_widget.mapToGlobal(QPoint(r.right() + 8, r.top()))
        else:
            p = anchor_widget.mapToGlobal(QPoint(r.left(), r.bottom() + 8))
            if p.y() + self.HEIGHT > sg.bottom():
                p = anchor_widget.mapToGlobal(QPoint(r.left(), r.top() - self.HEIGHT - 8))
        x = max(sg.left() + 4, min(p.x(), sg.right() - self.WIDTH - 4))
        y = max(sg.top() + 4, min(p.y(), sg.bottom() - self.HEIGHT - 4))
        self.move(x, y); self.show(); self.search.setFocus(); self.activateWindow()
