#!/usr/bin/env python3
"""Check that every relative link in the documentation resolves.

No network access, no external tools: it walks the repository for Markdown
files, skips fenced code blocks, extracts inline links and images, and
verifies that every non-absolute target exists on disk. Anchors are stripped
before the check, because GitHub resolves those at render time.

Exit status: 0 = every relative link resolves, 1 = at least one is broken.

Usage: check-docs.py [repo-root]
"""
from __future__ import annotations

import os
import re
import sys

SKIP_DIRS = {'.git', 'build', '__pycache__', '.venv'}
LINK_RE = re.compile(r'!?\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"')
FENCE_RE = re.compile(r'^\s*(```|~~~)')
EXTERNAL = ('http://', 'https://', 'mailto:', 'tel:')


def parse_links(text):
    """Yield links from Markdown, ignoring anything inside a fenced block."""
    links = []
    in_fence = False
    fence_token = ''
    for line in text.splitlines():
        match = FENCE_RE.match(line)
        if match:
            token = match.group(1)
            if not in_fence:
                in_fence = True
                fence_token = token
            elif token == fence_token:
                in_fence = False
                fence_token = ''
            continue
        if in_fence:
            continue
        for regex in (LINK_RE, IMG_RE):
            for hit in regex.finditer(line):
                links.append(hit.group(1))
    return links


def main(argv):
    root = argv[1] if len(argv) > 1 else '.'
    root = os.path.abspath(root)
    checked = 0
    broken = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if not name.endswith('.md'):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            with open(path, 'r', encoding='utf-8') as handle:
                text = handle.read()
            if text.count('{{') != text.count('}}'):
                print('unbalanced {{ }} braces in %s' % rel, file=sys.stderr)
            for target in parse_links(text):
                if target.startswith(EXTERNAL) or target.startswith('#'):
                    continue
                checked += 1
                clean = target.split('#', 1)[0].split('?', 1)[0]
                if not clean:
                    continue
                if clean.startswith('/'):
                    broken.append((rel, target, 'absolute path - will not work on GitHub'))
                    continue
                if ' ' in clean:
                    broken.append((rel, target, 'path contains a space but is not in angle brackets'))
                    continue
                resolved = os.path.normpath(os.path.join(dirpath, clean))
                if not os.path.exists(resolved):
                    broken.append((rel, target, 'target does not exist'))

    print('checked %d relative links in %s' % (checked, os.path.relpath(root)))
    if broken:
        print('%d broken link(s):' % len(broken), file=sys.stderr)
        for src, target, why in broken:
            print('  %s -> %s (%s)' % (src, target, why), file=sys.stderr)
        return 1
    print('all relative links resolve')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
