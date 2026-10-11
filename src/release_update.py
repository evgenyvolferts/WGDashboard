#!/usr/bin/env python3
"""Stage and apply a WGDashboard GitHub Release asset (Python 3.12+)."""
import argparse
import configparser
import re
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import urllib.error
import urllib.request
from urllib.parse import quote

PROTECTED = {
    'db', 'log', 'download', 'venv', '.git',
    'wg-dashboard.ini', 'ssl-tls.ini', 'certbot.ini',
    'wg-dashboard-oidc-providers.json', 'gunicorn.pid',
    '.env', 'gunicorn.conf.py',
}

def protected(path):
    return path.parts[0] in PROTECTED or path.suffix.lower() in {'.pem', '.key', '.crt', '.p12', '.pfx'}

def request_json(url):
    req = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'WGDashboard-updater'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

DEFAULT_REPOSITORY = 'WGDashboard/WGDashboard'
REPOSITORY_PATTERN = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
VERSION_PATTERN = re.compile(r'^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$')


def read_metadata(target):
    path = Path(target) / 'release.ini'
    if not path.exists() and not path.is_symlink():
        return None, DEFAULT_REPOSITORY
    if path.is_symlink() or not path.is_file():
        raise ValueError('Invalid release.ini')
    config = configparser.ConfigParser(interpolation=None)
    with path.open(encoding='utf-8') as f:
        config.read_file(f)
    if not config.has_section('Release'):
        raise ValueError('release.ini is missing [Release]')
    version = config.get('Release', 'version', fallback='').strip() or None
    repo = config.get('Release', 'repository', fallback='').strip() or DEFAULT_REPOSITORY
    if not REPOSITORY_PATTERN.fullmatch(repo) or '..' in repo:
        raise ValueError(f'Invalid repository in release.ini: {repo}')
    return version, repo


def version_key(value):
    match = VERSION_PATTERN.fullmatch(value or '')
    if match is None:
        raise ValueError(f'Unsupported release version: {value}')
    numeric = tuple(int(x) for x in match.group(1, 2, 3))
    suffix = match.group(4)
    if suffix is None:
        return numeric, (1, ())
    parts = tuple((0, int(x)) if x.isdigit() else (1, x.lower()) for x in suffix.split('.'))
    return numeric, (0, parts)


def metadata(args):
    version, repo = read_metadata(args.target)
    print(repo if args.field == 'repository' else version or '')


def compare(args):
    installed, _ = read_metadata(args.target)
    candidate = json.loads((Path(args.workspace) / 'release.json').read_text())['tag']
    if installed is None:
        print('unknown')
    else:
        new, old = version_key(candidate), version_key(installed)
        print('upgrade' if new > old else 'same' if new == old else 'downgrade')


def prepare(args):
    repo = args.repo
    if not all(x and x.replace('-', '').replace('_', '').isalnum() for x in repo.split('/')) or len(repo.split('/')) != 2:
        raise ValueError('Invalid repository: expected owner/name')
    if args.tag:
        release_url = (
            f'https://api.github.com/repos/{repo}/releases/tags/'
            f'{quote(args.tag, safe="")}'
        )
    else:
        release_url = f'https://api.github.com/repos/{repo}/releases/latest'

    release = request_json(release_url)
    tag = release['tag_name']
    asset_name = f'WGDashboard-{tag}.tar.gz'
    asset = next((a for a in release.get('assets', []) if a['name'] == asset_name), None)
    if asset is None:
        raise RuntimeError(f'Release {tag} does not have asset {asset_name}; refusing GitHub source archive')
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    archive = workspace / 'release.tar.gz'
    req = urllib.request.Request(asset['browser_download_url'], headers={'User-Agent': 'WGDashboard-updater'})
    with urllib.request.urlopen(req, timeout=60) as response, archive.open('wb') as out:
        shutil.copyfileobj(response, out)
    incoming = workspace / 'incoming'
    incoming.mkdir(exist_ok=True)
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'WGDashboard'
                    or not (member.isdir() or member.isfile())):
                raise ValueError(f'Unsafe or unsupported archive entry: {member.name}')
        tar.extractall(incoming, filter='data')
    src = incoming / 'WGDashboard' / 'src'
    for entry in ('wgd.sh', 'requirements.txt', 'static/dist/WGDashboardAdmin/index.html',
                  'static/dist/WGDashboardClient/client.html'):
        if not (src / entry).is_file() or not (src / entry).stat().st_size:
            raise RuntimeError(f'Incomplete release asset: missing {entry}')
    recorded_version, recorded_repo = read_metadata(src)
    if recorded_version != tag or recorded_repo != repo:
        raise RuntimeError('release.ini does not match release tag and repository')
    (workspace / 'release.json').write_text(json.dumps({'tag': tag, 'repo': repo}))
    print(f'[WGDashboard] Downloaded and validated {asset_name} from {repo}')

