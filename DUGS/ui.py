"""
ui.py - the dugs face (v3): two-tab Home (Projects | Tabels), icon-grid file
managers with right-click menus, the editor, and the Tabel spreadsheet editor.

Run:  Terminal 1: python3 api.py    Terminal 2: python3 ui.py
(Hyprland fallback: GDK_BACKEND=x11 python3 ui.py)
"""
from __future__ import annotations
import os, sys, json, shutil, urllib.request

from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QTextEdit, QStackedWidget, QLineEdit,
    QScrollArea, QInputDialog, QPlainTextEdit, QMenu, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QSize
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QPainterPath, QFont, QKeySequence, QShortcut,
    QPixmap, QIcon, QAction
)

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(HERE, "projects")
TABELS_DIR = os.path.join(HERE, "tabels")
DOWNLOADS = os.path.expanduser("~/Downloads")
API = "http://127.0.0.1:5800"
ACCENT = "#7ecfff"
DIM = "#888888"
NODE_SIZE = 84

# --------------------------------------------------------------------------- API
def api_get(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=10) as r:
        return json.loads(r.read().decode())

def api_post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{API}{path}", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

# ------------------------------------------------------------------- file helpers
def _ensure(d): os.makedirs(d, exist_ok=True)
def _list(d):
    _ensure(d); return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))
def _path(d, name): return os.path.join(d, f"{name}.json")
def _load(d, name):
    with open(_path(d, name)) as f: return json.load(f)
def _save(d, name, data):
    _ensure(d)
    with open(_path(d, name), "w") as f: json.dump(data, f, indent=2)

def list_projects(): return _list(PROJECTS_DIR)
def load_project(n): return _load(PROJECTS_DIR, n)
def save_project(n, d): _save(PROJECTS_DIR, n, d)

def list_tabels(): return _list(TABELS_DIR)
def load_tabel(n): return _load(TABELS_DIR, n)
def save_tabel(n, d):
    for i, row in enumerate(d.get("rows", []), start=1): row["id"] = i
    _save(TABELS_DIR, n, d)
def new_tabel(n): save_tabel(n, {"name": n, "columns": ["column1"], "rows": []})


# ----------------------------------------------------------------- file icon draw
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
    # folded corner
    p.setPen(QPen(QColor(ACCENT), 1.5))
    p.drawLine(int(x + w - fold), int(y), int(x + w - fold), int(y + fold))
    p.drawLine(int(x + w - fold), int(y + fold), int(x + w), int(y + fold))
    p.end()
    return QIcon(pm)


# ============================================================== ICON-GRID browser
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


# ===================================================================== HOME screen
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

        # two tabs, centered
        tabs = QHBoxLayout(); tabs.addStretch()
        self.tab_projects = QPushButton("Projects")
        self.tab_tabels = QPushButton("Tabels")
        for t in (self.tab_projects, self.tab_tabels):
            t.setFixedWidth(260); t.setStyleSheet(self._tab_style(False))
            t.setText("  " + t.text())  # text nudged left
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


