import os, shutil, hashlib, difflib
from pathlib import Path
from typing import Dict, Any

class FileSystemShadow:
    def __init__(self, workspace_dir: str, shadow_dir: str = ".agentgit/objects"):
        self.workspace = Path(workspace_dir).resolve()
        self.objects = Path(shadow_dir).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.objects.mkdir(parents=True, exist_ok=True)

    def _hash_file(self, filepath: Path) -> str:
        return hashlib.sha256(filepath.read_bytes()).hexdigest()

    def capture_state(self) -> Dict[str, str]:
        manifest = {}
        for root, _, files in os.walk(self.workspace):
            for fname in files:
                full_path = Path(root) / fname
                rel_path = str(full_path.relative_to(self.workspace))
                fhash = self._hash_file(full_path)
                blob = self.objects / fhash
                if not blob.exists():
                    shutil.copy2(full_path, blob)
                manifest[rel_path] = fhash
        return manifest

    def restore_state(self, manifest: Dict[str, str]) -> None:
        for root, _, files in os.walk(self.workspace):
            for fname in files:
                full_path = Path(root) / fname
                if str(full_path.relative_to(self.workspace)) not in manifest:
                    full_path.unlink()
        for rel_path, fhash in manifest.items():
            target = self.workspace / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.objects / fhash, target)

    def compute_diff(self, old_m: Dict[str, str], new_m: Dict[str, str]) -> Dict[str, Any]:
        added = [f for f in new_m if f not in old_m]
        deleted = [f for f in old_m if f not in new_m]
        modified = [f for f in new_m if f in old_m and old_m[f] != new_m[f]]
        patches = {}
        for f in modified:
            old_l = (self.objects / old_m[f]).read_text(errors="replace").splitlines()
            new_l = (self.objects / new_m[f]).read_text(errors="replace").splitlines()
            patches[f] = "\n".join(difflib.unified_diff(old_l, new_l, fromfile=f"a/{f}", tofile=f"b/{f}"))
        return {"added": added, "deleted": deleted, "modified": modified, "patches": patches}