def apply(args):
    workspace = Path(args.workspace).resolve()
    src = workspace / 'incoming/WGDashboard/src'
    target = Path(args.target).resolve()
    backup = workspace / 'backup'
    backup.mkdir(exist_ok=True)
    journal = {'replaced': [], 'added': []}
    journal_path = workspace / 'journal.json'
    # Snapshot first; never modify the target before the backup and journal exist.
    for source in sorted(src.rglob('*')):
        relative = source.relative_to(src)
        if protected(relative) or source.is_dir() or relative.parts[:2] == ('static', 'dist'):
            continue
        if not source.is_file() or source.is_symlink():
            raise RuntimeError(f'Unsupported release file: {relative}')
        dest = target / relative
        if any(p.is_symlink() for p in [dest, *dest.parents] if p == target or target in p.parents):
            raise RuntimeError(f'Refusing symlink destination: {dest}')
        if dest.exists():
            if not dest.is_file():
                raise RuntimeError(f'Existing non-file at {dest}')
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, saved)
            journal['replaced'].append(str(relative))
        else:
            journal['added'].append(str(relative))
    journal_path.write_text(json.dumps(journal, indent=2))
    # Replace hashed Vite bundles as complete directories to avoid stale assets.
    for bundle in ('WGDashboardAdmin', 'WGDashboardClient'):
        relative = Path('static/dist') / bundle
        dest = target / relative
        if any(parent.is_symlink() for parent in (target / 'static', target / 'static/dist')):
            raise RuntimeError(f'Unsafe frontend parent directory: {dest}')
        if dest.exists():
            if dest.is_symlink() or not dest.is_dir():
                raise RuntimeError(f'Unsafe frontend directory: {dest}')
            saved = backup / relative
            shutil.copytree(dest, saved)
            journal.setdefault('directories', []).append(str(relative))
        else:
            journal.setdefault('added_directories', []).append(str(relative))
    journal_path.write_text(json.dumps(journal, indent=2))
    for bundle in ('WGDashboardAdmin', 'WGDashboardClient'):
        relative = Path('static/dist') / bundle
        dest = target / relative
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src / relative, dest)
    for source in sorted(src.rglob('*')):
        relative = source.relative_to(src)
        if protected(relative) or source.is_dir() or relative.parts[:2] == ('static', 'dist'):
            continue
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    print('[WGDashboard] Application files updated (user data preserved)')

def rollback(args):
    workspace = Path(args.workspace).resolve()
    target = Path(args.target).resolve()
    journal_path = workspace / 'journal.json'
    if not journal_path.exists():
        return
    journal = json.loads(journal_path.read_text())
    for item in journal.get('added_directories', []):
        shutil.rmtree(target / item, ignore_errors=True)
    for item in journal.get('directories', []):
        dest = target / item
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(workspace / 'backup' / item, dest)
    for item in journal['added']:
        (target / item).unlink(missing_ok=True)
    for item in journal['replaced']:
        old = workspace / 'backup' / item
        new = target / item
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, new)
    print('[WGDashboard] Previous application files restored')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'apply', 'rollback', 'metadata', 'compare'])
    parser.add_argument('--repo', default='WGDashboard/WGDashboard')
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--target', default='.')
    parser.add_argument('--tag', default=None)
    parser.add_argument('--field', choices=['repository', 'version'], default='repository')
    args = parser.parse_args()
    try:
        {'prepare': prepare, 'apply': apply, 'rollback': rollback,
         'metadata': metadata, 'compare': compare}[args.action](args)
    except Exception as exc:
        parser.exit(1, f'[WGDashboard] Release update failed: {exc}\n')
