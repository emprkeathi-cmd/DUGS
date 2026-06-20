"""
home_screen.py — the landing screen: Projects | Tabels tabs, each backed by an
icon-grid file browser with right-click Open/Download/Duplicate/Rename/Delete.
"""
import os
import shutil

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QListWidget,
    QListWidgetItem, QStackedWidget, QInputDialog, QMenu, QMessageBox
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath, QIcon, QPixmap, QAction

from theme import ACCENT
from storage import (
    PROJECTS_DIR, TABELS_DIR, DOWNLOADS, _ensure, _path,
    list_projects, list_tabels, save_project, new_tabel,
)


def file_icon(size=64):
    pm = QPixmap(size, size); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    w, h = size * 0.62, size * 0.8
    x, y = (size - w) / 2, (size - h) / 2
    fold = size * 0.22
    path = QPainterPath()
    path.moveTo(x, y)
    path.lineTo(x + w - fold, y)
    path.lineTo(x + w, y + fold)
    path.lineTo(x + w, y + h)
    path.lineTo(x, y + h)
    path.closeSubpath()
    p.setPen(QPen(QColor(ACCENT), 2)); p.setBrush(QBrush(QColor(20, 28, 34, 200)))
    p.drawPath(path)
    p.setPen(QPen(QColor(ACCENT), 1.5))
    p.drawLine(int(x + w - fold), int(y), int(x + w - fold), int(y + fold))
    p.drawLine(int(x + w - fold), int(y + fold), int(x + w), int(y + fold))
    p.end()
    return QIcon(pm)


class IconBrowser(QWidget):
    """File-manager style grid of icons with right-click menu. Used for both
       Projects and Tabels."""
    def __init__(self, kind, app):
        super().__init__()
        self.kind = kind            # "project" or "tabel"
        self.app = app
        self._icon = file_icon(64)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        self.grid_host = QListWidget()
        self.grid_host.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid_host.setIconSize(QSize(64, 64))
        self.grid_host.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid_host.setSpacing(18)
        self.grid_host.setMovement(QListWidget.Movement.Static)
        self.grid_host.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid_host.customContextMenuRequested.connect(self.menu)
        self.grid_host.itemDoubleClicked.connect(lambda it: self.open(it.text()))
        self.grid_host.setStyleSheet(
            "QListWidget{background:transparent;border:none;}"
            "QListWidget::item{color:#ddd;}"
            f"QListWidget::item:selected{{color:{ACCENT};background:rgba(126,207,255,0.10);border-radius:4px;}}")
        lay.addWidget(self.grid_host)

    def names(self):
        return list_projects() if self.kind == "project" else list_tabels()

    def refresh(self):
        self.grid_host.clear()
        for n in self.names():
            it = QListWidgetItem(self._icon, n)
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            it.setSizeHint(QSize(96, 96))
            self.grid_host.addItem(it)

    def menu(self, pos):
        it = self.grid_host.itemAt(pos)
        if not it: return
        name = it.text()
        m = QMenu(self)
        for label in ("Open", "Download", "Duplicate", "Rename", "Delete"):
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, l=label, n=name: self.action(l, n))
            m.addAction(act)
        m.exec(self.grid_host.mapToGlobal(pos))

    def action(self, label, name):
        d = PROJECTS_DIR if self.kind == "project" else TABELS_DIR
        if label == "Open":
            self.open(name)
        elif label == "Download":
            _ensure(DOWNLOADS)
            shutil.copy(_path(d, name), os.path.join(DOWNLOADS, f"{name}.json"))
            self.app.toast(f"downloaded {name}.json to ~/Downloads")
        elif label == "Duplicate":
            base = f"{name}_copy"; i = 1; cand = base
            while cand in self.names(): i += 1; cand = f"{base}{i}"
            shutil.copy(_path(d, name), _path(d, cand)); self.refresh()
        elif label == "Rename":
            new, ok = QInputDialog.getText(self, "Rename", "New name:", text=name)
            if ok and new.strip() and new.strip() != name:
                os.rename(_path(d, name), _path(d, new.strip())); self.refresh()
        elif label == "Delete":
            if QMessageBox.question(self, "Delete", f"Delete '{name}'?") == QMessageBox.StandardButton.Yes:
                os.remove(_path(d, name)); self.refresh()

    def open(self, name):
        if self.kind == "project": self.app.open_project(name)
        else: self.app.open_tabel(name)


