"""
storage.py — local filesystem read/write for projects (workflows) and tabels
(spreadsheets). Pure file I/O, no Qt imports here on purpose.
"""
import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(HERE, "projects")
TABELS_DIR = os.path.join(HERE, "tabels")
DOWNLOADS = os.path.expanduser("~/Downloads")


def _ensure(d):
    os.makedirs(d, exist_ok=True)


def _list(d):
    _ensure(d)
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))


def _path(d, name):
    return os.path.join(d, f"{name}.json")


def _load(d, name):
    with open(_path(d, name)) as f:
        return json.load(f)


def _save(d, name, data):
    _ensure(d)
    with open(_path(d, name), "w") as f:
        json.dump(data, f, indent=2)


def list_projects(): return _list(PROJECTS_DIR)
def load_project(n): return _load(PROJECTS_DIR, n)
def save_project(n, d): _save(PROJECTS_DIR, n, d)


def list_tabels(): return _list(TABELS_DIR)
def load_tabel(n): return _load(TABELS_DIR, n)


def save_tabel(n, d):
    for i, row in enumerate(d.get("rows", []), start=1):
        row["id"] = i
    _save(TABELS_DIR, n, d)


def new_tabel(n):
    save_tabel(n, {"name": n, "columns": ["column1"], "rows": []})
