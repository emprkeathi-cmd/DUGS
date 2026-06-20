"""
editor.py — the workflow editor screen: palette, canvas, JSON preview,
run/save controls. Settings-panel rendering lives in editor_settings.py
(mixed in here) since that part changes most often.
"""
import json

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QTextEdit, QScrollArea, QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut

from theme import ACCENT, API
from api_client import api_get, api_post
from storage import list_projects, load_project, save_project
from canvas import Canvas
from editor_settings import SettingsPanelMixin


class Editor(QWidget, SettingsPanelMixin):
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

        json_header = QHBoxLayout()
        json_header.addWidget(self._tag("JSON"))
        json_header.addStretch()
        copy_btn = QPushButton("⎘ copy"); copy_btn.setFixedSize(54, 18)
        copy_btn.setStyleSheet("font-size:9px; padding:0px 4px; border:1px solid #444; color:#888; border-radius:3px;")
        copy_btn.clicked.connect(self._copy_json)
        json_header.addWidget(copy_btn)
        left.addLayout(json_header)
        self.json_view = QTextEdit(); self.json_view.setReadOnly(True); self.json_view.setFixedWidth(190)
        self.json_view.setStyleSheet("background: rgba(10,10,10,0.5); color:#9fb; font-family:monospace; font-size:9px; border:1px solid #444;")
        self.json_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left.addWidget(self.json_view, 1)

        root.addLayout(right); root.addLayout(center, 1); root.addLayout(left)
        QShortcut(QKeySequence("Delete"), self, lambda: self.canvas.delete_selected())

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

    def _copy_json(self):
        QApplication.clipboard().setText(self.json_view.toPlainText())
        btn = self.sender()
        if btn:
            btn.setText("✓ copied"); btn.setStyleSheet(f"font-size:9px; padding:0px 4px; border:1px solid {ACCENT}; color:{ACCENT}; border-radius:3px;")
            QTimer.singleShot(1200, lambda: (btn.setText("⎘ copy"), btn.setStyleSheet("font-size:9px; padding:0px 4px; border:1px solid #444; color:#888; border-radius:3px;")))

    def save(self):
        if not self.current_project: return
        wf = self.canvas.to_workflow(self.current_project)
        save_project(self.current_project, wf)
        has_webhook = any(n.get("type") == "webhook.trigger" for n in wf.get("nodes", []))
        if has_webhook:
            try:
                api_post("/webhooks/register", wf)
                self.results.setText(f"saved: {self.current_project}  (webhook registered)")
            except Exception as e:
                self.results.setText(f"saved: {self.current_project}  (webhook register failed: {e})")
        else:
            self.results.setText(f"saved: {self.current_project}")

    def _exec_order(self, wf):
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
        for n in names:
            if n not in seen: order.append(n)
        return order

    def _animate_run(self, wf, res):
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
        wf = self.canvas.to_workflow(self.current_project or "untitled")
        if not wf["nodes"]:
            self.results.setText("Canvas empty."); return
        try: res = api_post("/run", wf)
        except Exception as e: self.results.setText(f"Run failed:\n{e}"); return
        self.canvas.ran_nodes.clear()
        self.canvas.running_node = node_name; self.canvas.update()
        def done():
            self.canvas.ran_nodes.add(node_name); self.canvas.running_node = None
            self.canvas.update()
            self.results.setText(json.dumps(res.get("results", {}).get(node_name, res), indent=2))
        QTimer.singleShot(500, done)
