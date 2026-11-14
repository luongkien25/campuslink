"""Run gia de kiem nhan qua; khong phai bang chung autoscale tren cloud."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_cpu import A, B, C, PROJECT, NOW, fixture

BASE = Path(__file__).resolve().parents[1]
STACK = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
IMAGE = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'
HIGH = 'ffffffff-ffff-4fff-8fff-ffffffffffff'
LOW = '44444444-4444-4444-8444-444444444444'


def cpu(at, values):
    data = fixture(values)
    delta = datetime.fromisoformat(at.replace('Z', '+00:00'))-NOW
    data['collected_at_utc'] = at
    for resource in data['resources']:
        for row in resource['rows']:
            row['timestamp'] = (datetime.fromisoformat(row['timestamp'])+delta).isoformat()
    return data


def run_fixture():
    transitions = []
    policies = []
    for direction, at, alarm, values, threshold, periods in [
        ('out', '2026-11-14T12:08:00Z', HIGH, (38.4e9, 38.4e9), 36e9, 2),
        ('in', '2026-11-14T12:20:00Z', LOW, (6e9, 6e9, 6e9), 15e9, 3)]:
        transitions.append(dict(direction=direction, alarm_id=alarm, previous_state='ok', state='alarm', utc=at,
            threshold=threshold, periods=periods, granularity_seconds=60,
            max_age_seconds=120, cpu_snapshot=cpu(at, values)))
        stamp = datetime.fromisoformat(at.replace('Z','+00:00'))
        policies.append(dict(direction=direction, policy='scale_out' if direction=='out' else 'scale_in',
            stack_id=STACK, utc=(stamp+timedelta(seconds=2)).isoformat(), origin='aodh',alarm_id=alarm,
            notifier_utc=(stamp+timedelta(seconds=1)).isoformat(), notifier_status=202,
            evidence='evidence/G4/fixture-notifier.json'))
    milestones = [dict(instance_id=C,event=event,utc='2026-11-14T12:08:%02dZ'%second,
                       source='evidence/G4/fixture-guest.json',resolution_seconds=1,
                       timing='first-observed' if event=='vm_active' else 'event')
        for event,second in [('vm_active',10),('local_ready',14),('signal_ack',17),
                             ('wait_complete',16),('member_active',18),('first_request',20)]]
    return dict(schema_version=1, run_id='fixture-only',
        core=dict(stack_id=STACK,image_id=IMAGE,fixed_a=A,project_id=PROJECT,group='campuslink-app'),
        load=dict(start='2026-11-14T11:50:00Z',reduced='2026-11-14T12:10:00Z',stop='2026-11-14T12:22:00Z'),
        transitions=transitions, policy_events=policies, manual_signals=[], cooldown_seconds=180,
        capacity=[dict(utc='2026-11-14T11:49:00Z',guests=[A,B]),
                  dict(utc='2026-11-14T12:08:21Z',guests=[A,B,C]),
                  dict(utc='2026-11-14T12:20:10Z',guests=[A,C])],
        milestones=milestones,
        redirects=[dict(utc='2026-11-14T12:08:20Z',request_id='req-new-1',status=302,
                        location_matches_target=True)],
        guest_request_ids={A:[],B:[],C:['req-new-1']},
        deletion=dict(instance_id=B,member_removed='2026-11-14T12:20:03Z',
                      vm_delete_started='2026-11-14T12:20:08Z'),
        cleanup=dict(evaluation_enabled=False,action_count=0,temporary_resources_remaining=[],db_unchanged=True))


class AutoRunTests(unittest.TestCase):
    def setUp(self):
        path = BASE/'analyze_auto_run.py'
        self.assertTrue(path.exists(), 'autoscale timeline analyzer not implemented')
        spec = importlib.util.spec_from_file_location('auto_run',path)
        self.mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.mod)

    def test_load_alarm_policy_ready_new_backend_then_scale_in(self):
        result = self.mod.summarize(run_fixture())
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['durations']['alarm_to_first_request_seconds'],20)
        self.assertEqual(result['durations']['policy_out_to_policy_in_seconds'],720)
        self.assertEqual(result['new_instance'],C)

    def assert_fails(self, data):
        result = self.mod.summarize(data)
        self.assertFalse(result['passed'],result)
        return result

    def test_first_observed_request_can_follow_first_three_online_poll(self):
        data=run_fixture()
        data['milestones'][-1]['utc']='2026-11-14T12:09:00Z'
        data['redirects'][0]['utc']='2026-11-14T12:09:00Z'
        self.assertTrue(self.mod.summarize(data)['passed'])

    def test_policy_must_reference_the_actual_transition_alarm(self):
        data=run_fixture();data['policy_events'][0]['alarm_id']=LOW
        self.assert_fails(data)

    def test_fixed_raw_alarm_thresholds_reject_non_one_vcpu_guests(self):
        data=run_fixture();low=data['transitions'][1]
        low['cpu_snapshot']=cpu(low['utc'],(20e9,20e9,20e9))
        for resource in low['cpu_snapshot']['resources']: resource['vcpus']=2
        self.assert_fails(data)

    def test_ack_cannot_be_outside_observed_run(self):
        data=run_fixture()
        next(r for r in data['milestones'] if r['event']=='signal_ack')['utc']='2027-11-14T12:00:00Z'
        self.assert_fails(data)

    def test_report_preserves_allowlisted_utc_source_and_observation_precision(self):
        result=self.mod.summarize(run_fixture())
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['utc']['high_alarm'],'2026-11-14T12:08:00+00:00')
        self.assertEqual(result['utc']['guest']['vm_active'],dict(utc='2026-11-14T12:08:10+00:00',
            source='evidence/G4/fixture-guest.json',resolution_seconds=1,timing='first-observed'))
        for key,value in [('source',''),('resolution_seconds',float('nan')),('timing','guess')]:
            data=run_fixture();data['milestones'][0][key]=value
            with self.subTest(key=key): self.assert_fails(data)

    def test_manual_signal_or_missing_notifier_is_not_autoscaling(self):
        for change in ['manual','origin','status','evidence','missing']:
            data=run_fixture()
            if change=='manual': data['manual_signals']=['scale_out']
            elif change=='missing': data['policy_events'].pop()
            elif change=='origin': data['policy_events'][0]['origin']='manual'
            elif change=='status': data['policy_events'][0]['notifier_status']=403
            else: data['policy_events'][0]['evidence']=''
            with self.subTest(change=change): self.assert_fails(data)

    def test_policy_alarm_and_project_must_match_correct_direction_and_stack(self):
        for change in ['policy','stack','alarm','project','group']:
            data=run_fixture()
            if change=='policy': data['policy_events'][0]['policy']='scale_in'
            elif change=='stack': data['policy_events'][0]['stack_id']=IMAGE
            elif change=='alarm': data['transitions'][1]['alarm_id']=HIGH
            elif change=='project': data['core']['project_id']='b'*32
            else: data['core']['group']='lab'
            with self.subTest(change=change): self.assert_fails(data)

    def test_requires_redirect302_location_and_unique_new_guest_log_mapping(self):
        for change in ['status','location','missing','ambiguous','empty','late']:
            data=run_fixture()
            if change=='status': data['redirects'][0]['status']=401
            elif change=='location': data['redirects'][0]['location_matches_target']=False
            elif change=='missing': data['guest_request_ids'][C]=[]
            elif change=='ambiguous': data['guest_request_ids'][A]=['req-new-1']
            elif change=='empty': data['redirects']=[]
            else: data['redirects'][0]['utc']='2026-11-14T12:09:00Z'
            with self.subTest(change=change): self.assert_fails(data)

    def test_missing_partial_negative_stale_or_wrong_cohort_is_not_low_cpu(self):
        for change in ['missing','partial','negative','stale','cohort']:
            data=run_fixture(); snap=data['transitions'][1]['cpu_snapshot']
            if change=='missing': snap['resources'][0]['rows'].pop()
            elif change=='partial': snap['resources'][0]['rows'][-1]['timestamp']='2026-11-14T12:20:00Z'
            elif change=='negative': snap['resources'][0]['rows'][-1]['value']=-1
            elif change=='cohort': snap['resources'].pop()
            else:
                for resource in snap['resources']:
                    for row in resource['rows']:
                        row['timestamp']=(datetime.fromisoformat(row['timestamp'])-timedelta(hours=1)).isoformat()
            with self.subTest(change=change): self.assert_fails(data)

    def test_high_low_windows_and_real_cpu_thresholds(self):
        for change in ['threshold','periods','cpu','previous','short-load']:
            data=run_fixture(); high=data['transitions'][0]
            if change=='threshold': high['threshold']=1
            elif change=='periods': high['periods']=1
            elif change=='cpu': high['cpu_snapshot']=cpu(high['utc'],(36e9,36e9))
            elif change=='previous': high['previous_state']='alarm'
            else: data['load']['start']='2026-11-14T12:07:00Z'
            with self.subTest(change=change): self.assert_fails(data)

    def test_cooldown_bounds_fixed_a_and_member_before_vm_delete(self):
        for change in ['cooldown','bounds','fixed','delete-order','wrong-victim','missing-final']:
            data=run_fixture()
            if change=='cooldown': data['cooldown_seconds']=179
            elif change=='bounds': data['capacity'][1]['guests']=[A,B,C,IMAGE]
            elif change=='fixed': data['capacity'][2]['guests']=[B,C]
            elif change=='delete-order': data['deletion']['member_removed']='2026-11-14T12:20:09Z'
            elif change=='wrong-victim': data['deletion']['instance_id']=C
            else: data['capacity'].pop()
            with self.subTest(change=change): self.assert_fails(data)

    def test_allows_ack_after_wait_complete_but_rejects_duplicate_or_missing_milestones(self):
        self.assertTrue(self.mod.summarize(run_fixture())['passed'])
        data=run_fixture();data['milestones'].append(deepcopy(data['milestones'][0]));self.assert_fails(data)
        data=run_fixture();data['milestones'].pop();self.assert_fails(data)
        data=run_fixture();data['policy_events'][0]['utc']='2026-11-14T12:09:00Z';self.assert_fails(data)

    def test_cleanup_must_disable_actions_and_preserve_db(self):
        for key,value in [('evaluation_enabled',True),('action_count',1),
                          ('temporary_resources_remaining',['jump']),('db_unchanged',False)]:
            data=run_fixture();data['cleanup'][key]=value
            with self.subTest(key=key): self.assert_fails(data)

    def test_untrusted_or_malformed_payload_is_not_echoed_in_report_or_cli(self):
        data=run_fixture();data['private_action']='FAKE_PRIVATE_SENTINEL'
        result=self.assert_fails(data)
        self.assertNotIn('FAKE_PRIVATE_SENTINEL',json.dumps(result))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'run.json';path.write_text(json.dumps(data))
            proc=subprocess.run([sys.executable,'-B',str(BASE/'analyze_auto_run.py'),str(path)],capture_output=True,text=True)
        self.assertNotEqual(proc.returncode,0)
        self.assertNotIn('FAKE_PRIVATE_SENTINEL',proc.stdout+proc.stderr)
        self.assertNotIn('Traceback',proc.stderr)
        for value in [None,[],{},dict(run_fixture(),schema_version=2)]: self.assert_fails(value)


if __name__ == '__main__': unittest.main()
