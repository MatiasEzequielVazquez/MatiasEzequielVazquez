"""
update_langs.py
Lee todos los repos propios (incluyendo privados) via GitHub API
y actualiza la sección de lenguajes del README.md.

Variables de entorno requeridas:
  GH_TOKEN  - token con scope 'repo' (guardado como secret en el repo)
  GH_USER   - nombre de usuario de GitHub
"""

import os
import re
import requests

TOKEN = os.environ["GH_TOKEN"]
USER  = os.environ["GH_USER"]

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

BAR_LENGTH  = 20   # cantidad de bloques en la barra
TOP_N       = 7    # cuántos lenguajes mostrar
BLOCK_FULL  = "█"
BLOCK_EMPTY = "░"

# Marcadores en el README — el script reemplaza lo que haya entre ellos
MARKER_START = "<!-- LANG_STATS_START -->"
MARKER_END   = "<!-- LANG_STATS_END -->"


def fetch_repos():
    repos, page = [], 1
    while True:
        r = requests.get(
            f"https://api.github.com/user/repos",
            headers=HEADERS,
            params={"per_page": 100, "type": "all", "page": page},
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


def fetch_languages(repos):
    totals = {}
    for repo in repos:
        if repo.get("fork"):
            continue
        r = requests.get(repo["languages_url"], headers=HEADERS)
        if r.status_code != 200:
            continue
        for lang, bytes_ in r.json().items():
            totals[lang] = totals.get(lang, 0) + bytes_
    return totals


def build_section(lang_totals):
    sorted_langs = sorted(lang_totals.items(), key=lambda x: x[1], reverse=True)
    top = sorted_langs[:TOP_N]
    total = sum(v for _, v in sorted_langs)

    lines = [""]
    lines.append("```text")

    for lang, bytes_ in top:
        pct = bytes_ / total * 100
        filled = round(pct / 100 * BAR_LENGTH)
        bar = BLOCK_FULL * filled + BLOCK_EMPTY * (BAR_LENGTH - filled)
        lines.append(f"{lang:<20} {bar}  {pct:5.1f}%")

    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def update_readme(section_content):
    with open("README.md", "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
        re.DOTALL,
    )
    replacement = f"{MARKER_START}\n{section_content}\n{MARKER_END}"

    if pattern.search(content):
        new_content = pattern.sub(replacement, content)
    else:
        # Si no existen los marcadores, los agrega al final
        new_content = content.rstrip() + f"\n\n{replacement}\n"

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(new_content)

    print("README.md actualizado.")


if __name__ == "__main__":
    print("Fetching repos...")
    repos = fetch_repos()
    own = [r for r in repos if not r.get("fork")]
    print(f"  {len(own)} repos propios encontrados ({sum(1 for r in own if r['private'])} privados)")

    print("Fetching language data...")
    totals = fetch_languages(own)
    print(f"  {len(totals)} lenguajes detectados")

    section = build_section(totals)
    print("\nSección generada:\n")
    print(section)

    update_readme(section)
