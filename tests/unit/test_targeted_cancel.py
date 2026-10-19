import importlib
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests


@pytest.fixture
def comfy(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'worker/src'))
    original = sys.modules.pop('config', None)
    module = importlib.import_module('comfy_client')
    yield module, module.ComfyClient(logger=Mock())
    sys.modules.pop('config', None)
    if original is not None:
        sys.modules['config'] = original


def test_targeted_posts_and_failure(comfy, monkeypatch):
    module, client = comfy
    post = Mock(return_value=Mock())
    monkeypatch.setattr(module.requests, 'post', post)
    assert client.cancel_prompt('own')
    assert [(call.args[0].split('/')[-1], call.kwargs['json']) for call in post.call_args_list] == [
        ('queue', {'delete': ['own']}), ('interrupt', {'prompt_id': 'own'})]
    assert all(call.kwargs['timeout'] == module.COMFY_HTTP_TIMEOUT for call in post.call_args_list)
    post.side_effect = requests.Timeout()
    assert client.cancel_prompt('own') is False
    assert post.call_count == 4
    client.logger.warning.assert_called()


@pytest.mark.parametrize('mode', ['pending', 'running', 'race', 'unreachable'])
def test_wait_cancellation_and_completion_race(comfy, monkeypatch, mode):
    module, client = comfy
    empty = {'images': [], 'videos': [], 'gifs': []}
    history = Mock(return_value=empty)
    if mode == 'race':
        history.side_effect = [empty, {**empty, 'images': [{'filename': 'done.png'}]}]
    monkeypatch.setattr(client, 'get_outputs_from_history', history)
    socket = Mock()
    socket.recv.return_value = json.dumps({'type': 'execution_interrupted', 'data': {'prompt_id': 'own'}})
    monkeypatch.setattr(module.websocket, 'create_connection', Mock(return_value=socket))
    response = Mock()
    response.json.return_value = {'queue_running': [[0, 'other']] if mode != 'running' else [[0, 'own']], 'queue_pending': []}
    get = Mock(return_value=response)
    if mode == 'unreachable':
        get.side_effect = requests.Timeout()
        socket.recv.side_effect = module.websocket.WebSocketTimeoutException()
        times = iter([0, 0, 0, 2])
        monkeypatch.setattr(module.time, 'time', lambda: next(times))
    monkeypatch.setattr(module.requests, 'get', get)
    abort = Mock()
    result = client.wait_for_completion('own', timeout=1, should_abort=lambda: 'cancel', on_abort=abort)
    abort.assert_called_once()
    if mode == 'race':
        assert result['success'] and result['images'][0]['filename'] == 'done.png'
        assert not result.get('interrupted')
    elif mode == 'unreachable':
        assert result['timeout'] and not result.get('interrupted')
    else:
        assert result['interrupted'] and not result['success']
    socket.close.assert_called_once()
