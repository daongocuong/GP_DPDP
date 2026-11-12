"""Explicit, bounded relocation at resolution time; never rewrite evidence."""
import hashlib
import json
from pathlib import Path, PureWindowsPath

from dpdp_sealed import require_development_path

ROOT = Path(__file__).resolve().parent.parent


class Relocation:
    def __init__(self, old_root, new_root):
        self.old = PureWindowsPath(old_root)
        self.new = Path(new_root).resolve(strict=True)
        if not self.old.is_absolute() or self.new == Path(str(self.old)).resolve():
            raise ValueError('ambiguous relocation roots')

    def resolve(self, value, sha256=None):
        historical = PureWindowsPath(str(value))
        if '..' in historical.parts:
            raise ValueError('parent traversal in relocation path')
        try:
            suffix = historical.relative_to(self.old)
        except ValueError:
            candidate = Path(value)
            if not candidate.is_absolute():
                raise ValueError('relocation requires an absolute path')
        else:
            if Path(value).exists():
                raise ValueError('ambiguous relocation: historical path also exists')
            candidate = self.new.joinpath(*suffix.parts)
        require_development_path(candidate)
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(self.new):
            raise ValueError('resolved path escapes allowed root')
        require_development_path(resolved)
        if sha256 is not None:
            if not resolved.is_file() or hashlib.sha256(resolved.read_bytes()).hexdigest() != sha256:
                raise ValueError('relocated file checksum mismatch')
        return resolved


def load_relocation(path):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    if set(config) != {'schema', 'old_root', 'new_root'} or config['schema'] != 'dpdp-relocation-v1':
        raise ValueError('unsupported relocation config (exactly one root mapping required)')
    if Path(config['new_root']).resolve() != ROOT:
        raise ValueError('relocation destination must be the current repository root')
    return Relocation(config['old_root'], config['new_root'])
