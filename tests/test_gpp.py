import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gpp  # noqa: E402

CFG = dict(gpp.DEFAULTS, forbidden_terms=["Acme Corp"])

GOOD = """<div align="center">

# Demo Project

Does one thing well.

![a](https://img.shields.io/badge/a-b-green)
![b](https://img.shields.io/badge/b-c-green)
![c](https://img.shields.io/badge/c-d-green)

</div>

## Overview
text
## Key Features
- x
## Tech Stack
| a | b |
## Project Structure
text
## Getting Started
text
"""


class Slug(unittest.TestCase):
    def test_drops_filler_words(self):
        self.assertEqual(gpp.slugify("Railway-Management-System-using-Data-Structures", CFG["filler_words"]),
                         "railway-management-data-structures")

    def test_camel_case_and_symbols(self):
        self.assertEqual(gpp.slugify("myCoolApp_v2", CFG["filler_words"]), "my-cool-app-v2")

    def test_never_returns_empty(self):
        self.assertEqual(gpp.slugify("The-System", CFG["filler_words"]), "the-system")


class Lint(unittest.TestCase):
    def test_good_readme_passes(self):
        self.assertEqual(gpp.lint_readme(GOOD, CFG), [])

    def test_catches_problems(self):
        bad = GOOD.replace("## Overview", "## About").replace("Does one thing", "A powerful tool by Acme Corp \u2014 it")
        probs = gpp.lint_readme(bad, CFG)
        joined = " | ".join(probs)
        self.assertIn("missing section: Overview", joined)
        self.assertIn("non-ASCII", joined)
        self.assertIn("forbidden term: Acme Corp", joined)
        self.assertIn("marketing word: powerful", joined)

    def test_broken_relative_link(self):
        probs = gpp.lint_readme(GOOD + "\n![x](nope.png)\n", CFG, root=str(Path(__file__).parent))
        self.assertTrue(any("broken relative link" in p for p in probs))


class Detectors(unittest.TestCase):
    def test_secret_detection_without_real_keys(self):
        fake = "ghp_" + "a" * 36
        self.assertIn("github token", gpp.find_secrets("token = " + fake))
        self.assertIn("token in git remote", gpp.find_secrets("https://user:" + "b" * 30 + "@github.com/x/y.git"))
        self.assertEqual(gpp.find_secrets("nothing to see"), [])
        self.assertEqual(gpp.find_secrets('API_KEY = "your-api-key-goes-here-123"'), [])
        self.assertIn("secret assignment", gpp.find_secrets('API_KEY = "Zk39sdf8sdf7sdf6sdf5sdf4"'))

    def test_pii(self):
        self.assertEqual(gpp.find_pii("mail me@example.com or noreply@github.com"), [])
        self.assertTrue(gpp.find_pii("contact jane.doe@gmail.com"))
        self.assertTrue(gpp.find_pii("call +92 300 1234567"))
        self.assertEqual(gpp.find_pii("version 3.14.159265"), [])

    def test_badge_escaping(self):
        url = gpp.badge("Open to", "work-now", "0A66C2", "linkedin")
        self.assertIn("Open%20to-work--now-0A66C2", url)
        self.assertIn("logo=linkedin", url)


if __name__ == "__main__":
    unittest.main()
