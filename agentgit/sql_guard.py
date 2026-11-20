import sqlite3, hashlib
from pathlib import Path
from typing import Dict, Any

class SQLiteShadow:
    def __init__(self, db_path: str, shadow_dir: str = ".agentgit/sql_objects"):
        self.db_path = Path(db_path).resolve()
        self.objects = Path(shadow_dir).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.objects.mkdir(parents=True, exist_ok=True)

    def _get_table_counts(self, conn: sqlite3.Connection) -> Dict[str, int]:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        counts = {}
        for (t,) in cur.fetchall():
            cur.execute(f'SELECT COUNT(*) FROM "{t}"')
            counts[t] = cur.fetchone()[0]
        return counts

    def capture_state(self) -> Dict[str, Any]:
        if not self.db_path.exists():
            return {"hash": None, "counts": {}}
        with sqlite3.connect(self.db_path) as conn:
            dump_sql = "\n".join(conn.iterdump())
            counts = self._get_table_counts(conn)
        shash = hashlib.sha256(dump_sql.encode("utf-8")).hexdigest()
        blob = self.objects / f"{shash}.sql"
        if not blob.exists():
            blob.write_text(dump_sql, encoding="utf-8")
        return {"hash": shash, "counts": counts}

    def restore_state(self, snapshot: Dict[str, Any]) -> None:
        shash = snapshot.get("hash")
        if not shash:
            return
        dump_sql = (self.objects / f"{shash}.sql").read_text(encoding="utf-8")
        # Windows-safe in-place transactional restore (avoids WinError 32 file locks)
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            for (t,) in cur.fetchall():
                cur.execute(f'DROP TABLE IF EXISTS "{t}"')
            conn.executescript(dump_sql)
            conn.commit()

    def compute_diff(self, old_s: Dict[str, Any], new_s: Dict[str, Any]) -> Dict[str, Any]:
        oc, nc = old_s.get("counts", {}), new_s.get("counts", {})
        deltas, deleted_rows = {}, 0
        for t in set(oc) | set(nc):
            b, a = oc.get(t, 0), nc.get(t, 0)
            d = a - b
            if d != 0 or t not in oc or t not in nc:
                deltas[t] = {"before": b, "after": a, "delta": d}
            if d < 0: deleted_rows += abs(d)
        return {"changed": old_s.get("hash") != new_s.get("hash"), "row_deltas": deltas, "total_deleted_rows": deleted_rows}
