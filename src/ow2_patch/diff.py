"""Change detection: content hashing, manifest comparison, and deep text diffs.

Hashing is deliberately content-neutral: it covers the *original text* of a patch
only (sorted bag), never derived/enriched fields (before/after/by/metric/unit,
slugs, names, attribution moves). Upgrading extraction or attribution therefore
cannot masquerade as an official edit.

Legacy (OW1-era) pages degrade to a single raw_text blob that also carries site
template chrome (post-nav button, pagination links, intro/footer boilerplate);
that chrome is stripped from the hash bag (schema v3) so template churn never
flags the whole 2016-2020 archive as modified.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field

from .model import Patch

HASH_SCHEMA_VERSION = 3

# ---------------------------------------------------------------------------
# Legacy raw_text chrome cleaning (hash-only; stored raw_text keeps full text)
# ---------------------------------------------------------------------------

_LEGACY_MONTH = ("January|February|March|April|May|June|July|August|"
                 "September|October|November|December")

# Pagination block on legacy pages: link labels interleaved with their bare
# month mobile labels, e.g. "July Patch Notes July May Patch Notes May".
# Each link must be followed by its bare month label; a lone "May Patch
# Notes" inside prose is real content and must survive.
_LEGACY_PAGINATION_RE = re.compile(
    rf"\s*(?:(?:{_LEGACY_MONTH}) (?:Live )?Patch Notes\s+(?:{_LEGACY_MONTH})\s*)+")

_LEGACY_CHROME_PHRASES = (
    "Top of post",
    "Live Patch Notes",
    "PATCH HIGHLIGHTS",
    "General Discussion forum Bug Report forum Technical Support forum",
    "These patch notes represent general changes made to the Live version of "
    "Overwatch and the balance changes listed affect Quick Play, Competitive "
    "Play, Arcade, and Custom Games.",
    "Please note that some changes may not be documented or described in full detail.",
    "Read below to learn more about the latest changes.",
    "Read below to learn about the latest changes.",
    "A new patch is now live on Windows PC.",
    "A new patch is now live on Windows PC, PlayStation 4, and Xbox One.",
    "A new patch is now live on PC.",
    "A new patch is now live.",
)

# Intro/feedback boilerplate with variant punctuation (the NetEase-era legacy
# pages drop the periods between the sentences, and most end right after the
# "Technical Support forum" sentence without the trailing "Please note...").
_LEGACY_BOILERPLATE_RES = (
    re.compile(
        r"To share your feedback, please post in the General Discussion "
        r"forum\.? For a list of known issues, visit our Bug Report forum\.? "
        r"For troubleshooting assistance, visit our Technical Support forum\.?"
        r"(?: Please note that some changes may not be documented or described "
        r"in full detail\.?)?"
    ),
)


def clean_legacy_text(text: str) -> str:
    """Strip site template chrome from a legacy raw-text blob, for hashing only.

    Legacy (OW1-era) pages degrade to a single raw_text blob that includes site
    chrome (post-nav button, pagination links, intro/footer boilerplate).
    Template churn on those pages would otherwise flag every legacy patch as
    modified. The stored raw_text keeps the full page text; only the hash bag
    is cleaned.
    """
    cleaned = text
    # regex first: the variant-tolerant boilerplate blocks carry their own tail
    # ("Please note that some changes..."), which must still be present when
    # the block regex matches; the phrase pass below handles standalone pieces
    for pattern in _LEGACY_BOILERPLATE_RES:
        cleaned = pattern.sub("", cleaned)
    for phrase in _LEGACY_CHROME_PHRASES:
        cleaned = cleaned.replace(phrase, "")
    cleaned = _LEGACY_PAGINATION_RE.sub("", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def patch_hash(patch: Patch) -> str:
    """sha256 over (site, date, url, title, seq, sorted original-text bag)."""
    payload = (patch.site, patch.date, patch.url, patch.title, patch.seq,
               patch_canonical_texts(patch))
    return _digest(payload)


def patch_canonical_texts(patch: Patch) -> list[str]:
    texts = []
    if patch.raw_text:
        texts.append(clean_legacy_text(patch.raw_text))
    for section in patch.sections:
        texts += [section.title or "", section.description or ""]
        for hero in section.heroes:
            if hero.dev_note:
                texts.append(hero.dev_note)
            for entry in hero.general:  # str (legacy) or dict
                texts.append(entry if isinstance(entry, str)
                             else ((entry.get("text_en") or entry.get("text_cn")) or ""))
            for perk in hero.perks:
                # attribution splits a line into raw_text (full original) + lines
                # (parsed body); hash on the full original only, never both
                texts += perk.raw_text if perk.raw_text else perk.lines_en + perk.lines_cn
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
        texts.append(clean_legacy_text(data["raw_text"]))
    for section in data.get("sections", []):
        texts += [section.get("title") or "", section.get("description") or ""]
        for hero in section.get("heroes", []):
            if hero.get("dev_note"):
                texts.append(hero["dev_note"])
            for entry in hero.get("general", []):
                texts.append(entry if isinstance(entry, str)
                             else ((entry.get("text_en") or entry.get("text_cn")) or ""))
            for perk in hero.get("perks", []):
                raw = list(perk.get("raw_text") or [])
                texts += raw if raw else (list(perk.get("lines_en") or [])
                                          + list(perk.get("lines_cn") or []))
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
    cosmetic: bool = False  # modified whose diff is only names/chrome, not content


@dataclass
class DiffEntry:
    path: str
    old: object | None
    new: object | None


_COSMETIC_LEAF_SUFFIXES = (".name_en", ".name_cn", ".slug", ".role")


def is_cosmetic_diff(entries: list[DiffEntry], old: dict, new: dict) -> bool:
    """True when every diff entry is cosmetic: hero/ability name/slug/role
    fields, or a legacy raw_text that differs only in site template chrome.

    Cosmetic modified patches are still archived (data stays current) but are
    excluded from Issue/email notifications.
    """
    for entry in entries:
        if entry.path.endswith(_COSMETIC_LEAF_SUFFIXES):
            continue
        if entry.path == "raw_text":
            if clean_legacy_text(str(entry.old or "")) == clean_legacy_text(str(entry.new or "")):
                continue
        return False
    return True


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
