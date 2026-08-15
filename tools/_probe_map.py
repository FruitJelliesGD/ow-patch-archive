"""Probe: build ability map and report key mappings (T2 check)."""
import json
import pathlib
import sys

sys.path.insert(0, "src")
from ow2_patch.ability_map import build_ability_map, write_ability_map
from ow2_patch.pairing import pair_patches, patch_meta_from_manifest

data = pathlib.Path("data")
en, cn = patch_meta_from_manifest(data)
r = pair_patches(en, cn)
m = build_ability_map(data, r.pairs)
write_ability_map(data, m)
print("abilities:", len(m["abilities"]), "| perks:", len(m["perks"]))
for slug in ("heavy-pulse-rifle", "stim-pack", "helix-rockets", "sprint", "agility-training"):
    if slug in m["abilities"]:
        e = m["abilities"][slug]
        print(f"  {slug}: cn={e['name_cn']} | cn_variants={e['cn_variants']} | en_variants={e['en_variants'][:5]}")
for cn in ("重型脉冲步枪", "强化药剂", "螺旋飞弹", "全速疾奔"):
    print(f"by_cn {cn}:", m["by_cn"].get(cn))
print("by_en Helix Rocket:", m["by_en"].get("Helix Rocket"))
print("by_en Helix Rockets:", m["by_en"].get("Helix Rockets"))
if "agility-training" in m["perks"]:
    print("perk agility-training:", m["perks"]["agility-training"])
