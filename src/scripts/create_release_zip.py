#!/usr/bin/env python3
import argparse
import os
import zipfile


def should_skip(rel_path: str) -> bool:
    rel_path = rel_path.replace("\\", "/")
    if rel_path.startswith("logs/"):
        name = rel_path.split("/")[-1]
        if name in {".gitkeep"}:
            return False
        if name.lower().endswith(".log") or name == ".DS_Store":
            return True
    if rel_path.endswith(".DS_Store"):
        return True
    return False


def build_zip(project_dir: str, out_zip: str) -> None:
    os.makedirs(os.path.dirname(out_zip), exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        root_parent = os.path.dirname(project_dir)
        for root, _, files in os.walk(project_dir):
            for name in files:
                full_path = os.path.join(root, name)
                rel = os.path.relpath(full_path, root_parent)
                rel_inside = os.path.relpath(full_path, project_dir)
                if should_skip(rel_inside):
                    continue
                zf.write(full_path, rel)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create release zip with empty logs payload.")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build_zip(os.path.abspath(args.project_dir), os.path.abspath(args.output))


if __name__ == "__main__":
    main()
