import logging
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, g

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend' / 'src'))
from api_routes import create_blueprint
from job_service import JobService
from shared.job_repository import JobRepository


def history_app(repo=None, enabled=True, output_dir='.', user_id=''):
    runtime = SimpleNamespace(
        job_observability_enabled=enabled,
        repository_provider=lambda: repo,
        logger=logging.getLogger('history-test'),
        storage_output_dir=output_dir,
    )
    runtime.job_service = JobService(runtime)
    app = Flask(__name__)
    app.before_request(lambda: setattr(g, 'user_id', user_id))
    app.extensions['backend_runtime'] = runtime
    app.register_blueprint(create_blueprint(SimpleNamespace(limit=lambda _: lambda fn: fn)))
    return app


def test_history_query_and_safe_serialization():
    repo = Mock()
    repo.list_history.return_value = [dict(
        job_id='job-1', workflow_id='text_to_image', status='completed',
        prompt='<img src=x onerror=alert(1)>', filename='abc123_00001_.png',
        output_type='image', submitted_at=datetime(2026, 10, 16), sanitized_error_message=None,
        storage_uri='/private/secret', user_id='must-not-escape',
    )]
    repo.count_history.return_value = 30
    client = history_app(repo).test_client()
    data = client.get('/api/history').get_json()
    assert (data['offset'], data['limit'], data['total']) == (0, 24, 30)
    repo.list_history.assert_called_with(0, 24, ('completed',))
    item = data['items'][0]
    assert item['prompt'] == '&lt;img src=x onerror=alert(1)&gt;'
    assert item['output_url'] == '/outputs/abc123_00001_.png'
    assert item['created_at'] == '2026-10-16T00:00:00Z'
    assert set(item) == {'job_id', 'workflow', 'status', 'prompt', 'output_url', 'output_type', 'created_at', 'error', 'mine'}
    assert item['mine'] is False
    client.get('/api/history?offset=24&limit=1000&status=failed')
    repo.list_history.assert_called_with(24, 100, ('failed', 'cancelled'))
    client.get('/api/history?status=running')
    repo.list_history.assert_called_with(0, 24, ('created', 'queued', 'running'))
    client.get('/api/history?status=all')
    repo.list_history.assert_called_with(0, 24, ())
    for filename in ['../bad.png', 'folder/bad.png', r'folder\bad.png', '/bad.png', '', 'a b.png']:
        repo.list_history.return_value[0]['filename'] = filename
        assert client.get('/api/history').get_json()['items'][0]['output_url'] == ''
    repo.list_history.return_value[0].update(status='failed', sanitized_error_message='GPU timeout <img onerror=alert(1)>')
    item = client.get('/api/history?status=failed').get_json()['items'][0]
    assert item['status'] == 'failed'
    assert item['error'] == 'GPU timeout &lt;img onerror=alert(1)&gt;'
    repo.list_history.return_value[0]['status'] = 'created'
    assert client.get('/api/history?status=running').get_json()['items'][0]['status'] == 'queued'


@pytest.mark.parametrize('query', ['offset=-5', 'limit=abc', 'status=deleted', 'limit=0', 'limit=-1', 'offset=1.5'])
def test_invalid_history_query(query):
    response = history_app().test_client().get('/api/history?' + query)
    assert response.status_code == 400
    assert response.get_json() == {'error': 'Invalid history query'}


def test_history_store_unavailable_and_read_only():
    repo = Mock()
    repo.list_history.side_effect = RuntimeError('private SQL password host')
    for app in [history_app(repo), history_app(repo, enabled=False)]:
        response = app.test_client().get('/api/history')
        assert response.status_code == 503
        assert response.get_json() == {'error': 'History unavailable'}
    client = history_app(repo).test_client()
    for route in ['login', 'logout', 'register', 'me', 'active-users']:
        assert client.get('/api/' + route).status_code == 404


