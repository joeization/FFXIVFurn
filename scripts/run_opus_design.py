"""One bounded Opus design invocation, recording actual CLI usage/quota before+after."""
from pathlib import Path
import json
import shutil
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/opus-one-floor'


def call(args,timeout):
    result=subprocess.run([shutil.which('agy'),*args],cwd=OUT,capture_output=True,text=True,encoding='utf-8',timeout=timeout)
    return result


def usage(name):
    r=call(['-p','/usage','--output-format','json'],60)
    (OUT/name).write_text(r.stdout,encoding='utf-8')
    if r.returncode:raise RuntimeError('agy usage failed: '+r.stderr[:300])
    return json.loads(r.stdout)


def main():
    before=usage('quota-before.json');started=time.time()
    r=call(['-p',(OUT/'prompt.txt').read_text(encoding='utf-8'),'--model','claude-opus-5-5-medium',
        '--mode','plan','--output-format','json','--json-schema',str(OUT/'design-schema.json'),'--print-timeout','420s'],480)
    (OUT/'opus-response.json').write_text(r.stdout,encoding='utf-8')
    (OUT/'opus-stderr.txt').write_text(r.stderr,encoding='utf-8')
    after=usage('quota-after.json')
    raw=json.loads(r.stdout) if r.stdout.strip() else {}
    def fractions(v):
        return {b['id']:b['remaining_fraction'] for group in v['command']['data']['groups'] for b in group['buckets'] if b['id'].startswith('3p-')}
    a,b=fractions(before),fractions(after)
    cost={'requested_model':'claude-opus-5-5-medium','exit_code':r.returncode,'status':raw.get('status'),
          'conversation_id':raw.get('conversation_id'),'duration_seconds_measured':time.time()-started,
          'usage':raw.get('usage'),'num_turns':raw.get('num_turns'),
          'quota_before':a,'quota_after':b,'quota_consumed_percentage_points':{k:(a[k]-b[k])*100 for k in a},
          'quota_note':'Shared Claude/GPT quota fractions, not exact currency or proprietary credit units; other concurrent use can affect delta.'}
    (OUT/'consumption.json').write_text(json.dumps(cost,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(cost,ensure_ascii=False,indent=2),flush=True)
    if r.returncode or raw.get('status')!='SUCCESS':raise RuntimeError('Opus run failed; see actual response/stderr')


if __name__=='__main__':main()
