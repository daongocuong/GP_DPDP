"""Application-level boundary for locked final-test benchmark CSVs.

This protects the repository's Python loaders, not arbitrary OS processes or
copies of the data. No final-evaluation bypass is enabled in development.
"""
from pathlib import Path
import re

SEALED = frozenset({7, 8, 15, 16})

def sealed_instance(path):
    path = Path(path).resolve()
    for part in path.parts:
        match = re.fullmatch(r'instance_(\d+)', part, re.IGNORECASE)
        if match and int(match.group(1)) in SEALED:
            return int(match.group(1))
    return None

def require_development_path(path):
    instance = sealed_instance(path)
    if instance is not None:
        raise PermissionError(f'final-test instance_{instance} is sealed; data access requires an authorized final-evaluation workflow')
    return Path(path)
