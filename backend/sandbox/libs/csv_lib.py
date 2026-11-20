"""TBC CSV API — CSVHandler interface + legacy helpers."""
from __future__ import annotations
import csv
import os
from typing import Any, Dict, List

class CSVHandler:
    def __init__(self, filename: str, storage_root: str = None, bot_id: int = None):
        self.filename = filename
        self._root = storage_root or os.getcwd()
        self._bot_id = bot_id
        base = os.path.join(self._root, "bot_files", str(bot_id or "shared"), "csv")
        os.makedirs(base, exist_ok=True)
        name = os.path.basename(str(filename).replace("\\", "/"))      # no path traversal: files live in the bot's own csv folder
        if not name or name in (".", ".."):
            raise ValueError("invalid file name")
        self.path = os.path.join(base, name if name.endswith(".csv") else f"{name}.csv")

    # ---- helpers ----
    def _headers(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, newline="", encoding="utf-8") as f:
            r = csv.reader(f)
            return next(r, [])

    def _read_all(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                return []
            return list(reader)

    def _write_all(self, rows, headers=None):
        fieldnames = list(headers or self._headers())
        for r in rows:
            for k in r.keys():
                if k not in fieldnames:
                    fieldnames.append(k)
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if fieldnames:
                w.writeheader()
            w.writerows(rows)

    # ---- TBC API ----
    def create_csv(self, headers=None):
        """libs.CSV.CSVHandler("data.csv").create_csv(["Name", "Points", "Date"]) — creates the file with a header row."""
        if headers is not None and not isinstance(headers, (list, tuple)):
            raise ValueError("headers must be a list of column names")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        hs = [str(h) for h in (headers or [])]
        self._write_all([], headers=hs)
        return {"ok": True, "filename": os.path.basename(self.path), "headers": hs}

    def add_row(self, row):
        """Adds a row: a dict (column -> value) or a list in header order."""
        hs = self._headers()
        if isinstance(row, (list, tuple)):
            if not hs:
                raise ValueError("create_csv(headers) first, or pass a dict")
            row = dict(zip(hs, row))
        rows = self._read_all()
        rows.append(dict(row))
        self._write_all(rows, headers=hs)
        return {"ok": True, "index": len(rows) - 1, "row": dict(row)}

    def edit_row(self, row_index, row):
        rows = self._read_all()
        i = int(row_index)
        if i < 0 or i >= len(rows):
            raise IndexError("row index out of range")
        if isinstance(row, (list, tuple)):
            row = dict(zip(self._headers(), row))
        rows[i] = dict(row)
        self._write_all(rows)
        return {"ok": True, "index": i, "row": dict(row)}

    def get(self, index=None):
        """No argument: information about the CSV file (headers, rows, size). With an index: that row."""
        rows = self._read_all()
        if index is not None:
            i = int(index)
            if i < 0 or i >= len(rows):
                raise IndexError("row index out of range")
            return rows[i]
        exists = os.path.exists(self.path)
        return {"filename": os.path.basename(self.path), "exists": exists, "headers": self._headers(), "rows": rows,
                "row_count": len(rows), "size": os.path.getsize(self.path) if exists else 0}

    def delete(self, index=None):
        """No argument: deletes the CSV file. With an index: removes that row."""
        if index is None:
            if os.path.exists(self.path):
                os.remove(self.path)
                return {"ok": True, "deleted": True}
            return {"ok": False, "deleted": False, "error": "file not found"}
        rows = self._read_all()
        i = int(index)
        if i < 0 or i >= len(rows):
            raise IndexError("row index out of range")
        removed = rows.pop(i)
        self._write_all(rows)
        return {"ok": True, "removed": removed}


class CSVLib:
    def __init__(self, bot_id: int, storage_root: str):
        self._bot_id = bot_id
        self._root = storage_root

    def CSVHandler(self, filename: str):
        return CSVHandler(filename, storage_root=self._root, bot_id=self._bot_id)

    def create_csv(self, filename, headers=None):
        """TBC-style: libs.CSV.create_csv("file.csv", ["col1","col2"])"""
        h = self.CSVHandler(filename)
        if isinstance(filename, (list, tuple)):
            raise ValueError("libs.CSV.create_csv(filename, headers) needs a file name")
        return h.create_csv(headers or [])

    def add_row(self, filename, row_dict):
        return self.CSVHandler(filename).add_row(row_dict)

    def write_rows(self, filename, rows, fieldnames=None):
        h = self.CSVHandler(filename)
        h.create_csv(fieldnames or [])
        for r in rows:
            h.add_row(r if isinstance(r, dict) else dict(zip(fieldnames or [], r)))
        return True

    def edit_row(self, filename, index, row_dict):
        return self.CSVHandler(filename).edit_row(index, row_dict)

    def get(self, filename, index=None):
        h = self.CSVHandler(filename)
        return h._read_all() if index is None else h.get(index)

    def append_row(self, filename, row):
        return self.CSVHandler(filename).add_row(row)

    def read_rows(self, filename):
        return self.CSVHandler(filename)._read_all()

    def read_dicts(self, filename):
        return self.read_rows(filename)

    def delete(self, filename):
        h = self.CSVHandler(filename)
        if os.path.exists(h.path):
            os.remove(h.path)
            return True
        return False

    def Table(self, filename):
        """TBS Lib.CSV.Table(filename) — returns CSVHandler."""
        return self.CSVHandler(filename)
