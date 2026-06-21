"""
editor_settings.py — the right-hand settings panel logic for the node editor.
Split out from editor.py because this is the part that changes most often
(new param types, new conditional-visibility rules, webhook URL banner, etc).

Implemented as a mixin: Editor (in editor.py) inherits from SettingsPanelMixin
so `self` here is the Editor instance — it has self.settings_layout,
self.canvas, self.current_project, etc. already set up by Editor.__init__.
"""
import json
import random
import string

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QComboBox, QCheckBox, QApplication
)
from PyQt6.QtCore import Qt, QTimer

from theme import ACCENT, API
from api_client import api_get
from storage import list_tabels


class SettingsPanelMixin:
    def _tag(self, text):
        l = QLabel(text); l.setStyleSheet("color:#999; font-family:monospace; font-size:11px;"); return l

    # ----------------------------------------------------------- webhook banner
    def _build_webhook_url_banner(self, node):
        if not node.params.get("path"):
            rnd = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
            node.params["path"] = f"/{rnd}"

        path = node.params.get("path", "/webhook")
        if not path.startswith("/"):
            path = "/" + path
        method = node.params.get("method", "POST")
        full_url = f"{API}/hook{path}"

        box = QWidget()
        box_lay = QVBoxLayout(box); box_lay.setContentsMargins(0, 4, 0, 8); box_lay.setSpacing(5)
        box.setStyleSheet("background: rgba(20,20,20,0.45); border:1px solid #444; border-radius:5px;")

        tag = QLabel("WEBHOOK URL"); tag.setStyleSheet("color:#999; font-size:9px; font-weight:bold; border:none; padding:6px 8px 0px 8px;")
        box_lay.addWidget(tag)

        url_row = QHBoxLayout(); url_row.setContentsMargins(8, 0, 8, 0); url_row.setSpacing(0)
        method_pill = QLabel(method); method_pill.setFixedHeight(22)
        method_pill.setStyleSheet("background:#5a4632; color:#e8b06a; font-size:10px; font-weight:bold; padding:0px 7px; border-top-left-radius:4px; border-bottom-left-radius:4px;")
        method_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        url_row.addWidget(method_pill)
        url_field = QLineEdit(full_url); url_field.setReadOnly(True); url_field.setFixedHeight(22)
        url_field.setStyleSheet("font-size:10px; color:#ddd; background:#1a1a1a; border:1px solid #444; border-left:none; border-top-left-radius:0px; border-bottom-left-radius:0px; padding:0px 6px;")
        url_row.addWidget(url_field, 1)
        copy_btn = QPushButton("⎘"); copy_btn.setFixedSize(24, 22)
        copy_btn.setStyleSheet(f"font-size:11px; padding:0px; border:1px solid {ACCENT}; color:{ACCENT}; margin-left:4px;")
        def do_copy():
            QApplication.clipboard().setText(url_field.text())
            copy_btn.setText("✓")
            QTimer.singleShot(1000, lambda: copy_btn.setText("⎘"))
        copy_btn.clicked.connect(do_copy)
        url_row.addWidget(copy_btn)
        box_lay.addLayout(url_row)

        registered = self._is_webhook_registered(path)
        status_row = QHBoxLayout(); status_row.setContentsMargins(8, 0, 8, 2)
        if registered:
            dot = QLabel("●"); dot.setStyleSheet("color:#5c5; font-size:9px; border:none;")
            txt = QLabel("live — save again any time you change the path"); txt.setStyleSheet("color:#5c5; font-size:9px; border:none;")
        else:
            dot = QLabel("●"); dot.setStyleSheet("color:#888; font-size:9px; border:none;")
            txt = QLabel("not live yet — click Save to register this URL"); txt.setStyleSheet("color:#888; font-size:9px; border:none;")
        status_row.addWidget(dot); status_row.addWidget(txt); status_row.addStretch()
        box_lay.addLayout(status_row)

        if not self._has_downstream_respond(node):
            warn = QWidget()
            warn_lay = QVBoxLayout(warn); warn_lay.setContentsMargins(8, 6, 8, 6)
            warn.setStyleSheet("background: rgba(180,120,40,0.15); border:1px solid #a06820; border-radius:4px;")
            wl = QLabel("Add a 'Respond to Webhook' node to control\nwhat gets sent back. Without one, this will\nauto-reply with {\"ok\": true}.")
            wl.setWordWrap(True); wl.setStyleSheet("color:#d9a35c; font-size:9px; border:none;")
            warn_lay.addWidget(wl)
            box_lay.addWidget(warn)

        self.settings_layout.addWidget(box)
        self.refresh_json()

    def _is_webhook_registered(self, path):
        try:
            data = api_get("/webhooks")
            return any(w["path"] == path for w in data.get("registered", []))
        except Exception:
            return False

    def _has_downstream_respond(self, node):
        wf = self.canvas.to_workflow(self.current_project or "untitled")
        conns = wf.get("connections", {})
        types = {n["name"]: n["type"] for n in wf.get("nodes", [])}
        seen = set()
        queue = [node.name]
        while queue:
            cur = queue.pop(0)
            if cur in seen: continue
            seen.add(cur)
            for link in conns.get(cur, []):
                target = link["to"]
                if types.get(target) == "webhook.respond":
                    return True
                queue.append(target)
        return False

    # ----------------------------------------------------------- main panel
    def show_node_settings(self, node):
        while self.settings_layout.count():
            it = self.settings_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None); w.deleteLater()
        if node is None:
            hint = QLabel("Select a node\nto edit settings."); hint.setWordWrap(True)
            hint.setStyleSheet("color:#666; font-family:monospace; font-size:12px;")
            self.settings_layout.addWidget(hint); self.settings_layout.addStretch(); return

        meta = self.meta_by_type.get(node.type_id, {})
        params_spec = meta.get("params", [])

        head = QLabel(node.name); head.setStyleSheet(f"color:{ACCENT}; font-family:monospace; font-size:15px; font-weight:bold;")
        head.setWordWrap(True)
        self.settings_layout.addWidget(head)
        ttag = QLabel(node.type_id); ttag.setStyleSheet("color:#555; font-family:monospace; font-size:10px;")
        self.settings_layout.addWidget(ttag)

        self.settings_layout.addWidget(self._tag("name"))
        name_edit = QLineEdit(node.name)
        name_edit.setStyleSheet("font-size:13px;")
        def set_name():
            node.name = name_edit.text() or node.name
            head.setText(node.name); self.refresh_json()
        name_edit.editingFinished.connect(set_name)
        self.settings_layout.addWidget(name_edit)

        if node.type_id == "webhook.trigger":
            self._build_webhook_url_banner(node)

        if not params_spec:
            note = QLabel("(no settings for this node)")
            note.setStyleSheet("color:#555; font-family:monospace; font-size:11px;")
            self.settings_layout.addWidget(note)
            self.settings_layout.addStretch(); return

        param_widgets: dict[str, list] = {}

        def rebuild_visibility():
            op = node.params.get("operation", "")
            for key, widgets in param_widgets.items():
                visible = True
                if node.type_id == "data.tabel":
                    if key in ("filter_field", "filter_value"):
                        visible = (op == "read")
                if node.type_id == "core.log":
                    if key == "field":
                        visible = not node.params.get("show_all_fields", True)
                if node.type_id == "web.http":
                    if key == "response_field":
                        visible = (node.params.get("response_mode", "") == "add to item")
                if node.type_id == "logic.switch":
                    mode = node.params.get("mode", "rules")
                    if key in ("rules", "all_matching_outputs"):
                        visible = (mode == "rules")
                    if key == "expression":
                        visible = (mode == "expression")
                if node.type_id == "core.merge":
                    mode = node.params.get("mode", "append")
                    if key in ("field_input1", "field_input2", "join"):
                        visible = (mode == "combine_fields")
                    if key == "include_unpaired":
                        visible = (mode == "combine_position")
                    if key == "clash":
                        visible = mode in ("combine_position", "combine_fields", "combine_all")
                    if key == "branch":
                        visible = (mode == "choose_branch")
                for w in widgets:
                    w.setVisible(visible)

        def make_widget(p):
            key = p["key"]; ptype = p.get("type", "text")
            if key not in node.params:
                node.params[key] = p.get("default")
            cur = node.params.get(key, p.get("default"))

            label = self._tag(p.get("label", key))
            self.settings_layout.addWidget(label)

            widget = None
            if ptype == "select":
                widget = QComboBox()
                opts = [str(o) for o in p.get("options", [])]
                widget.addItems(opts)
                if cur is not None and str(cur) in opts:
                    widget.setCurrentText(str(cur))
                widget.setStyleSheet("font-size:13px;")
                def mksel(k, w):
                    def s():
                        node.params[k] = w.currentText()
                        self.refresh_json(); rebuild_visibility()
                        if node.type_id == "webhook.trigger" and k == "method":
                            self.show_node_settings(node)
                        if k in ("mode", "fallback") and node.type_id in ("logic.switch", "core.merge"):
                            self.canvas.update()
                    return s
                widget.currentTextChanged.connect(mksel(key, widget))

            elif ptype == "tabel":
                widget = QComboBox()
                tabels = list_tabels()
                widget.addItem("")
                widget.addItems(tabels)
                if cur and str(cur) in tabels:
                    widget.setCurrentText(str(cur))
                widget.setStyleSheet("font-size:13px;")
                def mktab(k, w):
                    def s(): node.params[k] = w.currentText() or None; self.refresh_json()
                    return s
                widget.currentTextChanged.connect(mktab(key, widget))

            elif ptype == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(cur))
                widget.setStyleSheet("font-size:13px;")
                def mkbool(k, w):
                    def s():
                        node.params[k] = w.isChecked()
                        self.refresh_json(); rebuild_visibility()
                    return s
                widget.stateChanged.connect(mkbool(key, widget))

            elif ptype == "json":
                widget = QPlainTextEdit(json.dumps(cur, indent=2) if cur is not None else "")
                widget.setFixedHeight(80); widget.setStyleSheet("font-size:11px;")
                def mk(k, w):
                    def s():
                        txt = w.toPlainText().strip()
                        try: node.params[k] = json.loads(txt) if txt else None
                        except Exception: node.params[k] = txt
                        self.refresh_json()
                    return s
                widget.textChanged.connect(mk(key, widget))

            elif ptype == "multiline":
                widget = QPlainTextEdit(str(cur) if cur is not None else "")
                widget.setFixedHeight(100); widget.setStyleSheet("font-size:11px;")
                def mk2(k, w):
                    def s(): node.params[k] = w.toPlainText(); self.refresh_json()
                    return s
                widget.textChanged.connect(mk2(key, widget))

            else:  # text / number
                widget = QLineEdit("" if cur is None else str(cur))
                widget.setStyleSheet("font-size:13px;")
                def mk3(k, w, is_num):
                    def s():
                        v = w.text()
                        if is_num:
                            try: v = float(v) if "." in v else int(v)
                            except Exception: pass
                        node.params[k] = v; self.refresh_json()
                        if node.type_id == "webhook.trigger" and k == "path":
                            self.show_node_settings(node)
                        if k in ("num_outputs", "num_inputs"):
                            self.canvas.update()
                    return s
                widget.editingFinished.connect(mk3(key, widget, ptype == "number"))

            self.settings_layout.addWidget(widget)
            param_widgets[key] = [label, widget]

        for p in params_spec:
            make_widget(p)

        rebuild_visibility()
        self.settings_layout.addStretch()