class Home(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        root = QVBoxLayout(self); root.setContentsMargins(24, 18, 24, 24); root.setSpacing(14)

        topbar = QHBoxLayout()
        self.dugs = QLabel("dugs")
        self.dugs.setStyleSheet(f"color:{ACCENT};font-family:monospace;font-size:24px;")
        self.dugs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dugs.mousePressEvent = lambda _e: self.app.go_home()
        topbar.addWidget(self.dugs); topbar.addStretch()
        self.new_btn = QPushButton("+ New")
        self.new_btn.clicked.connect(self.new_item)
        topbar.addWidget(self.new_btn)
        root.addLayout(topbar)

        tabs = QHBoxLayout(); tabs.addStretch()
        self.tab_projects = QPushButton("Projects")
        self.tab_tabels = QPushButton("Tabels")
        for t in (self.tab_projects, self.tab_tabels):
            t.setFixedWidth(260); t.setStyleSheet(self._tab_style(False))
            t.setText("  " + t.text())
        self.tab_projects.setText("Projects"); self.tab_tabels.setText("Tabels")
        self.tab_projects.clicked.connect(lambda: self.select("project"))
        self.tab_tabels.clicked.connect(lambda: self.select("tabel"))
        tabs.addWidget(self.tab_projects); tabs.addSpacing(12); tabs.addWidget(self.tab_tabels)
        tabs.addStretch()
        root.addLayout(tabs)

        self.browsers = QStackedWidget()
        self.proj_browser = IconBrowser("project", app)
        self.tabel_browser = IconBrowser("tabel", app)
        self.browsers.addWidget(self.proj_browser)
        self.browsers.addWidget(self.tabel_browser)
        root.addWidget(self.browsers, 1)

        self.section = "project"

    def _tab_style(self, active):
        if active:
            return (f"QPushButton{{background:rgba(126,207,255,0.18);color:{ACCENT};"
                    f"border:1px solid {ACCENT};border-radius:4px;padding:10px;text-align:left;"
                    f"font-family:monospace;font-size:14px;}}")
        return ("QPushButton{background:transparent;color:#aaa;"
                "border:1px solid #555;border-radius:4px;padding:10px;text-align:left;"
                "font-family:monospace;font-size:14px;}"
                f"QPushButton:hover{{color:{ACCENT};border-color:{ACCENT};}}")

    def select(self, section):
        self.section = section
        self.tab_projects.setStyleSheet(self._tab_style(section == "project"))
        self.tab_tabels.setStyleSheet(self._tab_style(section == "tabel"))
        if section == "project":
            self.browsers.setCurrentWidget(self.proj_browser); self.proj_browser.refresh()
            self.new_btn.setText("+ New Project")
        else:
            self.browsers.setCurrentWidget(self.tabel_browser); self.tabel_browser.refresh()
            self.new_btn.setText("+ New Tabel")

    def refresh(self):
        self.select(self.section)

    def new_item(self):
        if self.section == "project":
            name, ok = QInputDialog.getText(self, "New Project", "Project name:")
            if ok and name.strip():
                name = name.strip()
                save_project(name, {"name": name, "nodes": [], "connections": {}})
                self.app.open_project(name)
        else:
            name, ok = QInputDialog.getText(self, "New Tabel", "Tabel name:")
            if ok and name.strip():
                name = name.strip(); new_tabel(name); self.app.open_tabel(name)
