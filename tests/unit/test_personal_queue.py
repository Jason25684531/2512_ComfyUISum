"""Anonymous identity, ownership and queue degradation contracts."""
import hashlib
import hmac
import json
import logging
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from redis import ConnectionError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend/src'))
from job_service import JobService
from shared.job_repository import JobRepository


def service(repo=None, redis=None, enabled=True):
    return JobService(SimpleNamespace(
        project_root=ROOT, job_observability_enabled=enabled,
        repository_provider=lambda: repo, redis_client=redis,
        redis_queue_name='job_queue', logger=logging.getLogger('queue-test')))


def row(job_id='own', **values):
    return dict(job_id=job_id, workflow_id='text_to_image', status='queued', progress=7,
                submitted_at=datetime.now(timezone.utc), filename='', sanitized_error_message='', **values)


def test_queue_positions_limits_and_degradation():
    repo, redis = Mock(), Mock()
    repo.list_history.return_value = [row()]
    redis.lrange.return_value = [json.dumps({'job_id': value}) for value in ['other', 'line', 'own']]
    redis.hgetall.return_value = {'status': 'queued', 'progress': '12'}
    queue = service(repo, redis)
    payload, code = queue.my_queue('TC#owner', 100)
    assert code == 200 and payload['queue_length'] == 3
    assert payload['items'][0]['position'] == 3
    assert payload['items'][0]['progress'] == 12
    args, kwargs = repo.list_history.call_args
    assert args == (0, 50, ()) and kwargs['source_label'] == 'TC#owner'
    assert 86390 < (datetime.now(timezone.utc) - kwargs['since']).total_seconds() < 86410
    redis.lrange.side_effect = redis.hgetall.side_effect = ConnectionError('secret host/password')
    payload, code = queue.my_queue('TC#owner')
    assert code == 200 and payload['queue_length'] is None
    assert payload['items'][0]['position'] is None and payload['items'][0]['progress'] == 7
    repo.list_history.side_effect = RuntimeError('private SQL')
    assert queue.my_queue('TC#owner') == ({'error': 'Queue unavailable'}, 503)
    assert service(enabled=False).my_queue('TC#owner') == ({'error': 'Queue unavailable'}, 503)


@pytest.mark.parametrize('status', ['completed', 'failed', 'running'])
def test_queue_canonical_status_and_safe_output(status):
    repo = Mock()
    item = row()
    item.update(status=status, filename='../secret.png', sanitized_error_message='GPU timeout <script>')
    repo.list_history.return_value = [item]
    result = service(repo).my_queue('TC#owner')[0]['items'][0]
    assert result['status'] == status and result['output_url'] == ''
    assert '<script>' not in result['error']
    item.update(filename='safe.png', output_type='image')
    result = service(repo).my_queue('TC#owner')[0]['items'][0]
    assert result['output_url'] == ('/outputs/safe.png' if status == 'completed' else '')


def test_repository_filters_and_owner_query_are_parameterized():
    repo = JobRepository(host='unused', port=3306, user='unused', password='', database='unused')
    cursor = Mock()
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = {'source_label': 'TC#owner'}

    @contextmanager
    def transaction():
        yield cursor

    repo.transaction = transaction
    since = datetime.now(timezone.utc)
    repo.list_history(0, 50, (), source_label="TC#' OR 1=1", since=since)
    sql, params = cursor.execute.call_args.args
    assert 'd.source_label = %s' in sql and 'j.submitted_at >= %s' in sql
    assert "OR 1=1" not in sql and params[1] == "TC#' OR 1=1"
    assert repo.get_job_owner('job') == 'TC#owner'
    assert cursor.execute.call_args.args[1] == ('job',)


def test_cancel_ownership_and_missing_job():
    repo, redis = Mock(), Mock()
    repo.get_job.return_value = {'status': 'running'}
    queue = service(repo, redis)
    for owner in ['TC#other', 'IP#127.0.0.1', 'line', None]:
        repo.get_job_owner.return_value = owner
        assert queue.cancel('job', 'TC#owner') == ({'error': 'Forbidden'}, 403)
    repo.update_if_status.assert_not_called()
    redis.hset.assert_not_called()
    repo.get_job_owner.return_value = 'TC#owner'
    assert queue.cancel('job', 'TC#owner')[1] == 202
    assert redis.hset.call_args.args == ('job:status:job', 'cancel_requested', 'true')
    repo.get_job.return_value = None
    assert queue.cancel('missing', 'TC#owner')[1] == 404


def test_invalid_resolution_does_not_enqueue():
    redis = Mock()
    for value in ['8k', None, [], {}, 720]:
        assert service(redis=redis).submit({'prompt': 'test', 'resolution': value}, request_id='test', user_label='TC#owner') == ({'error': 'Unsupported resolution'}, 400)
    redis.rpush.assert_not_called()


def test_cookie_api_isolation_and_no_token_persistence(monkeypatch):
    # Reuse the existing import-isolation helper to avoid backend/worker config collisions.
    import importlib.util
    spec = importlib.util.spec_from_file_location('backend_test_loader', ROOT / 'tests/integration/test_backend_enqueue.py')
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    monkeypatch.setenv('STUDIO_ENV_FILE', '.env.local')
    monkeypatch.setenv('REDIS_CONNECT_RETRIES', '0')
    backend = loader.load_backend(monkeypatch)
    monkeypatch.setattr(backend, 'redis_client', None)
    repo = Mock()
    stored = []
    repo.list_history.side_effect = lambda *_args, source_label, **_kwargs: [item for label, item in stored if label == source_label]
    runtime = backend.app.extensions['backend_runtime']
    monkeypatch.setattr(runtime, 'repository_provider', lambda: repo)
    monkeypatch.setattr(backend, 'JOB_OBSERVABILITY_ENABLED', True)
    a, b = backend.app.test_client(), backend.app.test_client()
    response = a.get('/api/queue/me')
    cookie = a.get_cookie('studio_tc')
    assert len(cookie.value) == 22
    header = response.headers['Set-Cookie']
    assert all(value in header for value in ['HttpOnly', 'SameSite=Lax', 'Path=/', 'Max-Age=31536000'])
    label = 'TC#' + hmac.new(backend.app.config['SECRET_KEY'].encode(), cookie.value.encode(), hashlib.sha256).hexdigest()[:16]
    stored.extend([(label, row()), ('IP#127.0.0.1', row('legacy')), ('line', row('line'))])
    assert a.get('/api/queue/me').get_json()['items'][0]['job_id'] == 'own'
    assert a.get('/api/queue/me').get_json()['tempcode'] == 'U-' + label[3:9].upper()
    assert b.get('/api/queue/me').get_json()['items'] == []
    a.set_cookie('studio_tc', '<script>')
    assert a.get('/api/queue/me').get_json()['items'] == []
    assert a.get_cookie('studio_tc').value != '<script>'
    from shared.runtime_services import build_job_data
    payload = build_job_data(project_root=ROOT, data={'prompt': 'test'}, job_id='test', user_id=None,
                             user_label=label, created_at=datetime.now(timezone.utc))[1]
    assert cookie.value not in json.dumps(payload) and payload['user_label'] == label
    repo.get_job.return_value = {'status': 'running'}
    repo.get_job_owner.return_value = label
    a.set_cookie('studio_tc', cookie.value)
    assert a.post('/api/cancel/own').status_code == 202
    assert b.post('/api/cancel/own').status_code == 403
    repo.get_job.return_value = None
    assert a.post('/api/cancel/missing').status_code == 404
