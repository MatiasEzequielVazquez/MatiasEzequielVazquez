"""
update_langs.py
Fetches language statistics from GitHub repositories (including private repos)
and updates the language section in README.md.

Supported Environment Variables:
  GH_TOKEN         - GitHub token with 'repo' scope.
  GH_USER          - GitHub username.
  EXCLUDE_LANGS    - Comma-separated languages to ignore (default: markup/config languages).
  EXCLUDE_REPOS    - Comma-separated repository names to ignore.
  IGNORE_FORKS     - 'true' or 'false' (default: true).
  IGNORE_ARCHIVED  - 'true' or 'false' (default: true).
  TOP_N            - Number of languages to display (default: 7).
  BAR_LENGTH       - Number of character blocks in the bar (default: 20).
  BAR_STYLE        - 'smooth' (fractional blocks) or 'solid' (default: smooth).
  MAX_WORKERS      - Concurrency level for API requests (default: 10).
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import re
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from typing import Dict, List, Optional, Set
import requests

# Markers in README.md to replace
MARKER_START = "<!-- LANG_STATS_START -->"
MARKER_END = "<!-- LANG_STATS_END -->"

# Progress bar block characters
FRACTIONS = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉"]
BLOCK_FULL = "█"
BLOCK_EMPTY = "░"

# Default excluded non-programming or styling/config languages
DEFAULT_EXCLUDE_LANGS: Set[str] = {
    "HTML",
    "CSS",
    "SCSS",
    "Less",
    "Jupyter Notebook",
    "Roff",
    "Shell",
    "Batchfile",
    "Dockerfile",
    "Makefile",
    "TeX",
}


def get_env_list(name: str, default: Optional[Set[str]] = None) -> Set[str]:
    """Parse comma-separated values from an environment variable."""
    val = os.environ.get(name)
    if val is not None:
        return {item.strip() for item in val.split(",") if item.strip()}
    return set(default or set())


def get_env_bool(name: str, default: bool) -> bool:
    """Parse a boolean value from an environment variable."""
    val = os.environ.get(name)
    if val is not None:
        return val.strip().lower() in ("true", "1", "yes", "y")
    return default


def get_env_int(name: str, default: int) -> int:
    """Parse an integer value from an environment variable."""
    val = os.environ.get(name)
    if val is not None:
        try:
            return int(val.strip())
        except ValueError:
            return default
    return default


def render_bar(pct: float, length: int = 20, style: str = "smooth") -> str:
    """
    Renders a progress bar string of exact character count `length`.
    Supports 'smooth' (fractional sub-blocks) or 'solid' (classic blocks).
    """
    if pct <= 0.0:
        return BLOCK_EMPTY * length
    if pct >= 100.0:
        return BLOCK_FULL * length

    if style == "smooth":
        # 8 sub-block units per full block
        total_subblocks = round((pct / 100.0) * length * 8)
        full_count = total_subblocks // 8
        remainder = total_subblocks % 8

        if full_count >= length:
            return BLOCK_FULL * length

        bar = BLOCK_FULL * full_count
        if remainder > 0:
            bar += FRACTIONS[remainder]
            empty_count = length - full_count - 1
        else:
            empty_count = length - full_count

        bar += BLOCK_EMPTY * max(0, empty_count)
        return bar
    else:
        # Classic solid blocks
        filled = round((pct / 100.0) * length)
        filled = min(max(filled, 0), length)
        return BLOCK_FULL * filled + BLOCK_EMPTY * (length - filled)


def filter_repos(
    repos: List[dict],
    ignore_forks: bool = True,
    ignore_archived: bool = True,
    exclude_repos: Optional[Set[str]] = None,
) -> List[dict]:
    """Filters repository list by fork, archived status, and exclusion list."""
    excluded = exclude_repos or set()
    filtered = []
    for r in repos:
        name = r.get("name", "")
        if ignore_forks and r.get("fork"):
            continue
        if ignore_archived and r.get("archived"):
            continue
        if name in excluded:
            continue
        filtered.append(r)
    return filtered


def fetch_repos(headers: dict) -> List[dict]:
    """Fetches all repositories accessible by the authenticated user."""
    repos, page = [], 1
    while True:
        r = requests.get(
            "https://api.github.com/user/repos",
            headers=headers,
            params={"per_page": 100, "type": "all", "page": page},
            timeout=15,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_repo_languages(repo: dict, headers: dict, timeout: int = 10) -> Dict[str, int]:
    """Fetches language breakdown for a single repository."""
    url = repo.get("languages_url")
    if not url:
        return {}
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException as e:
        print(f"Warning: Failed to fetch languages for {repo.get('name')}: {e}")
    return {}


def fetch_languages(
    repos: List[dict],
    headers: dict,
    exclude_langs: Optional[Set[str]] = None,
    max_workers: int = 10,
) -> Dict[str, int]:
    """
    Fetches language statistics across repositories concurrently using ThreadPoolExecutor.
    Excluded languages are filtered out during aggregation.
    """
    excluded = exclude_langs or set()
    totals: Dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_repo = {
            executor.submit(fetch_repo_languages, repo, headers): repo
            for repo in repos
        }
        for future in as_completed(future_to_repo):
            lang_data = future.result()
            for lang, bytes_ in lang_data.items():
                if lang in excluded:
                    continue
                totals[lang] = totals.get(lang, 0) + bytes_

    return totals


def build_section(
    lang_totals: Dict[str, int],
    top_n: int = 7,
    bar_length: int = 20,
    bar_style: str = "smooth",
) -> str:
    """Formats language totals into a markdown code block with progress bars."""
    if not lang_totals:
        return "\n*No language data detected.*\n"

    sorted_langs = sorted(lang_totals.items(), key=lambda x: x[1], reverse=True)
    top = sorted_langs[:top_n]
    total_bytes = sum(v for _, v in sorted_langs)

    if total_bytes == 0:
        return "\n*No code bytes detected.*\n"

    lines = ["", "```text"]
    for lang, bytes_ in top:
        pct = (bytes_ / total_bytes) * 100.0
        bar = render_bar(pct, length=bar_length, style=bar_style)
        lines.append(f"{lang:<20} {bar}  {pct:5.1f}%")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def update_readme(section_content: str, readme_path: str = "README.md") -> bool:
    """Replaces content between MARKER_START and MARKER_END in the target README."""
    if not os.path.exists(readme_path):
        print(f"Error: {readme_path} does not exist.")
        return False

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
        re.DOTALL,
    )
    clean_section = section_content.strip()
    replacement = f"{MARKER_START}\n\n{clean_section}\n\n{MARKER_END}"

    if pattern.search(content):
        new_content = pattern.sub(replacement, content)
    else:
        new_content = content.rstrip() + f"\n\n{replacement}\n"

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"{readme_path} updated successfully.")
    return True


def get_mock_data() -> Dict[str, int]:
    """Sample dataset for dry-run testing and demonstration."""
    return {
        "Python": 284000,
        "C#": 8200,
        "JavaScript": 6500,
        "Java": 5100,
        "C": 4200,
        "SQL": 3800,
        "Rust": 2100,
        "HTML": 15000,  # Should be excluded if DEFAULT_EXCLUDE_LANGS is active
        "CSS": 5000,    # Should be excluded if DEFAULT_EXCLUDE_LANGS is active
    }


def main():
    parser = argparse.ArgumentParser(description="Update language stats in README.md")
    parser.add_argument("--dry-run", action="store_true", help="Print output without updating README.md")
    parser.add_argument("--mock", action="store_true", help="Use mock data instead of calling GitHub API")
    parser.add_argument("--readme", default="README.md", help="Path to README file (default: README.md)")
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN")
    user = os.environ.get("GH_USER", "MatiasEzequielVazquez")

    exclude_langs = get_env_list("EXCLUDE_LANGS", DEFAULT_EXCLUDE_LANGS)
    exclude_repos = get_env_list("EXCLUDE_REPOS", {user})
    ignore_forks = get_env_bool("IGNORE_FORKS", True)
    ignore_archived = get_env_bool("IGNORE_ARCHIVED", True)
    top_n = get_env_int("TOP_N", 7)
    bar_length = get_env_int("BAR_LENGTH", 20)
    bar_style = os.environ.get("BAR_STYLE", "smooth").strip().lower()
    max_workers = get_env_int("MAX_WORKERS", 10)

    if args.mock or (not token and args.dry_run):
        print("Running with mock data...")
        mock_raw = get_mock_data()
        totals = {k: v for k, v in mock_raw.items() if k not in exclude_langs}
    else:
        if not token:
            print("Error: GH_TOKEN environment variable is required (or use --mock / --dry-run with mock data).", file=sys.stderr)
            sys.exit(1)

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        print("Fetching repositories...")
        all_repos = fetch_repos(headers)
        repos = filter_repos(
            all_repos,
            ignore_forks=ignore_forks,
            ignore_archived=ignore_archived,
            exclude_repos=exclude_repos,
        )
        print(f"  {len(repos)} repositories to process (filtered out forks/archived/excluded).")

        print(f"Fetching language data in parallel (workers={max_workers})...")
        totals = fetch_languages(
            repos,
            headers=headers,
            exclude_langs=exclude_langs,
            max_workers=max_workers,
        )
        print(f"  {len(totals)} languages found (excluding non-code/markup).")

    section = build_section(
        totals,
        top_n=top_n,
        bar_length=bar_length,
        bar_style=bar_style,
    )

    print("\nGenerated section preview:\n")
    print(section)

    if args.dry_run:
        print("[Dry-run] Skipping README write.")
    else:
        update_readme(section, readme_path=args.readme)


if __name__ == "__main__":
    main()
