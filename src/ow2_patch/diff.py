"""Change detection: content hashing, manifest comparison, and deep text diffs.

Hashing is deliberately content-neutral: it covers the *original text* of a patch
only (sorted bag), never derived/enriched fields (before/after/by/metric/unit,
slugs, names, attribution moves). Upgrading extraction or attribution therefore
cannot masquerade as an official edit.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field

from .model import Patch

HASH_SCHEMA_VERSION = 2


def patch_hash(patch: Patch) -> str:
    """sha256 over (site, date, url, title, seq, sorted original-text bag)."""
    payload = (patch.site, patch.date, patch.url, patch.title, patch.seq,
               patch_canonical_texts(patch))
    return _digest(payload)


def patch_canonical_texts(patch: Patch) -> list[str]:
    texts = []
    if patch.raw_text:
        texts.append(patch.raw_text)
    for section in patch.sections:
        texts += [section.title or "", section.description or ""]
        for hero in section.heroes:
            if hero.dev_note:
                texts.append(hero.dev_note)
            for entry in hero.general:  # str (legacy) or dict
                texts.append(entry if isinstance(entry, str)
                             else ((entry.get("text_en") or entry.get("text_cn")) or ""))
            for perk in hero.perks:
                texts += perk.lines_en + perk.lines_cn + perk.raw_text
            for ability in hero.abilities:
                for change in ability.changes:
                    texts += [change.text_en or "", change.text_cn or ""]
        for block in section.blocks:
            texts += [block.title or "", block.body or "", block.dev or ""]
    return sorted(t for t in texts if t)


def patch_hash_from_dict(data: dict) -> str:
    """Same hash computed from a stored patch JSON dict (for offline migration)."""
    parts = data["id"].split("-")
    payload = (data["site"], data["date"], data["url"], data["title"],
               int(parts[4]), _dict_canonical_texts(data))
    return _digest(payload)


def _dict_canonical_texts(data: dict) -> list[str]:
    texts = []
    if data.get("raw_text"):
        texts.append(data["raw_text"])
    for section in data.get("sections", []):
        texts += [section.get("title") or "", section.get("description") or ""]
        for hero in section.get("heroes", []):
            if hero.get("dev_note"):
                texts.append(hero["dev_note"])
            for entry in hero.get("general", []):
                texts.append(entry if isinstance(entry, str)
                             else ((entry.get("text_en") or entry.get("text_cn")) or ""))
            for perk in hero.get("perks", []):
                texts += list(perk.get("lines_en") or []) + list(perk.get("lines_cn") or [])
                texts += list(perk.get("raw_text") or [])
            for ability in hero.get("abilities", []):
                for change in ability.get("changes", []):
                    texts += [change.get("text_en") or "", change.get("text_cn") or ""]
        for block in section.get("blocks", []):
            texts += [block.get("title") or "", block.get("body") or "", block.get("dev") or ""]
    return sorted(t for t in texts if t)


def _digest(payload) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
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


def ensure_hash_schema(data_dir, manifest: dict) -> bool:
    """Offline, idempotent migration of stored hashes to the current schema.

    Recomputes the hash field of every stored patch JSON and of the manifest from
    the original text only. No network, no notifications, no events.
    """
    if manifest.get("hash_schema") == HASH_SCHEMA_VERSION:
        return False
    import pathlib

    data_dir = pathlib.Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    for site in ("en", "cn"):
        for patch_file in (data_dir / "patches" / site).glob("*.json"):
            data = json.loads(patch_file.read_text(encoding="utf-8"))
            data["hash"] = patch_hash_from_dict(data)
            patch_file.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    for patch_id, meta in manifest.items():
        if patch_id == "hash_schema" or not isinstance(meta, dict):
            continue
        parts = patch_id.split("-")
        path = data_dir / "patches" / meta["site"] / f"{'-'.join(parts[1:4])}-{parts[4]}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        meta["hash"] = patch_hash_from_dict(data)
    manifest["hash_schema"] = HASH_SCHEMA_VERSION
    save_manifest(data_dir, manifest)
    return True
