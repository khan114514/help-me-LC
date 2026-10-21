"""Read-only AST/hash/JSON audit. Never import production or candidate modules."""
from pathlib import Path
from datetime import datetime, timezone
import ast
import copy
import difflib
import hashlib
import json
import math
import re

BASE = Path('${AUTHOR_HOME}/WorkBuddy/2026-10-03-00-43-02/rfsteps-fullflow-audit')
P = BASE / 'taREDACTED'
OLD = P / 'formal-run03-preparation'
NEW = P / 'formal-run04-preparation'
OUT = Path(__file__).parent
OLD_PROMPT = '6bbce6050c797cf0054b01fbc3585b6fbcd839f3514e9f2884e72f6f9bd4ec21'
PROMPT = 'fc748766095e76608aa29eecf033e07b2aca3d6ce38c7e13584a3d3411638b53'
OLD_DRIVER = 'e07528f452aed392528285724a7378915d13cf3060216edd7aa0ad0b3094872a'
DRIVER = '8d9e51d137c5ec2de61eee9f494986c9084690f576827ed71a355a3bcfde64c2'
TASK = '90bb7746559319dc6ce29dbbfae946f9a6b00694ef04b25d267f7def8c8249cb'
MANIFEST = 'b282cd50306ff561593fddd43538eeaf6a8f2bae02ea7950a7a61d0a7b272425'
checks = []

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def digest(value):
    return hashlib.sha256(value).hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def check(name, condition, **evidence):
    checks.append({'check': name, 'passed': bool(condition), **evidence})

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                     allow_nan=False) + '\n')

def normalize(value):
    return value.replace('formal-research-run03', 'formal-research-run04').replace(
        'formal-research-03', 'formal-research-04').replace(OLD_PROMPT, PROMPT).replace(
        OLD_DRIVER, DRIVER)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

manifest = read(NEW / 'MANIFEST.json')
check('manifest_exact_frozen_sha', sha(NEW / 'MANIFEST.json') == MANIFEST,
      sha256=sha(NEW / 'MANIFEST.json'))
entries = manifest['files']
check('manifest_42_unique_safe_paths', len(entries) == 42 and
      len({e['path'] for e in entries}) == 42 and
      all(not Path(e['path']).is_absolute() and '..' not in Path(e['path']).parts for e in entries))
verified = []
for entry in entries:
    path = NEW / entry['path']
    actual = sha(path)
    good = actual == entry['sha256'] and path.stat().st_size == entry['bytes']
    verified.append({'path': entry['path'], 'sha256': actual, 'bytes': path.stat().st_size,
                     'matched': good})
check('all_42_manifest_sha_and_bytes', all(e['matched'] for e in verified))
check('manifest_exact_file_inventory',
      {str(p.relative_to(NEW)) for p in NEW.rglob('*') if p.is_file()}
      == {e['path'] for e in entries} | {'MANIFEST.json'})
save('MANIFEST-VERIFICATION.json', {'source_manifest_sha256': MANIFEST, 'files': verified})

trees = []
templates = []
template_lines = []
for root in (OLD, NEW):
    tree = ast.parse((root / 'harness-source/continuation_research_codex.py').read_text())
    matches = [n for n in tree.body if isinstance(n, ast.Assign) and
               any(isinstance(t, ast.Name) and t.id == 'CONTINUATION_TEMPLATE' for t in n.targets)]
    assert len(matches) == 1
    node = matches[0]
    templates.append(ast.literal_eval(node.value))
    template_lines.append([node.lineno, node.end_lineno])
    tree.body.remove(node)
    trees.append(ast.dump(tree, include_attributes=False))
check('driver_ast_except_template_identical', trees[0] == trees[1],
      old_sha256=sha(OLD / 'harness-source/continuation_research_codex.py'),
      new_sha256=sha(NEW / 'harness-source/continuation_research_codex.py'),
      template_line_coordinates=template_lines)
check('driver_expected_sha', sha(NEW / 'harness-source/continuation_research_codex.py') == DRIVER)
diff = ''.join(difflib.unified_diff(templates[0].splitlines(True), templates[1].splitlines(True),
                                  fromfile='formal03/CONTINUATION_TEMPLATE',
                                  tofile='formal04/CONTINUATION_TEMPLATE'))
