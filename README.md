# remote-legal-jobs-ca

A tiny, **profile-driven**, rule-based job aggregator. As shipped it surfaces
**remote, Canada-eligible legal & law-adjacent roles** from four free public job
APIs — but *what* it looks for lives in a single config file, so the same engine
can be pointed at any role family or company list.

It pulls postings, tags each by location and role, and puts the roles you care
about on top — while keeping everything else browsable. No LLM, no API keys, no
account.

## Why it's built this way

- **Deterministic & cheap.** Plain regex classification — no model calls, no
  cost, reproducible. You can read exactly why a job was tagged the way it was.
- **Business logic is separated from infrastructure.** The package (`jobfinder/`)
  is generic plumbing; the search definition lives in [`profile.yaml`](profile.yaml)
  and the company list in [`companies.yaml`](companies.yaml). Swap those two files
  to repurpose the tool — no code changes.
- **Nothing is hidden.** Roles outside the profile, and jobs that aren't
  Canada-eligible, are relegated to lower sections — never silently dropped.

## Architecture

```
profile.yaml   companies.yaml          <-  business: what & where to look
      │              │
      ▼              ▼
   scrape  ──►  classify  ──►  report  (shortlist.md)         <-  jobfinder/: infra
                          └─►  serve   (web UI at localhost:5050)
```

1. **scrape** — fetch postings into a local SQLite DB.
2. **classify** — tag each job: country (CA / remote / other), remote policy
   (remote-ca / remote-global / hybrid / onsite), Canada-eligibility, and a
   role tag from the active profile's families.
3. **report / serve** — read a Markdown shortlist, or browse and mark statuses
   in a small web UI. The "surfaced" view = any job that matched a profile family.

The infrastructure in `jobfinder/` contains no role-specific knowledge; it reads
families from the profile via a generic matching engine (`jobfinder/roles.py`).

## Sources (all free, no auth)

| Source | What | Endpoint |
|---|---|---|
| Greenhouse | Curated companies' public boards | `boards-api.greenhouse.io` |
| Lever | Curated companies' public boards | `api.lever.co` |
| Remotive | Remote jobs incl. a real **legal** category | `remotive.com/api/remote-jobs` |
| RemoteOK | Remote jobs (tech-skewed) | `remoteok.com/api` |

The two remote boards are firehoses, so they're filtered to Canada-eligible
postings at scrape time.

## Quickstart

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate     macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

python -m jobfinder.cli verify              # check curated slugs are live
python -m jobfinder.cli scrape --curated --apis
python -m jobfinder.cli classify
python -m jobfinder.cli report              # writes shortlist.md
python -m jobfinder.cli serve               # browse at http://127.0.0.1:5050
```

## Configuring the search

Two business-config files, no code required:

- **[`profile.yaml`](profile.yaml) — what to look for.** Defines the surfaced
  section `label`, the `location` lens (`canada` is implemented), and ordered
  role `families`. Each family has `keywords` (matched whole-word) and/or
  `patterns` (raw regex for precision), plus an optional `exclude` veto. The
  first family a title matches becomes its role tag; a title matching none is
  `other` (kept, not surfaced). Edit this to change *what* gets surfaced.
- **[`companies.yaml`](companies.yaml) — where to look.** Greenhouse/Lever
  company slugs. Add a `slug` + `platform`, then run
  `python -m jobfinder.cli verify` to confirm the board exists.

## Commands

| Command | Does |
|---|---|
| `scrape --curated` | Greenhouse + Lever from `companies.yaml` |
| `scrape --apis` | Remotive + RemoteOK (CA-filtered) |
| `scrape --source <name> [--companies a,b]` | one source / specific slugs |
| `verify [--tag X]` | confirm curated slugs are live |
| `classify [--force]` | tag country / remote / role |
| `report` | write `shortlist.md` |
| `serve [--host --port]` | web UI |
| `list [--view surfaced] [--status S] [--limit N]` | list in the terminal |
| `show <id>` · `status <id> <new>` | inspect / set a job's status |

## Privacy

Everything stored is a public job posting. The SQLite DB and generated
`shortlist.md` are git-ignored build artifacts; only code and config are
committed. All data sources are public and keyless — there are no credentials
in this repo.

## Not yet (possible later)

Light/part-time intensity scoring (the data is captured at scrape time as a
hook), additional location lenses beyond Canada, LLM enrichment, résumé
tailoring, full application tracking, and more ATS integrations (Ashby/Workday).

## License

[MIT](LICENSE)
