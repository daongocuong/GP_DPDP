"""Fetch ONLY pinned Xingtian instance_2..16 plus common CSVs, unchanged bytes.

No Git mutation, no simulation, no GP. Refuse existing output. Network or byte
mismatch fails closed; never synthesize data or try another source/ref.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

from dpdp_dataset import ROOT, CASE, validate_instance
from dpdp_sealed import sealed_instance, require_development_path

COMMIT = 'e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04'
PREFIX = 'simulator/dpdp_competition/benchmark/'
API = f'https://api.github.com/repos/huawei-noah/xingtian/git/trees/{COMMIT}?recursive=1'
RAW = f'https://raw.githubusercontent.com/huawei-noah/xingtian/{COMMIT}/'


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def git_blob_sha(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def fetch(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'dpdp-pinned-data-preparation'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()
    except Exception as exc:
        raise RuntimeError(f'Network download failed for {url}: {type(exc).__name__}: {exc}') from exc


def compare_common(blobs, local_directory):
    matches = {}
    for name in ('factory_info.csv', 'route_info.csv'):
        local = (Path(local_directory)/name).read_bytes()
        if blobs[name] != local:
            raise ValueError(f'COMMON CSV BYTE MISMATCH: {name}; upstream={sha256(blobs[name])}, local={sha256(local)}; stop experiments')
        matches[name] = dict(local_relative_path=f'examples/case_studies/dpdp/data/{name}',
                             sha256=sha256(local), byte_identical=True)
    return matches


def acquire(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        tree = json.loads(fetch(API))
        if tree.get('truncated'):
            raise ValueError('source tree truncated; refusing incomplete inventory')
        selected = []
        for entry in tree['tree']:
            if entry['type'] != 'blob' or not entry['path'].startswith(PREFIX):
                continue
            relative = entry['path'][len(PREFIX):]
            parts = relative.split('/')
            if relative in ('factory_info.csv', 'route_info.csv') or (
                    len(parts) == 2 and parts[0] in {f'instance_{i}' for i in range(2,17)} and parts[1].endswith('.csv')):
                selected.append((relative, entry))
        if len(selected) != 32:
            raise ValueError(f'expected 32 CSVs at pinned source, found {len(selected)}')
        selected.sort()
        blobs, records = {}, []
        # Common CSVs first; compare BEFORE downloading or writing instances.
        first = sorted(selected, key=lambda pair: (pair[0] not in ('factory_info.csv', 'route_info.csv'), pair[0]))
        for relative, entry in first:
            require_development_path(output/'benchmark'/relative)
            raw = fetch(RAW+entry['path'])
            if git_blob_sha(raw) != entry['sha']:
                raise ValueError(f'upstream Git blob checksum mismatch: {relative}')
            blobs[relative] = raw
            records.append(dict(file=relative, url=RAW+entry['path'], commit=COMMIT,
                                source_path=entry['path'], git_blob_sha1=entry['sha'], sha256=sha256(raw), bytes=len(raw)))
            if relative == 'route_info.csv':
                common_match = compare_common(blobs, CASE/'data')
            print(f'verified download: {relative}', flush=True)
        benchmark = output/'benchmark'
        for relative, raw in blobs.items():
            dest = benchmark/relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as handle:
                handle.write(raw)
        instances = {}
        for i in range(2,17):
            verification = validate_instance(benchmark/f'instance_{i}')
            verification.update(directory=f'benchmark/instance_{i}', commit=COMMIT,
                                files=[r for r in records if r['file'].startswith(f'instance_{i}/')])
            instances[str(i)] = verification
        manifest = dict(repository='huawei-noah/xingtian', commit=COMMIT, source_prefix=PREFIX,
                        source_tree_sha=tree['sha'], common_csv_comparison=common_match,
                        files=sorted(records, key=lambda r:r['file']), instances=instances,
                        loader_relative_path='examples/case_studies/dpdp/dpdp_problemdata.py',
                        loader_sha256=sha256((CASE/'dpdp_problemdata.py').read_bytes()), all_verified=True)
        raw_manifest = (json.dumps(manifest, indent=2, sort_keys=True)+'\n').encode()
        with (output/'source_manifest.json').open('xb') as handle:
            handle.write(raw_manifest)
        with (output/'source_manifest.sha256').open('x', encoding='ascii') as handle:
            handle.write(sha256(raw_manifest)+'  source_manifest.json\n')
        print('manifest_sha256='+sha256(raw_manifest))
        return manifest
    except Exception as exc:
        with (output/'ACQUISITION_FAILED.json').open('x', encoding='utf-8') as handle:
            json.dump(dict(valid=False, experiments_allowed=False, error=str(exc), commit=COMMIT), handle, indent=2)
        raise


def verify_existing(output):
    output = Path(output).resolve()
    if (output/'ACQUISITION_FAILED.json').exists():
        raise ValueError('acquisition previously failed; experiments prohibited')
    raw = (output/'source_manifest.json').read_bytes()
    expected = (output/'source_manifest.sha256').read_text(encoding='ascii').split()[0]
    if sha256(raw) != expected:
        raise ValueError('manifest checksum mismatch')
    manifest = json.loads(raw)
    if manifest['commit'] != COMMIT or not manifest['all_verified']:
        raise ValueError('wrong source commit or unverified manifest')
    for record in manifest['files']:
        if sealed_instance(output/'benchmark'/record['file']) is not None:
            continue  # trusted manifest metadata only; do not open sealed CSVs
        require_development_path(output/'benchmark'/record['file'])
        content = (output/'benchmark'/record['file']).read_bytes()
        if sha256(content) != record['sha256'] or git_blob_sha(content) != record['git_blob_sha1']:
            raise ValueError(f'data checksum mismatch: {record["file"]}')
    compare_common({n:(output/'benchmark'/n).read_bytes() for n in ('factory_info.csv','route_info.csv')}, CASE/'data')
    for i, info in manifest['instances'].items():
        if int(i) in (7, 8, 15, 16):
            continue  # prior manifest metadata, not a fresh verification
        actual = validate_instance(output/'benchmark'/f'instance_{i}')
        if any(actual[k] != info[k] for k in actual):
            raise ValueError(f'validation no longer matches manifest: instance_{i}')
    print('offline development source/hash/schema/loader verification PASS; sealed CSVs not opened')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if Path(sys.executable).resolve() != (ROOT/'.venv/Scripts/python.exe').resolve():
        parser.error('use repository venv')
    (verify_existing if args.verify_only else acquire)(args.output)


if __name__ == '__main__':
    main()
