import logging
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend' / 'src'))
from api_routes import create_blueprint
from job_service import JobService
from shared.job_repository import JobRepository


def history_app(repo=None, enabled=True):
    runtime = SimpleNamespace(
        job_observability_enabled=enabled,
        repository_provider=lambda: repo,
        logger=logging.getLogger('history-test'),
    )
    runtime.job_service = JobService(runtime)
    app = Flask(__name__)
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
    assert set(item) == {'job_id', 'workflow', 'status', 'prompt', 'output_url', 'output_type', 'created_at', 'error'}
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
    assert client.delete('/api/history/job-1').status_code in {404, 405}
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
