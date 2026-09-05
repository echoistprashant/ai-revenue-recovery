import tarfile
import os
from pathlib import Path

def pack():
    root = Path(".")
    bundle_path = Path("deploy_bundle.tar.gz")
    if bundle_path.exists():
        bundle_path.unlink()

    exclude_dirs = {"node_modules", ".next", ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
    exclude_files = {"key.pem", "deploy_bundle.tar.gz"}

    print("Creating deployment bundle...")
    with tarfile.open(bundle_path, "w:gz") as tar:
        for p in root.rglob("*"):
            rel_path = p.relative_to(root)
            parts = rel_path.parts
            
            if any(part in exclude_dirs for part in parts):
                continue
            if p.name in exclude_files or p.name.endswith(".pyc") or p.name.endswith(".pem"):
                continue
            if p.is_file():
                tar.add(p, arcname=str(rel_path))

    print(f"Packed deployment bundle: {bundle_path.stat().st_size / (1024*1024):.2f} MB")

if __name__ == "__main__":
    pack()
