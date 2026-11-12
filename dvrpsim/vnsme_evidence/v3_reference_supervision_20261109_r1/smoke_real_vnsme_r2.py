"""Repeat the empty-epoch probe after adding durable live output capture."""
from pathlib import Path
source=Path(__file__).with_name('smoke_real_vnsme.py')
code=source.read_text(encoding='utf-8').replace('smoke_real_vnsme_session', 'smoke_real_vnsme_session_r2')
exec(compile(code,str(source),'exec'))
