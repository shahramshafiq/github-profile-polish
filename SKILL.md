---
name: github-profile-polish
description: "Audit and polish a GitHub account so recruiters are impressed: score every repo, scan for leaked secrets and personal data, fix names, descriptions, topics and READMEs to one consistent standard, build the profile README, order and pin repos. Use when the user says polish my GitHub, organize my repos, make my GitHub recruiter-ready, or finalize a repo they just finished."
---

# github-profile-polish

Turns a messy GitHub account into a consistent, recruiter-ready one. A Python CLI (`scripts/gpp.py`, standard library only) does the mechanical work, so Claude only spends effort on the parts that need judgment: reading code and writing honest READMEs.

Two modes. Pick from the request, ask one short question if unclear:
- **Whole account:** audit, scan, rename plan, fix every repo, profile README, pins.
- **One repo:** the user just finished a project; finalize that repo only.

Run commands as `python <skill-dir>/scripts/gpp.py <subcommand>`. Needs `git` and `gh` (logged in). Config is optional: copy `examples/gpp.config.example.json` to `gpp.config.json` and set `forbidden_terms` (employer names, internal codenames, anything that must never appear in public repos).

## Ground rules

1. Never delete a repo, change visibility, or force-push unless the user explicitly asks in chat. Always show the plan first for renames.
2. Never invent README facts. Every feature, command, file name and environment variable must be checked against the code.
3. Never print secret values. If a leaked token is found, tell the user to revoke it (GitHub: Settings, Developer settings, Tokens) and remove it from remotes and files.
4. Do not rename a repo that has a live deployment URL tied to it (GitHub Pages, Streamlit Cloud) or that other people link to. Flag it instead; GitHub redirects old URLs, but deployments can break.
5. Commits are authored as the user with their own git identity and no co-author trailer unless the user asks for one.
6. Keep token use low: use the CLI, not sub-agents, unless the user asks for parallel agents.

## Whole-account workflow

1. **Setup.** `gh auth status` must show the user's account. Ask for forbidden terms (employer names etc.) and write `gpp.config.json`.
2. **Audit.** `gpp.py audit --md audit.md` scores every public repo out of 100 (description, topics, README presence, depth and template sections, text rules, name, freshness, tabs, license). Show the average and the worst repos.
3. **Scan.** `gpp.py scan --clone-all --history` clones public repos and checks for secrets, personal data (emails, phone numbers), junk and build artifacts, large files, missing `.gitignore`, stale repo-name references, and every forbidden term in files, history and commit messages. Uses gitleaks too if installed.
4. **Plan names.** `gpp.py names` proposes kebab-case names (lowercase, 2-4 words, no filler). Present the rename map, mark fragile repos, wait for approval.
5. **Fix each repo** (inline, one at a time):
   - Read the tree, entry points, dependency files and existing README.
   - Write a README from `templates/README_TEMPLATE.md`, facts only. Check with `gpp.py lint README.md`.
   - Safe cleanups in one commit: add a real `.gitignore`, delete clearly generated junk, replace personal data in sample files.
   - `gpp.py finalize --repo OLD --new-name NEW --description "..." --topics a,b,c,d,e --readme README.md` commits, pushes, renames, sets description (40-110 chars, no trailing period), 5-8 topics and homepage, and turns off the empty Wiki and Projects tabs. Run it with `--dry-run` first.
6. **Profile README.** Copy `examples/profile.example.json`, fill it with the user's real skills (each backed by a repo), run `gpp.py profile profile.json --out README.md --push`. Keep it to intro, About with skills learned, toolbox table. No long project list: pinned repos do that job.
7. **Profile settings, pins, avatar.** `gh` cannot edit these. If a browser tool is available (Claude in Chrome or similar) and the user is signed in: edit bio, website and location at github.com/settings/profile; upload the avatar by setting the file input; open "Customize your pins" on the profile and tick up to six flagship repos by script (select checkboxes by label, not by coordinates, because the list re-sorts after each click); reorder with the per-card up and down buttons (`button[data-direction="up"|"down"]` inside `.js-pinned-items-reorder-form`). Otherwise give the user exact manual steps.
8. **Order.** `gpp.py order --repos <clones dir>` pushes and deletes a temporary branch in each repo oldest first so the Repositories tab shows newest work on top. No commits are added. Redo after any later push.
9. **Report.** Run `gpp.py audit` again and show before and after scores plus anything left for the user to decide (licenses, large media, history clean-ups).

## One-repo workflow

Steps 5 and 6 above for a single repo, then a quick `audit`. If it is a flagship project, offer to pin it.

## History clean-ups (only with explicit approval)

`gpp.py purge --repo DIR --path FILE` lists commits touching a file (dry run). With `--confirm --backup-dir DIR` it makes and verifies a backup bundle, rewrites local history to remove the path, and prints the push command. It never pushes. Rewriting history changes commit IDs and makes other clones diverge, so warn the user, and skip repos whose documents cite specific commit IDs.

## Standards

- Names: lowercase kebab-case, `<subject>-<what-it-is>` or a brand name.
- README order: header block, Overview, Demo (only with real media), Key Features, Tech Stack, Project Structure, Getting Started, Usage, Testing, Limitations and Roadmap, Author.
- Text: plain ASCII, no marketing filler (powerful, seamless, robust, cutting-edge).
