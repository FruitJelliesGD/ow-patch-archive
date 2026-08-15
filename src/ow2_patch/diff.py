"""Change detection: content hashing, manifest comparison, and deep text diffs."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field

from .model import Patch, patch_to_dict


def patch_hash(patch: Patch) -> str:
    """sha256 over the deterministic JSON of everything except the hash itself."""
    data = patch_to_dict(patch)
    data.pop("hash", None)
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class ChangeEvent:
    kind: str  # new | modified
    patch: Patch
    diff_entries: list[DiffEntry] = field(default_factory=list)


@dataclass
class DiffEntry:
    path: str
    old: object | None
    new: object | None


@dataclass
class RunReport:
    events: list[ChangeEvent] = field(default_factory=list)
    unchanged: int = 0
    unknown_heroes: list[tuple[str, str]] = field(default_factory=list)
    unknown_abilities: list[tuple[str, str]] = field(default_factory=list)


def detect_changes(patches: list[Patch], manifest: dict) -> RunReport:
    """Compare freshly parsed patches against the stored manifest."""
    report = RunReport()
    for patch in patches:
        patch.hash = patch_hash(patch)
        prev = manifest.get(patch.id)
        if prev is None:
            report.events.append(ChangeEvent("new", patch))
        elif prev.get("hash") != patch.hash:
            report.events.append(ChangeEvent("modified", patch))
        else:
            report.unchanged += 1
    return report


def deep_diff(old: dict, new: dict) -> list[DiffEntry]:
    """Leaf-level diff between two dicts; used for modified-patch changelogs."""
    entries: list[DiffEntry] = []

    def walk(a: object, b: object, path: str) -> None:
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                if key == "hash":
                    continue
                walk(a.get(key), b.get(key), f"{path}.{key}" if path else key)
        elif isinstance(a, list) and isinstance(b, list):
            for i in range(max(len(a), len(b))):
                walk(a[i] if i < len(a) else None,
                     b[i] if i < len(b) else None,
                     f"{path}[{i}]")
        elif a != b:
            entries.append(DiffEntry(path, a, b))

    walk(old, new, "")
    return entries


def load_manifest(data_dir) -> dict:
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    with open(manifest_path, encoding="utf-8") as fh:
        return json.load(fh)


def save_manifest(data_dir, manifest: dict) -> None:
    with open(data_dir / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)


def append_changelog(data_dir, entry: dict) -> None:
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry}
    with open(data_dir / "changelog.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
