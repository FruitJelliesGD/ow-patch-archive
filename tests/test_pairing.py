"""Pairing algorithm tests (constructed scenarios + real-data invariants)."""

from __future__ import annotations

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
