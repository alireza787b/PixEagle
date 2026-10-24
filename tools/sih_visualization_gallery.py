#!/usr/bin/env python3
"""Build a read-only visual contract gallery for every PixEagle follower."""

from __future__ import annotations

import argparse
import html
from pathlib import Path

import yaml


COLORS = {
    "image_position_2d": "#68b5ff",
    "gimbal_angles": "#ffbd69",
    "attitude_rate_image_position": "#c49cff",
}


def build_gallery(catalog: dict, base_path: Path) -> str:
    cards = []
    for item in catalog["followers"]:
        profile = html.escape(str(item["profile"]))
        input_contract = str(item["input"])
        input_label = html.escape(input_contract.replace("_", " "))
        command = html.escape(str(item["command"]).replace("_", " "))
        purpose = html.escape(str(item["purpose"]))
        behavior = html.escape(str(item["behavior"]))
        color = COLORS.get(input_contract, "#9fb3c8")
        report = item.get("report")
        report_link = (
            f'<a class="report" href="{html.escape(str(report))}">Open interactive replay</a>'
            if report
            else '<span class="muted">Contract guide only; no synthetic vehicle claim</span>'
        )
        cards.append(f'''<article class="card">
  <h2>{profile}</h2>
  <p class="purpose">{purpose}</p>
  <svg viewBox="0 0 520 116" role="img" aria-label="{input_label} to {command}">
    <rect x="8" y="25" width="166" height="62" rx="10" fill="#1c2b3a" stroke="{color}" stroke-width="2"/>
    <text x="91" y="52" text-anchor="middle" fill="#eef4f8">Input</text>
    <text x="91" y="73" text-anchor="middle" fill="{color}">{input_label}</text>
    <path d="M190 56h122" stroke="#8ca2b2" stroke-width="2" marker-end="url(#arrow)"/>
    <rect x="338" y="25" width="174" height="62" rx="10" fill="#1c2b3a" stroke="#8ca2b2" stroke-width="2"/>
    <text x="425" y="52" text-anchor="middle" fill="#eef4f8">Command intent</text>
    <text x="425" y="73" text-anchor="middle" fill="#ffb0b0">{command}</text>
  </svg>
  <p>{behavior}</p>
  {report_link}
</article>''')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PixEagle follower visual contracts</title>
<style>
:root {{ color-scheme: dark; --bg:#111820; --panel:#1d2732; --line:#3b4b5b; --muted:#9aaebe; }}
* {{ box-sizing:border-box }} body {{ margin:0; background:var(--bg); color:#eef4f8; font:15px system-ui,sans-serif }}
header {{ padding:22px max(20px,calc((100vw - 1200px)/2)); border-bottom:1px solid var(--line) }}
h1 {{ margin:0 0 6px; font-size:25px }} .muted {{ color:var(--muted) }}
main {{ max-width:1200px; margin:0 auto; padding:18px; display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:14px }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px; min-height:285px }}
h2 {{ margin:0 0 4px; font-size:18px }} .purpose {{ color:#d5e3ed; min-height:40px }}
svg {{ width:100%; height:auto; margin:2px 0 2px }} p {{ line-height:1.4 }} a {{ color:#9ed0ff }}
.report {{ display:inline-block; margin-top:4px }}
</style></head><body><header><h1>PixEagle follower visual contracts</h1>
<div class="muted">Read-only input-to-command guide. It explains each follower’s contract; interactive replays are linked only where evidence exists. No card sends commands.</div></header>
<main><svg width="0" height="0"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8z" fill="#8ca2b2"/></marker></defs></svg>{''.join(cards)}</main></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("tools/sih_visualization_scenarios/follower-contracts.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = yaml.safe_load(args.catalog.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or not isinstance(catalog.get("followers"), list):
        raise SystemExit("catalog must contain a followers list")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_gallery(catalog, args.output.parent), encoding="utf-8")
    print(f"Wrote follower contract gallery to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
