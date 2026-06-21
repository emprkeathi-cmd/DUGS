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
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject, QSize
from PyQt6.QtGui import QKeySequence, QShortcut, QColor

from theme import ACCENT, API
from api_client import api_get, api_post, api_post_stream
from storage import list_projects, load_project, save_project
from canvas import Canvas, node_pixmap
from editor_settings import SettingsPanelMixin


class RunWorker(QThread):
    """Streams a workflow run from the API and re-emits each execution event
    as a Qt signal, so the canvas can update live on the GUI thread."""
    event = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, workflow):
        super().__init__()
        self.workflow = workflow

    def run(self):
        try:
            for evt in api_post_stream("/run-stream", self.workflow):
                self.event.emit(evt)
        except Exception as e:
            self.failed.emit(str(e))


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
        # the global theme sets QListWidget::item padding:7px which clips our
        # custom name+icon rows; relax it just for the palette.
        self.palette.setStyleSheet("QListWidget::item { padding: 0px; }")
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
            if nd.get("__header__"):
                it.setHidden(False)   # keep section headers visible
                continue
            hay = (nd.get("title", "") + " " + nd.get("type", "")).lower()
            it.setHidden(bool(text) and text not in hay)

    def _add_palette_header(self, label):
        it = QListWidgetItem(label)
        it.setData(Qt.ItemDataRole.UserRole, {"__header__": True})
        it.setFlags(Qt.ItemFlag.NoItemFlags)   # not selectable/clickable
        f = it.font(); f.setBold(True); f.setPointSize(f.pointSize() - 1); it.setFont(f)
        it.setForeground(QColor(ACCENT))
        it.setSizeHint(QSize(180, 30))
        self.palette.addItem(it)

    def _add_palette_node(self, nd):
        """One palette row: node name on the left, its icon on the FAR right
        (just past the name slot, not overlapping the text)."""
        it = QListWidgetItem()
        it.setData(Qt.ItemDataRole.UserRole, nd)
        self.palette.addItem(it)

        ROW_H = 34   # comfortable height; text was getting vertically clipped
        row = QWidget()
        row.setFixedHeight(ROW_H)
        lay = QHBoxLayout(row); lay.setContentsMargins(10, 0, 10, 0); lay.setSpacing(6)
        name = QLabel(nd["title"])
        name.setStyleSheet("color: #ffffff; background: transparent;")
        name.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(name)
        lay.addStretch(1)                      # pushes the icon to the right edge
        pm = node_pixmap(nd["type"], 20)
        if pm is not None:
            ic = QLabel(); ic.setPixmap(pm)
            ic.setFixedSize(22, 22)
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic.setStyleSheet("background: transparent;")
            lay.addWidget(ic)
        # padding is overridden to 0 on the palette, so the hint == row height
        it.setSizeHint(QSize(180, ROW_H))
        self.palette.setItemWidget(it, row)

    def load_palette(self):
        self.palette.clear(); self.meta_by_type.clear()
        try:
            data = api_get("/nodes")
        except Exception as e:
            self.palette.addItem(QListWidgetItem("[API offline]"))
            self.results.setText(f"Can't reach API at {API}\nStart it: python3 api.py\n\n{e}"); return

        nodes = data["nodes"]
        for nd in nodes:
            self.meta_by_type[nd["type"]] = nd

        # split triggers out from everything else
        triggers = [n for n in nodes if n.get("category") == "trigger"]
        others   = [n for n in nodes if n.get("category") != "trigger"]

        if triggers:
            self._add_palette_header("TRIGGERS")
            for nd in triggers:
                self._add_palette_node(nd)
        if others:
            self._add_palette_header("NODES")
            for nd in others:
                self._add_palette_node(nd)

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
        if nd and not nd.get("__header__"):
            self.canvas.add_node(nd); self.refresh_json()

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

    def _on_run_event(self, evt):
        """Handle one live execution event on the GUI thread."""
        kind = evt.get("kind")
        c = self.canvas
        if kind == "start":
            c.run_states.clear(); c.edge_counts.clear()
            c.running_node = None; c.active_edge = None
            c.update()
        elif kind == "node_running":
            c.running_node = evt["node"]
            c.run_states[evt["node"]] = "running"
            c.update()
        elif kind == "node_done":
            c.run_states[evt["node"]] = "done"
            if c.running_node == evt["node"]:
                c.running_node = None
            # stash a short result preview in the side panel
            ms = evt.get("ms", 0)
            self._append_result(
                f"{evt['node']}  →  {evt.get('items_out', 0)} item(s)  ({ms:.0f} ms)"
            )
            c.update()
        elif kind == "node_error":
            c.run_states[evt["node"]] = "error"
            if c.running_node == evt["node"]:
                c.running_node = None
            self._append_result(f"{evt['node']}  ✗  ERROR: {evt.get('error','')}")
            c.update()
        elif kind == "edge":
            key = (evt["from"], evt.get("out", 0), evt["to"], evt.get("in", 0))
            c.edge_counts[key] = evt.get("items", 0)
            c.pulse_edge(key)   # animate a dot travelling the wire
            c.update()
        elif kind == "results":
            self._last_results = evt.get("results", {})
            c.running_node = None; c.active_edge = None; c.update()
        elif kind == "fatal":
            self._append_result(f"RUN FAILED: {evt.get('error','')}")
            c.running_node = None; c.update()

    def _append_result(self, line):
        prev = self.results.toPlainText()
        # keep the log readable: cap to last ~40 lines
        lines = (prev.splitlines() + [line])[-40:]
        self.results.setPlainText("\n".join(lines))
        sb = self.results.verticalScrollBar()
        sb.setValue(sb.maximum())

    def run(self):
        wf = self.canvas.to_workflow(self.current_project or "untitled")
        if not wf["nodes"]:
            self.results.setText("Canvas empty - drop some nodes first."); return
        self.results.clear()
        self.canvas.run_states.clear(); self.canvas.edge_counts.clear()
        self.canvas.running_node = None; self.canvas.update()
        self._run_worker = RunWorker(wf)
        self._run_worker.event.connect(self._on_run_event)
        self._run_worker.failed.connect(lambda e: self._append_result(f"Run failed:\n{e}"))
        self._run_worker.start()

    def run_from(self, node_name):
        # run the whole workflow but visually anchor on the chosen node;
        # the live stream will still light up everything as it executes.
        self.run()
