"""Protocol-locked GP v3 development experiments and no-rollout preflight."""
import argparse
from pathlib import Path
import sys

from dpdp_gp_training_v3 import DEFAULT_PROTOCOL, preflight, read, run_experiment, validate_protocol_document

ROOT = Path(__file__).resolve().parent


# Ghi chú: CLI huấn luyện V3: kiểm interpreter/resume, chọn preflight hoặc thí nghiệm; pilot chạy qua supervisor quản lý tiến trình.
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path,
                        help='new, empty experiment directory; existing paths are rejected')
    parser.add_argument('--protocol', type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument('--dataset', type=Path,
                        default=ROOT/'datasets/xingtian/e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04')
    parser.add_argument('--resume', action='store_true',
                        help='unsupported: exact config/RNG/cache restoration is not implemented')
    parser.add_argument('--preflight', action='store_true', help='audit locked inputs; no rollouts')
    parser.add_argument('--relocation-config', type=Path,
                        help='explicit mapping for historical smoke inputs; pilot pins its own mapping')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    expected = ROOT/'.venv/Scripts/python.exe'
    if Path(sys.executable).resolve() != expected.resolve():
        parser.error('use the repository .venv interpreter')
    if args.resume:
        parser.error('resume is unsupported; choose a new output directory')
    # Ghi chú: Preflight kiểm đầu vào và ghi báo cáo mới; không khởi chạy các rollout GP mới.
    if args.preflight:
        result = preflight(args.protocol, args.dataset, args.relocation_config)
        with args.output.open('x', encoding='utf-8') as handle:
            __import__('json').dump(result, handle, indent=2)
        print('PREFLIGHT_PASS; no rollout processes started')
        return 0
    protocol = validate_protocol_document(read(args.protocol))
    if 'pilot' in protocol and not args.worker:
        from dpdp_v3_supervisor import supervise
        args.output.mkdir(parents=True, exist_ok=False)
        command = [sys.executable, '-B', str(Path(__file__).resolve()),
                   '--worker', '--output', str(args.output.resolve()),
                   '--protocol', str(args.protocol.resolve()), '--dataset', str(args.dataset.resolve())]
        if args.relocation_config:
            command.extend(['--relocation-config', str(args.relocation_config.resolve())])
        # Includes input audits, evolution, cache re-audits and final selection.
        # Leave room for the supervisor's bounded process-tree cleanup.
        timeout = protocol['pilot']['max_total_wall_seconds'] - protocol['pilot']['cleanup_reserve_seconds']
        job = supervise(command, args.output/'trainer_supervision', timeout, interval=.5, gap_limit=5.)
        ok = job.get('valid_supervision') and job.get('state') == 'EXITED' and job.get('exit_code') == 0
        print(__import__('json').dumps(dict(status='development_pilot_complete' if ok else 'incomplete_supervised_run',
                                         output=str(args.output), resume_supported=False)))
        return 0 if ok else 2
    result = run_experiment(args.output, args.protocol, args.dataset, prepared_output=args.worker,
                            relocation_config=args.relocation_config)
    print(__import__('json').dumps({k: v for k, v in result.items()
                                    if k != 'rollout_records'}, indent=2, default=str))
    return 0 if result['status'] in ('development_smoke_complete', 'development_pilot_complete') else 2


if __name__ == '__main__':
    raise SystemExit(main())
