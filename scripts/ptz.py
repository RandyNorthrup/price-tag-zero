"""Shared helpers for build.py and check.py: paths, data loading and constants."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ASSETS = ROOT / "assets"

REPO = "RandyNorthrup/price-tag-zero"
REPO_URL = f"https://github.com/{REPO}"
ADD_APP_URL = f"{REPO_URL}/issues/new?template=add-app.yml"
REPORT_APP_URL = f"{REPO_URL}/issues/new?template=report-app.yml"

# Platform ids used in data/apps.yaml, in display order, with their labels.
PLATFORMS = {
    "windows": "Windows",
    "macos": "macOS",
    "linux": "Linux",
    "self-hosted": "Self-hosted",
}

# Reason groups used in data/excluded.yaml, in EXCLUDED.md order.
GROUPS = {
    "sells": (
        "Sells something",
        "The rule: nothing for sale. These projects sell a Pro or premium edition, paid features or add-ons, "
        "a paid cloud or hosted version, an enterprise edition, paid builds, or a paid license for some uses.",
    ),
    "ads": (
        "Ads in the app",
        "Ads on a project's website are fine. Ads inside the app are not.",
    ),
    "license": (
        "Not OSI open source",
        "The rule: an OSI-approved license, with a LICENSE file in the repo. Source-available, "
        "non-commercial and unlicensed code doesn't count, however generous.",
    ),
    "inactive": (
        "Inactive or archived",
        "The rule: a commit or release in the last 12 months. These may well come back.",
    ),
    "no-release": (
        "No downloadable release",
        "The rule: something you can download and run, such as a release, an installer, or a store or package listing.",
    ),
    "no-gui": (
        "No real GUI",
        "The rule: a desktop app or a self-hosted web app. Command-line tools and config files don't count.",
    ),
    "not-a-replacement": (
        "Doesn't replace paid software",
        "The rule: it has to do the main job of a well-known paid app. These are good tools that don't.",
    ),
}

ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _normalize(value):
    """Turn YAML dates into ISO strings so unquoted and quoted dates behave the same."""
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    return value


def load(name: str):
    """Load data/<name>.yaml."""
    path = DATA / f"{name}.yaml"
    with path.open(encoding="utf-8") as fh:
        return _normalize(yaml.safe_load(fh))


def load_all():
    return {
        "categories": load("categories"),
        "apps": load("apps"),
        "excluded": load("excluded"),
        "gaps": load("gaps"),
    }


def sort_key(name: str) -> str:
    return name.casefold()


def slug(text: str) -> str:
    """GitHub's heading anchor for plain text (mirrors github-slugger for ASCII and Latin text)."""
    text = text.lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def license_ids(expression: str) -> list[str]:
    """The license ids in an SPDX expression, without operators, parentheses or exceptions."""
    tokens = re.findall(r"[^\s()]+", expression)
    ids, skip_next = [], False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok in ("AND", "OR"):
            continue
        if tok == "WITH":
            skip_next = True
            continue
        ids.append(tok)
    return ids


def license_family(spdx_id: str) -> str:
    """GPL-3.0-only, GPL-3.0-or-later, GPL-3.0+ and GPL-3.0 all belong to GPL-3.0."""
    return re.sub(r"(-only|-or-later|\+)$", "", spdx_id)
