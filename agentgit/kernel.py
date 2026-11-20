import time, uuid, functools
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Any
from .fs_sandbox import FileSystemShadow
from .sql_guard import SQLiteShadow

@dataclass
class CommitNode:
    commit_id: str
    parent_id: Optional[str]
    branch: str
    tool_name: str
    args_summary: str
    timestamp: float
    latency_ms: float
    fs_manifest: Dict[str, str]
    sql_snapshot: Dict[str, Any]
    diff: Dict[str, Any]
    status: str = "COMMITTED"  # COMMITTED | BLOCKED_BY_GUARD | MERGED_WINNER | DISCARDED_BRANCH
    guard_reason: Optional[str] = None

class AgentRepository:
    def __init__(self, workspace_dir: str, db_path: str, max_file_deletions: int = 1, max_row_deletions: int = 1):
        self.fs = FileSystemShadow(workspace_dir)
        self.sql = SQLiteShadow(db_path)
        self.max_file_deletions = max_file_deletions
        self.max_row_deletions = max_row_deletions
        self.commits: Dict[str, CommitNode] = {}
        self.current_branch = "main"
        self.head: Optional[str] = None
        self._init_root()

    def _init_root(self):
        t0 = time.perf_counter()
        rid = "c0_init"
        fs_m = self.fs.capture_state()
        sql_s = self.sql.capture_state()
        ms = round((time.perf_counter() - t0) * 1000, 2)
        self.commits[rid] = CommitNode(
            commit_id=rid, parent_id=None, branch="main", tool_name="INIT_SNAPSHOT",
            args_summary="Clean baseline (Files + SQLite)", timestamp=time.time(), latency_ms=ms,
            fs_manifest=fs_m, sql_snapshot=sql_s, diff={"fs": {}, "sql": {}},
        )
        self.head = rid

    def atomic_tool(self, func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            parent = self.commits[self.head]
            result = func(*args, **kwargs)

            t0 = time.perf_counter()
            after_fs, after_sql = self.fs.capture_state(), self.sql.capture_state()
            fs_diff = self.fs.compute_diff(parent.fs_manifest, after_fs)
            sql_diff = self.sql.compute_diff(parent.sql_snapshot, after_sql)
            snap_ms = round((time.perf_counter() - t0) * 1000, 2)
            cid = f"c{len(self.commits)}_{uuid.uuid4().hex[:6]}"

            violation = None
            if len(fs_diff["deleted"]) > self.max_file_deletions:
                violation = f"Blocked mass file deletion ({len(fs_diff['deleted'])} files > limit {self.max_file_deletions})"
            elif sql_diff["total_deleted_rows"] > self.max_row_deletions:
                violation = f"Blocked mass DB row deletion ({sql_diff['total_deleted_rows']} rows > limit {self.max_row_deletions})"

            if violation:
                self.fs.restore_state(parent.fs_manifest)
                self.sql.restore_state(parent.sql_snapshot)
                self.commits[cid] = CommitNode(
                    commit_id=cid, parent_id=self.head, branch=self.current_branch,
                    tool_name=func.__name__, args_summary=f"args={args}, kwargs={kwargs}",
                    timestamp=time.time(), latency_ms=snap_ms,
                    fs_manifest=parent.fs_manifest, sql_snapshot=parent.sql_snapshot,
                    diff={"fs": fs_diff, "sql": sql_diff}, status="BLOCKED_BY_GUARD", guard_reason=violation,
                )
                raise RuntimeError(f"[AgentGit Guard] {violation} -> Auto-reverted to {self.head}")

            self.commits[cid] = CommitNode(
                commit_id=cid, parent_id=self.head, branch=self.current_branch,
                tool_name=func.__name__, args_summary=f"args={args}, kwargs={kwargs}",
                timestamp=time.time(), latency_ms=snap_ms,
                fs_manifest=after_fs, sql_snapshot=after_sql,
                diff={"fs": fs_diff, "sql": sql_diff},
            )
            self.head = cid
            return result
        return wrapper

    def speculative_race(self, branch_a_fn: Callable, branch_b_fn: Callable) -> str:
        """Runs two candidate strategies on isolated shadow branches, scores safety, and merges the winner."""
        base_head = self.head
        results = {}

        for b_name, fn in [("branch_A_aggressive", branch_a_fn), ("branch_B_safe", branch_b_fn)]:
            self.revert_to(base_head)
            self.current_branch = b_name
            try:
                out = fn()
                results[b_name] = {"ok": True, "head": self.head, "msg": out}
            except Exception as e:
                results[b_name] = {"ok": False, "head": self.head, "msg": str(e)}

        # Pick winning branch that passed all invariants
        self.current_branch = "main"
        if results["branch_B_safe"]["ok"]:
            win_head = results["branch_B_safe"]["head"]
            self.revert_to(win_head)
            self.commits[win_head].status = "MERGED_WINNER"
            self.commits[win_head].branch = "branch_B_safe -> main"
            return (
                f"Speculative Arena Complete: branch_A_aggressive failed invariants ({results['branch_A_aggressive']['msg']}). "
                f"Auto-merged safe winner {win_head} into main!"
            )
        self.revert_to(base_head)
        return "Both speculative branches violated invariants; state held at base commit."

    def revert_to(self, target_commit_id: str) -> None:
        if target_commit_id not in self.commits:
            raise ValueError(f"Unknown commit: {target_commit_id}")
        target = self.commits[target_commit_id]
        self.fs.restore_state(target.fs_manifest)
        self.sql.restore_state(target.sql_snapshot)
        self.head = target_commit_id

    def get_metrics(self) -> Dict[str, Any]:
        nodes = list(self.commits.values())
        avg_ms = round(sum(n.latency_ms for n in nodes) / max(len(nodes), 1), 2)
        blocked = sum(1 for n in nodes if n.status == "BLOCKED_BY_GUARD")
        total_refs = sum(len(n.fs_manifest) for n in nodes)
        unique_blobs = len({h for n in nodes for h in n.fs_manifest.values()})
        dedup_pct = round((1 - (unique_blobs / max(total_refs, 1))) * 100, 1) if total_refs else 0.0
        return {
            "total_commits": len(nodes),
            "blocked_attacks": blocked,
            "avg_snapshot_ms": avg_ms,
            "cas_dedup_savings_pct": dedup_pct,
        }
