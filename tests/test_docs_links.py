import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def github_slug(heading):
    text = heading.strip().lower()
    # Strip inline markdown formatting like *italics* or `code`
    text = re.sub(r"[`*]", "", text)
    # Keep unicode letters/digits, spaces, and hyphens (GitHub Flavored Markdown rules)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text


def heading_anchors(md_path):
    content = md_path.read_text(encoding="utf-8")
    counts = {}
    anchors = set()
    for match in HEADING_RE.finditer(content):
        base = github_slug(match.group(2))
        seen = counts.get(base, 0)
        counts[base] = seen + 1
        anchors.add(base if seen == 0 else f"{base}-{seen}")
    return anchors


class DocsLinksTests(unittest.TestCase):
    def test_all_local_markdown_links_and_anchors_exist(self):
        md_files = list(ROOT.glob("*.md")) + list((ROOT / "packaging").glob("*.md"))
        broken = []
        anchor_cache = {}
        for md in sorted(md_files):
            text = md.read_text(encoding="utf-8")
            for target in LINK_RE.findall(text):
                target = target.strip()
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                path_part, _, anchor = target.partition("#")
                dest = (md.parent / path_part).resolve() if path_part else md.resolve()
                if not dest.exists():
                    broken.append(f"{md.relative_to(ROOT)} -> missing file: {target}")
                    continue
                if anchor and dest.suffix.lower() == ".md":
                    if dest not in anchor_cache:
                        anchor_cache[dest] = heading_anchors(dest)
                    if anchor not in anchor_cache[dest]:
                        broken.append(f"{md.relative_to(ROOT)} -> missing anchor: {target}")
        self.assertEqual(broken, [], "Broken Markdown links found:\n" + "\n".join(broken))


if __name__ == "__main__":
    unittest.main()
