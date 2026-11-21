#!/usr/bin/env python3
"""Generate README.md, REPLACES.md, EXCLUDED.md and assets/badges/ from the files in data/.

Usage:
    python scripts/build.py           write the generated files
    python scripts/build.py --check   change nothing; exit 1 if any generated file is out of date
"""

from __future__ import annotations

import argparse
import base64
import html
import re
import sys
from collections import defaultdict
from pathlib import Path

import ptz

GENERATED = (
    "GENERATED FILE: do not edit by hand. "
    "Edit the files in data/ and run: python scripts/build.py"
)
BADGES = ptz.ASSETS / "badges"

WHY_TEXT = """\
<!--lint ignore no-emphasis-as-heading-->
> **Why this list exists**
>
> Too much of the software we depend on has turned into a toll booth. Tools you used to buy once are now monthly rentals. Features you already had move behind higher tiers. Your files and workflows get locked into formats and clouds that are hard to leave, and the price keeps climbing because leaving is painful.
>
> It doesn't have to be that way. People all over the world build excellent tools and give them away, with the source open for anyone to check. Price Tag Zero collects the ones that replace the paid stuff, with no strings: no Pro tier, no trial, no subscription, no cloud upsell, nothing for sale. Ever.
"""

RULES_TEXT = """\
> **The rules**
>
> 1. **Open source.** An OSI-approved license, with the code public.
> 2. **A real GUI.** A desktop app for Windows, macOS or Linux, or a web app you host yourself, with a release you can download. Command-line-only tools don't count.
> 3. **Nothing for sale.** No Pro tier, trial, subscription, paid add-on, paid cloud or hosting, enterprise edition or in-app ads.
> 4. **Donate buttons are fine** if they block nothing now and can't later.
> 5. **Active.** A commit or release in the last 12 months.
> 6. **Replaces something paid.** It does the main job of a well-known paid app.
>
> Every app here passes all six. The details, and the evidence each app needs, are in [the contributing guide](CONTRIBUTING.md#the-rules).
"""


# --------------------------------------------------------------------------- badges
# Verdana Bold advance widths at 11px. Badges use 10px text, so these are scaled.
# Measured once from verdanab.ttf so the build needs no font files or extra packages.
_W11 = {
    " ": 3.76, "!": 4.43, '"': 6.46, "#": 9.54, "$": 7.82, "%": 13.99, "&": 9.49, "'": 3.65,
    "(": 5.98, ")": 5.98, "*": 7.82, "+": 9.54, ",": 3.98, "-": 5.28, ".": 3.98, "/": 7.58,
    "0": 7.82, "1": 7.82, "2": 7.82, "3": 7.82, "4": 7.82, "5": 7.82, "6": 7.82, "7": 7.82,
    "8": 7.82, "9": 7.82, ":": 4.43, ";": 4.43, "<": 9.54, "=": 9.54, ">": 9.54, "?": 6.78,
    "@": 10.6, "A": 8.54, "B": 8.38, "C": 7.96, "D": 9.13, "E": 7.51, "F": 7.15, "G": 8.92,
    "H": 9.21, "I": 6.0, "J": 6.11, "K": 8.48, "L": 7.01, "M": 10.43, "N": 9.31, "O": 9.35,
    "P": 8.06, "Q": 9.35, "R": 8.6, "S": 7.82, "T": 7.5, "U": 8.93, "V": 8.4, "W": 12.41,
    "X": 8.4, "Y": 8.1, "Z": 7.61, "[": 5.98, "\\": 7.58, "]": 5.98, "^": 9.54, "_": 7.82,
    "`": 7.82, "a": 7.35, "b": 7.69, "c": 6.47, "d": 7.69, "e": 7.3, "f": 4.65, "g": 7.69,
    "h": 7.84, "i": 3.76, "j": 4.43, "k": 7.38, "l": 3.76, "m": 11.64, "n": 7.84, "o": 7.55,
    "p": 7.69, "q": 7.69, "r": 5.47, "s": 6.53, "t": 5.01, "u": 7.84, "v": 7.15, "w": 10.78,
    "x": 7.36, "y": 7.16, "z": 6.56, "{": 7.82, "|": 5.98, "}": 7.82, "~": 9.54,
}
FONT_SIZE = 10
PAD = 6
ICON = 12

