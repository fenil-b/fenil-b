#!/usr/bin/env python3
"""
Refresh README tech-stack markers from GitHub public repo language stats (stdlib only).
CV supplement is static text from CV sections other than Skills.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER") or os.environ.get("GITHUB_ACTOR") or "fenil-b"
README = os.path.join(os.path.dirname(__file__), "..", "README.md")
MARK_BEGIN = "<!--PROFILE_TECH_STACK:BEGIN-->"
MARK_END = "<!--PROFILE_TECH_STACK:END-->"

# From CV: Experience, Projects, Education — not the Skills keyword block.
CV_SUPPLEMENT_MD = (
    "**Also reflected in my work:** "
    "LoRA · DPO · GRPO · NeRF · 3D Gaussian splatting · distributed post-training · "
    "NL-to-SQL · agentic & schema-guided pipelines · Mamba & Transformer adaptation/unlearning · "
    "ResNet · U-Net · ConvNeXt · Swin · ViT · I-JEPA · VAEs (video) · multimodal evaluation"
)


def http_get(url: str, token: str | None) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "fenil-b-profile-readme-updater")
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read()


def github_colors() -> dict[str, str]:
    url = "https://raw.githubusercontent.com/ozh/github-colors/master/colors.json"
    try:
        raw = http_get(url, None)
        data = json.loads(raw.decode())
        return {k: v.get("color") or "555555" for k, v in data.items() if isinstance(v, dict)}
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return {}


def fetch_all_repos(owner: str, token: str | None) -> list[dict]:
    repos: list[dict] = []
    page = 1
    per_page = 100
    while True:
        url = (
            f"https://api.github.com/users/{owner}/repos"
            f"?per_page={per_page}&page={page}&type=owner&sort=pushed"
        )
        raw = http_get(url, token)
        batch = json.loads(raw.decode())
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return repos


def repo_languages(repo: dict, token: str | None) -> dict[str, int]:
    langs_url = repo.get("languages_url")
    if not langs_url:
        return {}
    raw = http_get(langs_url, token)
    return json.loads(raw.decode())


def aggregate_languages(repos: list[dict], token: str | None) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for r in repos:
        if r.get("fork"):
            continue
        if r.get("archived"):
            continue
        name = r.get("name") or ""
        if name == OWNER:
            continue
        for lang, n in repo_languages(r, token).items():
            totals[lang] += int(n)
    return dict(totals)


def shield_badge(lang: str, pct: float, colors: dict[str, str]) -> str:
    color = (colors.get(lang) or "555555").lstrip("#")
    label = urllib.parse.quote(str(lang))
    message = urllib.parse.quote(f"{pct:.1f}%")
    return (
        f"![{lang}](https://img.shields.io/static/v1?style=for-the-badge"
        f"&label={label}&message={message}&color={color})"
    )


def format_stack_block(totals: dict[str, int]) -> str:
    if not totals:
        return (
            "_No language data found on public repositories (or API limit). "
            "This block refreshes on the next workflow run._\n\n"
            + CV_SUPPLEMENT_MD
        )

    colors = github_colors()
    ordered = sorted(totals.items(), key=lambda x: -x[1])
    total_bytes = sum(totals.values()) or 1
    top = ordered[:10]

    lines = [
        "_Languages weighted by bytes across my public repositories "
        "(excluding forks, archived repos, and this profile repository)._",
        "",
    ]
    lines.append(" ".join(shield_badge(lang, 100.0 * n / total_bytes, colors) for lang, n in top))
    lines.append("")
    lines.append(
        f"**{len(ordered)}** distinct languages detected; showing the top **{len(top)}** by share of code."
    )
    lines.append("")
    lines.append(CV_SUPPLEMENT_MD)
    return "\n".join(lines)


def patch_readme(text: str, block: str) -> str:
    pattern = re.compile(
        re.escape(MARK_BEGIN) + r".*?" + re.escape(MARK_END),
        re.DOTALL,
    )
    replacement = MARK_BEGIN + "\n" + block.rstrip() + "\n" + MARK_END
    if not pattern.search(text):
        print("Markers not found in README.md", file=sys.stderr)
        sys.exit(1)
    return pattern.sub(replacement, text, count=1)


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repos = fetch_all_repos(OWNER, token)
    totals = aggregate_languages(repos, token)
    block = format_stack_block(totals)

    path = os.path.abspath(README)
    with open(path, encoding="utf-8") as f:
        original = f.read()
    updated = patch_readme(original, block)
    if updated != original:
        with open(path, "w", encoding="utf-8") as f:
            f.write(updated)
        print("README updated.")
    else:
        print("README unchanged.")


if __name__ == "__main__":
    main()
