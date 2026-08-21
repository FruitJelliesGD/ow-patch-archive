"""Pairing algorithm tests (constructed scenarios + real-data invariants)."""

from __future__ import annotations

import json
import pathlib

from ow2_patch.pairing import (
    _parse_title_date,
    pair_patches,
    patch_meta_from_manifest,
)

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def make_patch(site: str, date: str, seq: int = 1, title: str | None = None) -> dict:
    return {
        "patch_id": f"{site}-{date}-{seq}",
        "site": site,
        "date": date,
        "title": title or f"{site} patch {date}",
        "url": f"https://x/{site}/{date}",
        "seq": seq,
        "title_date": _parse_title_date(title or f"{site} patch {date}", site),
    }


def test_exact_date_match():
    en = [make_patch("en", "2026-08-12", title="Overwatch Patch Notes – August 12, 2026")]
    cn = [make_patch("cn", "2026-08-12", title="《守望先锋》补丁说明——2026年8月12日")]
    result = pair_patches(en, cn)
    assert len(result.pairs) == 1
    assert result.pairs[0]["match"]["by"] == "anchor"
    assert result.pairs[0]["en"]["patch_id"] == "en-2026-08-12-1"
    assert result.pairs[0]["cn"]["patch_id"] == "cn-2026-08-12-1"


def test_one_day_lag_cluster_max_cardinality():
    # EN 26..29, CN 27..30: greedy diff0 would match CN27->EN27 leaving CN30 unmatched;
    # max-cardinality must match all four with CNx -> EN(x-1).
    en = [make_patch("en", f"2025-08-{d}") for d in (26, 27, 28, 29)]
    cn = [make_patch("cn", f"2025-08-{d}") for d in (27, 28, 29, 30)]
    result = pair_patches(en, cn)
    assert len(result.pairs) == 4
    matched = {p["cn"]["patch_id"]: p["en"]["date"] for p in result.pairs}
    assert matched["cn-2025-08-27-1"] == "2025-08-26"
    assert matched["cn-2025-08-30-1"] == "2025-08-29"
    assert result.unpaired_en == [] and result.unpaired_cn == []


def test_title_date_second_signal():
    # EN anchor 03-19 but title says March 21; CN 03-22 trial pairs via title diff 1
    en = [make_patch("en", "2025-03-19", title="Freja Hero Trial – March 21, 2025")]
    cn = [make_patch("cn", "2025-03-22", title="《守望先锋》补丁说明——2025年3月22日")]
    result = pair_patches(en, cn)
    assert len(result.pairs) == 1
    assert result.pairs[0]["match"]["by"] == "title"


def test_one_en_one_cn_no_orphan():
    en = [make_patch("en", "2025-03-18", title="Overwatch Patch Notes – March 18, 2025")]
    cn = [make_patch("cn", "2025-03-19", title="《守望先锋》补丁说明——2025年3月19日")]
    result = pair_patches(en, cn)
    assert len(result.pairs) == 1
    assert result.pairs[0]["match"]["date_diff"] == 1


def test_seq_only_matches_exact():
    en = [make_patch("en", "2025-06-27", 1), make_patch("en", "2025-06-27", 2)]
    cn = [make_patch("cn", "2025-06-27", 1)]
    result = pair_patches(en, cn)
    assert len(result.pairs) == 1
    assert result.pairs[0]["cn"]["patch_id"] == "cn-2025-06-27-1"
    assert result.pairs[0]["en"]["patch_id"] == "en-2025-06-27-1"
    assert "en-2025-06-27-2" in result.unpaired_en


def test_real_data_pairing_invariants():
    en, cn = patch_meta_from_manifest(DATA)
    assert len(en) == 342 and len(cn) == 55
    result = pair_patches(en, cn)
    assert len(result.pairs) >= 45, f"only {len(result.pairs)} pairs"
    # every CN patch appears at most once across pairs + unpaired
    all_cn = [p["cn"]["patch_id"] for p in result.pairs] + result.unpaired_cn
    assert sorted(all_cn) == sorted(p["patch_id"] for p in cn)
    # pairs are deterministic
    again = pair_patches(en, cn)
    assert [p["en"]["patch_id"] for p in result.pairs] == [p["en"]["patch_id"] for p in again.pairs]


def test_patches_index_mode_pair(tmp_path):
    """Pair-level mode: either side non-standard wins (the CN April Fools title
    is tagged april_fools through its EN pair)."""
    from ow2_patch.pairing import PairResult, build_patches_index

    result = PairResult(pairs=[
        {"id": "p-2025-04-01-1", "date": "2025-04-01",
         "en": {"patch_id": "en-2025-04-01-1", "date": "2025-04-01", "seq": 1,
                "title": "Totally Normal Patch Notes for Totally Normalwatch - April 1, 2025",
                "url": "u"},
         "cn": {"patch_id": "cn-2025-04-01-1", "date": "2025-04-01", "seq": 1,
                "title": "《守望先锋》完全正常的“完全正常先锋”补丁说明——2025年4月1日",
                "url": "u"}},
        {"id": "p-2025-03-19-1", "date": "2025-03-19",
         "en": {"patch_id": "en-2025-03-19-1", "date": "2025-03-19", "seq": 1,
                "title": "Overwatch 2 Freja Hero Trial - March 21, 2025", "url": "u"},
         "cn": {"patch_id": "cn-2025-03-22-1", "date": "2025-03-22", "seq": 1,
                "title": "《守望先锋》英雄试玩：弗蕾娅——2025年3月22日", "url": "u"}},
    ])
    build_patches_index(tmp_path, result)
    index = json.loads((tmp_path / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    assert by_id["p-2025-04-01-1"]["mode"] == "april_fools"
    assert by_id["p-2025-03-19-1"]["mode"] == "hero_trial"


def test_real_patches_index_mode_invariants():
    """Real regenerated index: special patches carry their mode, standard ones
    stay standard (incl. unpaired entries)."""
    index = json.loads((DATA / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    assert by_id["en-2024-01-12-1"]["mode"] == "quick_play_hacked"  # unpaired
    assert by_id["en-2024-04-01-1"]["mode"] == "april_fools"
    assert by_id["p-2025-04-01-1"]["mode"] == "april_fools"  # pair, CN side non-keyword
    assert by_id["en-2024-12-17-1"]["mode"] == "experiment_6v6"
    assert by_id["en-2018-03-29-1"]["mode"] == "ptr"
    assert by_id["en-2022-10-04-1"]["mode"] == "announcement"
    assert by_id["p-2026-08-11-1"]["mode"] == "standard"
    assert by_id["en-2017-02-27-1"]["mode"] == "standard"  # uppercase variant
    assert all(p.get("mode") for p in index["patches"])
