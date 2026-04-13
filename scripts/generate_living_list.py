import os
import requests
import json
from datetime import datetime

BADGE_TABLE = \"\"\"| ![Last Updated](https://img.shields.io/badge/dynamic/xml?label=Last%20updated&query=%2F%2Fbadge%2FlastUpdated&url=https%3A%2F%2Fraw.githubusercontent.com%2FMetaphyKing%2Fliving-repo-catalog%2Fmain%2Fbadges.xml) | ![Repo count](https://img.shields.io/badge/dynamic/json?label=Public%20Repos&query=%24.count&url=https%3A%2F%2Fapi.github.com%2Fusers%2FMetaphyKing%2Frepos) | ![Stars](https://img.shields.io/github/stars/MetaphyKing?style=social) | ![Forks](https://img.shields.io/github/forks/MetaphyKing?style=social) | ![Open Issues](https://img.shields.io/github/issues/MetaphyKing/living-repo-catalog) | ![Pull Requests](https://img.shields.io/github/issues-pr/MetaphyKing/living-repo-catalog) | ![Workflow](https://github.com/MetaphyKing/living-repo-catalog/actions/workflows/update-list.yml/badge.svg)\n|
|---|---|---|---|---|---|---|\"\"\"

def github_api(url, headers, params=None):
    out = []
    while url:
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            raise Exception(f'{resp.status_code} error: {resp.text}\nURL: {url}')
        data = resp.json()
        if isinstance(data, dict) and 'items' in data:
            out.extend(data['items'])
        elif isinstance(data, list):
            out.extend(data)
        else:
            out.append(data)
        link = resp.headers.get('link', '')
        url = None
        for section in link.split(','):
            if 'rel=\"next\"' in section:
                url = section[section.find('<')+1:section.find('>')]
    return out

def safe_desc(d):
    if not d:
        return ''
    return d.replace('\n',' ').replace('\r', '').strip()

def main():
    with open('config.json') as f:
        config = json.load(f)
    username = config['github_username']
    exclude = set(config.get('repo_exclude_list', []))
    cat_override = config.get('category_override', {})

    token = os.getenv('GITHUB_TOKEN')
    headers = {'Authorization': f'token {token}'} if token else {}

    # Owned + Forked
    user_repos = github_api(f'https://api.github.com/users/{username}/repos?per_page=100&type=owner', headers)
    owned, forked = [], []
    for r in user_repos:
        (forked if r['fork'] else owned).append(r)

    # Starred
    starred = github_api(f'https://api.github.com/users/{username}/starred?per_page=100', headers)

    # Contributed: find repos where user made PRs
    events = github_api(f'https://api.github.com/users/{username}/events/public?per_page=100', headers)
    contributed = []
    seen = set(r['full_name'] for r in owned + forked + starred)
    for e in events:
        if e['type'] in ('PushEvent', 'PullRequestEvent', 'IssuesEvent'):
            repo = e['repo']['name']
            if repo not in seen:
                repo_resp = requests.get(f'https://api.github.com/repos/{repo}', headers=headers)
                if repo_resp.status_code == 200:
                    r = repo_resp.json()
                    contributed.append(r)
                    seen.add(repo)

    # Build catalog (priority order)
    all_repos, repo_map = [], {}
    for r in owned: repo_map[r['full_name']] = ('Owned', r)
    for r in forked: repo_map.setdefault(r['full_name'], ('Forked', r))
    for r in starred: repo_map.setdefault(r['full_name'], ('Starred', r))
    for r in contributed: repo_map.setdefault(r['full_name'], ('Contributed', r))

    # Exclude any in exclude_list
    entries = [ (c, r) for (fn, (c, r)) in repo_map.items() if r['name'] not in exclude ]

    # Category overrides
    for idx, (cat, r) in enumerate(entries):
        ovr = cat_override.get(r['name'])
        if ovr:
            entries[idx] = (ovr, r)

    # Sort: category (Owned,Forked,Starred,Contributed), then alpha
    cat_rank = {'Owned':0,'Forked':1,'Starred':2,'Contributed':3}
    entries.sort(key=lambda t: (cat_rank.get(t[0],99), t[1]['name'].lower()))

    # Markdown lines
    lines = ['| Name | URL | Category | Description |','|---|---|---|---|']
    for cat, r in entries:
        n = r['name']
        u = r['html_url']
        cat = cat_override.get(n, cat)
        d = safe_desc(r.get('description'))
        lines.append(f'| [{n}]({u}) | {u} | {cat} | {d} |')

    # Load readme template
    with open('README.md', 'r', encoding='utf-8') as f:
        text = f.read()
    tbl_start = text.index('| Name')
    tbl_end = text.find('---table-end---', tbl_start)
    badge_placeholder = text.find('<!--BADGES-->')

    last_updated = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    new_table = '\n'.join(lines)
    new_readme = text[:tbl_start] + new_table + '\n---table-end---' + text[tbl_end+14:]
    new_readme = new_readme.replace('<!--LAST_UPDATED-->', last_updated)

    # Add badges
    badge_line = BADGE_TABLE.replace('MetaphyKing', username)
    if badge_placeholder != -1:
        new_readme = new_readme.replace('<!--BADGES-->', badge_line)

    with open('README.md', 'w', encoding='utf-8') as f:
        f.write(new_readme)

    # Write badges.xml (last updated)
    with open('badges.xml', 'w') as f:
        f.write(f'<badge>\n  <lastUpdated>{last_updated}</lastUpdated>\n</badge>\n')

    print('Done. Catalog updated.')

if __name__ == '__main__':
    main()