(OUT / 'CONTINUATION-TEMPLATE-DIFF.patch').write_text(diff)
check('template_addition_only_and_explicit_tools', templates[0] == templates[1].replace(
      '''For local file inspection, coding and scoring commands, use the declared
functions.exec tool with JavaScript invoking the local tools.exec_command:
const result = await tools.exec_command({cmd: "YOUR SHELL COMMAND", workdir: "/workspace", max_output_tokens: 3000});
text(result);
This invokes the actual local shell. Use its real output; an assistant message,
self-message or wait on an uncreated exec cell cannot perform a research command.
If a command fails, inspect and correct it truthfully using the same local tool.
''', ''))
base_instruction = (P / 'task/instruction.md').read_bytes()
check('base_instruction_frozen_a253', digest(base_instruction) ==
      'a253ba99c1cbc50d5679e6ab75642d8197617adffa1386a72347749c7934be46',
      sha256=digest(base_instruction), path=str(P / 'task/instruction.md'))
check('full04_exact_base_plus_template', (NEW / 'actual-instruction.md').read_bytes()
      == base_instruction + templates[1].encode(), sha256=sha(NEW / 'actual-instruction.md'))
check('full_prompt_expected_sha', sha(NEW / 'actual-instruction.md') == PROMPT)
check('full03_original_base_plus_template', (OLD / 'actual-instruction.md').read_bytes()
      == base_instruction + templates[0].encode())

check('formal_preflight_only_fresh_root_prompt_and_job_identity_changes',
      normalize((OLD / 'formal_preflight.py').read_text()) == (NEW / 'formal_preflight.py').read_text())
check('test_fixture_only_new_driver_and_job_identity_changes',
      normalize((OLD / 'test_formal_release.py').read_text()) == (NEW / 'test_formal_release.py').read_text())
unchanged_code = ['owned_harbor_runner.py', 'start_formal_track.py', 'serial_track_supervisor.py']
unchanged_code += [str(q.relative_to(NEW)) for folder in ['source', 'harness-source']
                   for q in (NEW / folder).glob('*.py')
                   if q.name != 'continuation_research_codex.py']
check('all_other_runtime_code_bytes_unchanged',
      all((OLD / name).read_bytes() == (NEW / name).read_bytes() for name in unchanged_code),
      paths=unchanged_code)
policy = read(NEW / 'policy-template.json')
old_policy = read(OLD / 'policy-template.json')
check('policy_only_prompt_driver_and_fresh_source_paths_changes',
      normalize(canonical(old_policy)) == canonical(policy))
check('same_task_scorer_gpu_assets_tolerance', policy['task_sha256'] == TASK
      and policy['near_duplicate_absolute_tolerance'] == 1e-12
      and policy['public_asset_sha256'] == old_policy['public_asset_sha256']
      and policy['scorer_sha256'] == old_policy['scorer_sha256']
      and policy['gpu_uuid'] == old_policy['gpu_uuid'])
check('policy_driver_prompt_pins_match', policy['native_harness_sha256'] == DRIVER and
      policy['frozen_instruction_sha256'] == PROMPT)
known = policy['excluded_node_vectors']
excluded = set(policy['excluded_nodes_sha256'])
known_valid = len(known) == 10 and len(excluded) == 10
for v in known:
    nodes = v.get('nodes', [])
    known_valid &= set(v) == {'nodes_sha256', 'nodes'} and len(nodes) == 26
    known_valid &= all(isinstance(n, (int, float)) and not isinstance(n, bool)
                       and math.isfinite(n) for n in nodes)
    known_valid &= abs(nodes[0] - 1) <= 1e-6 and abs(nodes[-1]) <= 1e-6
    known_valid &= all(-1e-9 <= n <= 1 + 1e-9 for n in nodes)
    known_valid &= all(a >= b - 1e-12 for a, b in zip(nodes, nodes[1:]))
    known_valid &= digest(json.dumps([float(n) for n in nodes], separators=(',', ':'),
                                    allow_nan=False).encode()) == v['nodes_sha256']
check('ten_private_vectors_hash_bound_legal_and_exactly_same', known_valid and
      {v['nodes_sha256'] for v in known} == excluded and
      known == old_policy['excluded_node_vectors'], count=len(known),
      canonical_list_sha256=digest(canonical(known).encode()), vectors_published=False)
contract = read(NEW / 'launch-contract.json')
summary = read(NEW / 'source-pin-summary.json')
runtime_pins = contract['runtime_sources']
check('contract_all_runtime_pins_match_actual_bytes',
      all(sha(NEW / name) == value for name, value in runtime_pins.items()), count=len(runtime_pins))
