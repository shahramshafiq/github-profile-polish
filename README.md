<div align="center">

# GitHub Profile Polish

A Claude Code skill that audits your GitHub account and fixes it up so recruiters are impressed.

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Dependencies](https://img.shields.io/badge/Dependencies-none-2E7D32?style=flat-square)
![Claude Code](https://img.shields.io/badge/Claude%20Code-skill-D97757?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)

</div>

## Overview

Recruiters read your resume, then open your GitHub. Most student accounts have random repo names, empty descriptions, missing READMEs and the occasional leaked key. This skill scores every repo, finds the problems, and walks Claude through fixing them to one consistent standard, from repo names to the profile README and pinned projects.

A small Python CLI (`scripts/gpp.py`, standard library only) does the mechanical work. Claude only spends effort where judgment matters: reading your code and writing honest READMEs.

## Key Features

- **Recruiter-readiness audit:** scores every public repo out of 100 on description, topics, README depth and structure, naming, freshness and more.
- **Leak scan:** secrets, personal data (emails, phone numbers), junk and build artifacts, oversized files, missing `.gitignore`, stale repo-name links, plus your own list of terms that must never appear (employer names, codenames) in files, history and commit messages. Secret values are never printed.
- **Naming plan:** suggests lowercase kebab-case names and warns about repos with live URLs.
- **README linter and template:** one consistent structure for every repo, checked for sections, badges, broken links and marketing filler.
- **One-command finalize:** commits the README, renames the repo, sets description, topics and homepage, turns off empty Wiki and Projects tabs.
- **Profile README generator:** builds a clean profile README from a small JSON file.
- **Build-order sorting:** makes the Repositories tab show your work in the order you built it, without adding commits.
- **Safe history purge:** removes a file from history with a verified backup bundle first, and never pushes for you.
- **Guardrails:** no deletions, no force-pushes and no invented README facts without your say-so.

## Tech Stack

| Area | Technology |
|---|---|
| CLI | Python 3.9+ standard library |
| GitHub access | GitHub CLI (`gh`) |
| Git operations | `git` |
| Optional | `gitleaks` for deeper history scans |
| Agent | Claude Code skill (`SKILL.md`) |

## Project Structure

```text
github-profile-polish/
  SKILL.md                      Instructions Claude follows
  scripts/gpp.py                The CLI: audit, scan, lint, names, finalize, order, profile, purge
  templates/README_TEMPLATE.md  The README standard
  examples/                     Config and profile JSON examples
  tests/test_gpp.py             Unit tests
  docs/index.html               Landing page
```

## Getting Started

### Prerequisites

- [Claude Code](https://claude.com/claude-code) (CLI or desktop app)
- [Git](https://git-scm.com) and the [GitHub CLI](https://cli.github.com), signed in with `gh auth login`
- Python 3.9 or newer

### Installation

Install the skill by cloning it into your Claude skills folder.

macOS or Linux:

```bash
git clone https://github.com/shahramshafiq/github-profile-polish ~/.claude/skills/github-profile-polish
```

Windows (PowerShell):

```powershell
git clone https://github.com/shahramshafiq/github-profile-polish $env:USERPROFILE\.claude\skills\github-profile-polish
```

Update later with `git pull` inside that folder.

### Run

Open Claude Code and say one of these:

```text
/github-profile-polish
polish my GitHub
finalize my repo my-new-project
```

Claude audits your account, shows you the plan, and asks before anything risky such as renames. You can also use the CLI directly:

```bash
python scripts/gpp.py audit                      # score every public repo
python scripts/gpp.py scan --clone-all --history # leak and hygiene scan
python scripts/gpp.py names                      # suggested repo names
python scripts/gpp.py lint README.md             # check a README
python scripts/gpp.py profile profile.json       # build the profile README
```

## Usage

Copy `examples/gpp.config.example.json` to `gpp.config.json` and list anything that must never appear publicly:

```json
{ "forbidden_terms": ["Your Employer Name", "internal-codename"] }
```

Sample audit output:

```text
Average score: 93 / 100 across 19 repos
| Repo | Score | What to fix |
| chw-report-agent | 80 | set a one-line description; add a license |
```

`gh` cannot edit your bio, pins or avatar. If Claude has a browser tool and you are signed in to GitHub, it can do those steps for you. Otherwise it gives you exact manual steps.

## Testing

```bash
python -m unittest discover -s tests
```

## Limitations and Roadmap

- Scores are a guide, not a verdict: some checks (for example a license) are your decision.
- Pins, avatar and bio need a signed-in browser; there is no GitHub API for them.
- Secret and personal-data detection is pattern based. Run `gitleaks` for a deeper history scan.
- The audit covers public repos and skips forks unless you pass `--include-forks`.

## Author

**Shahram Shafiq** - [GitHub](https://github.com/shahramshafiq) | [LinkedIn](https://www.linkedin.com/in/shahramshafiq/)
