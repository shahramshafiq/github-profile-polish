#!/usr/bin/env python3
"""github-profile-polish (gpp): audit and polish a GitHub account for recruiters.

Subcommands:
  audit     score every public repo (description, topics, README, naming ...)
  scan      scan local clones for secrets, personal data, junk, big files, custom terms
  lint      check README files against the template rules
  names     suggest consistent kebab-case repo names
  finalize  commit a README, rename, set description/topics for ONE repo
  order     push and delete a temp branch so the Repositories tab shows build order
  profile   generate the profile README from a small JSON file
  purge     remove files from git history (backup first, explicit --confirm)

Needs git and the GitHub CLI (gh, logged in). Optional: gitleaks. No other dependencies.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULTS = {
    "owner": None,
    "forbidden_terms": [],
    "filler_words": ["using", "in", "of", "the", "a", "an", "and", "for", "with", "system"],
    "description_min": 40,
    "description_max": 110,
    "topics_min": 5,
    "topics_max": 8,
    "ascii_only": True,
    "readme_sections": ["Overview", "Key Features", "Tech Stack", "Project Structure", "Getting Started"],
    "stale_months": 18,
    "ignore_repos": [],
}
KEBAB = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*$")
BANNED_WORDS = ["powerful", "seamless", "cutting-edge", "robust", "leverage", "revolutionary",
                "state-of-the-art", "blazing", "effortless"]
SECRETS = {
    "github token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "aws access key": r"AKIA[0-9A-Z]{16}",
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "slack token": r"xox[baprs]-[A-Za-z0-9-]{10,}",
    "openai-style key": r"sk-[A-Za-z0-9]{20,}",
    "google api key": r"AIza[0-9A-Za-z_-]{35}",
    "token in git remote": r"https://[^\s:@/]+:[^\s@/]{20,}@github\.com",
    "secret assignment": r"(?i)(?:api[_-]?key|secret|token|passwd|password)\s*[:=]\s*['\"][A-Za-z0-9_\-/+=]{16,}['\"]",
}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[a-z]{2,}")
PHONE = re.compile(r"(?<![\d.])(?:\+\d{1,3}[ -]?\d{2,4}[ -]?\d{6,8}|0\d{3}[ -]?\d{7})(?![\d.])")
JUNK_PARTS = ["__pycache__/", ".pyc", ".class", "/node_modules/", "node_modules/", ".DS_Store", "Thumbs.db",
              ".idea/", ".vs/", "/bin/Debug/", "/obj/", ".ipynb_checkpoints/"]
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".mp4", ".wav", ".mp3", ".pdf", ".zip", ".ico", ".woff", ".woff2",
            ".ttf", ".otf", ".exe", ".dll", ".jar", ".bin", ".sqlite3", ".pickle", ".pyc", ".class", ".so"}


def load_config(path=None):
    cfg = dict(DEFAULTS)
    for p in [path, "gpp.config.json", str(Path.home() / ".github-profile-polish.json")]:
        if p and Path(p).is_file():
            cfg.update(json.loads(Path(p).read_text(encoding="utf-8")))
            break
    return cfg


def sh(args, cwd=None, check=True):
    r = subprocess.run(args, cwd=cwd, text=True, capture_output=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        sys.exit("command failed: " + " ".join(args) + "\n" + r.stdout + r.stderr)
    return r.stdout.strip()


def gh_json(args):
    return json.loads(sh(["gh"] + args) or "null")


def get_owner(cfg):
    return cfg["owner"] or sh(["gh", "api", "user", "--jq", ".login"])


# ---------- pure helpers (unit tested) ----------
def slugify(name, fillers):
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
    words = [w.lower() for w in re.split(r"[^A-Za-z0-9]+", s) if w]
    kept = [w for w in words if w not in fillers]
    return "-".join(kept or words)


def lint_readme(text, cfg, root=None):
    probs = []
    if cfg["ascii_only"]:
        bad = sorted({c for c in text if ord(c) > 127})
        if bad:
            probs.append("non-ASCII characters: " + "".join(bad[:10]))
    for t in cfg["forbidden_terms"]:
        if re.search(re.escape(t), text, re.I):
            probs.append("forbidden term: " + t)
    for w in BANNED_WORDS:
        if re.search(r"\b" + re.escape(w) + r"\b", text, re.I):
            probs.append("marketing word: " + w)
    heads = [h.strip().lower() for h in re.findall(r"^##\s+(.+)$", text, re.M)]
    pos = -1
    for s in cfg["readme_sections"]:
        if s.lower() not in heads:
            probs.append("missing section: " + s)
        elif heads.index(s.lower()) < pos:
            probs.append("section out of order: " + s)
        else:
            pos = heads.index(s.lower())
    if not re.match(r'\s*<div align="center">', text) or not re.search(r"^#\s+\S", text, re.M):
        probs.append("missing centered header block with an H1 title")
    n = len(re.findall(r"img\.shields\.io", text))
    if n < 3:
        probs.append("add 3-5 shields.io badges (found %d)" % n)
    if root:
        for m in re.finditer(r"!?\[[^\]]*\]\(([^)\s]+)\)", text):
            u = m.group(1)
            if re.match(r"(https?:|mailto:|#)", u):
                continue
            p = Path(root) / re.sub(r"%20", " ", u.split("#")[0])
            if not p.exists():
                probs.append("broken relative link: " + u)
    return probs


PLACEHOLDER = re.compile(r"your|xxx|example|changeme|placeholder|<|\*\*\*|dummy|sample", re.I)


def find_secrets(text):
    out = []
    for k, rx in SECRETS.items():
        for m in re.finditer(rx, text):
            if k == "secret assignment" and PLACEHOLDER.search(m.group(0)):
                continue
            out.append(k)
            break
    return out


def find_pii(text):
    out = []
    for e in EMAIL.findall(text):
        if not re.search(r"example\.(com|org)|noreply|users\.noreply", e, re.I):
            out.append("email " + e)
    out += ["phone " + p for p in PHONE.findall(text)]
    return out


def badge(label, message, color, logo=None):
    esc = lambda s: s.replace("-", "--").replace("_", "__").replace(" ", "%20")
    url = "https://img.shields.io/badge/%s-%s-%s?style=flat-square" % (esc(label), esc(message), color)
    if logo:
        url += "&logo=%s&logoColor=white" % logo
    return url


# ---------- subcommands ----------
def cmd_audit(a, cfg):
    o = get_owner(cfg)
    fields = "name,description,repositoryTopics,homepageUrl,licenseInfo,pushedAt,isFork,isArchived,visibility,hasWikiEnabled,hasProjectsEnabled"
    repos = gh_json(["repo", "list", o, "--limit", "300", "--json", fields])
    rows = []
    now = datetime.now(timezone.utc)
    for r in repos:
        if r["name"] in cfg["ignore_repos"] or r["name"] == o:
            continue
        if r["visibility"] != "PUBLIC" and not a.include_private:
            continue
        if r["isFork"] and not a.include_forks:
            continue
        readme = sh(["gh", "api", "repos/%s/%s/readme" % (o, r["name"]), "-H", "Accept: application/vnd.github.raw"], check=False)
        desc = r["description"] or ""
        topics = [t["name"] for t in (r["repositoryTopics"] or [])]
        age = (now - datetime.fromisoformat(r["pushedAt"].replace("Z", "+00:00"))).days / 30.4
        text_probs = lint_readme(readme, cfg) if readme else []
        sec_miss = [p for p in text_probs if p.startswith("missing section") or p.startswith("section out")]
        other = [p for p in text_probs if p not in sec_miss and not p.startswith("add 3-5") and not p.startswith("missing centered")]
        checks = [
            ("description", 15, cfg["description_min"] <= len(desc) <= cfg["description_max"] and not desc.endswith("."),
             "set a one-line description (%d-%d chars, no trailing period)" % (cfg["description_min"], cfg["description_max"])),
            ("topics", 10, cfg["topics_min"] <= len(topics) <= cfg["topics_max"],
             "set %d-%d topics" % (cfg["topics_min"], cfg["topics_max"])),
            ("readme", 10, bool(readme), "add a README"),
            ("readme depth", 10, len(readme) >= 1500, "expand the README (overview, setup, structure)"),
            ("readme sections", 20, bool(readme) and not sec_miss and not any("header" in p or "badges" in p for p in text_probs),
             "follow the README template sections"),
            ("text rules", 10, bool(readme) and not other, "fix text rules: " + "; ".join(other[:2])),
            ("name", 10, bool(KEBAB.match(r["name"])) and len(r["name"].split("-")) <= 5, "rename to short lowercase kebab-case"),
            ("fresh", 5, age <= cfg["stale_months"], "repo looks stale"),
            ("tabs", 5, not r["hasWikiEnabled"] and not r["hasProjectsEnabled"], "turn off empty Wiki and Projects tabs"),
            ("license", 5, bool(r["licenseInfo"]), "add a license (your call)"),
        ]
        score = sum(w for _, w, ok, _ in checks if ok)
        rows.append({"repo": r["name"], "score": score, "fix": [f for _, _, ok, f in checks if not ok]})
    rows.sort(key=lambda x: x["score"])
    avg = sum(x["score"] for x in rows) / max(len(rows), 1)
    lines = ["# GitHub audit for %s" % o, "", "Average score: %.0f / 100 across %d repos" % (avg, len(rows)), "",
             "| Repo | Score | What to fix |", "|---|---|---|"]
    for x in rows:
        lines.append("| %s | %d | %s |" % (x["repo"], x["score"], "; ".join(x["fix"]) or "nothing"))
    out = "\n".join(lines)
    print(out)
    if a.md:
        Path(a.md).write_text(out + "\n", encoding="utf-8")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=2), encoding="utf-8")


def clone_all(o, workdir):
    Path(workdir).mkdir(parents=True, exist_ok=True)
    for r in gh_json(["repo", "list", o, "--limit", "300", "--json", "name,visibility,isFork"]):
        if r["visibility"] == "PUBLIC" and not r["isFork"]:
            d = Path(workdir) / r["name"][:40]
            if not d.exists():
                sh(["gh", "repo", "clone", "%s/%s" % (o, r["name"]), str(d), "--", "--quiet", "--no-tags"], check=False)
    return workdir


def repo_dirs(path):
    p = Path(path)
    return [p] if (p / ".git").exists() else sorted(d for d in p.iterdir() if (d / ".git").exists())


def cmd_scan(a, cfg):
    o = get_owner(cfg)
    base = clone_all(o, a.workdir) if a.clone_all else a.repos
    if not base:
        sys.exit("give --repos DIR or --clone-all")
    names = {r["name"].lower() for r in gh_json(["repo", "list", o, "--limit", "300", "--json", "name"])}
    gl = shutil.which("gitleaks")
    total = 0
    for d in repo_dirs(base):
        f = []
        files = sh(["git", "ls-files", "-z"], d).split("\0")
        if not (d / ".gitignore").exists():
            f.append(("medium", "no .gitignore"))
        for rel in filter(None, files):
            fp = d / rel
            try:
                size = fp.stat().st_size
            except OSError:
                continue
            if any(j in "/" + rel for j in JUNK_PARTS):
                f.append(("low", "junk or build artifact: " + rel))
            if size > 5 * 1024 * 1024:
                f.append(("medium", "large file %.1f MB: %s" % (size / 1048576, rel)))
            if fp.suffix.lower() in SKIP_EXT or size > 1024 * 1024:
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for k in find_secrets(text):
                f.append(("high", "possible %s in %s" % (k, rel)))
            if not rel.lower().startswith(("package-lock", "poetry.lock")):
                for p in find_pii(text)[:3]:
                    f.append(("medium", "personal data (%s) in %s" % (p, rel)))
            for t in cfg["forbidden_terms"]:
                if re.search(re.escape(t), text, re.I):
                    f.append(("high", "forbidden term '%s' in %s" % (t, rel)))
            for m in re.finditer(r"github\.com/%s/([A-Za-z0-9._-]+)" % re.escape(o), text):
                n = m.group(1).rstrip(".").lower().removesuffix(".git")
                if n not in names and n != o.lower():
                    f.append(("low", "stale repo reference '%s' in %s" % (n, rel)))
        if a.history and cfg["forbidden_terms"]:
            rx = "|".join(re.escape(t) for t in cfg["forbidden_terms"])
            hist = sh(["git", "log", "--all", "-i", "-G" + rx, "--name-only", "--format="], d, check=False).split("\n")
            msgs = sh(["git", "log", "--all", "-i", "-E", "--grep=" + rx, "--format=%h %s"], d, check=False).split("\n")
            for h in sorted({x for x in hist if x}):
                f.append(("high", "forbidden term appears in history of " + h))
            for m in [x for x in msgs if x]:
                f.append(("high", "forbidden term in commit message: " + m))
        if gl and a.history:
            rep = Path(tempfile.gettempdir()) / "gpp-gitleaks.json"
            sh([gl, "detect", "--source", str(d), "--redact", "--no-banner", "--exit-code", "0",
                "--report-format", "json", "--report-path", str(rep)], check=False)
            try:
                for x in json.loads(rep.read_text(encoding="utf-8")):
                    f.append(("high", "gitleaks %s in history: %s" % (x.get("RuleID"), x.get("File"))))
            except (OSError, ValueError):
                pass
        seen = set()
        f = [x for x in f if not (x in seen or seen.add(x))]
        total += len(f)
        print("== %s: %s" % (d.name, "clean" if not f else "%d finding(s)" % len(f)))
        for sev, msg in sorted(f, key=lambda x: ["high", "medium", "low"].index(x[0]))[:25]:
            print("   [%s] %s" % (sev, msg))
    print("\nTotal findings: %d (secret values are never printed)" % total)


def cmd_lint(a, cfg):
    bad = 0
    for p in a.files:
        probs = lint_readme(Path(p).read_text(encoding="utf-8"), cfg, root=str(Path(p).parent))
        print("%s: %s" % (p, "OK" if not probs else "%d problem(s)" % len(probs)))
        for x in probs:
            print("   -", x)
        bad += bool(probs)
    sys.exit(1 if bad else 0)


def cmd_names(a, cfg):
    o = get_owner(cfg)
    names = a.names or [r["name"] for r in gh_json(["repo", "list", o, "--limit", "300", "--json", "name"]) if r["name"] != o]
    taken = {n.lower() for n in names}
    print("| Current | Suggested | Notes |\n|---|---|---|")
    for n in names:
        s = slugify(n, cfg["filler_words"])
        notes = []
        if s == n:
            continue
        if len(s.split("-")) > 4:
            notes.append("still long, shorten by hand")
        if s in taken:
            notes.append("name collision")
        pages = sh(["gh", "api", "repos/%s/%s/pages" % (o, n), "--jq", ".html_url"], check=False) if not a.names else ""
        if pages.startswith("http"):
            notes.append("has GitHub Pages: renaming changes the URL")
        print("| %s | %s | %s |" % (n, s, "; ".join(notes)))


def cmd_finalize(a, cfg):
    o = get_owner(cfg)
    new = a.new_name or a.repo
    topics = [t.strip() for t in a.topics.split(",") if t.strip()]
    readme = Path(a.readme).read_text(encoding="utf-8")
    probs = lint_readme(readme, cfg)
    if not (cfg["description_min"] <= len(a.description) <= cfg["description_max"]) or a.description.endswith("."):
        probs.append("description length or trailing period")
    if not (cfg["topics_min"] <= len(topics) <= cfg["topics_max"]) or not all(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,49}", t) for t in topics):
        probs.append("topics invalid")
    if new != a.repo and not KEBAB.match(new):
        probs.append("new name must be kebab-case")
    if probs:
        sys.exit("Fix first:\n- " + "\n- ".join(probs))
    if a.dry_run:
        print("dry run OK, nothing touched")
        return
    clone = os.path.join(tempfile.mkdtemp(prefix="gpp-"), "r")
    sh(["gh", "repo", "clone", "%s/%s" % (o, a.repo), clone])
    for f in sh(["git", "ls-files"], clone).splitlines():
        if re.fullmatch(r"(?i)readme(\.(md|txt|markdown))?", f) and f != "README.md":
            sh(["git", "rm", "-q", f], clone)
    Path(clone, "README.md").write_text(readme, encoding="utf-8", newline="\n")
    sh(["git", "add", "README.md"], clone)
    if sh(["git", "diff", "--cached", "--name-only"], clone):
        sh(["git", "commit", "-q", "-m", "docs: update README"], clone)
        sh(["git", "push", "-q", "origin", "HEAD"], clone)
        print("README pushed")
    if new != a.repo:
        sh(["gh", "api", "-X", "PATCH", "repos/%s/%s" % (o, a.repo), "-f", "name=" + new])
        print("renamed to", new)
    args = ["gh", "api", "-X", "PATCH", "repos/%s/%s" % (o, new), "-f", "description=" + a.description,
            "-F", "has_wiki=false", "-F", "has_projects=false"]
    if a.homepage:
        args += ["-f", "homepage=" + a.homepage]
    sh(args)
    sh(["gh", "api", "-X", "PUT", "repos/%s/%s/topics" % (o, new)] + sum([["-f", "names[]=" + t] for t in topics], []))
    print("description and topics set")


def cmd_order(a, cfg):
    dirs = repo_dirs(a.repos)
    if a.order:
        dirs = [Path(a.repos) / n for n in a.order.split(",")]
    else:
        dirs.sort(key=lambda d: int(sh(["git", "log", "--reverse", "--format=%at"], d).splitlines()[0]))
    print("order, oldest first (newest ends on top of the Repositories tab):")
    for d in dirs:
        print("  ", d.name)
    if a.dry_run:
        return
    import time
    for d in dirs:
        sh(["git", "push", "-q", "origin", "HEAD:refs/heads/zz-order"], d, check=False)
        sh(["git", "push", "-q", "origin", "--delete", "zz-order"], d, check=False)
        time.sleep(1.3)
    print("done; no commits were added")


def cmd_profile(a, cfg):
    p = json.loads(Path(a.config_file).read_text(encoding="utf-8"))
    o = p.get("owner") or get_owner(cfg)
    out = ['<div align="center">', "", "# " + p["name"], "", "**%s**" % p["headline"], "", p["summary"], ""]
    for b in p.get("badges", []):
        out.append("[![%s](%s)](%s)" % (b["label"], badge(b["label"], b["message"], b.get("color", "111827"), b.get("logo")), b["url"]))
    out += ["", "</div>", "", "## About", "", p["about_intro"], ""]
    out += ["- " + x for x in p.get("about_bullets", [])]
    out += ["", "## Toolbox", "", "| Area | Technologies |", "|---|---|"]
    out += ["| %s | %s |" % (k, ", ".join(v)) for k, v in p.get("toolbox", {}).items()]
    if p.get("show_languages_card", True):
        out += ["", '<p align="center">',
                '  <img height="150" alt="Top languages" src="https://github-readme-stats.vercel.app/api/top-langs/?username=%s&layout=compact&theme=transparent&title_color=0969da&text_color=6e7681&hide_border=true" />' % o,
                "</p>"]
    text = "\n".join(out) + "\n"
    probs = lint_readme(text, dict(cfg, readme_sections=[]))
    probs = [x for x in probs if "shields" not in x]
    if probs:
        sys.exit("Fix first:\n- " + "\n- ".join(probs))
    dest = Path(a.out)
    dest.write_text(text, encoding="utf-8", newline="\n")
    print("wrote", dest)
    if a.push:
        clone = os.path.join(tempfile.mkdtemp(prefix="gpp-"), "r")
        sh(["gh", "repo", "clone", "%s/%s" % (o, o), clone])
        shutil.copy(dest, Path(clone, "README.md"))
        sh(["git", "add", "README.md"], clone)
        if sh(["git", "diff", "--cached", "--name-only"], clone):
            sh(["git", "commit", "-q", "-m", "docs: update profile README"], clone)
            sh(["git", "push", "-q", "origin", "HEAD"], clone)
            print("pushed to %s/%s" % (o, o))


def cmd_purge(a, cfg):
    d = Path(a.repo)
    branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], d)
    hits = sh(["git", "log", "--all", "--format=%h %s", "--"] + a.path, d).splitlines()
    print("%d commit(s) touch %s:" % (len(hits), ", ".join(a.path)))
    for h in hits[:20]:
        print("  ", h)
    if not a.confirm:
        print("\ndry run. Re-run with --confirm --backup-dir DIR to rewrite local history. It will NOT push.")
        return
    if not a.backup_dir:
        sys.exit("--backup-dir is required with --confirm")
    Path(a.backup_dir).mkdir(parents=True, exist_ok=True)
    bundle = Path(a.backup_dir) / (d.resolve().name + "-before-purge.bundle")
    sh(["git", "bundle", "create", str(bundle), "--all"], d)
    sh(["git", "bundle", "verify", str(bundle)], d)
    print("backup verified:", bundle)
    rm = " ".join("'%s'" % p for p in a.path)
    env = dict(os.environ, FILTER_BRANCH_SQUELCH_WARNING="1")
    subprocess.run(["git", "filter-branch", "-f", "--index-filter",
                    "git rm -r --cached --ignore-unmatch -q " + rm, "--prune-empty", "--", "--branches"],
                   cwd=d, env=env, check=True, capture_output=True)
    for ref in sh(["git", "for-each-ref", "--format=%(refname)", "refs/original"], d).splitlines():
        sh(["git", "update-ref", "-d", ref], d)
    left = sh(["git", "log", "--branches", "--format=%h", "--"] + a.path, d)
    print("rewritten locally; remaining commits touching those paths:", len(left.splitlines()))
    print("Review it, then publish with: git push --force origin HEAD:%s   (needs your explicit decision)" % branch)


def main():
    ap = argparse.ArgumentParser(prog="gpp", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("audit"); s.add_argument("--md"); s.add_argument("--json")
    s.add_argument("--include-private", action="store_true"); s.add_argument("--include-forks", action="store_true")
    s = sub.add_parser("scan"); s.add_argument("--repos"); s.add_argument("--clone-all", action="store_true")
    s.add_argument("--workdir", default=str(Path(tempfile.gettempdir()) / "gpp-clones")); s.add_argument("--history", action="store_true")
    s = sub.add_parser("lint"); s.add_argument("files", nargs="+")
    s = sub.add_parser("names"); s.add_argument("names", nargs="*")
    s = sub.add_parser("finalize"); s.add_argument("--repo", required=True); s.add_argument("--new-name")
    s.add_argument("--description", required=True); s.add_argument("--topics", required=True)
    s.add_argument("--readme", required=True); s.add_argument("--homepage", default=""); s.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("order"); s.add_argument("--repos", required=True); s.add_argument("--order")
    s.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("profile"); s.add_argument("config_file"); s.add_argument("--out", default="README.md")
    s.add_argument("--push", action="store_true")
    s = sub.add_parser("purge"); s.add_argument("--repo", required=True); s.add_argument("--path", action="append", required=True)
    s.add_argument("--backup-dir"); s.add_argument("--confirm", action="store_true")
    a = ap.parse_args()
    cfg = load_config(a.config)
    globals()["cmd_" + a.cmd](a, cfg)


if __name__ == "__main__":
    main()
