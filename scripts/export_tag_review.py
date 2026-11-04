"""Export a vocabulary snapshot to spreadsheet-safe review CSVs; never edit it."""
import argparse
import csv
import json
from pathlib import Path


def safe_cell(value):
    if isinstance(value,(dict,list)):
        value=json.dumps(value,ensure_ascii=False)
    if value is None:
        return ''
    value=str(value)
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value


def export(vocab_path,output_dir):
    vocab=json.loads(Path(vocab_path).read_text(encoding='utf-8'))
    concepts=vocab['concepts']
    if len({x['concept_id'] for x in concepts})!=len(concepts):
        raise ValueError('Duplicate concept ID')
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    fields=['concept_id','key','category','name','status','merged_into','definition',
            'aliases','original_names','source_unique_images','source_furniture_candidates',
            'source_strata','include','exclude','examples']
    with (output/'tags.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for concept in sorted(concepts,key=lambda x:(x['category'],x['name'],x['concept_id'])):
            row={k:concept.get(k) for k in fields}
            for field,target in [('unique_images','source_unique_images'),('furniture_candidates','source_furniture_candidates'),('source_strata','source_strata')]:
                row[target]=concept.get('frequency',{}).get(field)
            writer.writerow({k:safe_cell(v) for k,v in row.items()})
    fields=['proposal_id','action','source','target','status','interchangeable','reason','policy']
    proposals=vocab.get('proposals',[])
    with (output/'decisions.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for proposal in proposals:
            writer.writerow({k:safe_cell(proposal.get(k)) for k in fields})
    return {'vocabulary':str(Path(vocab_path).resolve()),'concept_rows':len(concepts),
            'proposal_rows':len(proposals),'output_dir':str(output.resolve()),
            'note':'Source frequencies are original evidence counts, not summed canonical-group prevalence.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vocab',required=True)
    p.add_argument('--output-dir',required=True)
    a=p.parse_args();print(json.dumps(export(a.vocab,a.output_dir),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
