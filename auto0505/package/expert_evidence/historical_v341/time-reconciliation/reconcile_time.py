"""Read-only reconciliation of timestamps under the user's revised time rule.

No provider/GPU/candidate runs; no legacy supervisor contents or credentials.
Do not interpret a point-event hull or a supervisor timer as continuous work.
"""
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import collections

BASE = Path('${AUTHOR_HOME}/WorkBuddy/2026-10-03-00-43-02/rfsteps-fullflow-audit')
OUT = Path(__file__).parent
intervals = []
outer = []
sources = {}
ambiguous = []

def load(path):
    data = path.read_bytes()
    sources[str(path)] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    return json.loads(data)

def dt(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone not explicit')
    return result.astimezone(timezone.utc)

def interval(role, start, finish, source, field, kind, **extra):
    if start is None or finish is None:
        return
    try:
        left, right = dt(start), dt(finish)
    except ValueError:
        ambiguous.append({'source': str(source), 'field': field, 'start': start,
                          'finish': finish, 'reason': 'No explicit timezone; not imputed.'})
        return
    assert left <= right
    intervals.append({'role': role, 'start': left.isoformat(), 'finish': right.isoformat(),
                      'seconds': (right-left).total_seconds(), 'source': str(source),
                      'field': field, 'kind': kind, **extra})

def union(values):
    merged = []
    for a,b in sorted(values):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a,b))
    return merged

def seconds(values):
    return sum((b-a).total_seconds() for a,b in union(values))

def intersect(left, right):
    return union([(max(a,c),min(b,d)) for a,b in union(left) for c,d in union(right)
                  if max(a,c) < min(b,d)])

def encoded(values):
    return [{'start_utc': a.isoformat(), 'finish_utc': b.isoformat(),
             'seconds': (b-a).total_seconds()} for a,b in union(values)]

# Actual expert native intervals, including failed/partial invocations and
# duplicate preserved copies (duplicates disappear through interval union).
for path in sorted(BASE.rglob('native-segment.json')):
    if any(part in str(path).lower() for part in ['cpu-evidence', 'cpu-validation', 'source-snapshots']):
        continue
    data = load(path)
    if data.get('evidence_kind') != 'formal':
        continue
    interval(data['track'], data.get('started_at'), data.get('finished_at'), path,
             'started_at/finished_at', 'research_native',
             native_exit_code=data.get('expert_verification', {}).get('exit_code'),
             task_sha256=data.get('task_sha256'),
             note='No zeroing for failure, duplicate candidate or source-version migration.')

# Trial Z timestamps are authoritative; top-level Job result datetimes are naive
# and +8h relative to corresponding trials, and are explicitly not assumed UTC.
trial_roots = [BASE/'model-smoke', BASE/'model-preflight',
               BASE/'formal-research-run02/preserved-harbor-job',
               BASE/'formal-research-run03/preserved-harbor-job']
trial_roots += [BASE/'taREDACTED'/name/'harbor-job' for name in
                ['formal-run01-failed-preservation', 'formal-run02-ledger-bug-preservation',
                 'formal-run03-tool-loop-preservation']]
for root in trial_roots:
    for path in sorted(root.rglob('result.json')):
        data = load(path)
        if 'agent_execution' not in data:
            if data.get('started_at') and data.get('finished_at'):
                try:
                    dt(data['started_at']); dt(data['finished_at'])
                except ValueError:
                    ambiguous.append({'source': str(path), 'field': 'Job started_at/finished_at',
                        'start': data['started_at'], 'finish': data['finished_at'],
                        'reason': 'Naive Job clock; corresponding trial Z clock used instead.'})
            continue
        role = 'seed' if 'seed' in str(path).lower() else 'gpt'
        is_probe = any(part in str(path) for part in ['model-smoke', 'model-preflight'])
        agent = data.get('agent_execution') or {}
        interval(role, agent.get('started_at'), agent.get('finished_at'), path,
                 'agent_execution.started_at/finished_at',
                 'model_tool_probe' if is_probe else 'research_agent_execution',
                 task_sha256=data.get('task_checksum'))
        if data.get('started_at') and data.get('finished_at'):
            try:
                outer.append({'role':role,'start':dt(data['started_at']).isoformat(),
                              'finish':dt(data['finished_at']).isoformat(),'source':str(path),
                              'scope':'Outer Trial bounds, not automatically continuous Agent work.'})
            except ValueError:
                pass