# ============================================================== TABEL editor screen
class TabelEditor(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app; self.current = None
        root = QVBoxLayout(self); root.setContentsMargins(16, 12, 16, 16); root.setSpacing(8)

        bar = QHBoxLayout()
        dugs = QLabel("dugs"); dugs.setStyleSheet(f"color:{ACCENT};font-family:monospace;font-size:20px;")
        dugs.setCursor(Qt.CursorShape.PointingHandCursor)
        dugs.mousePressEvent = lambda _e: self.app.go_home()
        bar.addWidget(dugs)
        self.title = QLabel("-"); self.title.setStyleSheet(f"color:{ACCENT};font-family:monospace;font-size:14px;")
        bar.addSpacing(16); bar.addWidget(self.title); bar.addStretch()
        add_col = QPushButton("+ Column"); add_col.clicked.connect(self.add_column)
        add_row = QPushButton("+ Row"); add_row.clicked.connect(self.add_row)
        save = QPushButton("Save"); save.clicked.connect(self.save)
        for b in (add_col, add_row, save): bar.addWidget(b)
        root.addLayout(bar)

        self.table = QTableWidget()
        self.table.setStyleSheet(
            "QTableWidget{background:rgba(12,12,12,0.55);color:#eee;gridline-color:#444;"
            "font-family:monospace;border:1px solid #444;}"
            f"QHeaderView::section{{background:rgba(20,20,20,0.8);color:{ACCENT};"
            "border:1px solid #444;padding:4px;font-family:monospace;}}"
            "QTableWidget::item:selected{background:rgba(126,207,255,0.18);}")
        self.table.itemChanged.connect(self._cell_changed)
        root.addWidget(self.table, 1)

        self.hint = QLabel("double-click a header to rename a column · right-click a row number to delete")
        self.hint.setStyleSheet(f"color:{DIM};font-family:monospace;font-size:9px;")
        root.addWidget(self.hint)

        self.table.horizontalHeader().sectionDoubleClicked.connect(self.rename_column)
        self.table.verticalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.verticalHeader().customContextMenuRequested.connect(self.row_menu)
        self._loading = False

    def open(self, name):
        self.current = name; self.title.setText(name)
        self.data = load_tabel(name)
        self.rebuild()

    def rebuild(self):
        self._loading = True
        cols = self.data.get("columns", [])
        rows = self.data.get("rows", [])
        self.table.clear()
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setRowCount(len(rows))
        # id shown as the vertical header (row number)
        self.table.setVerticalHeaderLabels([str(r.get("id", i + 1)) for i, r in enumerate(rows)])
        for ri, row in enumerate(rows):
            for ci, c in enumerate(cols):
                val = row.get(c)
                self.table.setItem(ri, ci, QTableWidgetItem("" if val is None else str(val)))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._loading = False

    def _cell_changed(self, item):
        if self._loading: return
        cols = self.data["columns"]
        ri, ci = item.row(), item.column()
        if ri < len(self.data["rows"]) and ci < len(cols):
            self.data["rows"][ri][cols[ci]] = item.text()

    def add_column(self):
        name, ok = QInputDialog.getText(self, "New Column", "Column name:")
        if ok and name.strip():
            name = name.strip()
            if name in self.data["columns"] or name == "id": return
            self.data["columns"].append(name)
            for r in self.data["rows"]: r[name] = ""
            self.rebuild()

    def add_row(self):
        row = {"id": len(self.data["rows"]) + 1}
        for c in self.data["columns"]: row[c] = ""
        self.data["rows"].append(row); self.rebuild()

    def rename_column(self, idx):
        cols = self.data["columns"]
        if idx >= len(cols): return
        old = cols[idx]
        new, ok = QInputDialog.getText(self, "Rename Column", "Name:", text=old)
        if ok and new.strip() and new.strip() != old:
            new = new.strip()
            cols[idx] = new
            for r in self.data["rows"]:
                r[new] = r.pop(old, "")
            self.rebuild()

    def row_menu(self, pos):
        ri = self.table.verticalHeader().logicalIndexAt(pos)
        if ri < 0: return
        m = QMenu(self)
        act = QAction("Delete row", self)
        act.triggered.connect(lambda: self._del_row(ri))
        m.addAction(act)
        m.exec(self.table.verticalHeader().mapToGlobal(pos))

    def _del_row(self, ri):
        if 0 <= ri < len(self.data["rows"]):
            del self.data["rows"][ri]; self.rebuild()

    def save(self):
        if not self.current: return
        save_tabel(self.current, self.data)
        self.open(self.current)  # reload to refresh ids
        self.app.toast(f"saved Tabel {self.current}")


# ============================================================ (editor canvas below)
class CanvasNode:
    _counter = 0
    def __init__(self, type_id, title, inputs, outputs, x, y, name=None, params=None):
        CanvasNode._counter += 1
        self.id = CanvasNode._counter
        self.type_id = type_id; self.title = title
        self.inputs = inputs; self.outputs = outputs
        self.name = name or f"{title} {self.id}"
        self.x = x; self.y = y; self.s = NODE_SIZE
        self.params = params or {}
    def rect(self): return QRectF(self.x, self.y, self.s, self.s)
    def in_port(self): return QPointF(self.x, self.y + self.s/2)
    def del_rect(self): return QRectF(self.x + self.s - 18, self.y + 2, 16, 16)
    def out_port(self): return QPointF(self.x + self.s, self.y + self.s/2)


class Canvas(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setMinimumSize(500, 500)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.nodes = []; self.connections = []
        self.dragging = None; self.drag_off = QPointF()
        self.wire_from = None; self.selected = None; self.selected_conn = None
        self._mouse = QPointF(); self.hovered = None
        self.offset = QPointF(0, 0)        # pan offset
        self.panning = False; self.pan_start = QPointF()
        self.running_node = None           # node name currently "running" (animation)
        self.ran_nodes = set()             # names that finished (green-ish flash)
        self.setMouseTracking(True)

    # convert a screen position to world (canvas) coordinates
    def world(self, pos):
        return QPointF(pos.x() - self.offset.x(), pos.y() - self.offset.y())

    def clear(self):
        self.nodes.clear(); self.connections.clear()
        self.selected = None; self.selected_conn = None
        self.running_node = None; self.ran_nodes.clear(); self.update()

    def add_node(self, meta):
        n = CanvasNode(meta["type"], meta["title"], meta["inputs"], meta["outputs"],
                       60 + (len(self.nodes)*24) % 280, 60 + (len(self.nodes)*30) % 280)
        for p in meta.get("params", []): n.params[p["key"]] = p.get("default")
        self.nodes.append(n); self.select_node(n); self.update(); return n

    def select_node(self, n):
        self.selected = n; self.selected_conn = None; self.editor.show_node_settings(n)

    def node_at(self, wpos):
        for n in reversed(self.nodes):
            if n.rect().contains(wpos): return n
        return None

    def port_at(self, wpos):
        r = 11
        for n in self.nodes:
            if n.outputs > 0 and (wpos - n.out_port()).manhattanLength() < r: return ("out", n)
            if n.inputs > 0 and (wpos - n.in_port()).manhattanLength() < r: return ("in", n)
        return None

    def conn_at(self, wpos):
        for i, (src, oi, dst, ii) in enumerate(self.connections):
            a, b = src.out_port(), dst.in_port()
            mid = QPointF((a.x()+b.x())/2, (a.y()+b.y())/2)
            if (wpos - mid).manhattanLength() < 18: return i
        return None

    def run_rect(self, n):
        # play button: left side, mirrors the delete x on the right
        return QRectF(n.x + 2, n.y + 2, 16, 16)

    def delete_selected(self):
        if self.selected is not None:
            n = self.selected
            self.connections = [c for c in self.connections if c[0] is not n and c[2] is not n]
            self.nodes = [x for x in self.nodes if x is not n]
            self.selected = None; self.editor.show_node_settings(None)
        elif self.selected_conn is not None:
            del self.connections[self.selected_conn]; self.selected_conn = None
        self.editor.refresh_json(); self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self.offset)   # apply pan
        # connections
        for i, (src, oi, dst, ii) in enumerate(self.connections):
            a, b = src.out_port(), dst.in_port(); sel = (i == self.selected_conn)
            p.setPen(QPen(QColor("#ff6b6b" if sel else ACCENT), 2.2 if sel else 1.6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath(a); cx = (a.x()+b.x())/2
            path.cubicTo(QPointF(cx, a.y()), QPointF(cx, b.y()), b); p.drawPath(path)
        if self.wire_from:
            n, _ = self.wire_from
            p.setPen(QPen(QColor(ACCENT), 1.2, Qt.PenStyle.DashLine))
            p.drawLine(n.out_port(), self.world(self._mouse))
        for n in self.nodes:
            is_sel = (n is self.selected)
            running = (n.name == self.running_node)
            ran = (n.name in self.ran_nodes)
            # border color: running=yellow, ran=green, selected=accent, else white
            if running: border = QColor("#ffd166")
            elif ran:   border = QColor("#7CFC9B")
            elif is_sel: border = QColor(ACCENT)
            else: border = QColor("#ffffff")
            p.setPen(QPen(border, 2.4 if (running or is_sel) else 1))
            fill = QColor(40, 38, 15, 235) if running else QColor(15, 15, 15, 235)
            p.setBrush(QBrush(fill)); p.drawRoundedRect(n.rect(), 4, 4)
            p.setPen(QColor("#ffffff")); f = QFont("monospace"); f.setPointSize(8); p.setFont(f)
            p.drawText(n.rect(), Qt.AlignmentFlag.AlignCenter, n.title)
            p.setPen(QColor(ACCENT)); f2 = QFont("monospace"); f2.setPointSize(6); p.setFont(f2)
            p.drawText(QRectF(n.x, n.y+n.s-16, n.s, 14), Qt.AlignmentFlag.AlignCenter, n.type_id)
            p.setBrush(QBrush(QColor(ACCENT))); p.setPen(QPen(QColor(ACCENT), 1))
            if n.inputs > 0: p.drawEllipse(n.in_port(), 5, 5)
            if n.outputs > 0: p.drawEllipse(n.out_port(), 5, 5)
            if n is self.hovered:
                # delete x (right)
                dr = n.del_rect()
                p.setPen(QPen(QColor('#ff6b6b'), 1)); p.setBrush(QBrush(QColor(40,15,15,230)))
                p.drawRoundedRect(dr, 3, 3)
                p.setPen(QColor('#ff6b6b')); fx = QFont('monospace'); fx.setPointSize(9); p.setFont(fx)
                p.drawText(dr, Qt.AlignmentFlag.AlignCenter, 'x')
                # run play (left)
                rr = self.run_rect(n)
                p.setPen(QPen(QColor('#7CFC9B'), 1)); p.setBrush(QBrush(QColor(15,40,20,230)))
                p.drawRoundedRect(rr, 3, 3)
                p.setPen(QColor('#7CFC9B'))
                tri = QPainterPath()
                tri.moveTo(rr.x()+5, rr.y()+4); tri.lineTo(rr.x()+12, rr.y()+8)
                tri.lineTo(rr.x()+5, rr.y()+12); tri.closeSubpath()
                p.setBrush(QBrush(QColor('#7CFC9B'))); p.drawPath(tri)

    def mousePressEvent(self, e):
        self.setFocus()
        spos = QPointF(e.position()); wpos = self.world(spos)
        # middle mouse => pan
        if e.button() == Qt.MouseButton.MiddleButton:
            self.panning = True; self.pan_start = spos; return
        # hovered node buttons (run / delete)
        for n in self.nodes:
            if n is self.hovered and self.run_rect(n).contains(wpos):
                self.editor.run_from(n.name); return
            if n is self.hovered and n.del_rect().contains(wpos):
                self.connections = [c for c in self.connections if c[0] is not n and c[2] is not n]
                self.nodes = [x for x in self.nodes if x is not n]
                if self.selected is n: self.selected = None; self.editor.show_node_settings(None)
                self.editor.refresh_json(); self.update(); return
        hit = self.port_at(wpos)
        if hit and hit[0] == "out":
            self.wire_from = (hit[1], 0); self._mouse = spos; return
        n = self.node_at(wpos)
        if n:
            self.select_node(n); self.dragging = n
            self.drag_off = wpos - QPointF(n.x, n.y); self.update(); return
        ci = self.conn_at(wpos)
        if ci is not None:
            self.selected = None; self.selected_conn = ci
            self.editor.show_node_settings(None); self.update(); return
        self.selected = None; self.selected_conn = None
        self.editor.show_node_settings(None); self.update()

    def mouseMoveEvent(self, e):
        spos = QPointF(e.position()); self._mouse = spos; wpos = self.world(spos)
        if self.panning:
            d = spos - self.pan_start; self.offset += d; self.pan_start = spos; self.update(); return
        new_hover = self.node_at(wpos)
        if new_hover is not self.hovered: self.hovered = new_hover; self.update()
        if self.dragging:
            self.dragging.x = (wpos - self.drag_off).x()
            self.dragging.y = (wpos - self.drag_off).y(); self.update()
        elif self.wire_from: self.update()

    def mouseReleaseEvent(self, e):
        spos = QPointF(e.position()); wpos = self.world(spos)
        if e.button() == Qt.MouseButton.MiddleButton:
            self.panning = False; return
        if self.wire_from:
            hit = self.port_at(wpos)
            if hit and hit[0] == "in" and hit[1] is not self.wire_from[0]:
                self.connections.append((self.wire_from[0], 0, hit[1], 0)); self.editor.refresh_json()
            self.wire_from = None; self.update()
        self.dragging = None

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace): self.delete_selected()

    def to_workflow(self, name="untitled"):
        nodes = [{"name": n.name, "type": n.type_id, "params": n.params,
                  "_x": n.x, "_y": n.y} for n in self.nodes]
        conns = {}
        for src, oi, dst, ii in self.connections:
            conns.setdefault(src.name, []).append({"to": dst.name, "out": oi, "in": ii})
        return {"name": name, "nodes": nodes, "connections": conns}

    def load_workflow(self, wf, meta_by_type):
        self.clear(); by_name = {}
        for nspec in wf.get("nodes", []):
            meta = meta_by_type.get(nspec["type"], {"title": nspec["type"], "inputs": 1, "outputs": 1})
            n = CanvasNode(nspec["type"], meta.get("title", nspec["type"]),
                           meta.get("inputs", 1), meta.get("outputs", 1),
                           nspec.get("_x", 80), nspec.get("_y", 80),
                           name=nspec["name"], params=nspec.get("params", {}))
            self.nodes.append(n); by_name[n.name] = n
        for src_name, links in wf.get("connections", {}).items():
            for link in links:
                src = by_name.get(src_name); dst = by_name.get(link["to"])
                if src and dst:
                    self.connections.append((src, link.get("out", 0), dst, link.get("in", 0)))
        self.update()

class Editor(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app; self.current_project = None; self.meta_by_type = {}
        root = QHBoxLayout(self); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(8)

        # LEFT column: dugs(home) + settings + other projects + results
        right = QVBoxLayout(); right.setSpacing(6)
        home = QLabel("dugs")
        home.setStyleSheet(f"color:{ACCENT}; font-family:monospace; font-size:20px;")
        home.setCursor(Qt.CursorShape.PointingHandCursor)
        home.mousePressEvent = lambda _e: self.app.go_home()
        right.addWidget(home)
        right.addWidget(self._tag("SETTINGS"))
        self.settings_area = QScrollArea(); self.settings_area.setWidgetResizable(True); self.settings_area.setFixedWidth(250)
        self.settings_host = QWidget(); self.settings_layout = QVBoxLayout(self.settings_host)
        self.settings_layout.addStretch(); self.settings_area.setWidget(self.settings_host)
        right.addWidget(self.settings_area, 2)
        right.addWidget(self._tag("OTHER PROJECTS"))
        self.other_projects = QListWidget(); self.other_projects.setFixedWidth(250)
        self.other_projects.itemClicked.connect(self.switch_project)
        right.addWidget(self.other_projects, 1)
        self.results = QTextEdit(); self.results.setReadOnly(True); self.results.setFixedWidth(250)
        self.results.setStyleSheet("background: rgba(10,10,10,0.5); color:#ddd; font-family:monospace; font-size:9px; border:1px solid #444;")
        right.addWidget(self.results, 1)

        # CENTER
        center = QVBoxLayout(); center.setSpacing(6)
        bar = QHBoxLayout()
        self.proj_label = QLabel("-"); self.proj_label.setStyleSheet(f"color:{ACCENT}; font-family:monospace; font-size:14px;")
        bar.addWidget(self.proj_label); bar.addStretch()
        run_btn = QPushButton("Run"); run_btn.clicked.connect(self.run)
        save_btn = QPushButton("Save"); save_btn.clicked.connect(self.save)
        for b in (save_btn, run_btn): bar.addWidget(b)
        center.addLayout(bar)
        self.canvas = Canvas(self); center.addWidget(self.canvas, 1)

        # RIGHT column: palette + json
        left = QVBoxLayout(); left.setSpacing(6)
        left.addWidget(self._tag("NODES"))
        self.palette_search = QLineEdit(); self.palette_search.setFixedWidth(190)
        self.palette_search.setPlaceholderText("search nodes...")
        self.palette_search.textChanged.connect(self.filter_palette)
        left.addWidget(self.palette_search)
        self.palette = QListWidget(); self.palette.setFixedWidth(190)
        self.palette.itemClicked.connect(self.drop_node)
        left.addWidget(self.palette, 2)
        left.addWidget(self._tag("JSON"))
        self.json_view = QTextEdit(); self.json_view.setReadOnly(True); self.json_view.setFixedWidth(190)
        self.json_view.setStyleSheet("background: rgba(10,10,10,0.5); color:#9fb; font-family:monospace; font-size:9px; border:1px solid #444;")
        left.addWidget(self.json_view, 1)

        # SWAPPED: settings/projects on LEFT, palette/json on RIGHT
        root.addLayout(right); root.addLayout(center, 1); root.addLayout(left)
        QShortcut(QKeySequence("Delete"), self, lambda: self.canvas.delete_selected())

    def _tag(self, text):
        l = QLabel(text); l.setStyleSheet("color:#888; font-family:monospace; font-size:9px;"); return l

    def filter_palette(self, text):
        text = text.lower().strip()
        for i in range(self.palette.count()):
            it = self.palette.item(i)
            nd = it.data(Qt.ItemDataRole.UserRole) or {}
            hay = (it.text() + " " + nd.get("type", "")).lower()
            it.setHidden(text not in hay)

    def load_palette(self):
        self.palette.clear(); self.meta_by_type.clear()
        try:
            data = api_get("/nodes")
        except Exception as e:
            self.palette.addItem(QListWidgetItem("[API offline]"))
            self.results.setText(f"Can't reach API at {API}\nStart it: python3 api.py\n\n{e}"); return
        for nd in data["nodes"]:
            it = QListWidgetItem(f"{nd['title']}"); it.setData(Qt.ItemDataRole.UserRole, nd)
            self.palette.addItem(it); self.meta_by_type[nd["type"]] = nd

    def open_project(self, name):
        self.current_project = name; self.proj_label.setText(name); self.load_palette()
        try: wf = load_project(name)
        except Exception: wf = {"name": name, "nodes": [], "connections": {}}
        self.canvas.load_workflow(wf, self.meta_by_type)
        self.refresh_other_projects(); self.refresh_json(); self.show_node_settings(None)

    def refresh_other_projects(self):
        self.other_projects.clear()
        for p in list_projects():
            if p == self.current_project: continue
            self.other_projects.addItem(QListWidgetItem(p))

    def switch_project(self, item):
        self.save(); self.open_project(item.text())

    def drop_node(self, item):
        nd = item.data(Qt.ItemDataRole.UserRole)
        if nd: self.canvas.add_node(nd); self.refresh_json()

    def refresh_json(self):
        wf = self.canvas.to_workflow(self.current_project or "untitled")
        self.json_view.setText(json.dumps(wf, indent=2))

    def show_node_settings(self, node):
        # clear EVERYTHING (widgets AND spacers) so nothing lingers
        while self.settings_layout.count():
            it = self.settings_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None); w.deleteLater()
        if node is None:
            hint = QLabel("Select a node to edit its settings."); hint.setWordWrap(True)
            hint.setStyleSheet("color:#777; font-family:monospace;")
            self.settings_layout.addWidget(hint); self.settings_layout.addStretch(); return

        meta = self.meta_by_type.get(node.type_id, {})
        params_spec = meta.get("params", [])

        head = QLabel(node.name); head.setStyleSheet(f"color:{ACCENT}; font-family:monospace; font-size:13px;")
        self.settings_layout.addWidget(head)
        ttag = QLabel(node.type_id); ttag.setStyleSheet("color:#666; font-family:monospace; font-size:9px;")
        self.settings_layout.addWidget(ttag)

        self.settings_layout.addWidget(self._tag("name"))
        name_edit = QLineEdit(node.name)
        def set_name():
            node.name = name_edit.text() or node.name; self.refresh_json()
        name_edit.editingFinished.connect(set_name); self.settings_layout.addWidget(name_edit)

        if not params_spec:
            note = QLabel("(this node has no settings)")
            note.setStyleSheet("color:#666; font-family:monospace; font-size:10px;")
            self.settings_layout.addWidget(note)

        for p in params_spec:
            key = p["key"]; ptype = p.get("type", "text")
            # ensure the node actually has this param seeded (fixes loaded-from-disk nodes)
            if key not in node.params:
                node.params[key] = p.get("default")
            cur = node.params.get(key, p.get("default"))
            self.settings_layout.addWidget(self._tag(p.get("label", key)))
            if ptype == "select":
                combo = QComboBox()
                opts = [str(o) for o in p.get("options", [])]
                combo.addItems(opts)
                if cur is not None and str(cur) in opts:
                    combo.setCurrentText(str(cur))
                def mksel(k, widget):
                    def s(): node.params[k] = widget.currentText(); self.refresh_json()
                    return s
                combo.currentTextChanged.connect(mksel(key, combo))
                self.settings_layout.addWidget(combo)
            elif ptype == "tabel":
                combo = QComboBox()
                tabels = list_tabels()
                combo.addItem("")  # allow blank
                combo.addItems(tabels)
                if cur and str(cur) in tabels:
                    combo.setCurrentText(str(cur))
                def mktab(k, widget):
                    def s(): node.params[k] = widget.currentText() or None; self.refresh_json()
                    return s
                combo.currentTextChanged.connect(mktab(key, combo))
                self.settings_layout.addWidget(combo)
            elif ptype == "bool":
                chk = QCheckBox()
                chk.setChecked(bool(cur))
                def mkbool(k, widget):
                    def s(): node.params[k] = widget.isChecked(); self.refresh_json()
                    return s
                chk.stateChanged.connect(mkbool(key, chk))
                self.settings_layout.addWidget(chk)
            elif ptype == "json":
                box = QPlainTextEdit(json.dumps(cur) if cur is not None else ""); box.setFixedHeight(60)
                def mk(k, widget):
                    def s():
                        txt = widget.toPlainText().strip()
                        try: node.params[k] = json.loads(txt) if txt else None
                        except Exception: node.params[k] = txt
                        self.refresh_json()
                    return s
                box.textChanged.connect(mk(key, box)); self.settings_layout.addWidget(box)
            elif ptype == "multiline":
                box = QPlainTextEdit(str(cur) if cur is not None else ""); box.setFixedHeight(90)
                def mk2(k, widget):
                    def s(): node.params[k] = widget.toPlainText(); self.refresh_json()
                    return s
                box.textChanged.connect(mk2(key, box)); self.settings_layout.addWidget(box)
            else:
                edit = QLineEdit("" if cur is None else str(cur))
                def mk3(k, widget, is_num):
                    def s():
                        v = widget.text()
                        if is_num:
                            try: v = float(v) if "." in v else int(v)
                            except Exception: pass
                        node.params[k] = v; self.refresh_json()
                    return s
                edit.editingFinished.connect(mk3(key, edit, ptype == "number"))
                self.settings_layout.addWidget(edit)
        self.settings_layout.addStretch()

    def save(self):
        if not self.current_project: return
        save_project(self.current_project, self.canvas.to_workflow(self.current_project))
        self.results.setText(f"saved: {self.current_project}")

    def _exec_order(self, wf):
        # topological-ish order: start nodes first, then follow connections (BFS)
        conns = wf.get("connections", {})
        has_incoming = set()
        for src, links in conns.items():
            for l in links: has_incoming.add(l["to"])
        names = [n["name"] for n in wf["nodes"]]
        starts = [n for n in names if n not in has_incoming]
        order = []; queue = list(starts); seen = set()
        while queue:
            cur = queue.pop(0)
            if cur in seen: continue
            seen.add(cur); order.append(cur)
            for l in conns.get(cur, []):
                if l["to"] not in seen: queue.append(l["to"])
        # add any stragglers
        for n in names:
            if n not in seen: order.append(n)
        return order

    def _animate_run(self, wf, res):
        from PyQt6.QtCore import QTimer
        self.canvas.ran_nodes.clear(); self.canvas.running_node = None; self.canvas.update()
        order = self._exec_order(wf)
        self._anim_i = 0
        def step():
            if self._anim_i >= len(order):
                self.canvas.running_node = None; self.canvas.update()
                self.results.setText(json.dumps(res, indent=2)); return
            name = order[self._anim_i]
            if self.canvas.running_node:
                self.canvas.ran_nodes.add(self.canvas.running_node)
            self.canvas.running_node = name; self.canvas.update()
            self._anim_i += 1
            QTimer.singleShot(380, step)
        step()

    def run(self):
        wf = self.canvas.to_workflow(self.current_project or "untitled")
        if not wf["nodes"]:
            self.results.setText("Canvas empty - drop some nodes first."); return
        try: res = api_post("/run", wf)
        except Exception as e: self.results.setText(f"Run failed:\n{e}"); return
        self._animate_run(wf, res)

    def run_from(self, node_name):
        # run the whole workflow but visually start the animation from this node
        wf = self.canvas.to_workflow(self.current_project or "untitled")
        if not wf["nodes"]:
            self.results.setText("Canvas empty."); return
        try: res = api_post("/run", wf)
        except Exception as e: self.results.setText(f"Run failed:\n{e}"); return
        # flash just this node then show results
        from PyQt6.QtCore import QTimer
        self.canvas.ran_nodes.clear()
        self.canvas.running_node = node_name; self.canvas.update()
        def done():
            self.canvas.ran_nodes.add(node_name); self.canvas.running_node = None
            self.canvas.update()
            self.results.setText(json.dumps(res.get("results", {}).get(node_name, res), indent=2))
        QTimer.singleShot(500, done)


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("dugs"); self.resize(1200, 760)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.stack = QStackedWidget()
        self.home = Home(self); self.editor = Editor(self); self.tabel = TabelEditor(self)
        for w in (self.home, self.editor, self.tabel): self.stack.addWidget(w)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.addWidget(self.stack)
        self.setStyleSheet(f"""
            QWidget {{ background: transparent; color:#fff; font-family:monospace; }}
            QPushButton {{ background: transparent; color:{ACCENT}; border:1px solid {ACCENT}; border-radius:3px; padding:5px 10px; }}
            QPushButton:hover {{ background: rgba(126,207,255,0.12); }}
            QListWidget {{ background: rgba(15,15,15,0.4); border:1px solid #444; border-radius:3px; }}
            QListWidget::item {{ padding:6px; }}
            QListWidget::item:hover {{ color:{ACCENT}; }}
            QListWidget::item:selected {{ color:{ACCENT}; background: rgba(126,207,255,0.10); }}
            QLineEdit, QPlainTextEdit {{ background: rgba(20,20,20,0.6); color:#fff; border:1px solid #555; border-radius:3px; padding:3px; font-family:monospace; }}
            QComboBox {{ background: rgba(20,20,20,0.6); color:#fff; border:1px solid #555; border-radius:3px; padding:3px 6px; font-family:monospace; }}
            QComboBox:hover {{ border:1px solid {ACCENT}; }}
            QComboBox QAbstractItemView {{ background:#141414; color:#eee; border:1px solid {ACCENT}; selection-background-color: rgba(126,207,255,0.20); selection-color:{ACCENT}; }}
            QCheckBox {{ color:#fff; font-family:monospace; }}
            QCheckBox::indicator {{ width:16px; height:16px; border:1px solid #555; border-radius:3px; background: rgba(20,20,20,0.6); }}
            QCheckBox::indicator:checked {{ background:{ACCENT}; border:1px solid {ACCENT}; }}
            QMenu {{ background: #141414; color:#eee; border:1px solid {ACCENT}; font-family:monospace; }}
            QMenu::item:selected {{ background: rgba(126,207,255,0.20); color:{ACCENT}; }}
        """)
        self.go_home()

    def toast(self, msg):
        # lightweight status: reuse editor results if visible, else print
        try: self.editor.results.setText(msg)
        except Exception: pass
        print("  dugs:", msg)

    def go_home(self):
        self.home.refresh(); self.stack.setCurrentWidget(self.home)

    def open_project(self, name):
        self.editor.open_project(name); self.stack.setCurrentWidget(self.editor)

    def open_tabel(self, name):
        self.tabel.open(name); self.stack.setCurrentWidget(self.tabel)


if __name__ == "__main__":
    _ensure(PROJECTS_DIR); _ensure(TABELS_DIR)
    app = QApplication(sys.argv)
    w = App(); w.show()
    sys.exit(app.exec())
