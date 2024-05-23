import pytest
import json
import uuid
from bs4 import BeautifulSoup

ADMIN_ROLE_NAME = 'Admin'
MOD_ROLE_NAME = 'Mod'
DA_ROLE_NAME = 'DA'
# the fiture lifcycle is maintained, as 'module' level but the value is accessible as a global variable
CUSTOM_ROLE_NAME = str(uuid.uuid4())
SECOND_CUSTOM_ROLE_NAME = str(uuid.uuid4())

SYSTEM_ROLE_NAMES = [ADMIN_ROLE_NAME, MOD_ROLE_NAME, DA_ROLE_NAME]
CUSTOM_ROLE_NAMES = [CUSTOM_ROLE_NAME, SECOND_CUSTOM_ROLE_NAME]
TEST_USER_PASSWORD = "keyword123!"

def create_system_role(auth_session, role_name):
  new_role_object = {'name': role_name}
  res = auth_session.post('/admin/api/role/',
                          data=json.dumps({'item': new_role_object}),
                          headers={"Content-Type": "application/json"})
  assert res.status_code == 200
  return res.data

# This module-level fixture creates two custom roles in bayanat in addition to the default Admin, Mod, and DA roles
# This fixture returns a dictionary of role objects that exist in Bayanat, indexed by the role names
@pytest.fixture(scope='module')
def roles_by_role_name(auth_session):
  for role_name in CUSTOM_ROLE_NAMES:
    create_system_role(auth_session, role_name)

  # api roles GET uses a default query with 30 results
  # this will cause test failures, posibly system failures in situations with more than 30 roles   
  res = auth_session.get('/admin/api/roles/?per_page=500')
  assert res.status_code == 200
  roles = res.json.get('items')
  roles_by_role_name = {}
  custom_role_ids = []
  for role in roles:
    if role['name'] in SYSTEM_ROLE_NAMES:
      roles_by_role_name[role['name']] = role
    if role['name'] in CUSTOM_ROLE_NAMES:
      custom_role_ids.append(role['id'])
      roles_by_role_name[role['name']] = role

  yield roles_by_role_name

def create_user_with_roles(auth_session, roles):
  username = str(uuid.uuid4())[:32]
  user_name = str(uuid.uuid4())[:32]
  user = {
        "password": TEST_USER_PASSWORD,
        "active": True,
        "username": username,
        "name": user_name,
        "roles": roles
  }
  res = auth_session.post('/admin/api/user/',
                          data=json.dumps({'item': user}),
                          headers={"Content-Type": "application/json"})
  assert res.status_code == 200
  return username

def create_user_session(test_flask_app, username):
  test_client = test_flask_app.test_client()
  res = test_client.get('/login')
  parsed_html = BeautifulSoup(res.data)
  csrf = parsed_html.body.find('input', attrs={'id': 'csrf_token'}).get('value')

  login_data = {
    'csrf_token': csrf,
    'next': '/dashboard',
    'username': username,
    'password': TEST_USER_PASSWORD
  }
  res = test_client.post('/login', data=json.dumps(login_data), headers={"Content-Type": "application/json"})
  assert res.status_code == 200
  return test_client
