"""Render a Patch into a human-readable Markdown archive file."""

from __future__ import annotations

from .model import HeroUpdate, Patch, Section

ROLE_CN = {"tank": "重装", "damage": "输出", "support": "支援"}
STATUS_CN = {"added": "新增", "removed": "移除", "reworked": "重做", "moved": "变更", "changed": "调整"}
_ITEM_KIND_CN = {"weapon": "武器", "ability": "技能", "survival": "生存", "power": "异能"}


def render_md(patch: Patch) -> str:
    lines: list[str] = [f"# {patch.title}", "", f"> 日期: {patch.date} · 站点: {patch.site} · 来源: {patch.url}", ""]
    if patch.raw_text:
        lines += [patch.raw_text, ""]
    for section in patch.sections:
        lines += _render_section(section)
    return "\n".join(lines).rstrip() + "\n"


def _entry_text(entry) -> str:
    """Text of a general entry that may be a legacy str or a dict."""
    if isinstance(entry, dict):
        return entry.get("text_en") or entry.get("text_cn") or ""
    return str(entry)


def _render_section(section: Section) -> list[str]:
    lines: list[str] = []
    role = f"（{ROLE_CN.get(section.role, section.role)}）" if section.role else ""
    lines.append(f"## {section.title}{role}")
    lines.append("")
    if section.description:
        lines += [section.description, ""]
    if section.dev:
        lines += [f"*开发者注：{section.dev}*", ""]
    for map_update in section.maps:
        heading = " ".join(p for p in (map_update.map_name, map_update.area) if p)
        lines.append(f"#### {heading}" if heading else "####")
        lines.append("")
        lines += [f"- 修改前: {map_update.before}", f"- 修改后: {map_update.after}", ""]
    for hero in section.heroes:
        lines += _render_hero(hero)
    for block in section.blocks:
        lines.append(f"### {block.title}" if block.title else "###")
        lines.append("")
        if block.body:
            lines += [block.body, ""]
        if block.dev:
            lines += [f"*开发者注：{block.dev}*", ""]
    return lines


def _render_hero(hero: HeroUpdate) -> list[str]:
    name = hero.name_en or hero.name_cn or hero.slug
    role = f"（{ROLE_CN.get(hero.role, hero.role)}）" if hero.role else ""
    lines: list[str] = [f"### {name}{role}", ""]
    if hero.dev_note:
        lines += [f"*开发者注：{hero.dev_note}*", ""]
    for g in hero.general:
        lines.append(f"- {_entry_text(g)}")
    if hero.general:
        lines.append("")
    for perk in hero.perks:
        pname = perk.name_en or perk.name_cn or ""
        lines.append(f"- 威能 **{pname}** —— {STATUS_CN.get(perk.status, perk.status)}")
        for line in perk.lines_en or perk.lines_cn or []:
            lines.append(f"  - {line}")
    for item in hero.stadium_items:
        iname = item.name_en or item.name_cn or ""
        label = " ".join(p for p in (item.rarity, _ITEM_KIND_CN.get(item.kind, item.kind or "")) if p)
        lines.append(f"- 物品 **{iname}**（{label}）—— {STATUS_CN.get(item.status, item.status)}")
        for line in item.lines_en or item.lines_cn or []:
            lines.append(f"  - {line}")
    for ability in hero.abilities:
        aname = ability.name_en or ability.name_cn or ability.slug
        lines.append(f"#### {aname}")
        for change in ability.changes:
            text = change.text_en or change.text_cn or ""
            lines.append(f"- {text}")
        lines.append("")
    return lines
