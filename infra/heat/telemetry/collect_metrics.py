"""Doc Gnocchi bang member tren A; xuat snapshot allowlist, khong raw API."""
import argparse
from datetime import datetime, timezone
import json
import logging
import os
import re
import uuid

try:
    from .analyze_cpu import number, timestamp
except ImportError:
    from analyze_cpu import number, timestamp


class CollectionError(Exception):
    pass


def identifier(value):
    return str(uuid.UUID(value))


def active_query(project_id):
    return {'and': [{'=': {'server_group': 'campuslink-app'}},
                    {'=': {'project_id': uuid.UUID(project_id).hex}}, {'=': {'ended_at': None}},
                    {'=': {'deleted_at': None}}]}


def seconds(value):
    if isinstance(value, str):
        match = re.fullmatch(r'(?:(\d+) days?, )?(\d+):(\d{2}):(\d{2}(?:\.\d+)?)', value)
        if not match or int(match[3]) >= 60 or float(match[4]) >= 60:
            raise ValueError('invalid-duration')
        return int(match[1] or 0)*86400 + int(match[2])*3600 + int(match[3])*60 + float(match[4])
    return number(value)


def collect(api, project_id, *, start, stop, now):
    try:
        project_id = uuid.UUID(project_id).hex
        for stamp in (start, stop, now):
            if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
                raise ValueError('utc-required')
        if not 0 < (stop-start).total_seconds() <= 3600 or stop > now:
            raise ValueError('window-contract')
        # Gnocchi tra bucket chua start; yeu cau moc phut ro rang truoc khi doc.
        start = start.replace(second=0, microsecond=0)
        query = active_query(project_id)
        resources = []; seen = set()
        for raw in api.resource.search(resource_type='instance', query=query):
            ident = identifier(raw['id'])
            if (ident in seen or uuid.UUID(raw['project_id']).hex != project_id
                    or raw['ended_at'] is not None or raw['deleted_at'] is not None
                    or raw['server_group'] != 'campuslink-app'):
                raise ValueError('resource-contract')
            seen.add(ident)
            if len(seen) > 6:
                raise ValueError('unexpected-resource-count')
            metric_id = identifier(raw['metrics']['cpu'])
            metric = api.metric.get(metric_id)
            if identifier(metric['id']) != metric_id or metric['unit'] != 'ns':
                raise ValueError('metric-contract')
            policy = metric['archive_policy']
            if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', policy['name']):
                raise ValueError('policy-name')
            methods = policy['aggregation_methods']
            if (not isinstance(methods, list) or any(not isinstance(m, str) or
                    not re.fullmatch(r'[A-Za-z0-9_:%.-]{1,32}', m) for m in methods)):
                raise ValueError('policy-methods')
            definition = []
            for row in policy['definition']:
                definition.append(dict(granularity=seconds(row['granularity']),
                                       points=number(row['points']), timespan=seconds(row['timespan'])))
            rows = []
            for aggregation in ('mean', 'rate:mean'):
                measures = api.metric.get_measures(metric_id, aggregation=aggregation,
                    granularity=60, start=start.isoformat(), stop=stop.isoformat())
                if len(measures) > 61:
                    raise ValueError('unexpected-measure-count')
                for stamp, granularity, value in measures:
                    parsed = timestamp(str(stamp))
                    if not start <= parsed < stop:
                        raise ValueError('out-of-window-measure')
                    # Bucket dang ghi khong phai diem hoan tat de evaluate.
                    if (now-parsed).total_seconds() < 60:
                        continue
                    rows.append(dict(timestamp=parsed.isoformat(), granularity_seconds=number(granularity),
                                     value=number(value), aggregation=aggregation))
            vcpu_metric_id = identifier(raw['metrics']['vcpus'])
            vcpu_metric = api.metric.get(vcpu_metric_id)
            if identifier(vcpu_metric['id']) != vcpu_metric_id or vcpu_metric['unit'] != 'vcpu':
                raise ValueError('vcpu-metric-contract')
            vcpu_rows = api.metric.get_measures(vcpu_metric_id, aggregation='mean', granularity=60,
                                              start=start.isoformat(), stop=stop.isoformat())
            if len(vcpu_rows) > 61:
                raise ValueError('unexpected-vcpu-measure-count')
            vcpu_points = {}
            for stamp, granularity, value in vcpu_rows:
                stamp = timestamp(str(stamp))
                if stamp in vcpu_points or granularity != 60 or not start <= stamp < stop:
                    raise ValueError('vcpu-series-contract')
                if (now-stamp).total_seconds() >= 60:
                    vcpu_points[stamp] = number(value)
            counts = {vcpu_points[timestamp(row['timestamp'])] for row in rows if row['aggregation'] == 'mean'}
            if len(counts) != 1:
                raise ValueError('missing-or-changing-vcpu')
            vcpus = counts.pop()
            if vcpus <= 0 or int(vcpus) != vcpus:
                raise ValueError('vcpu-not-positive-integer')
            resources.append(dict(uuid=ident, project_id=project_id, vcpus=int(vcpus), vcpus_metric_id=vcpu_metric_id,
                group=raw['server_group'], ended_at=None, deleted_at=None, metric_id=metric_id, unit='ns',
                archive_policy=dict(name=policy['name'], aggregation_methods=methods, definition=definition), rows=rows))
        return dict(schema_version=1, collected_at_utc=now.isoformat(), project_id=project_id,
                    query=query, resources=resources)
    except Exception:
        # Keystone/HTTP exception co the kem URL/header; chi tra ma loi co dinh.
        raise CollectionError('metric-collection-failed') from None


def main():
    parser = argparse.ArgumentParser(description='Read safe CPU snapshot on A, cloud campus-tv2 only')
    parser.add_argument('--project', required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--stop', required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        if os.environ.get('OS_CLOUD', 'campus-tv2') != 'campus-tv2':
            raise ValueError('wrong-cloud')
        # Doc credential qua SDK o A; khong copy file/cai client tren laptop.
        from openstack.config import OpenStackConfig
        from gnocchiclient.v1.client import Client
        cloud = OpenStackConfig(load_envvars=False).get_one(cloud='campus-tv2')
        session = cloud.get_session()
        session.timeout = 10
        if uuid.UUID(session.get_project_id()).hex != uuid.UUID(args.project).hex:
            raise ValueError('wrong-project')
        api = Client(session=session, adapter_options={
            'interface': cloud.config.get('interface', 'public'), 'region_name': cloud.region_name})
        snapshot = collect(api, args.project, start=timestamp(args.start), stop=timestamp(args.stop),
                           now=datetime.now(timezone.utc))
    except Exception:
        print('FAIL: metric collection unavailable; verify member API/schema/client on A, no payload printed')
        return 1
    print(json.dumps(snapshot, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
