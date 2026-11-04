"""Flag suspicious FINAL furniture tags without inference or modifying the run/catalog."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ffxiv_furniture.classification.audit import audit_final


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',type=Path,default=ROOT/'runs/round1')
    p.add_argument('--output-dir',type=Path)
    p.add_argument('--round',type=int,dest='round_number',help='default: latest final-all round only')
    p.add_argument('--allow-partial',action='store_true',help='interim audit only; exclude unfinished images and report coverage explicitly')
    a=p.parse_args()
    out=a.output_dir or a.run_dir/'finalization'/('tag-audit-partial' if a.allow_partial else 'tag-audit')
    try:
        summary=audit_final(a.run_dir,out,allow_partial=a.allow_partial,round_number=a.round_number)
        print(json.dumps({'output_dir':str(out.resolve()),**{k:v for k,v in summary.items() if k not in ('policy','limitations')}},ensure_ascii=False,indent=2))
        return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