check('contract_runtime_pin_inventory_same_as03', set(runtime_pins) ==
      set(read(OLD / 'launch-contract.json')['runtime_sources']))
check('contract_external_source_pins_same_as03_and_local_frozen_snapshots',
      contract['external_sources'] == read(OLD / 'launch-contract.json')['external_sources'] and
      all(sha(NEW / 'source' / Path(name).name) == value
          for name, value in contract['external_sources'].items()),
      scope='Local snapshot SHA only; actual remote installed copies require Root precheck.')
check('summary_all_source_pins_match', all(sha(NEW / name) == value
      for name, value in summary['source_sha256'].items()), count=len(summary['source_sha256']))
for key, name in [('worker_source', 'remote_gpu_worker.py'),
                  ('numerical_controller_source', 'trusted_controller.py'),
                  ('controller_source', 'expert_model_controller.py'),
                  ('lifecycle_source', 'detached_gateway_lifecycle.py')]:
    check('policy_' + key + '_pin_matches',
          policy[key]['sha256'] == sha(NEW / 'source' / name) and
          policy[key]['path'] == ('' + ('/' + 'root/') + 'rfsteps-v341-formal-research-run04-20261004/source/') + name)
check('summary_contract_and_prompt_sha_consistent',
      summary['launch_contract_sha256'] == sha(NEW / 'launch-contract.json') and
      summary['task_sha256'] == contract['task_sha256'] == TASK and
      summary['full_prompt_sha256'] == contract['prompt_sha256'] == PROMPT and
      summary['task_id'] is None and contract['task_id'] is None)
for role, model, effort in [('gpt', 'gpt-6.1-sol', 'xhigh'),
                            ('seed', 'doubao-seed-2-1-turbo-260628', 'high')]:
    job = read(NEW / role / 'job.json')
    check(role + '_job_only_fresh_paths_changed', normalize(canonical(read(OLD / role / 'job.json')))
          == canonical(job))
    agent = job['agents'][0]
    check(role + '_exact_model_effort_own_socket_same_task', agent['model_name'] == model
          and agent['kwargs']['reasoning_effort'] == effort and agent['kwargs']['role'] == role
          and job['tasks'] == [{'path': ('' + ('/' + 'root/') + 'rfsteps-v341-build-check-20261004')}]
          and job['environment']['mounts'] == [{'type': 'bind',
              'source': ('' + ('/' + 'root/') + 'rfsteps-v341-model-rpc-20261004/sockets/') + role + '.sock',
              'target': '/run/rfsteps-model/' + role + '.sock', 'read_only': True}])
    bindings = read(NEW / role / 'initial-bindings.json')
    check(role + '_initial_bindings_v1_empty_tracks', bindings['schema_version'] == 1
          and set(bindings) == {'schema_version', 'tracks'} and set(bindings['tracks']) == {'gpt', 'seed'}
          and all(v['round_bindings'] == [] and v['trajectory']['sha256'] ==
                  sha(NEW / r / 'empty-trajectory.json') and v['trajectory']['path'] ==
                  ('' + ('/' + 'root/') + 'rfsteps-v341-formal-research-run04-20261004/') + r + '/empty-trajectory.json'
                  for r, v in bindings['tracks'].items()))
    check(role + '_empty_trajectory_exact_rounds', read(NEW / role / 'empty-trajectory.json') == {'rounds': []})
initial = read(NEW / 'empty-initial-ledger.json')
check('empty_initial_ledger_unchanged_and_zero_no_carry',
      (OLD / 'empty-initial-ledger.json').read_bytes() == (NEW / 'empty-initial-ledger.json').read_bytes()
      and initial['round_audit'] == [] and all(v['state'] == 'NOT_STARTED' and
          v['formal_started_at'] is None and v['qualifying_scoring_seconds'] == 0 and
          v['qualifying_model_seconds'] is None and v['accepted_rounds'] == [] and
          v['conservative_lower_bound_seconds'] == 0 and not v['gate_pass']
          for v in initial['tracks'].values()))
check('summary_history02_03_04_zero_carry', all(summary[k] == 0 for k in
      ['history_credit_seconds', 'run02_prior_credit_seconds', 'run03_prior_credit_seconds',
       'run04_prior_credit_seconds']) and summary['qualifying_seconds'] == {'gpt': 0, 'seed': 0})
