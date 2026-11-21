#!/usr/bin/env python3
"""Validate the files in data/.

Usage:
    python scripts/check.py                  schema, required fields, licenses, duplicates, categories
    python scripts/check.py --live           also ask GitHub about every listed repo (needs GITHUB_TOKEN)
    python scripts/check.py --live --report live-report.md
                                             also write the live results as Markdown (for the weekly issue)

The live check flags repos that are missing, archived, inactive for 12 months (no commit or release),
or whose license no longer matches the data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

import yaml

import ptz

DESCRIPTION_MAX = 90
STALE_DAYS = 365
OSI_FILE = Path(__file__).with_name("osi-licenses.txt")
URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$")
GITHUB_RE = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")

APP_REQUIRED = {
    "id": str,
    "name": str,
    "url": str,
    "repo": str,
    "category": str,
    "description": str,
    "replaces": list,
    "platforms": list,
    "portable": bool,
    "license": str,
    "last_release": str,
    "last_activity": str,
    "checked": str,
    "evidence": dict,
}
APP_OPTIONAL = {"maintainer": bool}
EVIDENCE_REQUIRED = {"license_url": str, "release_url": str, "money": str, "gui": str}
# github_license: what GitHub's license detection reports for this repo when it differs from
# `license` (for example NOASSERTION for multi-license repos). The live check compares against it.
EVIDENCE_OPTIONAL = {"license_note": str, "release_note": str, "github_license": str}

EXCLUDED_REQUIRED = {
    "id": str,
    "name": str,
    "url": str,
    "category": str,
    "replaces": list,
    "group": str,
    "reason": str,
    "checked": str,
}
EXCLUDED_OPTIONAL = {"repo": str, "maintainer": bool}
CATEGORY_REQUIRED = {"id": str, "name": str, "blurb": str}
GAP_REQUIRED = {"product": str, "job": str, "status": str}


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, msg: str):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str):
        self.warnings.append(f"{where}: {msg}")


def osi_licenses() -> set[str]:
    lines = OSI_FILE.read_text(encoding="utf-8").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def norm_url(url: str) -> str:
    url = url.strip().lower()
    url = re.sub(r"^https?://(www\.)?", "", url)
    return url.rstrip("/")


def check_fields(r: Report, where: str, entry, required: dict, optional: dict) -> bool:
    if not isinstance(entry, dict):
        r.error(where, "must be a mapping of fields")
        return False
    ok = True
    for key, typ in required.items():
        if key not in entry:
            r.error(where, f"missing required field '{key}'")
            ok = False
        elif not isinstance(entry[key], typ):
            r.error(where, f"'{key}' must be a {typ.__name__}, got {type(entry[key]).__name__}")
            ok = False
        elif typ is str and not entry[key].strip():
            r.error(where, f"'{key}' is empty")
            ok = False
    for key, typ in optional.items():
        if key in entry and not isinstance(entry[key], typ):
            r.error(where, f"'{key}' must be a {typ.__name__}")
            ok = False
    for key in entry:
        if key not in required and key not in optional:
            r.error(where, f"unknown field '{key}'")
    for key, value in entry.items():
        if isinstance(value, str) and value != value.strip():
            r.error(where, f"'{key}' has leading or trailing spaces")
    return ok


def check_date(r: Report, where: str, key: str, value: str):
    if not ptz.DATE_RE.match(value):
        r.error(where, f"'{key}' must be a date like 2026-01-31, got {value!r}")
        return
    try:
        d = dt.date.fromisoformat(value)
    except ValueError:
        r.error(where, f"'{key}' is not a real date: {value!r}")
        return
    if d > today() + dt.timedelta(days=1):
        r.error(where, f"'{key}' is in the future: {value}")


def check_url(r: Report, where: str, key: str, value: str, https: bool = False):
    if not URL_RE.match(value):
        r.error(where, f"'{key}' is not a valid URL: {value!r}")
    elif https and not value.startswith("https://"):
        r.error(where, f"'{key}' must use https://")


def check_license(r: Report, where: str, expression: str, allowed: set[str]):
    if re.search(r"[^A-Za-z0-9.+\-() ]", expression):
        r.error(where, f"license {expression!r} has characters that don't belong in an SPDX expression")
        return
    ids = ptz.license_ids(expression)
    if not ids:
        r.error(where, f"license {expression!r} names no license")
    lower = {a.lower(): a for a in allowed}
    for spdx in ids:
        if spdx in allowed:
            continue
        if spdx.lower() in lower:
            r.error(where, f"license id {spdx!r} should be written {lower[spdx.lower()]!r}")
        else:
            r.error(where, f"license {spdx!r} is not an OSI-approved SPDX id (see scripts/osi-licenses.txt)")
    if expression.count("(") != expression.count(")"):
        r.error(where, f"license {expression!r} has unbalanced parentheses")


def check_description(r: Report, where: str, name: str, text: str):
    if len(text) > DESCRIPTION_MAX:
        r.error(where, f"description is {len(text)} characters; the limit is {DESCRIPTION_MAX}")
    if not text.endswith("."):
        r.error(where, "description must end with a period")
    first = re.split(r"[\s:,]", text, maxsplit=1)[0]
    if not (first[:1].isupper() or first[:1].isdigit() or re.search(r"[A-Z]", first)):
        r.error(where, "description must start with a capital letter (or a name like macOS)")
    low = text.casefold()
    if low.startswith(name.casefold()):
        rest = text[len(name):]
        if not rest or re.match(r"[\s.,!?:-]", rest):
            r.error(where, "description must not start with the app's name")
    if "replaces" in low:
        r.error(where, "leave 'Replaces' out of the description; the build adds it from 'replaces'")
    if re.search(r"[<>|\[\]`]", text):
        r.error(where, "description must not contain < > | [ ] or backticks")
    if "  " in text:
        r.error(where, "description has a double space")


def check_replaces(r: Report, where: str, replaces: list):
    if not 1 <= len(replaces) <= 3:
        r.error(where, f"'replaces' needs 1 to 3 paid products, got {len(replaces)}")
    for item in replaces:
        if not isinstance(item, str) or not item.strip():
            r.error(where, "'replaces' items must be non-empty text")
        elif "," in item:
            r.error(where, f"'replaces' item {item!r} contains a comma; list products separately")
        elif item != item.strip():
            r.error(where, f"'replaces' item {item!r} has leading or trailing spaces")
    dupes = [k for k, v in Counter(replaces).items() if v > 1]
    if dupes:
        r.error(where, f"'replaces' lists {dupes} more than once")


def check_categories(r: Report, cats) -> set[str]:
    ids: set[str] = set()
    if not isinstance(cats, list) or not cats:
        r.error("data/categories.yaml", "must be a non-empty list")
        return ids
    names = Counter()
    for i, c in enumerate(cats):
        where = f"data/categories.yaml[{i}]"
        if not check_fields(r, where, c, CATEGORY_REQUIRED, {}):
            continue
        where = f"data/categories.yaml {c['id']}"
        if not ptz.ID_RE.match(c["id"]):
            r.error(where, "id must be lowercase-kebab-case")
        if c["id"] in ids:
            r.error(where, "duplicate category id")
        ids.add(c["id"])
        names[c["name"]] += 1
        if not c["blurb"].endswith("."):
            r.error(where, "blurb must end with a period")
        for size in (28, 64):
            icon = ptz.ASSETS / "icons" / str(size) / f"{c['id']}.png"
            if not icon.exists():
                r.error(where, f"missing icon {icon.relative_to(ptz.ROOT).as_posix()}")
    for name, n in names.items():
        if n > 1:
            r.error("data/categories.yaml", f"duplicate category name {name!r}")
    return ids


def check_apps(r: Report, apps, cat_ids: set[str], allowed: set[str]):
    if not isinstance(apps, list) or not apps:
        r.error("data/apps.yaml", "must be a non-empty list")
        return
    seen = {"id": {}, "name": {}, "url": {}, "repo": {}}
    per_cat = Counter()
    for i, a in enumerate(apps):
        where = f"data/apps.yaml[{i}]"
        if isinstance(a, dict) and isinstance(a.get("id"), str):
            where = f"data/apps.yaml {a['id']}"
        if not check_fields(r, where, a, APP_REQUIRED, APP_OPTIONAL):
            continue
        if not ptz.ID_RE.match(a["id"]):
            r.error(where, "id must be lowercase-kebab-case")
        for key, value in (
            ("id", a["id"]),
            ("name", a["name"].casefold()),
            ("url", norm_url(a["url"])),
            ("repo", norm_url(a["repo"])),
        ):
            if value in seen[key]:
                r.error(where, f"duplicate {key}: also used by {seen[key][value]}")
            else:
                seen[key][value] = a["id"]
        if a["category"] not in cat_ids:
            r.error(where, f"unknown category {a['category']!r}; use an id from data/categories.yaml")
        per_cat[a["category"]] += 1
        check_url(r, where, "url", a["url"])
        check_url(r, where, "repo", a["repo"], https=True)
        check_description(r, where, a["name"], a["description"])
        check_replaces(r, where, a["replaces"])
        plats = a["platforms"]
        if not plats:
            r.error(where, "'platforms' must list at least one platform")
        for p in plats:
            if p not in ptz.PLATFORMS:
                r.error(where, f"unknown platform {p!r}; use {', '.join(ptz.PLATFORMS)}")
        if len(set(plats)) != len(plats):
            r.error(where, "'platforms' lists a platform twice")
        check_license(r, where, a["license"], allowed)
        for key in ("last_release", "last_activity", "checked"):
            check_date(r, where, key, a[key])
        ev = a["evidence"]
        if check_fields(r, f"{where} evidence", ev, EVIDENCE_REQUIRED, EVIDENCE_OPTIONAL):
            check_url(r, f"{where} evidence", "license_url", ev["license_url"])
            check_url(r, f"{where} evidence", "release_url", ev["release_url"])
        if ptz.DATE_RE.match(a["last_activity"]):
            age = (today() - dt.date.fromisoformat(a["last_activity"])).days
            if age > STALE_DAYS:
                r.warn(where, f"last_activity {a['last_activity']} is over 12 months old; re-check the project")
    for cid in cat_ids:
        if per_cat[cid] == 0:
            r.warn("data/apps.yaml", f"category {cid!r} has no apps")


def check_excluded(r: Report, excluded, apps, cat_ids: set[str]):
    if not isinstance(excluded, list):
        r.error("data/excluded.yaml", "must be a list")
        return
    listed_ids = {a.get("id") for a in apps if isinstance(a, dict)}
    listed_names = {str(a.get("name", "")).casefold() for a in apps if isinstance(a, dict)}
    listed_repos = {norm_url(str(a.get("repo", ""))) for a in apps if isinstance(a, dict)}
    ids, names = set(), set()
    for i, x in enumerate(excluded):
        where = f"data/excluded.yaml[{i}]"
        if isinstance(x, dict) and isinstance(x.get("id"), str):
            where = f"data/excluded.yaml {x['id']}"
        if not check_fields(r, where, x, EXCLUDED_REQUIRED, EXCLUDED_OPTIONAL):
            continue
        if not ptz.ID_RE.match(x["id"]):
            r.error(where, "id must be lowercase-kebab-case")
        if x["id"] in ids:
            r.error(where, "duplicate id")
        if x["name"].casefold() in names:
            r.error(where, "duplicate name")
        ids.add(x["id"])
        names.add(x["name"].casefold())
        if x["id"] in listed_ids or x["name"].casefold() in listed_names:
            r.error(where, "is both listed in apps.yaml and excluded")
        if x.get("repo") and norm_url(x["repo"]) in listed_repos:
            r.error(where, "repo is also listed in apps.yaml")
        if x["category"] not in cat_ids:
            r.error(where, f"unknown category {x['category']!r}")
        if x["group"] not in ptz.GROUPS:
            r.error(where, f"unknown group {x['group']!r}; use one of {', '.join(ptz.GROUPS)}")
        if not x["reason"].endswith("."):
            r.error(where, "reason must end with a period")
        if "|" in x["reason"]:
            r.error(where, "reason must not contain |")
        check_url(r, where, "url", x["url"])
        if x.get("repo"):
            check_url(r, where, "repo", x["repo"])
        check_date(r, where, "checked", x["checked"])


def check_gaps(r: Report, gaps):
    if not isinstance(gaps, list):
        r.error("data/gaps.yaml", "must be a list")
        return
    seen = set()
    for i, g in enumerate(gaps):
        where = f"data/gaps.yaml[{i}]"
        if not check_fields(r, where, g, GAP_REQUIRED, {}):
            continue
        if g["product"].casefold() in seen:
            r.error(where, f"duplicate product {g['product']!r}")
        seen.add(g["product"].casefold())
        if g["job"].endswith("."):
            r.error(where, "'job' is a phrase; leave off the final period")
        if not g["status"].endswith("."):
            r.error(where, "'status' must end with a period")


def check_issue_form(r: Report, cats):
    """The add-app issue form's category dropdown must match data/categories.yaml."""
    path = ptz.ROOT / ".github" / "ISSUE_TEMPLATE" / "add-app.yml"
    where = ".github/ISSUE_TEMPLATE/add-app.yml"
    if not path.exists():
        r.error(where, "missing")
        return
    form = yaml.safe_load(path.read_text(encoding="utf-8"))
    dropdown = next((b for b in form.get("body", []) if b.get("id") == "category"), None)
    if not dropdown:
        r.error(where, "has no field with id 'category'")
        return
    options = dropdown.get("attributes", {}).get("options", [])
    expected = [c["name"] for c in cats if isinstance(c, dict)]
    if options != expected:
        r.error(where, f"category options must match data/categories.yaml in order: {expected}")