def test_repository_history_query_is_parameterized_and_uses_one_output():
    repo = JobRepository(host='unused', port=3306, user='unused', password='', database='unused')
    cursor = Mock()
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = {'total': 7}

    @contextmanager
    def transaction():
        yield cursor

    repo.transaction = transaction
    assert repo.list_history(24, 100, ('failed', 'cancelled')) == []
    sql, parameters = cursor.execute.call_args.args
    assert parameters == ('line', 'failed', 'cancelled', 100, 24)
    assert 'MIN(first_output.output_id)' in sql
    assert 'd.prompt_text AS prompt' in sql
    assert 'ORDER BY j.submitted_at DESC, j.job_id' in sql
    assert "COALESCE(d.source_label, '') <> %s" in sql
    assert repo.count_history(('completed',)) == 7
    count_sql, parameters = cursor.execute.call_args.args
    assert parameters == ('line', 'completed')
    assert "COALESCE(d.source_label, '') <> %s" in count_sql
    repo.list_history(0, 24, ())
    assert cursor.execute.call_args.args[1] == ('line', 24, 0)
    repo.count_history(())
    assert cursor.execute.call_args.args[1] == ('line',)


def test_history_mine_flag_never_leaks_owner():
    repo = Mock()
    row = dict(job_id='j', workflow_id='w', status='completed', prompt='', filename='', output_type='image',
               submitted_at=datetime(2026, 10, 16), sanitized_error_message=None, source_label='TC#owner')
    repo.list_history.return_value = [row]
    repo.count_history.return_value = 1
    for user, mine in [('TC#owner', True), ('TC#other', False), ('IP#1.2.3.4', False), ('', False)]:
        data = history_app(repo, user_id=user).test_client().get('/api/history').get_data(as_text=True)
        assert 'TC#owner' not in data
        assert history_app(repo, user_id=user).test_client().get('/api/history').get_json()['items'][0]['mine'] is mine
    row['source_label'] = 'IP#x'
    assert history_app(repo, user_id='IP#x').test_client().get('/api/history').get_json()['items'][0]['mine'] is False


def test_owner_delete_rules_and_file_containment(tmp_path):
    outputs = tmp_path / 'outputs'
    outputs.mkdir()
    (outputs / 'mine.png').write_bytes(b'x')
    (tmp_path / 'secret.png').write_bytes(b'x')
    repo = Mock()
    repo.get_job.return_value = {'status': 'completed'}
    repo.get_job_owner.return_value = 'TC#owner'
    repo.delete_job.return_value = ['mine.png', '../secret.png', 'sub/x.png', '']

    def call(user='TC#owner', job='job-1'):
        response = history_app(repo, output_dir=str(outputs), user_id=user).test_client().delete(f'/api/history/{job}')
        return response.status_code, response.get_json()

    for user in ['TC#other', 'IP#127.0.0.1', '']:
        assert call(user) == (403, {'error': 'Forbidden'})
    repo.get_job_owner.return_value = 'line'
    assert call('line') == (403, {'error': 'Forbidden'})
    repo.get_job_owner.return_value = 'TC#owner'
    for status in ['created', 'queued', 'running']:
        repo.get_job.return_value = {'status': status}
        assert call() == (409, {'error': 'Job is still running'})
    repo.delete_job.assert_not_called()
    repo.get_job.return_value = None
    assert call() == (404, {'error': 'Job not found'})
    repo.get_job.return_value = {'status': 'failed'}
    assert call() == (200, {'success': True})
    repo.delete_job.assert_called_once_with('job-1')
    assert not (outputs / 'mine.png').exists()
    assert (tmp_path / 'secret.png').exists()
    repo.delete_job.side_effect = RuntimeError('private SQL password host')
    assert call() == (503, {'error': 'History unavailable'})
    assert history_app(repo, enabled=False, user_id='TC#owner').test_client().delete('/api/history/j').status_code == 503


def test_repository_delete_job_is_parameterized_in_fk_order():
    repo = JobRepository(host='unused', port=3306, user='unused', password='', database='unused')
    cursor = Mock()
    cursor.fetchall.return_value = [{'filename': 'a.png'}, {'filename': None}]

    @contextmanager
    def transaction():
        yield cursor

    repo.transaction = transaction
    assert repo.delete_job("x' OR 1=1") == ['a.png']
    calls = [c.args for c in cursor.execute.call_args_list]
    assert [sql.split()[2] for sql, _ in calls[1:]] == ['job_events', 'job_outputs', 'job_dispatches', 'jobs']
    assert all(params == ("x' OR 1=1",) and 'OR 1=1' not in sql for sql, params in calls)
