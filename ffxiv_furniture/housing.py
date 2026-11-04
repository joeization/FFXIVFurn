"""User-supplied furnishing caps and optional floor-closure policy.

Caps are a policy snapshot supplied by the user, not inferred from app save version.
Interior caps cover the WHOLE house, including hidden/overlapping/attached instances.
"""
HOUSING_LIMITS={
    'Apartment':{'interior':150,'exterior':0},
    'PrivateRoom':{'interior':150,'exterior':0},
    'Small':{'interior':300,'exterior':40},
    'Medium':{'interior':450,'exterior':60},
    'Large':{'interior':600,'exterior':80},
}
FLOORS={
    'Apartment':('ground',),'PrivateRoom':('ground',),
    'Small':('ground','basement'),
    'Medium':('ground','upper','basement'),'Large':('ground','upper','basement'),
}


def count_instances(items,ancestors=()):
    if not isinstance(items,list):raise ValueError('Furniture/attachments must be arrays')
    count=0
    for item in items:
        if not isinstance(item,dict):raise ValueError('Furniture instances must be objects')
        if id(item) in ancestors:raise ValueError('Cyclic attachments')
        count+=1+count_instances(item.get('attachments',[]),ancestors+(id(item),))
    return count


def validate_layout_budget(layout):
    size=layout.get('houseSize')
    if size not in HOUSING_LIMITS:raise ValueError(f'Unknown houseSize furnishing policy: {size!r}; explicit supported houseSize required')
    result={'house_size':size,'policy_source':'user-provided housing caps','scope_budgets':{}}
    for scope in ('interior','exterior'):
        count=count_instances(layout.get(scope+'Furniture',[]));limit=HOUSING_LIMITS[size][scope]
        if count>limit:raise ValueError(f'{size} {scope} furnishing cap exceeded: {count}>{limit}')
        result['scope_budgets'][scope]={'used':count,'limit':limit,'remaining':limit-count}
    return result


def floor_access_policy(house_size,used_floors=None):
    """Conceal only unused-floor connections; never auto-remove main entrance access.

    This is planning policy, NOT geometric verification of a stair keepout polygon.
    Hidden stairs are native structure, so only furniture used to hide them consumes slots.
    """
    if house_size not in FLOORS:raise ValueError('Unknown house_size')
    known=FLOORS[house_size]
    if isinstance(used_floors,str):raise ValueError('used_floors must be a collection, not string')
    used=set(known if used_floors is None else used_floors)
    if not used<=set(known) or 'ground' not in used:raise ValueError('Used floors must include entrance ground floor and only existing floors')
    connections=[{'from':'ground','to':floor} for floor in known if floor!='ground']
    return {'house_size':house_size,'used_floors':[f for f in known if f in used],
        'required_open_connections':[c for c in connections if c['to'] in used],
        'may_conceal_connections':[c for c in connections if c['to'] not in used],
        'main_entrance_must_remain_accessible':True,'geometric_access_verified':False,
        'concealment_furniture_consumes_budget':True,'interior_budget_is_shared_across_floors':True}