cpu = (NEW / 'cpu-validation.log').read_text()
first = (NEW / 'cpu-first-stale-harness-fixture-failed.log').read_text()
check('cpu76_pass_log_and_initial_stale_fixture_failure_preserved',
      re.search(r'Ran 76 tests.*\n\nOK\s*$', cpu) is not None and
      'FAILED (failures=1)' in first and 'launch_receipt_identity' in first,
      cpu_log_sha256=sha(NEW / 'cpu-validation.log'),
      preserved_failure_sha256=sha(NEW / 'cpu-first-stale-harness-fixture-failed.log'),
      scope='Read-only retained suite results and minimal fixture diff; no suite rerun in this audit.')
acceptance = read(NEW / 'accepted-native-preflight05.json')
check('prior_actual_preflight05_acceptance_exact_copy_zero_credit',
      sha(NEW / 'accepted-native-preflight05.json') ==
      'acb5ca0d5ad2765bd26211da348d88cf520f40ee4bfd28ba3c61a01be3f61b4f'
      and acceptance['research_credit_seconds'] == 0,
      scope='Prior common tool-format preflight; this is not actual formal04 success evidence.')

preservation = P / 'formal-run03-tool-loop-preservation'
preserved_manifest = read(preservation / 'preservation-manifest.json')
preserved_checks = [{'path': name, 'matched': sha(preservation / name) == expected}
                    for name, expected in preserved_manifest['files'].items()]
check('failed03_preserved_91_files_exact_local_sha', len(preserved_checks) == 91 and
      all(v['matched'] for v in preserved_checks),
      manifest_sha256=sha(preservation / 'preservation-manifest.json'),
      scope='Exact local bytes against Root recorded remote SHA map; no new remote access.')
owned_exit = read(preservation / 'remote-root/gpt/owned-harbor-exit.json')
check('failed03_cancelled_owned_wait_not_success_zero_credit', owned_exit['return_code'] == -9
      and owned_exit['stop_requested'] is True and owned_exit['harbor_wait_completed'] is True
      and owned_exit['research_credit_seconds'] == 0 and preserved_manifest['history_credit_seconds'] == 0,
      evidence=owned_exit,
      sha256=sha(preservation / 'remote-root/gpt/owned-harbor-exit.json'))
report = {'schema_version': 1, 'utc': datetime.now(timezone.utc).isoformat(),
          'verdict': 'SOURCE_RELEASE_PASS_PENDING_ACTUAL_INSTALLED_PRECHECK'
              if all(c['passed'] for c in checks) else 'SOURCE_RELEASE_BLOCKED',
          'checks': checks, 'failed_checks': [c['check'] for c in checks if not c['passed']],
          'source_manifest_sha256': MANIFEST, 'driver_sha256': DRIVER,
          'full_prompt_sha256': PROMPT, 'task_sha256': TASK,
          'ledger_sha256': sha(NEW / 'harness-source/research_ledger.py'),
          'base_task_instruction_sha256': digest(base_instruction),
          'template_sha256': digest(templates[1].encode()),
          'behavior_change_scope': 'Only CONTINUATION_TEMPLATE tool invocation format guidance; formal preflight changes only frozen prompt and fresh-root/job constants. No method suggestion.',
          'pending': ['Actual installed source/Task/gateway PID-start-tick/UDS identity and mode checks; bounded keyless numeric501/model405 connectivity before Native construction.',
                      'Actual Native formal04 tool execution and round closures; template is not proof of future shell success.',
                      'Each independent 36000-second unique legal closed-loop scoring lower bound and complete full16 verifier before serial Seed qualification.'],
          'evidence_limits': ['Task SHA and task path pins/base instruction independently matched; no new full Task63-file rehash or Hidden-pixel read.',
                              'No fresh remote source/runtime reachability check by this audit; Root is performing installed precheck.',
                              'Failed03 native-loop cause is not re-diagnosed here; owned cancellation and preserved byte hashes verified.'],
          'research_credit_seconds': 0, 'formal04_credit_carry': 0,
          'fullflow_completion_claim': False, 'source_task_record_mutations': 0,
          'model_requests': 0, 'gpu_requests': 0, 'candidate_executions': 0,
          'new_files_scope': str(OUT)}
save('SOURCE-REVIEW.json', report)
print(json.dumps({'verdict': report['verdict'], 'checks': len(checks),
                  'failed_checks': report['failed_checks'], 'report_sha256': sha(OUT / 'SOURCE-REVIEW.json')}, ensure_ascii=False))
