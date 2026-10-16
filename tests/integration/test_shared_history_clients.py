from datetime import datetime
from types import SimpleNamespace

from test_backend_enqueue import load_backend


def test_shared_history_is_anonymous_and_independent_of_redis(monkeypatch):
    monkeypatch.setenv('REDIS_CONNECT_RETRIES', '0')
    backend = load_backend(monkeypatch)
    monkeypatch.setattr(backend, 'JOB_OBSERVABILITY_ENABLED', True)

    class DisconnectedRedis:
        def __bool__(self):
            raise AssertionError('history must not even inspect Redis')

    monkeypatch.setattr(backend, 'redis_client', DisconnectedRedis())
    repo = SimpleNamespace(
        list_history=lambda *_: [dict(job_id='shared', workflow_id='text_to_image', status='completed',
            submitted_at=datetime(2026, 10, 16), prompt='<img onerror=alert(1)>', filename='shared.png', output_type='image')],
        count_history=lambda *_: 1,
    )
    runtime = backend.app.extensions['backend_runtime']
    monkeypatch.setattr(runtime, 'repository_provider', lambda: repo)
    first = backend.app.test_client(use_cookies=False).get('/api/history')
    second = backend.app.test_client(use_cookies=False).get('/api/history')
    assert first.status_code == second.status_code == 200
    assert first.get_json() == second.get_json()
    payload = first.get_json()
    assert payload['items'][0]['prompt'] == '&lt;img onerror=alert(1)&gt;'
    assert not {'user', 'user_id', 'email', 'token', 'session_id'} & payload['items'][0].keys()
    for path in ['login', 'logout', 'register', 'me']:
        # Membership requests do not need a live queue either.
        monkeypatch.setattr(backend, 'redis_client', None)
        assert backend.app.test_client().get('/api/' + path).status_code == 404
    assert backend.app.test_client().get('/profile.html').status_code == 302
    assert backend.app.test_client().get('/login.html').status_code == 302