# --------------------------------------------------------------------------- live
QUERY_FIELDS = """
  nameWithOwner isArchived isDisabled pushedAt
  licenseInfo { spdxId }
  latestRelease { publishedAt }
  defaultBranchRef { target { ... on Commit { committedDate } } }
"""


def graphql(token: str, query: str) -> dict:
    body = json.dumps({"query": query}).encode()
    for attempt in range(4):
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=body,
            headers={
                "Authorization": f"bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "price-tag-zero-check",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code in (502, 503, 504) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError:
            if attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def parse_date(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value[:10]) if value else None


def live_check(apps, batch: int = 40):
    """Returns (errors, warnings, skipped) as lists of (app, message)."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("--live needs a GitHub token in GITHUB_TOKEN or GH_TOKEN")
    errors, warnings, skipped = [], [], []
    targets = []
    for a in apps:
        m = GITHUB_RE.match(a["repo"])
        if m:
            targets.append((a, m.group(1), m.group(2)))
        else:
            skipped.append((a, f"not on GitHub ({a['repo']})"))

    cutoff = today() - dt.timedelta(days=STALE_DAYS)
    for start in range(0, len(targets), batch):
        chunk = targets[start:start + batch]
        parts = [
            f'r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{{QUERY_FIELDS}}}'
            for i, (_, owner, name) in enumerate(chunk)
        ]
        result = graphql(token, "query {\n" + "\n".join(parts) + "\n}")
        data = result.get("data") or {}
        for i, (a, owner, name) in enumerate(chunk):
            repo = data.get(f"r{i}")
            if repo is None:
                errors.append((a, "repository not found (deleted, renamed or made private)"))
                continue
            if repo["isArchived"]:
                errors.append((a, "repository is archived"))
            if repo.get("isDisabled"):
                errors.append((a, "repository is disabled"))
            if repo["nameWithOwner"].lower() != f"{owner}/{name}".lower():
                warnings.append((a, f"repository moved to {repo['nameWithOwner']}; update 'repo'"))
            commit = None
            if repo.get("defaultBranchRef") and repo["defaultBranchRef"].get("target"):
                commit = parse_date(repo["defaultBranchRef"]["target"].get("committedDate"))
            release = parse_date((repo.get("latestRelease") or {}).get("publishedAt"))
            latest = max(d for d in (commit, release, dt.date.min) if d)
            if latest < cutoff:
                errors.append((a, f"inactive: no commit or release since {latest.isoformat()}"))
            observed = (repo.get("licenseInfo") or {}).get("spdxId") or "NONE"
            baseline = a["evidence"].get("github_license")
            if baseline is not None:
                if observed != baseline:
                    errors.append((a, f"license changed: GitHub now reports {observed}, was {baseline}"))
            else:
                families = {ptz.license_family(x) for x in ptz.license_ids(a["license"])}
                if ptz.license_family(observed) not in families:
                    errors.append((a, f"license mismatch: GitHub reports {observed}, the list says {a['license']}"))
    return errors, warnings, skipped


def markdown_report(errors, warnings, skipped, total) -> str:
    out = [f"# Weekly live check, {today().isoformat()}", ""]
    out.append(
        f"Checked {total - len(skipped)} GitHub repos; {len(skipped)} apps live elsewhere and were skipped."
    )
    out.append("")

    def table(rows):
        lines = ["| App | Repo | Problem |", "| --- | --- | --- |"]
        for a, msg in rows:
            lines.append(f"| {a['name']} (`{a['id']}`) | {a['repo']} | {msg} |")
        return lines

    if errors:
        out += ["## Needs attention", "", *table(errors), ""]
        out.append(
            "Re-check each one against the rules in CONTRIBUTING.md. Move apps that no longer pass to "
            "data/excluded.yaml, or update the data if the project simply changed."
        )
        out.append("")
    if warnings:
        out += ["## Warnings", "", *table(warnings), ""]
    if not errors and not warnings:
        out += ["Everything passed.", ""]
    return "\n".join(out)


# --------------------------------------------------------------------------- main
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="also query GitHub for license and activity")
    parser.add_argument("--report", type=Path, help="with --live: write a Markdown report to this file")
    args = parser.parse_args(argv)

    r = Report()
    try:
        data = ptz.load_all()
    except yaml.YAMLError as exc:
        print(f"YAML error: {exc}")
        return 1
    cat_ids = check_categories(r, data["categories"])
    check_apps(r, data["apps"], cat_ids, osi_licenses())
    check_excluded(r, data["excluded"], data["apps"] or [], cat_ids)
    check_gaps(r, data["gaps"])
    check_issue_form(r, data["categories"] or [])

    for w in r.warnings:
        print(f"warning: {w}")
    for e in r.errors:
        print(f"error: {e}")
    apps = data["apps"] if isinstance(data["apps"], list) else []
    if r.errors:
        print(f"\n{len(r.errors)} error(s). Fix them and run again.")
        return 1
    print(
        f"Data OK: {len(apps)} apps in {len(cat_ids)} categories, "
        f"{len(data['excluded'])} excluded, {len(data['gaps'])} gaps."
    )

    if not args.live:
        return 0

    errors, warnings, skipped = live_check(apps)
    for a, msg in warnings:
        print(f"live warning: {a['id']}: {msg}")
    for a, msg in errors:
        print(f"live error: {a['id']}: {msg}")
    print(
        f"Live check: {len(apps) - len(skipped)} GitHub repos checked, {len(skipped)} skipped (not on GitHub), "
        f"{len(errors)} problem(s), {len(warnings)} warning(s)."
    )
    if args.report:
        args.report.write_text(markdown_report(errors, warnings, skipped, len(apps)), encoding="utf-8")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
