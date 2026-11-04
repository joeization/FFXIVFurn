"""Constrained decoding contracts; runtime validation still checks exact ID coverage."""
from . import CATEGORIES


def visual_response_format(expected_ids,phase,vocabulary=None):
    string={'type':'string','minLength':1,'maxLength':300}
    confidence={'type':'number','minimum':0,'maximum':1}
    def obj(properties):
        return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
    if phase=='explore':
        tag=obj({'category':{'type':'string','enum':list(CATEGORIES)},'name':string,
                 'confidence':confidence,'evidence':string})
    else:
        keys=sorted(c['key'] for c in vocabulary['concepts'] if c['status'] in ('accepted','provisional') and not c.get('superseded_by'))
        if not keys:
            raise ValueError('Controlled vocabulary must contain an active key')
        tag=obj({'key':{'type':'string','enum':keys},'confidence':confidence,'evidence':string})
    proposal=obj({'category':{'type':'string','enum':list(CATEGORIES)},'name':string,
                  'definition':string,'reason':string,'confidence':confidence,'evidence':string})
    item=obj({'id':{'type':'string','enum':list(expected_ids)},
              'visual_description':{'type':'string','minLength':1,'maxLength':600},
              'tags':{'type':'array','items':tag,'maxItems':6},
              'proposed_tags':{'type':'array','items':proposal,'maxItems':6 if phase=='guided' else 0},
              'uncertain':{'type':'array','items':string,'maxItems':12}})
    schema=obj({'items':{'type':'array','items':item,'minItems':len(expected_ids),'maxItems':len(expected_ids)}})
    return {'type':'json_schema','json_schema':{'name':'furniture_visual_batch','strict':True,'schema':schema}}