for path in sorted((BASE/'taREDACTED').glob('model-preflight*/preserved-remote/*/summary.json')):
    data = load(path)
    interval(data['role'], data.get('started_at'), data.get('finished_at'), path,
             'summary.started_at/finished_at', 'model_tool_probe',
             outcome_passed=data.get('passed'),
             note='Real model/tool preparation; separately reported, no GPU-only qualification constraint.')

# Continuous currently running formal04 envelope is supported only through the
# last already archived native segment, never extended to now or a future end.
launch_path = BASE/'taREDACTED/gpt-formal-run04-launch-receipt.json'
launch = load(launch_path)
formal04 = [r for r in intervals if r['kind']=='research_native' and
            '/formal-run04-' in r['source']]
last_archived = max(dt(r['finish']) for r in formal04)
interval('gpt', launch['launched_at_utc'], last_archived.isoformat(), launch_path,
         'launched_at_utc -> last archived native.finished_at', 'ongoing_confirmed_run_envelope',
         finish_scope='Censored at latest archived segment; includes actual expert close-loop gaps; no extrapolation.',
         owned_pid=launch['pid'], owned_start_ticks=launch['start_ticks'])

historical_audit = load(BASE/'tracks/tracks-audit.json')
historical = {}
for entry in historical_audit['tracks']:
    role = 'gpt' if entry['track']=='codex' else 'seed'
    path = BASE/('tracks/historical-code-and-events/expert_evidence/trajectories/trajectory_'+entry['track']+'.jsonl')
    raw = path.read_bytes()
    sources[str(path)]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    events = [json.loads(v) for v in raw.decode().splitlines() if v.strip()]
    stamps = sorted(dt(v['ts']) for v in events)
    canonical = entry['canonical_trajectory']
    completed_start, completed_end = dt(canonical['first_completion']),dt(canonical['last_completion'])
    errors = entry['transport_error_bookmarks']
    historical[role] = {
        'completed_attempts':canonical['rounds'], 'event_count':len(events),
        'completion_point_span':encoded([(completed_start,completed_end)])[0],
        'all_event_point_span_including_wrap_recovery':encoded([(stamps[0],stamps[-1])])[0],
        'time_evidence_status':'POINT_EVENT_HULL_NOT_CONTINUOUS_RUNTIME_PROOF',
        'network_deduction_seconds':None,
        'network_duration_status':'OLD_ERROR_BOOKMARKS_HAVE_NO_TIMESTAMP; cannot derive duration from counts or gaps.',
        'safe_error_bookmark_counts':dict(collections.Counter(v['category'] for v in errors)),
        'error_bookmark_scope':entry['transport_error_scope'],
        'largest_completion_gaps':canonical['largest_completion_gaps'],
        'supervisor_timer':entry['timer_log'],
        'timer_status':'Timezone absent and UTC/local interpretation ambiguous; no 10h assumption.',
        'raw_supervisor_source_sha_only':entry['raw_supervisor'],
        'model_configuration_scope':entry['banner_summary'],
        'clock_zeroing_for_old_version_or_failure_applied':False,
        'canonical_snapshot_path':str(BASE/('tracks/historical-package-trajectories/trajectory_'+entry['track']+'.json')),
        'canonical_snapshot_sha256':hashlib.sha256((BASE/('tracks/historical-package-trajectories/trajectory_'+entry['track']+'.json')).read_bytes()).hexdigest(),
        'actual_legacy_supervisor_contents_read':False,
    }

