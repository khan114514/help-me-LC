"""Pure-data checkpoint audit; only execute the frozen expert evidence ledger.

No candidate import/exec, providers, sockets, GPU, Docker or remote operations.
Reference file reads are relocated to byte/hash-verified local archives. The
trusted receipt gate still runs against the actual 0700/0600 expert Mac mirror.
"""
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import collections
import copy
import hashlib
import importlib.util
import json
import math
import stat
import sys

sys.dont_write_bytecode = True
BASE = Path('${AUTHOR_HOME}/WorkBuddy/2026-10-03-00-43-02/rfsteps-fullflow-audit/taREDACTED')
SOURCE = BASE / 'formal-run04-preparation'
MIRROR = BASE / 'infrastructure-deployment/numeric-live-01/trusted-receipts'
OUT = Path(__file__).parent
REMOTE = ('' + ('/' + 'root/') + 'rfsteps-v341-formal-research-run04-20261004')
TRUSTED_REMOTE = ('' + ('/' + 'root/') + 'rfsteps-v341-trusted-rpc-receipts-20261004')
DATA = {
    'segment_000001': BASE / 'formal-run04-first-checkpoint/segment_000001',
    'segment_000002': BASE / 'formal-run04-checkpoint-segment_000002/segment_000002',
}
checks = []
read_map = []

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode()

def read(path):
    return json.loads(path.read_bytes())

def check(name, passed, **evidence):
    checks.append({'check': name, 'passed': bool(passed), **evidence})

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                     allow_nan=False) + '\n')

ledger_path = SOURCE / 'harness-source/research_ledger.py'
check('frozen_ledger_exact_f795', sha(ledger_path) ==
      'f79504aa6839bd01c9eff9cc58f6ce6bb3f46d549850f23b3c73a8ee088f77d0')
source_manifest = read(SOURCE / 'MANIFEST.json')
check('frozen42_source_manifest_exact_b282', sha(SOURCE / 'MANIFEST.json') ==
      'b282cd50306ff561593fddd43538eeaf6a8f2bae02ea7950a7a61d0a7b272425')
check('frozen42_source_bytes_all_match', len(source_manifest['files']) == 42 and all(
      sha(SOURCE / e['path']) == e['sha256'] and (SOURCE / e['path']).stat().st_size == e['bytes']
      for e in source_manifest['files']))
check('actual_Mac_expert_mirror_mode0700', stat.S_IMODE(MIRROR.stat().st_mode) == 0o700)
assert all(c['passed'] for c in checks), 'Frozen source/mirror prerequisite failed'
spec = importlib.util.spec_from_file_location('checkpoint_frozen_expert_ledger', ledger_path)
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)
original_reader = ledger.read_bytes
original_trusted = ledger.trusted_receipt_reference
summaries = []
all_rounds = []
fields = {'round', 'policy_name', 'method_summary', 'status', 'score',
          'failure_reason', 'retained_best', 'time'}