# Brand palette: yellow #FFC82E, black #000000, hot pink #FF3D89, white #FFFFFF.
STYLES = {
    #              fill       text       shadow
    "platform": ("#FFC82E", "#000000", "#FF3D89"),
    "plain": ("#FFFFFF", "#000000", "#FF3D89"),
    "license": ("#000000", "#FFC82E", "#FF3D89"),
    "maintainer": ("#FF3D89", "#000000", "#FFC82E"),
}


def text_width(text: str) -> float:
    return round(sum(_W11.get(c, 8.0) for c in text) * FONT_SIZE / 11, 1)


def badge_svg(text: str, style: str, label: str, icon: Path | None = None) -> str:
    fill, ink, shadow = STYLES[style]
    tw = text_width(text)
    icon_w = ICON + 4 if icon else 0
    body_w = round(tw + 2 * PAD + icon_w, 1)
    width = round(body_w + 3, 1)
    tx = round(0.5 + PAD + icon_w, 1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" '
        f'viewBox="0 0 {width} 20" role="img" aria-label="{html.escape(label)}">',
        f"<!-- {GENERATED} -->",
        f"<title>{html.escape(label)}</title>",
        f'<rect x="2.5" y="2.5" width="{body_w}" height="17" rx="4" fill="{shadow}"/>',
        f'<rect x="0.5" y="0.5" width="{body_w}" height="17" rx="4" fill="{fill}" stroke="#000000"/>',
    ]
    if icon:
        data = base64.b64encode(icon.read_bytes()).decode("ascii")
        parts.append(
            f'<image x="{0.5 + PAD - 1}" y="3" width="{ICON}" height="{ICON}" '
            f'href="data:image/png;base64,{data}"/>'
        )
    parts.append(
        f'<text x="{tx}" y="12.6" fill="{ink}" font-family="Verdana,Geneva,\'DejaVu Sans\',sans-serif" '
        f'font-size="{FONT_SIZE}" font-weight="bold" textLength="{tw}" '
        f'lengthAdjust="spacingAndGlyphs">{html.escape(text)}</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def license_file(spdx: str) -> str:
    return "license-" + re.sub(r"[^a-z0-9.+]+", "-", spdx.lower()).strip("-") + ".svg"


def build_badges(apps) -> dict[str, str]:
    """Every badge SVG the README needs, as {filename: content}."""
    out = {
        "windows.svg": badge_svg("Windows", "platform", "Runs on Windows"),
        "macos.svg": badge_svg("macOS", "platform", "Runs on macOS"),
        "linux.svg": badge_svg("Linux", "platform", "Runs on Linux"),
        "self-hosted.svg": badge_svg(
            "Self-hosted", "plain", "Self-hosted web app", ptz.ASSETS / "icons" / "28" / "self-hosted.png"
        ),
        "portable.svg": badge_svg("Portable", "plain", "Portable: runs without installing"),
        "maintainer.svg": badge_svg("maintainer's project", "maintainer", "Made by this list's maintainer"),
    }
    for spdx in sorted({a["license"] for a in apps}):
        out[license_file(spdx)] = badge_svg(spdx, "license", f"License: {spdx}")
    return out


def img(file: str, alt: str, title: str | None = None) -> str:
    t = f' title="{html.escape(title)}"' if title else ""
    return f'<img src="assets/badges/{file}" alt="{html.escape(alt)}"{t} height="20">'


PLATFORM_TITLES = {
    "windows": "Runs on Windows",
    "macos": "Runs on macOS",
    "linux": "Runs on Linux",
    "self-hosted": "A web app you host yourself",
}


def entry_badges(app) -> str:
    out = []
    for p in ptz.PLATFORMS:
        if p in app["platforms"]:
            out.append(img(f"{p}.svg", ptz.PLATFORMS[p], PLATFORM_TITLES[p]))
    if app["portable"]:
        out.append(img("portable.svg", "Portable", "Runs without installing"))
    out.append(img(license_file(app["license"]), f"License: {app['license']}", f"License: {app['license']}"))
    if app.get("maintainer"):
        out.append(img("maintainer.svg", "Maintainer's project", "Made by this list's maintainer"))
    return " ".join(out)


# --------------------------------------------------------------------------- markdown helpers
def md_text(text: str) -> str:
    """Escape characters that would turn plain text into markdown or HTML."""
    return re.sub(r"([\\`*_\[\]<>|])", r"\\\1", text)


def cell(text: str) -> str:
    return md_text(text)


def shield(label: str, message: str, color: str) -> str:
    def esc(s):
        return s.replace("-", "--").replace("_", "__").replace(" ", "%20")

    return f"https://img.shields.io/badge/{esc(label)}-{esc(message)}-{color}?style=for-the-badge&amp;labelColor=000000"


def heading_icon(cat_id: str) -> str:
    return f"![](assets/icons/28/{cat_id}.png)"


def category_anchor(cat) -> str:
    # The heading is "<icon> Name"; the image has empty alt text, so GitHub's anchor
    # is the slug of " Name", which starts with a hyphen.
    return "#" + ptz.slug(" " + cat["name"])


def last_updated(data) -> str:
    dates = [a["checked"] for a in data["apps"]] + [x["checked"] for x in data["excluded"]]
    return max(dates)


# --------------------------------------------------------------------------- README
def build_readme(data) -> str:
    cats = data["categories"]
    apps = data["apps"]
    by_cat = defaultdict(list)
    for a in apps:
        by_cat[a["category"]].append(a)
    for lst in by_cat.values():
        lst.sort(key=lambda a: ptz.sort_key(a["name"]))
    total = len(apps)
    updated = last_updated(data)

    out = []
    out.append(
        '<h1 align="center">\n'
        f"<!-- {GENERATED} -->\n"
        "<picture>\n"
        '<source media="(prefers-color-scheme: dark)" srcset="assets/banner/banner-dark.png">\n'
        '<source media="(prefers-color-scheme: light)" srcset="assets/banner/banner-light.png">\n'
        '<img src="assets/banner/banner-light.png" alt="Price Tag Zero: free, open-source apps that '
        'replace the ones you pay for. No strings attached.">\n'
        "</picture>\n"
        "</h1>\n"
    )
    out.append(
        '<p align="center">\n'
        f'<a href="#contents"><img alt="{total} apps" src="{shield("apps", str(total), "FFC82E")}"></a>\n'
        f'<a href="LICENSE"><img alt="License: CC0-1.0" src="{shield("license", "CC0-1.0", "FF3D89")}"></a>\n'
        f'<img alt="Last updated {updated}" src="{shield("last updated", updated, "FFC82E")}">\n'
        "</p>\n"
    )
    out.append(
        '<p align="center">\n'
        "<b>Hand-checked, free and open-source apps with a real GUI that replace the software you pay for.</b>\n"
        "</p>\n"
    )
    out.append(
        '<p align="center">\n'
        '<a href="REPLACES.md">Paid app to free app, A to Z</a> ·\n'
        "<a href=\"EXCLUDED.md\">Why isn't X here?</a> ·\n"
        f'<a href="{ptz.ADD_APP_URL}">Suggest an app</a>\n'
        "</p>\n"
    )
    out.append(WHY_TEXT)
    out.append(RULES_TEXT)

    # Contents
    out.append("## Contents\n")
    toc = []
    for c in cats:
        n = len(by_cat[c["id"]])
        toc.append(f"- [{heading_icon(c['id'])} {md_text(c['name'])}]({category_anchor(c)}) ({n})")
    toc.append("- [Gaps](#gaps)")
    out.append("\n".join(toc) + "\n")

    example_license = "GPL-3.0"
    maintainer_alt = "Maintainer's project"
    legend = [
        "**How to read an entry**<br>",
        f"{img('windows.svg', 'Windows')} {img('macos.svg', 'macOS')} {img('linux.svg', 'Linux')} "
        "Runs on Windows, macOS or Linux.<br>",
        f"{img('self-hosted.svg', 'Self-hosted')} A web app you run on your own computer or server.<br>",
        f"{img('portable.svg', 'Portable')} Runs without installing.<br>",
        f"{img(license_file(example_license), 'License: ' + example_license)} Its open-source license.<br>",
        f"{img('maintainer.svg', maintainer_alt)} Made by this list's maintainer. "
        "Same rules, no special treatment.",
    ]
    out.append("\n".join(legend) + "\n")

    # Categories
    for c in cats:
        out.append(f"## {heading_icon(c['id'])} {md_text(c['name'])}\n")
        out.append(f"*{md_text(c['blurb'])}*\n")
        lines = []
        for a in by_cat[c["id"]]:
            replaces = ", ".join(md_text(r) for r in a["replaces"])
            lines.append(
                f"- [{md_text(a['name'])}]({a['url']}) - {md_text(a['description'])} "
                f"Replaces: {replaces}. {entry_badges(a)}"
            )
        out.append("\n".join(lines) + "\n")

    # Gaps
    out.append("## Gaps\n")
    out.append(
        "Some paid apps still have no free, open-source replacement that passes every rule. "
        "These are the big ones. Know an app that fills a gap, or a near miss that has changed? "
        "Please [suggest it](CONTRIBUTING.md#suggest-an-app). It's the most useful contribution there is.\n"
    )
    out.append(
        "\n".join(f"- {md_text(g['product'])}: {md_text(g['job'])}. {md_text(g['status'])}" for g in data["gaps"])
        + "\n"
    )

    # Contributing and license
    out.append("## Contributing\n")
    out.append(
        "Suggestions are welcome, and every app is held to the same rules. Read the "
        "[contributing guide](CONTRIBUTING.md) first, then "
        f"[suggest an app with the issue form]({ptz.ADD_APP_URL}) or open a pull request that edits "
        "`data/apps.yaml`. If a listed app starts selling something or goes quiet, "
        f"[report it]({ptz.REPORT_APP_URL}). Wondering why a popular app is missing? "
        "See [Why isn't X here?](EXCLUDED.md). Looking for a replacement for one paid product? "
        "See [the A to Z table](REPLACES.md).\n"
    )
    out.append("Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).\n")
    out.append(
        "**License:** [CC0-1.0](LICENSE). To the extent possible under law, the contributors have waived "
        "all copyright and related rights to this list. Each app keeps its own license.\n"
    )
    return "\n".join(out)


# --------------------------------------------------------------------------- REPLACES.md
def letter_of(name: str) -> str:
    c = name[0].upper()
    return c if "A" <= c <= "Z" else "0-9"


def build_replaces(data) -> str:
    paid = defaultdict(list)
    for a in data["apps"]:
        for r in a["replaces"]:
            paid[r].append(a)
    products = sorted(paid, key=ptz.sort_key)
    letters = []
    for p in products:
        letter = letter_of(p)
        if letter not in letters:
            letters.append(letter)

    out = [f"<!-- {GENERATED} -->\n"]
    out.append("# Paid app to free app, A to Z\n")
    out.append(
        f"Every paid product named in [Price Tag Zero](README.md), A to Z, with the free, open-source apps "
        "on the list that replace it. "
        "Every free app here passes [the rules](CONTRIBUTING.md#the-rules): open source, a real GUI, "
        "nothing for sale, active, and a fair replacement.\n"
    )
    out.append("**Jump to:** " + " · ".join(f"[{l}](#{ptz.slug(l)})" for l in letters) + "\n")
    for letter in letters:
        out.append(f"## {letter}\n")
        rows = ["| Paid product | Free, open-source replacements |", "| --- | --- |"]
        for p in products:
            if letter_of(p) != letter:
                continue
            alts = sorted(paid[p], key=lambda a: ptz.sort_key(a["name"]))
            links = ", ".join(f"[{cell(a['name'])}]({a['url']})" for a in alts)
            rows.append(f"| {cell(p)} | {links} |")
        out.append("\n".join(rows) + "\n")
    out.append(f"[Back to the list](README.md) · [Suggest an app]({ptz.ADD_APP_URL})\n")
    return "\n".join(out)


# --------------------------------------------------------------------------- EXCLUDED.md
def build_excluded(data) -> str:
    cat_name = {c["id"]: c["name"] for c in data["categories"]}
    by_group = defaultdict(list)
    for x in data["excluded"]:
        by_group[x["group"]].append(x)

    out = [f"<!-- {GENERATED} -->\n"]
    out.append("# Why isn't X here?\n")
    out.append(
        "Plenty of great apps didn't make the list. Each one below was checked against "
        "[the rules](CONTRIBUTING.md#the-rules) and fails at least one, so it isn't listed. "
        "This isn't a verdict on the app or the people behind it: a project with a paid tier can still be "
        "excellent. Price Tag Zero just makes one strict promise: nothing on it costs anything, ever.\n"
    )
    out.append(
        "Projects change. If an app below has dropped its paid tier, moved to an OSI license or come back "
        f"to life, [suggest it again]({ptz.ADD_APP_URL}) with the new evidence.\n"
    )
    out.append(f"{len(data['excluded'])} apps checked and not listed, as of {last_updated(data)}.\n")
    jump = []
    for g, (title, _) in ptz.GROUPS.items():
        if by_group[g]:
            jump.append(f"[{title} ({len(by_group[g])})](#{ptz.slug(title)})")
    out.append("**Jump to:** " + " · ".join(jump) + "\n")
    for g, (title, blurb) in ptz.GROUPS.items():
        items = sorted(by_group[g], key=lambda x: ptz.sort_key(x["name"]))
        if not items:
            continue
        out.append(f"## {title}\n")
        out.append(f"{blurb}\n")
        rows = ["| App | Category | Would replace | Why it's not listed |", "| --- | --- | --- | --- |"]
        for x in items:
            rows.append(
                f"| [{cell(x['name'])}]({x['url']}) | {cell(cat_name[x['category']])} | "
                f"{cell(', '.join(x['replaces']))} | {cell(x['reason'])} |"
            )
        out.append("\n".join(rows) + "\n")
    out.append(f"[Back to the list](README.md) · [Paid app to free app, A to Z](REPLACES.md)\n")
    return "\n".join(out)


# --------------------------------------------------------------------------- main
def outputs(data) -> dict[Path, str]:
    files = {
        ptz.ROOT / "README.md": build_readme(data),
        ptz.ROOT / "REPLACES.md": build_replaces(data),
        ptz.ROOT / "EXCLUDED.md": build_excluded(data),
    }
    for name, svg in build_badges(data["apps"]).items():
        files[BADGES / name] = svg
    return files


def read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except FileNotFoundError:
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="exit 1 if a generated file is out of date")
    args = parser.parse_args(argv)

    files = outputs(ptz.load_all())
    stale_badges = sorted(p for p in BADGES.glob("*.svg") if p not in files) if BADGES.exists() else []

    if args.check:
        problems = [str(p.relative_to(ptz.ROOT)) for p, text in files.items() if read(p) != text]
        problems += [f"{p.relative_to(ptz.ROOT)} (no longer used)" for p in stale_badges]
        if problems:
            print("Generated files are out of date. Run: python scripts/build.py")
            for p in problems:
                print(f"  {p.replace(chr(92), '/')}")
            return 1
        print(f"Generated files are up to date ({len(files)} files).")
        return 0

    BADGES.mkdir(parents=True, exist_ok=True)
    changed = 0
    for path, text in files.items():
        if read(path) != text:
            path.write_text(text, encoding="utf-8", newline="\n")
            changed += 1
    for p in stale_badges:
        p.unlink()
    print(f"Wrote {changed} changed file(s), removed {len(stale_badges)} unused badge(s); {len(files)} generated in all.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
