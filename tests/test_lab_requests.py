"""Retry and stale-client behavior through the actual middleware."""
from fastapi.testclient import TestClient

from genesis.harness.chain import AnvilChain
from genesis.lab.api import LabConfig, create_app
from tests.fake_anvil import FakeAnvil
from tests.harness_support import SCENARIOS


def test_retry_does_not_replace_session_and_old_version_is_refused() -> None:
    app = create_app(LabConfig(scenarios_dir=SCENARIOS), chain=AnvilChain(FakeAnvil()))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = {"Idempotency-Key": "start-1"}
        first = client.post('/api/session', headers=headers)
        assert first.status_code == 200
        version = first.headers['X-Lab-Version']
        retry = client.post('/api/session', headers=headers)
        assert retry.json() == first.json()
        assert retry.headers['Idempotency-Replayed'] == 'true'
        assert retry.headers['X-Lab-Version'] == version
        foreign = client.post('/api/session', headers={**headers, 'host': 'attacker.example'})
        assert foreign.status_code == 400
        hint = client.post('/api/session/hints', headers={'X-Lab-Version': version})
        assert hint.status_code == 200
        stale = client.post('/api/session/reset', headers={'X-Lab-Version': version})
        assert stale.status_code == 409
        assert stale.json()['error']['code'] == 'stale-state'
        assert client.get('/api/session').json()['hints']['revealed']
        conflict = client.post('/api/session/reset', headers=headers)
        assert conflict.status_code == 409


def test_duplicate_hint_is_delivered_once() -> None:
    app = create_app(LabConfig(scenarios_dir=SCENARIOS), chain=AnvilChain(FakeAnvil()))
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.post('/api/session')
        for _ in range(2):
            assert client.post('/api/session/hints', headers={'Idempotency-Key': 'hint-1'}).status_code == 200
        assert len(client.get('/api/session').json()['hints']['revealed']) == 1
