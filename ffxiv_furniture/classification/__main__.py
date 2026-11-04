"""python -m ffxiv_furniture.classification --help"""
import argparse
import json
import sys
from .manifest import prepare
from .sampling import sample
from .runner import classify
from .vocabulary import apply_vocab, consolidate, freeze_vocab
from .reports import report
from .scheduler import next_round, discover_rest, final_all, status, anchor_qa


def parser():
    p = argparse.ArgumentParser(description='Astra classification staging; inference is explicit; no publishing')
    sub = p.add_subparsers(dest='command', required=True)
    for command in ('prepare','sample','classify','consolidate','report','vocab-apply','vocab-freeze',
                    'next-round','discover-rest','final-all','status','anchor-qa'):
        child = sub.add_parser(command)
        child.add_argument('--run-dir', required=True)
        if command in ('next-round','discover-rest','final-all','anchor-qa'):
            child.add_argument('--vocab')
            child.add_argument('--seed', type=int, default=43)
            child.add_argument('--dry-run', action='store_true', help='Read-only preview, no snapshot writes or network')
            child.add_argument('--execute', action='store_true', help='Explicitly authorize bounded inference')
            child.add_argument('--endpoint')
            child.add_argument('--model')
            child.add_argument('--timeout', type=float, default=180)
            child.add_argument('--deployment-revision')
            child.add_argument('--batch-size', type=int, default=4)
            child.add_argument('--max-batches', type=int, default=1)
            if command == 'next-round':
                child.add_argument('--targets', nargs='*', help='Explicit rare/conflict target image SHA-256 hashes')
        if command == 'prepare':
            child.add_argument('--manifest', required=True)
        if command == 'sample':
            child.add_argument('--budget', type=int, default=96)
            child.add_argument('--seed', type=int, default=42)
            child.add_argument('--min-per-stratum', type=int, default=2)
        if command in ('classify','consolidate'):
            child.add_argument('--endpoint', required=True, help='OpenAI API base URL including /v1')
            child.add_argument('--model', required=True)
            child.add_argument('--timeout', type=float, default=180)
            child.add_argument('--deployment-revision', help='Optional immutable model deployment identity')
        if command == 'classify':
            child.add_argument('--batch-size', type=int, default=4)
            child.add_argument('--max-batches', type=int)
            child.add_argument('--phase', choices=('explore','guided','final'), default='explore')
            child.add_argument('--vocab')
        if command == 'consolidate':
            child.add_argument('--max-proposals', type=int, default=96)
        if command in ('vocab-apply','vocab-freeze'):
            child.add_argument('--file', required=True)
    return p


def main(argv=None):
    args = vars(parser().parse_args(argv))
    command = args.pop('command')
    try:
        functions = {'prepare': prepare, 'sample': sample, 'classify': classify,
                     'next-round': next_round, 'discover-rest': discover_rest,
                     'final-all': final_all, 'status': status, 'anchor-qa': anchor_qa,
                     'consolidate': consolidate, 'report': report,
                     'vocab-apply': apply_vocab, 'vocab-freeze': freeze_vocab}
        result = functions[command](**args)
        if command in ('classify','consolidate'):
            summary = report(args['run_dir'])
            result['report'] = {'round_complete': summary['round_complete'],
                                'successful_unique_images': summary['successful_unique_images']}
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except Exception as error:
        # Best-effort failure report never hides the real exception or marks jobs successful.
        try:
            if command in ('classify', 'consolidate'):
                report(args['run_dir'])
        except Exception:
            pass
        print(json.dumps({'error': str(error), 'type': type(error).__name__}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
