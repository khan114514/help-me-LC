"""Pure-data name-contract replay; never imports scorer/ledger/candidate modules.

This proposed predicate is audit evidence, not a ledger repair or admission.
Historical data and all synthetic mutations remain zero-credit fixtures.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
LEDGER = BASE.parent / "taREDACTED/formal-run02-preparation/harness-source/research_ledger.py"


def proposed_image_contract(metrics, fixed_metric_names):
    images = metrics.get("per_image")
    if not isinstance(images,list) or len(images)!=12:
        return False
    if not all(isinstance(row,dict) and type(row.get("image")) is str
               and row.get("split")=="public" for row in images):
        return False
    names = [row["image"] for row in images]
    return len(set(names))==12 and set(names)==fixed_metric_names


def main():
    tree=ast.parse(LEDGER.read_text())
    assets=None
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="PUBLIC_NAMES" for t in node.targets):
            assets=ast.literal_eval(node.value)
    assert isinstance(assets,set) and len(assets)==12 and all(n.endswith('.png') for n in assets)
    stems={n[:-4] for n in assets};assert len(stems)==12
    bindings=json.loads((BASE/'remote-evidence/ledger-bindings.json').read_text())
    policy=json.loads((BASE/'remote-evidence/ledger-policy.json').read_text())
    round_results=[]
    for row in bindings['tracks']['gpt']['round_bindings']:
        job=Path(row['receipt']['path']).stem
        trusted=json.loads((BASE/'remote-evidence'/('trusted-rpc-'+job+'.json')).read_text())
        metric=trusted['metrics']
        per_names=[v['image'] for v in metric['per_image']]
        agent=json.loads((BASE/'remote-evidence'/'agent-output'/f"round_{row['round']:06d}"/'metrics.json').read_text())
        digest=hashlib.sha256(json.dumps([float(v) for v in row['nodes']],separators=(',',':'),allow_nan=False).encode()).hexdigest()
        round_results.append({'round':row['round'],'purpose':row['purpose'],'job_id':job,
            'trusted_status':trusted['status'],'evaluation_completed':trusted['evaluation_completed'],
            'trusted_sha256':hashlib.sha256((BASE/'remote-evidence'/('trusted-rpc-'+job+'.json')).read_bytes()).hexdigest(),
            'binding_receipt_sha256_matches':hashlib.sha256((BASE/'remote-evidence'/('trusted-rpc-'+job+'.json')).read_bytes()).hexdigest()==row['receipt']['sha256'],
            'per_image_count':len(per_names),'actual_exact_stems':set(per_names)==stems,
            'old_filename_guard_matches':set(per_names)==assets,
            'proposed_stem_guard_matches':proposed_image_contract(metric,stems),
            'agent_per_image_matches_trusted':agent['per_image']==metric['per_image'],
            'asset_filename_contract_unchanged':set(trusted['receipt']['asset_sha256']['public'])==assets and trusted['receipt']['asset_sha256']['public']==policy['public_asset_sha256'],
            'pure_nodes_json_hash_matches':digest==row['nodes_sha256']==trusted['receipt']['nodes_sha256'],
            'contribution_seconds':0,'full_ledger_replayed':False})
    source=copy.deepcopy(trusted['metrics'])
    cases=[]
    def case(name,mutate=None,expected=False):
        value=copy.deepcopy(source)
        if mutate:mutate(value)
        actual=proposed_image_contract(value,stems)
        assert actual is expected
        cases.append({'case':name,'predicate_result':actual,'expected':expected,'passed':True,'research_credit_seconds':0})
    case('real_frozen_scorer_metrics_stems',expected=True)
    case('different_list_order_is_permitted',lambda v:v['per_image'].reverse(),True)
    case('all_metric_names_with_png_suffix',lambda v:[r.update(image=r['image']+'.png') for r in v['per_image']])
    case('one_mixed_png_suffix',lambda v:v['per_image'][0].update(image=v['per_image'][0]['image']+'.png'))
    case('path_alias_is_not_normalized',lambda v:v['per_image'][0].update(image='/tmp/'+v['per_image'][0]['image']))
    case('png_path_alias_is_not_normalized',lambda v:v['per_image'][0].update(image='../'+v['per_image'][0]['image']+'.png'))
    case('duplicate_replacing_missing_public_name',lambda v:v['per_image'][1].update(image=v['per_image'][0]['image']))
    case('unknown_stem',lambda v:v['per_image'][0].update(image='unknown_public_image'))
    case('case_mismatch',lambda v:v['per_image'][0].update(image=v['per_image'][0]['image'].upper()))
    case('hidden_split',lambda v:v['per_image'][0].update(split='hidden'))
    case('missing_image_field',lambda v:v['per_image'][0].pop('image'))
    case('unhashable_image_field',lambda v:v['per_image'][0].update(image=[]))
    case('boolean_image_field',lambda v:v['per_image'][0].update(image=True))
    case('missing_public_row',lambda v:v['per_image'].pop())
    case('extra_public_row',lambda v:v['per_image'].append(copy.deepcopy(v['per_image'][0])))
    case('non_dictionary_row',lambda v:v['per_image'].__setitem__(0,'repo_art'))
    asset_tests=[{'case':'assets_exact_png_keys','passed':set(policy['public_asset_sha256'])==assets},
                 {'case':'asset_stems_are_rejected','passed':set(n[:-4] for n in policy['public_asset_sha256'])!=assets}]
    assert all(v['passed'] for v in asset_tests)
    report={'schema_version':1,'status':'PURE_DATA_NAME_CONTRACT_REPLAY_ONLY',
        'source_ledger_sha256':hashlib.sha256(LEDGER.read_bytes()).hexdigest(),
        'fixed_asset_names':sorted(assets),'fixed_metric_names':sorted(stems),
        'rounds':round_results,'predicate_cases':cases,'asset_cases':asset_tests,
        'full_ledger_replayed':False,'qualification_or_admission_performed':False,
        'all_formal_and_historical_credit_seconds':0,'model_requests':0,'gpu_requests':0,
        'candidate_executions':0,'source_files_modified':False}
    target=BASE/'PURE-DATA-REPLAY.json'
    with target.open('x') as out:json.dump(report,out,indent=2);out.write('\n')
    print(json.dumps({'rounds':len(round_results),'pure_data_cases_passed':len(cases)+len(asset_tests),
                      'old_rejects_all':all(not r['old_filename_guard_matches'] for r in round_results),
                      'proposed_exact_stems_match_all':all(r['proposed_stem_guard_matches'] for r in round_results),
                      'full_ledger_replayed':False,'research_credit_seconds':0},indent=2))


if __name__=='__main__':main()
