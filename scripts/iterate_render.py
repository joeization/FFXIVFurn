"""One bounded local-Qwen render critique -> guarded yaw patch -> multiview rerender."""
from contextlib import closing
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ffxiv_furniture.config import model_settings
from ffxiv_furniture.classification.client import Client
from ffxiv_furniture.classification.runner import execute_job
from ffxiv_furniture.classification.state import connect,digest,read_json,write_json
from ffxiv_furniture.rendering.pipeline import run_pipeline


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    manifest=read_json(a.run_dir/'manifest.json');request=read_json(a.run_dir/'review-request.json')
    # Initial automated loop is rotation-only, avoiding unknown support/group translations.
    eligible=[o['instance_id'] for o in manifest['objects'].values() if o.get('item_id') and any(w in o['name'].lower() for w in ['stool','chair'])]
    if not eligible:raise ValueError('No eligible standalone seating rotation targets')
    if not a.execute:
        print(json.dumps({'will_call_local_model':True,'eligible_instances':eligible,'max_iterations':1,'max_changes':3,'translation_allowed':False},indent=2));return
    endpoint,model=model_settings()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    schema={'type':'object','additionalProperties':False,'required':['summary','changes'],'properties':{
        'summary':{'type':'string'},'changes':{'type':'array','maxItems':3,'items':{'type':'object','additionalProperties':False,'required':['instance_id','yaw_delta_degrees','reason'],'properties':{
        'instance_id':{'type':'string','enum':eligible},'yaw_delta_degrees':{'type':'number','minimum':-45,'maximum':45},'reason':{'type':'string'}}}}}}
    client=Client(endpoint,model,240,enable_thinking=False,structured_output=True)
    client.response_format={'type':'json_schema','json_schema':{'name':'render_critique','strict':True,'schema':schema}};client.discover()
    text=('Review these actual mesh previews. This is a bounded geometry-only experiment. Real material graphs and lights are not reconstructed; grey/white surfaces may be unresolved or tintable. '
        'Do not critique or change material colors, lighting, walls or stairs. Only consider whether a small arbitrary-angle rotation of an eligible stool/chair would improve seating orientation/composition. '
        'No translations, new objects, or whole-scene redesign. At most3 targets, at most45 degrees delta each. Do not force a change: empty changes is valid. '
        'Model front orientation is not calibrated; express uncertainty. Output only JSON matching schema.\n'+json.dumps({'eligible':eligible,'objects':request['objects'],'warnings':request['warnings']},ensure_ascii=False))
    content=[{'type':'text','text':text}];images=[]
    for i,view in enumerate(manifest['views'][:4],1):
        data=Path(view.get('labeled',view['image'])).read_bytes();images.append({'anon_id':f'VIEW{i}','image_hash':hashlib.sha256(data).hexdigest()})
        content.extend([{'type':'text','text':json.dumps({'view':i,'camera':view['camera']})},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(data).decode()}}])
    def validate(value):
        if set(value)!={'summary','changes'} or not isinstance(value['summary'],str) or not isinstance(value['changes'],list) or len(value['changes'])>3:raise ValueError('Critique shape mismatch')
        seen=set()
        for c in value['changes']:
            if set(c)!={'instance_id','yaw_delta_degrees','reason'} or c['instance_id'] not in eligible or c['instance_id'] in seen:raise ValueError('Invalid critique target')
            if isinstance(c['yaw_delta_degrees'],bool) or not isinstance(c['yaw_delta_degrees'],(int,float)) or not -45<=c['yaw_delta_degrees']<=45:raise ValueError('Critique yaw limit')
            seen.add(c['instance_id'])
        return value
    with closing(connect(a.output_dir/'inference')) as db:
        result,cached=execute_job(db,a.output_dir/'inference',client,'visual','render-critique',[{'role':'user','content':content}],validate,{'input_render_manifest_hash':digest(manifest),'policy':'rotation-only-v1'},images,max_tokens=3000)
    if result is None:raise ValueError('Inference owned by another worker')
    write_json(a.output_dir/'critique.json',result)
    patch={'base_layout_sha256':manifest['rendered_layout_sha256'],'changes':[{'instance_id':c['instance_id'],'delta_translation_m':[0,0,0],'yaw_delta_degrees':c['yaw_delta_degrees']} for c in result['changes']]}
    write_json(a.output_dir/'patch.json',patch)
    summary={'model':client.model,'cached':cached,'proposed_changes':len(result['changes']),'rendered_after':False,'automatic_quality_improvement_claimed':False,'iterations':1}
    if patch['changes']:
        try:
            after=run_pipeline(manifest['rendered_layout'],a.output_dir/'after',patch=patch,room_context=manifest['room_context'],approximate_tint=manifest['approximate_tint_enabled'],cameras=[v['camera'] for v in manifest['views']],size=tuple(manifest['views'][0]['size']),artifacts=True)
            summary.update(rendered_after=True,after_manifest=str((a.output_dir/'after/manifest.json').resolve()),guard_passed=True)
        except ValueError as error:summary.update(guard_passed=False,rejected_reason=str(error))
    write_json(a.output_dir/'iteration-report.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