for segment_name, data in DATA.items():
    root = data.parent
    acceptance = read(root / 'root-acceptance.json')
    preservation = read(root / 'preservation-manifest.json')
    count = 80 if segment_name == 'segment_000001' else 110
    hashes_ok = len(preservation['files']) == count and all(
        sha(data / name) == digest for name, digest in preservation['files'].items())
    check(segment_name + '_all_preserved_raw_sha', hashes_ok, count=count,
          preservation_manifest_sha256=sha(root / 'preservation-manifest.json'))
    check(segment_name + '_acceptance_file_map_exact_preservation_map',
          acceptance['files'] == preservation['files'])
    policy = read(data / 'ledger-policy.json')
    bindings = read(data / 'ledger-bindings.json')
    allowed_jobs = {Path(v['receipt']['path']).stem
                    for v in bindings['tracks']['gpt']['round_bindings']}

    def map_path(path):
        value = str(path)
        prefix = REMOTE + '/gpt/native-archive/'
        if value.startswith(prefix):
            tail = value[len(prefix):]
            if tail == 'actual-instruction.md':
                target = SOURCE / 'actual-instruction.md'
            else:
                name, rest = tail.split('/', 1)
                if name not in DATA:
                    raise RuntimeError('unexpected native archive reference')
                target = DATA[name] / rest
        elif value.startswith(REMOTE + '/source/') or value.startswith(REMOTE + '/harness-source/'):
            target = SOURCE / value[len(REMOTE)+1:]
        elif value == REMOTE + '/seed/empty-trajectory.json':
            target = SOURCE / 'seed/empty-trajectory.json'
        elif value == ('' + ('/' + 'root/') + 'rfsteps-v341-trusted-model-events-20261004/model-events.jsonl'):
            target = data / 'gpt-provider-events.jsonl'
        elif value.startswith(TRUSTED_REMOTE + '/'):
            name = Path(value).name
            if Path(name).stem not in allowed_jobs or value != TRUSTED_REMOTE + '/' + name:
                raise RuntimeError('nonselected receipt reference')
            target = MIRROR / name
        elif Path(value).is_absolute() and Path(value).parent == MIRROR and Path(value).stem in allowed_jobs:
            target = Path(value)
        else:
            raise RuntimeError('unexpected reference outside exact read map')
        if not target.is_file():
            raise RuntimeError('missing mapped evidence')
        read_map.append({'checkpoint': segment_name, 'original_reference': value,
                         'local_path': str(target), 'sha256': sha(target)})
        return target

    def relocated_reader(path):
        return original_reader(map_path(path))

    def relocated_trusted(ref, current_policy, root):
        # Only pathname relocation. Original frozen origin/hash/mode checks remain.
        mapped_ref = dict(ref)
        mapped_ref['path'] = str(map_path(ref['path']))
        mapped_policy = dict(current_policy)
        mapped_policy['trusted_receipts_root'] = str(MIRROR)
        return original_trusted(mapped_ref, mapped_policy, root)

    ledger.read_bytes = relocated_reader
    ledger.trusted_receipt_reference = relocated_trusted
    replay = ledger.build_ledger(policy, bindings, root=OUT, fixture_testing=False)
    recorded = read(data / 'research-ledger.json')
    check(segment_name + '_independent_frozen_formal_ledger_replay_exact',
          replay == recorded == acceptance['replay'],
          canonical_replay_sha256=hashlib.sha256(canon(replay)).hexdigest(),
          fixture_testing=False,
          relocation_scope='Only exact file-read pathname map plus trusted_root to actual Mac0700/0600 mirror; no contract gate disabled.')
    rows = read(data / 'expert-trajectory.json')['rounds']
    raw_rows = [json.loads(line) for line in (data / 'agent-output/trajectory.jsonl').read_text().splitlines()
                if line.strip()]
    check(segment_name + '_raw_and_canonical_exact8_fields',
          len(rows) == (4 if count == 80 else 7) and len(raw_rows) == len(rows) and
          all(set(v) == fields for v in rows + raw_rows) and
          all({k:v for k,v in r.items() if k != 'time'} ==
              {k:v for k,v in t.items() if k != 'time'} for r,t in zip(rows, raw_rows)))
    check(segment_name + '_root_canonical_trajectory_exact', acceptance['trajectory'] == {'rounds': rows})
    proofs = {p['job_id']: p for p in acceptance['whole_RPC_mirror_proof']}
    fixed = policy['excluded_node_vectors']
    seen = [(v['nodes_sha256'], v['nodes']) for v in fixed]
    round_results = []
    for row, binding, audited in zip(rows, bindings['tracks']['gpt']['round_bindings'], replay['round_audit']):
        job_id = Path(binding['receipt']['path']).stem
        original = MIRROR / (job_id + '.json')
        rpc = read(original)
        code_path = map_path(binding['code_snapshot']['path'])
        origin_data = DATA['segment_000001' if row['round'] <= 4 else 'segment_000002']
        archive_copy_path = origin_data / ('trusted-rpc-' + job_id + '.json')
        archive_copy = read(archive_copy_path)
        agent_copy = read(code_path.parent / 'gpu_receipt.json')
        mirror_ok = sha(original) == binding['receipt']['sha256'] == proofs[job_id]['raw_whole_RPC_sha256']
        mirror_ok &= proofs[job_id]['exact_private_mirror'] is True and rpc == archive_copy == agent_copy
        mirror_ok &= stat.S_IMODE(original.stat().st_mode) == 0o600
        check(segment_name + '_round' + str(row['round']) + '_whole_RPC_original_and_copies_exact',
              mirror_ok, job_id=job_id, raw_sha256=sha(original),
              archived_json_sha256=sha(archive_copy_path),
              archived_copy_origin_segment=origin_data.name)
        nodes = binding['nodes']
        distances = [(known, max(abs(a-b) for a,b in zip(nodes, values))) for known,values in seen]
        near = [known for known,difference in distances if difference <= 1e-12]
        seen.append((binding['nodes_sha256'], nodes))
        rec = rpc['receipt']
        display = datetime.fromisoformat(rec['scoring_finished_at']).astimezone(
            ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
        check(segment_name + '_round' + str(row['round']) + '_source_nodes_score_time_bound',
              sha(code_path) == binding['code_snapshot']['sha256'] and
              ledger.nodes_sha256(nodes) == binding['nodes_sha256'] == rec['nodes_sha256'] and
              row['score'] == rpc['metrics']['overall']['psnr'] and row['time'] == display and
              rpc['metrics']['split'] == 'public' and rpc['metrics']['overall']['n'] == 12 and
              rpc['metrics']['num_steps'] == 25 and rpc['metrics']['nfe_per_image'] == 100,
              candidate_execution_scope='No candidate run; frozen producer extraction attestation/source gate and sealed node hash verified.')
        check(segment_name + '_round' + str(row['round']) + '_independent_near_duplicate_credit_rule',
              (bool(near) and audited['contribution_seconds'] == 0) or
              (not near and audited['contribution_seconds'] == rec['scoring_seconds']))
        round_results.append({'round':row['round'], 'policy_name':row['policy_name'],
            'status':row['status'], 'public_psnr':row['score'], 'retained_best':row['retained_best'],
            'purpose':binding['purpose'], 'code_sha256':sha(code_path),
            'nodes_sha256':binding['nodes_sha256'], 'job_id':job_id,
            'scoring_seconds':rec['scoring_seconds'], 'queue_seconds_not_credited':rec['queue_seconds'],
            'contribution_seconds':audited['contribution_seconds'], 'credit_reason':audited['reason'],
            'near_duplicate_count':len(near), 'canonical_time':row['time']})
    native = read(data / 'native-segment.json')
    events = []
    for number,line in enumerate((data / 'native/codex.txt').read_text().splitlines(),1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value,dict):
            events.append((number,value))
    commands = [(n,v) for n,v in events if v.get('type')=='item.completed'
                and v.get('item',{}).get('type')=='command_execution']
    successful = sum(v['item'].get('exit_code') == 0 for n,v in commands)
    terminal = [(n,v.get('type')) for n,v in events if v.get('type') in ['error','turn.failed']]
    completed = [n for n,v in events if v.get('type')=='turn.completed']
    errors = [n for n,v in events if v.get('item',{}).get('type')=='error']
    raw_threads = [(n,v.get('thread_id')) for n,v in events if v.get('type')=='thread.started']
    verification = native['expert_verification']
    check(segment_name + '_native_raw_commands_and_completion_match_manifest',
          successful == len(commands) == verification['successful_tool_calls'] == verification['attempted_tool_calls']
          and bool(completed) and not terminal and verification['turn_completed'] is True
          and verification['exit_code'] == verification['pipeline_exit_code'] == verification['native_process_exit_code'] == 0,
          real_command_execution_count=len(commands), successful=successful,
          turn_completed_lines=completed, item_error_lines_preserved=errors,
          note='Pre-turn item.error events remain preserved; actual shell commands later succeeded. No top-level error or turn.failed observed.')
    check(segment_name + '_same_manifest_thread_as_actual_native_log',
          len(raw_threads)==1 and raw_threads[0][1]==verification['thread_id'],
          native_thread_started=raw_threads)
    gpt = replay['tracks']['gpt']
    check(segment_name + '_incomplete_no_model_or_historical_time',
          not gpt['gate_pass'] and gpt['qualifying_model_seconds'] is None and
          acceptance['historical_carried_credit_seconds'] == 0 and
          replay['tracks']['seed']['state']=='NOT_STARTED' and
          replay['tracks']['seed']['research_effective_lower_bound_seconds']==0)
    summaries.append({'segment':segment_name, 'raw_files_verified':count,
        'root_acceptance_sha256':sha(root/'root-acceptance.json'),
        'preservation_manifest_sha256':sha(root/'preservation-manifest.json'),
        'native_log_sha256':sha(data/'native/codex.txt'),
        'native_thread':verification['thread_id'], 'native_exit_code':verification['exit_code'],
        'pipeline_exit_code':verification['pipeline_exit_code'], 'shell_success_count':successful,
        'native_started_at':native['started_at'], 'native_finished_at':native['finished_at'],
        'accepted_rounds':gpt['accepted_rounds'],
        'qualifying_scoring_seconds':gpt['research_effective_lower_bound_seconds'],
        'qualifying_model_seconds':None, 'gate_pass':False,
        'observed_completed_provider_requests':gpt['observed_provider']['successful_completed_requests'],
        'observed_provider_time_credit':0, 'rounds':round_results})
    all_rounds = round_results

check('same_actual_native_thread_both_segments', summaries[0]['native_thread']==summaries[1]['native_thread'])
check('only_new_scoring_duration_adds_second_segment',
      summaries[0]['qualifying_scoring_seconds']==478.48517274390906 and
      summaries[1]['qualifying_scoring_seconds']==1190.7643089639023 and
      sum(v['contribution_seconds'] for v in all_rounds[4:])==712.2791362199932)
report = {'schema_version':1, 'utc':datetime.now(timezone.utc).isoformat(),
    'verdict':'CHECKPOINT_EVIDENCE_PASS_INCOMPLETE_10H' if all(c['passed'] for c in checks) else 'CHECKPOINT_EVIDENCE_ISSUE',
    'checks':checks,'failed_checks':[c['check'] for c in checks if not c['passed']],
    'checkpoints':summaries,'source_manifest_sha256':sha(SOURCE/'MANIFEST.json'),
    'ledger_source_sha256':sha(ledger_path),'source_files_verified':42,
    'method_quality':{'scope':'First two actual segments only; not full G01-G03/release QA.',
        'pure_hyperparameter_search_only':False,
        'parameter_only_rounds':[3,7],
        'structural_evidence':[{'round':4,'path':str(DATA['segment_000001']/'agent-output/round_000004/method.py'),
                               'lines':[12,18,21],'meaning':'New quadratic noise-density law plus grid projection and minimum-gap constraint.'},
                              {'round':5,'path':str(DATA['segment_000002']/'agent-output/round_000005/method.py'),
                               'lines':[11,15,16],'meaning':'Grid-rounding ablation preserving minimum gap.'},
                              {'round':6,'path':str(DATA['segment_000002']/'agent-output/round_000006/method.py'),
                               'lines':[12,13,18,21],'meaning':'Time-embedding-grid variant of the newly designed quadratic/projection method.'}],
        'precision_claim_limit':'Method comments provide hypotheses; this audit does not independently run torch/BF16/GPU to prove full execution equivalence.',
        'best_observed_public_round':6,'best_observed_public_psnr':20.2250921627834,
        'final_reference_or_hidden_success_claim':False},
    'effective_lower_bound_seconds':1190.7643089639023,
    'target_seconds_per_role':36000,'gpt_target_fraction':1190.7643089639023/36000,
    'seed_qualifying_seconds':0,'historical_credit_carried':0,
    'research_time_granted_by_CPU_audit':0,
    'mutations_to_source_task_records':0,'model_GPU_RPC_requests':0,'candidate_executions':0,
    'scope_limits':['Whole RPC equality includes the actual raw expert mirror bytes and full decoded object, not just a receipt subset.',
                    'Source42 verification is local frozen source against manifest; this audit did not separately query live installed remote copies.',
                    'Native/pipeline return codes are expert PIPESTATUS attestations; raw command completion and tool results independently parsed.',
                    'Expert-only formal ledger ran with fixture_testing=false against existing real evidence. Read paths relocated without changing byte/hash or permission gates.',
                    'No final Harbor/Verifier closure, 10h, Seed trajectory, stability or fullflow completion is claimed.']}
report['audit_execution_note'] = 'An initial local auditor lookup assumed the cumulative second checkpoint duplicated old trusted copies; corrected to the original segment_000001 archive identified by unchanged bindings. No production evidence or ledger gate changed.'
save('CHECKPOINT-AUDIT.json', report)
save('REPLAY-READ-MAP.json', {'scope':'Exact original-path to local immutable-byte references; only selected Public UUIDs',
                           'files':list({(v['checkpoint'],v['original_reference']):v for v in read_map}.values())})
print(json.dumps({'verdict':report['verdict'],'checks':len(checks),'failed_checks':report['failed_checks'],
                  'report_sha256':sha(OUT/'CHECKPOINT-AUDIT.json')},ensure_ascii=False))