# Confirmed v341 stale reverse-forward outage. Its internal EXHAUSTED state
# never restored itself; operator UP is a separate lifecycle origin.
outage_path=BASE/'connection-outage-20261004-1239/OUTAGE-AUDIT.json'
outage=load(outage_path)
operator_path=BASE/'taREDACTED/infrastructure-deployment/operator-recovery-01/minimal-model-live-01/operator-events.jsonl'
raw=operator_path.read_bytes();sources[str(operator_path)]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
operator_events=[json.loads(v) for v in raw.decode().splitlines() if v.strip()]
up=next(v for v in operator_events if v['event']=='reverse_forward_up')
forward=(dt(outage['lifecycle']['first_model_outage_utc']),dt(up['utc']))
network=[{'scope':'v341 model reverse forward', 'start_utc':forward[0].isoformat(),
          'finish_utc':forward[1].isoformat(), 'seconds':(forward[1]-forward[0]).total_seconds(),
          'status':'OWNED_FORWARD_OUTAGE_THROUGH_EXTERNAL_OPERATOR_UP',
          'sources':[str(outage_path),str(operator_path)],'deduction_roles':['gpt','seed']}]

# Failed stream start is not treated as network loss start: it can contain valid
# model thinking/data. Exact failed-connect request intervals are known; true
# outage onset/end and retry gaps have wider uncertainty.
provider_path=BASE/'tracks/run03-qualification-followup/provider-terminal-details.json'
provider=load(provider_path)
failed=[v for v in provider['records'] if v.get('event')=='model_request' and
        v.get('failure_kind')=='transport_failure']
connect=[(dt(v.get('upstream_started_at',v['started_at'])),dt(v['finished_at']))
         for v in failed if v.get('request_phase')=='upstream_connect']
potential=(dt(failed[0]['started_at']),dt(failed[-1]['finished_at']))
network.append({'scope':'v34 formal03 upstream transport failures','status':'REQUEST_INTERVALS_EXACT_OUTAGE_BOUNDARIES_UNCERTAIN',
    'failure_requests':len(failed),'direct_failed_connect_intervals':encoded(connect),
    'direct_failed_connect_union_seconds':seconds(connect),
    'first_failed_stream_request_start_utc':potential[0].isoformat(),
    'first_stream_failure_detected_at_utc':failed[0]['finished_at'],
    'last_failed_request_finished_at_utc':potential[1].isoformat(),
    'potential_outage_envelope_seconds':(potential[1]-potential[0]).total_seconds(),
    'recovery_at':None,'source':str(provider_path),
    'note':'No completed model response after the failed cluster in this run. Stream onset/retry gaps not silently credited or fully deducted.'})
known_network=[forward]+connect
possible_network=[forward,potential]
summaries={}
for role in ['gpt','seed']:
    total=union([(dt(r['start']),dt(r['finish'])) for r in intervals if r['role']==role])
    research=union([(dt(r['start']),dt(r['finish'])) for r in intervals if r['role']==role and r['kind']!='model_tool_probe'])
    probes=union([(dt(r['start']),dt(r['finish'])) for r in intervals if r['role']==role and r['kind']=='model_tool_probe'])
    known=intersect(total,known_network)
    possible=intersect(total,possible_network)
    gross=seconds(total);deduct=seconds(known);maxdeduct=seconds(possible)
    h=historical[role]
    summaries[role]={
        'exact_oct4_actual_activity_intervals_union':encoded(total),
        'exact_oct4_gross_seconds':gross,
        'oct4_research_process_union_seconds':seconds(research),
        'oct4_real_model_tool_preparation_union_seconds':seconds(probes),
        'exact_known_network_intersection':encoded(known),
        'exact_known_network_deduction_seconds':deduct,
        'oct4_net_after_only_exact_known_network_seconds':gross-deduct,
        'oct4_net_if_full_uncertain_failure_envelope_is_blocked_seconds':gross-maxdeduct,
        'oct4_net_status':('BOUNDED_OLD03_STREAM_NETWORK_UNCERTAINTY; no arbitrary exclusion for failed tools/version/ledger repair.' if role=='gpt' else 'NO_OBSERVED_OCT4_NETWORK_OVERLAP; not a claim that all historical network intervals are known.'),
        'nominal_historical_completion_span_plus_oct4_known_net_seconds':h['completion_point_span']['seconds']+gross-deduct,
        'nominal_historical_all_event_span_plus_oct4_known_net_seconds':h['all_event_point_span_including_wrap_recovery']['seconds']+gross-deduct,
        'nominal_combination_scope':'Arithmetic sensitivity only; point spans may include inactive/network intervals; NOT a certified total.',
        'all_history_network_deducted_actual_research_total_seconds':None,
        'target_met':None,
        'evidence_certified_target_met':None,
        'user_accepted_time_sufficiency':True,
    }

