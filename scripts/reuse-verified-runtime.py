"""Promote an identical merged PR's immutable, successful CI runtime artifact.

An unavailable artifact or a changed source tree falls back to a source build.
Downloaded content must pass provenance and checksum checks before promotion.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path], text=True))


def main():
    if os.environ.get('GITHUB_REF') != 'refs/heads/main':
        return
    repo, commit = os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_SHA']
    tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True).strip()
    for pr in api(f'repos/{repo}/commits/{commit}/pulls'):
        if not pr.get('merged_at') or pr.get('merge_commit_sha') != commit or pr['base']['ref'] != 'main':
            continue
        if pr['head']['repo']['full_name'] != repo:
            continue
        head = pr['head']['sha']
        if api(f'repos/{repo}/git/commits/{head}')['tree']['sha'] != tree:
            continue
        runs = api(f'repos/{repo}/actions/workflows/android.yml/runs?head_sha={head}&status=success&per_page=10')
        for run in runs['workflow_runs']:
            if run['head_sha'] != head or run['conclusion'] != 'success' or run['event'] != 'push':
                continue
            run_id = str(run['id'])
            artifacts = api(f'repos/{repo}/actions/runs/{run_id}/artifacts')['artifacts']
            if not any(a['name'] == 'fex-runtime-release' and not a['expired'] for a in artifacts):
                continue
            output = Path('runtime-work/fex/release')
            output.mkdir(parents=True)
            subprocess.run(['gh', 'run', 'download', run_id, '-R', repo,
                            '--name', 'fex-runtime-release', '--dir', str(output)], check=True)
            manifest = json.loads((output/'client-runtime-manifest.json').read_text())
            archive = output/'client-runtime-arm64.tar.gz'
            assert (manifest['format'], manifest['runtime'], manifest['architecture'], manifest['file']) == (
                2, 'fex-arm64ec-1', 'arm64', archive.name)
            assert manifest['source_commit'] == head
            assert archive.stat().st_size == manifest['bytes']
            with archive.open('rb') as source:
                assert hashlib.file_digest(source, 'sha256').hexdigest() == manifest['sha256']
            for source in ('wine-arm64ec-source.tar.gz', 'fex-2510-source-with-submodules.tar.gz'):
                assert (output/source).stat().st_size > 0
            logs = Path('runtime-work/fex/logs'); logs.mkdir(parents=True, exist_ok=True)
            evidence = {'verified_run': run['html_url'], 'source_commit': head,
                        'release_commit': commit, 'identical_tree': tree, 'sha256': manifest['sha256']}
            (logs/'verified-artifact-promotion.log').write_text(json.dumps(evidence, indent=2)+'\n')
            print(json.dumps(evidence))
            with open(os.environ['GITHUB_OUTPUT'], 'a') as result:
                result.write('reused=true\n')
            return
    print('No identical, successfully verified runtime artifact; building from source.')


if __name__ == '__main__':
    main()
