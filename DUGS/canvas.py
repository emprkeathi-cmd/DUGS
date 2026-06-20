"""
canvas.py — the node-graph editor surface: CanvasNode (visual model for a
node) and Canvas (the QWidget that draws/drags/wires nodes together).
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath, QFont

from theme import ACCENT, NODE_SIZE


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
    def del_rect(self): return QRectF(self.x + self.s - 18, self.y + 2, 16, 16)

    # ---- effective port counts (some nodes vary with their params) -------
    def n_inputs(self):
        if self.type_id == "core.merge":
            try: return max(1, int(self.params.get("num_inputs", 2) or 2))
            except (TypeError, ValueError): return 2
        return self.inputs

    def n_outputs(self):
        if self.type_id == "logic.switch":
            try: n = max(1, int(self.params.get("num_outputs", 4) or 4))
            except (TypeError, ValueError): n = 4
            if self.params.get("fallback") == "extra":
                n += 1
            return n
        return self.outputs

    # ---- per-port positions (evenly spaced down the side) ----------------
    def _port_y(self, idx, count):
        if count <= 1:
            return self.y + self.s / 2
        # spread across the node height with small margins
        top = self.y + 10
        usable = self.s - 20
        return top + usable * (idx / (count - 1))

    def in_port(self, idx=0):
        return QPointF(self.x, self._port_y(idx, self.n_inputs()))

    def out_port(self, idx=0):
        return QPointF(self.x + self.s, self._port_y(idx, self.n_outputs()))


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
        self.offset = QPointF(0, 0)
        self.panning = False; self.pan_start = QPointF()
        self.running_node = None
        self.ran_nodes = set()
        # --- live run visualisation state ---
        self.run_states = {}      # node name -> "running" | "done" | "error"
        self.edge_counts = {}     # (src, out, dst, in) -> item count shown on wire
        self.active_edge = None   # edge key currently pulsing
        self._pulse_t = 0.0       # 0..1 progress of the travelling dot
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._advance_pulse)
        self.setMouseTracking(True)

    def pulse_edge(self, key):
        """Start a dot travelling along the given wire to show data moving."""
        self.active_edge = key
        self._pulse_t = 0.0
        if not self._pulse_timer.isActive():
            self._pulse_timer.start(16)   # ~60fps

    def _advance_pulse(self):
        self._pulse_t += 0.06
        if self._pulse_t >= 1.0:
            self._pulse_t = 0.0
            self.active_edge = None
            self._pulse_timer.stop()
        self.update()

    def world(self, pos):
        return QPointF(pos.x() - self.offset.x(), pos.y() - self.offset.y())

    def clear(self):
        self.nodes.clear(); self.connections.clear()
        self.selected = None; self.selected_conn = None
        self.running_node = None; self.ran_nodes.clear()
        self.run_states.clear(); self.edge_counts.clear()
        self.active_edge = None
        self.update()

    def add_node(self, meta):
        n = CanvasNode(meta["type"], meta["title"], meta["inputs"], meta["outputs"],
                       60 + (len(self.nodes) * 24) % 280, 60 + (len(self.nodes) * 30) % 280)
        for p in meta.get("params", []): n.params[p["key"]] = p.get("default")
        self.nodes.append(n); self.select_node(n); self.update(); return n

    def select_node(self, n):
        self.selected = n; self.selected_conn = None; self.editor.show_node_settings(n)

    def node_at(self, wpos):
        for n in reversed(self.nodes):
            if n.rect().contains(wpos): return n
        return None

    def port_at(self, wpos):
        r = 16
        for n in self.nodes:
            no = n.n_outputs()
            for i in range(no):
                if (wpos - n.out_port(i)).manhattanLength() < r:
                    return ("out", n, i)
            ni = n.n_inputs()
            for i in range(ni):
                if n.inputs > 0 and (wpos - n.in_port(i)).manhattanLength() < r:
                    return ("in", n, i)
        return None

    def conn_at(self, wpos):
        for i, (src, oi, dst, ii) in enumerate(self.connections):
            a, b = src.out_port(oi), dst.in_port(ii)
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            if (wpos - mid).manhattanLength() < 18: return i
        return None

    def run_rect(self, n):
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
        p.translate(self.offset)
        for i, (src, oi, dst, ii) in enumerate(self.connections):
            a, b = src.out_port(oi), dst.in_port(ii); sel = (i == self.selected_conn)
            key = (src.name, oi, dst.name, ii)
            is_active = (self.active_edge == key)
            if is_active:
                wire_col = QColor("#ffd166")
            elif sel:
                wire_col = QColor("#ff6b6b")
            else:
                wire_col = QColor(ACCENT)
            p.setPen(QPen(wire_col, 2.6 if (sel or is_active) else 1.6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath(a); cx = (a.x() + b.x()) / 2
            c1 = QPointF(cx, a.y()); c2 = QPointF(cx, b.y())
            path.cubicTo(c1, c2, b); p.drawPath(path)

            # item-count badge at wire midpoint (after a run delivers items)
            cnt = self.edge_counts.get(key)
            if cnt is not None:
                t = 0.5
                mt = path.pointAtPercent(t)
                badge = QRectF(mt.x() - 13, mt.y() - 8, 26, 16)
                p.setBrush(QBrush(QColor(20, 20, 20, 230)))
                p.setPen(QPen(wire_col, 1))
                p.drawRoundedRect(badge, 7, 7)
                p.setPen(QColor("#fff")); fb = QFont("monospace"); fb.setPointSize(7); fb.setBold(True); p.setFont(fb)
                p.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(cnt))

            # travelling pulse dot showing data moving along this wire
            if is_active:
                pt = path.pointAtPercent(max(0.0, min(1.0, self._pulse_t)))
                p.setBrush(QBrush(QColor("#ffd166"))); p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(pt, 5, 5)
        if self.wire_from:
            n, oi = self.wire_from
            p.setPen(QPen(QColor(ACCENT), 1.2, Qt.PenStyle.DashLine))
            p.drawLine(n.out_port(oi), self.world(self._mouse))
        for n in self.nodes:
            is_sel = (n is self.selected)
            state = self.run_states.get(n.name)
            running = (state == "running")
            done = (state == "done")
            errored = (state == "error")
            if running:    border = QColor("#ffd166")
            elif errored:  border = QColor("#ff6b6b")
            elif done:     border = QColor("#7CFC9B")
            elif is_sel:   border = QColor(ACCENT)
            else:          border = QColor("#ffffff")
            p.setPen(QPen(border, 2.6 if (running or is_sel or errored) else 1))
            if running:    fill = QColor(46, 42, 14, 240)
            elif errored:  fill = QColor(46, 16, 16, 240)
            elif done:     fill = QColor(14, 34, 20, 240)
            else:          fill = QColor(15, 15, 15, 235)
            p.setBrush(QBrush(fill)); p.drawRoundedRect(n.rect(), 4, 4)
            p.setPen(QColor("#ffffff")); f = QFont("monospace"); f.setPointSize(9); f.setBold(True); p.setFont(f)
            p.drawText(n.rect(), Qt.AlignmentFlag.AlignCenter, n.title)
            p.setPen(QColor(ACCENT)); f2 = QFont("monospace"); f2.setPointSize(7); p.setFont(f2)
            p.drawText(QRectF(n.x, n.y + n.s - 18, n.s, 16), Qt.AlignmentFlag.AlignCenter, n.type_id)
            # status glyph top-right corner during/after a run
            if state:
                glyph = {"running": "▶", "done": "✓", "error": "✗"}.get(state, "")
                gcol = {"running": "#ffd166", "done": "#7CFC9B", "error": "#ff6b6b"}.get(state, "#fff")
                p.setPen(QColor(gcol)); fg = QFont("monospace"); fg.setPointSize(10); fg.setBold(True); p.setFont(fg)
                p.drawText(QRectF(n.x + n.s - 20, n.y + 1, 18, 16), Qt.AlignmentFlag.AlignCenter, glyph)
            p.setBrush(QBrush(QColor(ACCENT))); p.setPen(QPen(QColor(ACCENT), 1))
            ni = n.n_inputs()
            if n.inputs > 0:
                for i in range(ni):
                    p.setBrush(QBrush(QColor(ACCENT))); p.setPen(QPen(QColor(ACCENT), 1))
                    p.drawEllipse(n.in_port(i), 7, 7)
                    p.setPen(QColor("#000")); f3 = QFont("monospace"); f3.setPointSize(5); f3.setBold(True); p.setFont(f3)
                    lbl = "IN" if ni == 1 else str(i)
                    p.drawText(QRectF(n.x - 16, n.in_port(i).y() - 6, 16, 12), Qt.AlignmentFlag.AlignCenter, lbl)
            no = n.n_outputs()
            if n.outputs > 0:
                for i in range(no):
                    p.setBrush(QBrush(QColor(ACCENT))); p.setPen(QPen(QColor(ACCENT), 1))
                    p.drawEllipse(n.out_port(i), 7, 7)
                    p.setPen(QColor("#000")); f3 = QFont("monospace"); f3.setPointSize(5); f3.setBold(True); p.setFont(f3)
                    lbl = "OUT" if no == 1 else str(i)
                    p.drawText(QRectF(n.x + n.s, n.out_port(i).y() - 6, 16, 12), Qt.AlignmentFlag.AlignCenter, lbl)
            p.setPen(QPen(QColor(ACCENT), 1)); p.setBrush(QBrush(QColor(ACCENT)))
            if n is self.hovered:
                dr = n.del_rect()
                p.setPen(QPen(QColor('#ff6b6b'), 1)); p.setBrush(QBrush(QColor(40, 15, 15, 230)))
                p.drawRoundedRect(dr, 3, 3)
                p.setPen(QColor('#ff6b6b')); fx = QFont('monospace'); fx.setPointSize(9); p.setFont(fx)
                p.drawText(dr, Qt.AlignmentFlag.AlignCenter, 'x')
                rr = self.run_rect(n)
                p.setPen(QPen(QColor('#7CFC9B'), 1)); p.setBrush(QBrush(QColor(15, 40, 20, 230)))
                p.drawRoundedRect(rr, 3, 3)
                p.setPen(QColor('#7CFC9B'))
                tri = QPainterPath()
                tri.moveTo(rr.x() + 5, rr.y() + 4); tri.lineTo(rr.x() + 12, rr.y() + 8)
                tri.lineTo(rr.x() + 5, rr.y() + 12); tri.closeSubpath()
                p.setBrush(QBrush(QColor('#7CFC9B'))); p.drawPath(tri)

    def mousePressEvent(self, e):
        self.setFocus()
        spos = QPointF(e.position()); wpos = self.world(spos)
        if e.button() == Qt.MouseButton.MiddleButton:
            self.panning = True; self.pan_start = spos; return
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
            self.wire_from = (hit[1], hit[2]); self._mouse = spos; return
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
                src, oi = self.wire_from
                self.connections.append((src, oi, hit[1], hit[2])); self.editor.refresh_json()
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