latest_gpu_file=max((p for p in BASE.glob('taREDACTED/formal-run04-checkpoint-segment_*/segment_*/research-ledger.json')),
                    key=lambda p:p.parent.name)
gpu=load(latest_gpu_file)
report={'schema_version':1,'utc':datetime.now(timezone.utc).isoformat(),
    'status':'RECONCILED_USER_ACCEPTED_TIME_WITH_EVIDENCE_LIMITS',
    'time_requirement_disposition':{
        'status':'USER_CONFIRMATION_ACCEPTED',
        'source':'Human user confirmation relayed by Root: 时间肯定够.',
        'applies_to_roles':['gpt','seed'],
        'independent_numeric_certification':False,
        'exact_missing_historical_seconds_invented':False,
        'additional_research_required_by_this_time_audit':False,
        'old_GPU_only_shortfall_is_a_task_blocker':False},
    'user_rule':'Count actual research process time; deduct only network-unreachable periods. Do not use GPU scoring_seconds as total or zero real work for expert ledger fixes/version changes.',
    'separate_roles_not_added':True,'interval_union_deduplication':True,
    'exact_activity_records':intervals,'outer_trial_bounds_separately_not_double_counted':outer,
    'historical':historical,'network':network,'role_summaries':summaries,
    'ambiguous_timezone_records':ambiguous,
    'preserved_original_gpu_only_lower_bound':{
        'source':str(latest_gpu_file),'name':'qualifying_scoring_seconds',
        'by_role':{r:v['qualifying_scoring_seconds'] for r,v in gpu['tracks'].items()},
        'scope':'Retained original metric, not revised-rule research total or revised 10h gate.'},
    'unresolved':['Historical network bookmarks lack timestamped outage start/end; original raw supervisor secrets not read.',
                  'Historical point spans do not prove continuous model-process activity, especially GPT late recovery/wrap tail and Seed long gaps.',
                  'Historical timer timezone not explicit; no repair- or migration-driven zeroing and no invented timer interpretation.',
                  'Oct4 failed-stream outage onset lies somewhere after request start; exact request failures are known but continuous recovery boundary is not.',
                  'Model/tool preparation is explicit separate activity; it is shown in broad actual-process union, not mislabeled as scoring research.',
                  'Historical Seed xhigh banner/model isolation qualifications remain separate metadata; timing does not silently certify high or isolation.'],
    'source_manifest':sources,'threshold_pass_claim':False,
    'models_GPU_RPC_or_candidates_executed':0,'production_sources_or_records_modified':0}
report['audit_cutoff']={
    'latest_archived_formal04_finish_utc':last_archived.isoformat(),
    'latest_archived_formal04_finish_asia_shanghai':last_archived.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'),
    'continuing_run_after_cutoff_included':False}
report['scope_limit']='Only observed original timestamps and safe prior projections are reconciled. User acceptance is separate from an independently certified all-history numeric total. Model/effort/isolation/method/verification acceptance is not inferred from timing.'
(OUT/'TIME-RECONCILIATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':report['status'],'exact_records':len(intervals),'asof_archived_formal04_utc':last_archived.isoformat(),
                  'summaries':summaries},ensure_ascii=False,indent=2))
