"""Compile the unchanged supplied VNSME sources, targeting Java 8 bytecode."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / 'third_party/vnsme'


def hashes(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob('*')) if p.is_file()}


def build():
    compiler = shutil.which('javac')
    if not compiler:
        raise RuntimeError('Missing JDK: javac is not on PATH')
    target = VENDOR / 'build'
    target.mkdir(exist_ok=True)
    command = [compiler, '--release', '8', '-encoding', 'UTF-8', '-cp', str(VENDOR/'lib'),
               '-d', str(target), *map(str, sorted((VENDOR/'original').rglob('*.java')))]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    record = dict(command=command, cwd=str(ROOT), javac=subprocess.check_output(
        [compiler, '-version'], text=True, stderr=subprocess.STDOUT).strip(),
        java=subprocess.check_output(['java', '-version'], text=True, stderr=subprocess.STDOUT).strip(),
        returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
        source_sha256=hashes(VENDOR/'original'), library_sha256=hashes(VENDOR/'lib'),
        class_sha256=hashes(target))
    (VENDOR/'build_manifest.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(result.stderr)
    if result.returncode:
        raise RuntimeError('VNSME compilation failed; see third_party/vnsme/build_manifest.json')
    print('VNSME build completed')


if __name__ == '__main__':
    build()
