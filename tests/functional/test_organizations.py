import json
import uuid
from random import randint
import datetime

from tests.functional.test_actors import create_actor, new_actor

def new_organization():
    organization = {
        "name": str(uuid.uuid4()),
        "name_ar": str(uuid.uuid4()),
        "description": str(uuid.uuid4()),
        "status": "Human Created",
        "founded_date": datetime.date.today().strftime("%Y-%m-%d"),
        "comments": str(uuid.uuid4())
    }
    return organization

def create_organization(auth_session, organization):
    payload = json.dumps({"item": organization})
    response = auth_session.post('/admin/api/organization/',
                                 data = payload,
                                 headers={"Content-Type": "application/json"})
    organization_id = str(response.data).split('#')[1].strip("'") #'Created organization #4' -> 4
    assert response.status_code == 200
    return organization_id

def get_all_organizations(auth_session):
    response = auth_session.get('/admin/api/organizations/',
                                headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    return json.loads(response.data)

def update_organization(auth_session, new_organization, organization_id):
    payload = json.dumps({"item": new_organization})
    url = '/admin/api/organization/' + str(organization_id)
    response = auth_session.put(url,
                                 data = payload,
                                 headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    return

def get_specific_organization(auth_session, organization_id):
    url = '/admin/api/organization/' + str(organization_id)
    response = auth_session.get(url, headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    return json.loads(response.data)

def assert_organizations_match(organization1, organization2):
    assert organization1["name"] == organization2["name"]
    assert organization1["name_ar"] == organization2["name_ar"]
    assert organization1["description"] == organization2["description"]
    assert organization1["status"] == organization2["status"]
    assert organization1["comments"] == organization2["comments"]
    return

def delete_organization(auth_session, organization_id):
    url = '/admin/api/organization/' + str(organization_id)
    response = auth_session.delete(url, headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    return

def test_create_organization(auth_session):
    organization = new_organization()
    organization_id = create_organization(auth_session, organization)
    get_specific_organization(auth_session, organization_id)
    delete_organization(auth_session, organization_id)
    return

def test_get_all_organizations(auth_session):
    organization = new_organization()
    organization_id = create_organization(auth_session, organization)
    organizations = get_all_organizations(auth_session)
    assert type(organizations["items"]) == list
    delete_organization(auth_session, organization_id)
    return

def test_update_organization(auth_session):
    organization = new_organization()
    organization_id = create_organization(auth_session, organization)
    new_organization_update = {
        "name": str(uuid.uuid4()),
        "name_ar": str(uuid.uuid4()),
        "description": str(uuid.uuid4()),
        "status": "Human Created",
        "founded_date": datetime.date.today().strftime("%Y-%m-%d"),
        "comments": str(uuid.uuid4())
    }
    update_organization(auth_session, new_organization_update, organization_id)
    assert_organizations_match(get_specific_organization(auth_session, organization_id), new_organization_update)
    delete_organization(auth_session, organization_id)
    return

def test_create_organization_with_aliases(auth_session):
    organization = new_organization()
    aliases = [{
        "name": str(uuid.uuid4()),
        "name_ar": str(uuid.uuid4())
    }]
    organization["aliases"] = aliases
    organization_id = create_organization(auth_session, organization)
    get_specific_organization(auth_session, organization_id)
    delete_organization(auth_session, organization_id)
    return

def test_create_organization_with_roles_within(auth_session):
    organization = new_organization()
    actor_id = create_actor(auth_session, new_actor())
    role_actors = [{
        "actor_id": actor_id,
        "currently_active": True,
        "from_date": datetime.date.today().strftime("%Y-%m-%d"),
        "to_date": datetime.date.today().strftime("%Y-%m-%d"),
    }]
    roles = [{
        "title": str(uuid.uuid4()),
        "currently_active": True,
        "from_date": datetime.date.today().strftime("%Y-%m-%d"),
        "to_date": datetime.date.today().strftime("%Y-%m-%d"),
        "actors": role_actors,
    }]
    organization["roles_within"] = roles
    organization_id = create_organization(auth_session, organization)
    get_specific_organization(auth_session, organization_id)
    delete_organization(auth_session, organization_id)
    return
