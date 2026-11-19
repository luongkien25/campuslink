"""Kiem evidence autoscale da chuan hoa; khong tu chung minh tinh xac thuc log."""
import argparse
import json
import math
from pathlib import Path
import re
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collect_app_timeline import summarize as guest_timeline
from probe_app_pool import correlate
from telemetry.analyze_cpu import analyze as analyze_cpu, timestamp

TOP_KEYS = {'schema_version', 'run_id', 'core', 'load', 'transitions', 'policy_events',
            'manual_signals', 'cooldown_seconds', 'capacity', 'milestones', 'redirects',
            'guest_request_ids', 'deletion', 'cleanup'}


class Invalid(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Invalid(reason)


def ident(value):
    require(isinstance(value, str) and str(uuid.UUID(value)) == value, 'invalid-identifier')
    return value


def evidence(value):
    require(isinstance(value, str) and value.startswith('evidence/')
            and '..' not in Path(value).parts and '?' not in value and ':' not in value
            and not any(c.isspace() for c in value), 'missing-evidence-reference')


def summarize(run):
    result = dict(passed=False, checks={}, errors=[], durations={})
    try:
        require(isinstance(run, dict) and set(run) == TOP_KEYS and type(run['schema_version']) is int
                and run['schema_version'] == 1, 'invalid-run-schema')
        require(isinstance(run['run_id'], str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', run['run_id']), 'invalid-run-id')
        core = run['core']
        require(set(core) == {'stack_id','image_id','fixed_a','project_id','group'}, 'invalid-core')
        for key in ('stack_id','image_id','fixed_a'): ident(core[key])
        require(re.fullmatch(r'[a-f0-9]{32}', core['project_id']) and core['group']=='campuslink-app', 'invalid-project-group')
        require(run['manual_signals'] == [], 'manual-signal-in-run')
        require(type(run['cooldown_seconds']) in (int,float) and math.isfinite(run['cooldown_seconds'])
                and run['cooldown_seconds'] >= 180, 'invalid-cooldown')
        require(set(run['load']) == {'start','reduced','stop'}, 'invalid-load')
        start, reduced, stop = (timestamp(run['load'][k]) for k in ('start','reduced','stop'))
        require(start < reduced <= stop, 'invalid-load-order')
        result['checks']['run_contract'] = True

        capacities = run['capacity']
        require(isinstance(capacities,list) and len(capacities)==3, 'missing-capacity-transition')
        cohorts=[]; cap_times=[]
        for row, size in zip(capacities,(2,3,2)):
            require(set(row)=={'utc','guests'} and isinstance(row['guests'],list), 'invalid-capacity')
            guests = [ident(v) for v in row['guests']]
            require(len(guests)==size and len(set(guests))==size and core['fixed_a'] in guests, 'capacity-or-fixed-a-changed')
            cohorts.append(set(guests));cap_times.append(timestamp(row['utc']))
        require(cap_times[0] <= start < cap_times[1] < reduced <= cap_times[2] <= stop,
                'invalid-capacity-timing')
        require(cohorts[0] < cohorts[1] and cohorts[2] < cohorts[1], 'invalid-cohort-change')
        new = next(iter(cohorts[1]-cohorts[0]))
        removed = next(iter(cohorts[1]-cohorts[2]))
        result['checks']['capacity_2_3_2'] = True

        transitions=run['transitions'];policies=run['policy_events']
        require(isinstance(transitions,list) and len(transitions)==2
                and isinstance(policies,list) and len(policies)==2, 'missing-alarm-or-policy')
        alarm_times=[];policy_times=[];alarm_ids=[]
        for index,direction,threshold,periods,kind in [(0,'out',36e9,2,'high'),(1,'in',15e9,3,'low')]:
            alarm=transitions[index];policy=policies[index]
            require(set(alarm)=={'direction','alarm_id','previous_state','state','utc','threshold','periods',
                    'granularity_seconds','max_age_seconds','cpu_snapshot'}, 'invalid-alarm-schema')
            alarm_ids.append(ident(alarm['alarm_id']))
            require(alarm['direction']==direction and alarm['previous_state']=='ok' and alarm['state']=='alarm'
                    and alarm['threshold']==threshold and alarm['periods']==periods
                    and alarm['granularity_seconds']==60, 'wrong-alarm-rule-or-transition')
            at=timestamp(alarm['utc']);alarm_times.append(at)
            require((start <= at < reduced) if index==0 else (reduced <= at <= stop), 'alarm-outside-load-phase')
            max_age=alarm['max_age_seconds']
            require(type(max_age) in (int,float) and math.isfinite(max_age) and 0<=max_age<=3600, 'invalid-freshness-limit')
            snap=alarm['cpu_snapshot']
            require(snap['project_id']==core['project_id'], 'wrong-cpu-project')
            require(all(type(r['vcpus']) is int and r['vcpus']==1 for r in snap['resources']),
                    'unsupported-alarm-vcpu')
            report=analyze_cpu(snap,cohorts[index],now=at,max_age_seconds=max_age,rate_semantics='delta-ns')
            require(report['passed'] and report[kind+'_state']=='alarm', 'invalid-or-insufficient-cpu-window')
            phase_start=start if index==0 else reduced
            for resource in snap['resources']:
                points=[r for r in resource['rows'] if r['aggregation']=='rate:mean'][-periods:]
                require(all(timestamp(r['timestamp']) >= phase_start for r in points), 'cpu-window-before-load-phase')
            require(set(policy)=={'direction','policy','stack_id','utc','origin','notifier_utc',
                                  'notifier_status','evidence','alarm_id'}, 'invalid-policy-schema')
            require(policy['direction']==direction and policy['policy']==('scale_out' if index==0 else 'scale_in')
                    and policy['stack_id']==core['stack_id'] and policy['origin']=='aodh'
                    and policy['alarm_id']==alarm['alarm_id']
                    and type(policy['notifier_status']) is int and policy['notifier_status'] in (200,202,204),
                    'not-an-accepted-aodh-policy-event')
            evidence(policy['evidence'])
            notify=timestamp(policy['notifier_utc']); applied=timestamp(policy['utc'])
            require(at <= notify <= applied <= cap_times[index+1], 'invalid-alarm-notifier-policy-order')
            policy_times.append(applied)
        require(len(set(alarm_ids))==2,'duplicate-alarm')
        require((policy_times[1]-policy_times[0]).total_seconds()>=run['cooldown_seconds'], 'cooldown-not-observed')
        result['checks']['alarm_cpu_notifier_policy'] = True

        milestones=run['milestones']
        require(isinstance(milestones,list) and all(r['instance_id']==new for r in milestones),'wrong-milestone-instance')
        normalized=[]; guest_sources={}
        for row in milestones:
            require(set(row)=={'instance_id','event','utc','source','resolution_seconds','timing'},
                    'missing-milestone-provenance')
            evidence(row['source'])
            resolution=row['resolution_seconds']
            require(type(resolution) in (int,float) and math.isfinite(resolution) and 0<resolution<=3600
                    and row['timing'] in ('event','first-observed'), 'invalid-milestone-provenance')
            at=timestamp(row['utc'])
            require(start<=at<=stop,'milestone-outside-run')
            normalized.append({k:row[k] for k in ('instance_id','event','utc')})
            guest_sources[row['event']]=dict(utc=at.isoformat(),source=row['source'],
                resolution_seconds=resolution,timing=row['timing'])
        timeline=guest_timeline(normalized)
        require(timeline['passed'],'invalid-or-missing-guest-milestones')
        stamps=timeline['instances'][new]['utc']
        active=timestamp(stamps['vm_active']);first=timestamp(stamps['first_request'])
        require(policy_times[0] <= active <= cap_times[1] and first < reduced, 'guest-before-policy-or-after-capacity')
        redirects=run['redirects']; logs=run['guest_request_ids']
        require(isinstance(redirects,list) and bool(redirects) and isinstance(logs,dict),'missing-redirect-correlation')
        require(set(logs)==cohorts[1] and all(isinstance(ids,list) and all(isinstance(v,str)
                    and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',v) for v in ids) for ids in logs.values()), 'invalid-log-cohort')
        request_ids=[];request_times=[]
        for row in redirects:
            require(set(row)=={'utc','request_id','status','location_matches_target'},'invalid-redirect-schema')
            require(type(row['status']) is int and row['status']==302 and row['location_matches_target'] is True
                    and isinstance(row['request_id'],str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',row['request_id']),
                    'invalid-redirect')
            request_ids.append(row['request_id']);request_times.append(timestamp(row['utc']))
        require(correlate(request_ids,logs,{new})['passed'], 'missing-or-ambiguous-new-guest-request')
        require(min(request_times)==first and all(first<=at<reduced for at in request_times),'first-request-not-correlated')
        result['checks']['ready_and_new_backend_request'] = True

        deletion=run['deletion']
        require(set(deletion)=={'instance_id','member_removed','vm_delete_started'} and deletion['instance_id']==removed,
                'wrong-deleted-instance')
        require(policy_times[1] <= timestamp(deletion['member_removed']) <= timestamp(deletion['vm_delete_started'])
                <= cap_times[2], 'member-not-removed-before-vm')
        cleanup=run['cleanup']
        require(set(cleanup)=={'evaluation_enabled','action_count','temporary_resources_remaining','db_unchanged'}
                and cleanup['evaluation_enabled'] is False and type(cleanup['action_count']) is int
                and cleanup['action_count']==0 and cleanup['temporary_resources_remaining']==[]
                and cleanup['db_unchanged'] is True,'unsafe-final-state')
        result['checks']['scale_in_and_cleanup'] = True
        result.update(passed=True,new_instance=new,utc={
            'load_start':start.isoformat(),'load_reduced':reduced.isoformat(),'load_stop':stop.isoformat(),
            'high_alarm':alarm_times[0].isoformat(),'low_alarm':alarm_times[1].isoformat(),
            'policy_out':policy_times[0].isoformat(),'policy_in':policy_times[1].isoformat(),
            'guest':guest_sources},durations={
            'alarm_to_first_request_seconds':(first-alarm_times[0]).total_seconds(),
            'alarm_to_active_seconds':(active-alarm_times[0]).total_seconds(),
            'policy_out_to_policy_in_seconds':(policy_times[1]-policy_times[0]).total_seconds(),
            'load_to_high_alarm_seconds':(alarm_times[0]-start).total_seconds(),
            'reduced_load_to_low_alarm_seconds':(alarm_times[1]-reduced).total_seconds()})
    except Invalid as error:
        result['errors']=[str(error)]
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,StopIteration):
        result['errors']=['invalid-normalized-run']
    return result


def main():
    parser=argparse.ArgumentParser(description='Validate normalized autoscale evidence; never output raw payload')
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    try:
        result=summarize(json.loads(args.run.read_text()))
    except (OSError,ValueError,TypeError):
        result=dict(passed=False,checks={},errors=['invalid-run-file'],durations={})
    print(json.dumps(result,allow_nan=False))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
