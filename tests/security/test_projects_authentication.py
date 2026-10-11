"""Project mutations share the production OIDC/CSRF/Core boundary."""
import pytest
from database.repositories.organization_repo import OrganizationRepository
from tests.security.test_deployment_authentication import hosted as hosted, login


def test_hosted_member_list_create_edit_and_foreign_denial(hosted):
    client, _, db, *_ = hosted
    assert client.get('/api/projects').status_code == 401
    login(hosted)
    page = client.get('/api/projects').json()
    assert [item['id'] for item in page['items']] == ['project']
    assert not page['can_create']
    payload = {'name': 'Hosted project', 'idempotency_key': 'hosted-project-request'}
    assert client.post('/api/projects', json=payload).status_code == 403
    assert client.patch('/api/projects/project', json={**payload, 'expected_generation': 1}).status_code == 403
    assert client.get('/api/projects/private').status_code == 403
    assert client.get('/api/projects/foreign-project').status_code == 403
    with db.session(write=True) as session:
        OrganizationRepository(session).get_member('org', 'human').role = 'admin'
    created = client.post('/api/projects', json=payload)
    assert created.status_code == 201, created.text
    with db.session(write=True) as session:
        OrganizationRepository(session).revoke_member('org', 'human')
    assert client.get('/api/projects').status_code == 403
    assert client.post('/api/projects', json=payload).status_code == 403


@pytest.mark.parametrize('action', ['post', 'patch'])
def test_hosted_projects_reject_csrf_and_origin(hosted, action):
    client, _, _, *_ = hosted
    login(hosted)
    payload = {'name': 'Denied project', 'idempotency_key': 'denied-project-request'}
    path = '/api/projects'
    if action == 'patch':
        path += '/project'
        payload['expected_generation'] = 1
    response = getattr(client, action)(path, json=payload, headers={'X-CSRF-Token': 'invalid'})
    assert response.status_code == 403
    response = getattr(client, action)(path, json=payload, headers={'Origin': 'https://untrusted.invalid'})
    assert response.status_code == 403
