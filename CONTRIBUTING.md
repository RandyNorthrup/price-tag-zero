# Contributing to Price Tag Zero

Thanks for helping. This list makes one promise: every app on it is free and open source, with nothing for sale, ever. Keeping that promise means checking each app carefully, so every suggestion comes with evidence, and a maintainer reviews each one against the rules before it's added.

- [The rules](#the-rules)
- [Suggest an app](#suggest-an-app)
- [The evidence to provide](#the-evidence-to-provide)
- [Report an app that broke the rules](#report-an-app-that-broke-the-rules)
- [How the repo works](#how-the-repo-works)

## The rules

An app is listed only if **every one** of these holds.

### 1. Open source

- It has an OSI-approved license ([the OSI list](https://opensource.org/licenses)), with a LICENSE file in the repository.
- Source-available licenses don't count: BSL, SSPL, the Functional Source License, Commons Clause, "free for personal use", non-commercial licenses such as CC BY-NC, and custom licenses.
- If part of the app's code is under a license that isn't OSI-approved, the app is out.

### 2. A real GUI

- A desktop app for Windows, macOS or Linux. Any toolkit is fine, including Electron and Tauri.
- Or a self-hosted web app with a full web UI that you run on your own computer or server (Docker is fine). These get the Self-hosted badge. A web app only counts if the project offers no hosted or cloud version, which would break rule 4 anyway.
- Command-line tools, terminal UIs and apps you can only configure through files don't count.

### 3. A downloadable release

- A binary or installer, an app-store or package-manager listing, or a Flathub entry. "Build it from source" isn't enough.

### 4. Nothing for sale

The project sells nothing at all. Any one of these rules an app out:

- a Pro, Plus, Premium or other paid edition with extra features
- paid features, add-ons, plugins, sound libraries or assets sold by the project
- a trial
- a subscription
- paid cloud, sync or hosting, even optional, even on another platform
- an enterprise or business edition
- a paid license for commercial use
- ads inside the app
- official builds that you can only get by paying

These are fine:

- Donations, sponsorships, Patreon, Open Collective and merch, as long as they unlock nothing in the app now and can't later. Supporter keys that change nothing and "pay what you want" buttons with a free option both pass.
- Supporter perks that gate nothing in the app, such as early preview builds or a sponsor-only build with the same features.
- The same free app also sold in an app store, as a convenience.
- Ads on the project's website, including affiliate links to paid hosting.
- A company behind the app that sells a different product.
- Paid training, certification or support contracts.

### 5. Active

- A commit or release in the last 12 months. A weekly check flags listed apps whose repositories are archived or have gone quiet.

### 6. Replaces something paid

- It names 1 to 3 well-known paid products it replaces, and it does the main job of those products, not a small part of it.
- Apps that only replace free software don't qualify. A PDF reader, for example, competes with free readers that come with every system.

When a case is unclear, say so in your suggestion. The maintainer makes the call and records it with the app's evidence.

## Suggest an app

### The easy way: the issue form

[Open the "Suggest an app" form](https://github.com/RandyNorthrup/price-tag-zero/issues/new?template=add-app.yml). It asks for everything in the next section. A maintainer checks the evidence and adds the app.

### The pull request way

1. Add an entry to [`data/apps.yaml`](data/apps.yaml). Copying an existing entry is the quickest start; every field is explained at the top of the file.
2. Install the one dependency: `pip install -r requirements.txt` (Python 3.10 or newer).
3. Run `python scripts/build.py`. It regenerates README.md, REPLACES.md and the badges.
4. Run `python scripts/check.py` and fix anything it reports.
5. Commit the data change and the regenerated files together, and open a pull request. The template has the same checklist as the issue form.

CI runs both scripts, [awesome-lint](https://github.com/sindresorhus/awesome-lint) and a link check on every pull request.

Don't edit README.md, REPLACES.md or EXCLUDED.md by hand. They're generated from `data/`, and CI fails if they drift.

### Writing the entry

| Field | What to write |
| --- | --- |
| `id` | The name in lowercase-kebab-case, such as `db-browser-for-sqlite`. |
| `name` | The app's name as the project writes it. |
| `url` | The homepage. The README links here. |
| `repo` | The source repository. |
| `category` | One id from [`data/categories.yaml`](data/categories.yaml). |
| `description` | What it does, in plain words: 90 characters or fewer, ending with a period. Don't start with the app's name. |
| `replaces` | 1 to 3 paid products, by their common names. |
| `platforms` | Any of `windows`, `macos`, `linux`, `self-hosted`. |
| `portable` | `true` only if there's an official build that runs without installing. |
| `license` | The SPDX id from the LICENSE file, such as `GPL-3.0-or-later` or `MIT`. Use an SPDX expression for a choice of licenses: `MPL-2.0 OR LGPL-2.1`. |
| `last_release`, `last_activity`, `checked` | Dates as `YYYY-MM-DD`: the latest release, the latest commit or release, and the day you checked. |

Leave out `maintainer`. It marks apps made by this list's maintainer, which sit in their normal categories with a "maintainer's project" badge and pass exactly the same rules.

## The evidence to provide

Every entry keeps its proof in an `evidence` block. No evidence, no entry. The README doesn't show it, but reviewers and the weekly check use it.

| Field | What to give |
| --- | --- |
| `license_url` | A link to the LICENSE file in the repository. |
| `release_url` | A link to the latest downloadable release. Put its date in `last_release`. |
| `money` | The pages you checked for anything sold (pricing page, website, README, app-store listings) and what you found. For example: "https://example.org/pricing checked: no paid tier; donations through Open Collective unlock nothing." |
| `gui` | How you know it has a real GUI, such as screenshots in the README, on the website or in a store listing. |
| `license_note`, `release_note` | Optional notes, such as "GitHub repo is a mirror" or where the downloads live. |
| `github_license` | Optional. Only when GitHub's license detection disagrees with `license` (it often reports `NOASSERTION` for repos with several license files): write what GitHub reports, so the weekly check can spot a real change. |

## Report an app that broke the rules

Projects change. If a listed app starts selling something, adds ads, changes its license, loses its downloads or goes quiet, [open a report](https://github.com/RandyNorthrup/price-tag-zero/issues/new?template=report-app.yml) with links that show it. A maintainer re-checks the app. If it no longer passes, it moves to [Why isn't X here?](EXCLUDED.md) with the reason.

It works the other way too. If an app in EXCLUDED.md now passes, perhaps because it dropped a paid tier or moved to an OSI license, suggest it again with fresh evidence.

## How the repo works

- `data/apps.yaml` holds every listed app and its evidence. It's the single source of truth.
- `data/categories.yaml`, `data/excluded.yaml` and `data/gaps.yaml` hold the categories, the apps that were checked and not listed, and the paid apps with no passing replacement yet.
- `scripts/build.py` generates README.md, REPLACES.md, EXCLUDED.md and the badges in `assets/badges/`.
- `scripts/check.py` validates the data: the schema, required fields, OSI licenses, duplicates, categories and description length. With `--live` (and a `GITHUB_TOKEN`), it asks GitHub about every listed repository and flags archived or inactive repos and license changes. A weekly workflow runs it and opens an issue when something needs attention.

## Code of conduct

Everyone taking part agrees to the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing, you agree to release your contribution under [CC0-1.0](LICENSE).
