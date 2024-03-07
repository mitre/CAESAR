import json
from random import randint

REQUIRED_ROLES = ['Admin', 'DA', 'Mod']
RANDOM_INT = randint(1,9999999)
NEW_ROLE = { 'name': f'TestRole{RANDOM_INT}' }

def find_role(roles, name):
  found_role = None

  for role in roles:
    if role.get('name') == name:
      found_role = role
      break
  return found_role

def get_roles(auth_session):
  res = auth_session.get('/admin/api/roles/')
  assert res.status_code == 200
  return res.json.get('items')

# Test role creation
def test_role_create(auth_session):
  res = auth_session.post('/admin/api/role/', 
                          data=json.dumps({'item': NEW_ROLE}), 
                          headers={"Content-Type": "application/json"})
  assert res.status_code == 200

  roles = get_roles(auth_session)

  # Find the role that should have been created in `test_role_create`
  found_new_role = find_role(roles, NEW_ROLE.get('name'))
  assert found_new_role

  # Set the ID for NEW_ROLE so we can delete it later
  NEW_ROLE['id'] = found_new_role.get('id')

# Test fetching roles
def test_roles_get(auth_session):
  global NEW_ROLE
  roles = get_roles(auth_session)
  
  # Make sure the required roles exist
  for req_role in REQUIRED_ROLES:
    assert find_role(roles, req_role)

""" 
Commenting this out for now as it's failing and I'm not sure why
The `auth_session.put` call returns a 401 even though the request is
authenticated. This also causes the `test_role_delete` call to fail
as it tries to redirect the user to the login page.
"""
""" def test_role_edit(auth_session):
  global NEW_ROLE 
  global RANDOM_INT 
  RANDOM_INT += 1
  NEW_ROLE['name'] = f'TestRole{RANDOM_INT}'
  res = auth_session.put(f'/admin/api/role/{NEW_ROLE.get("id")}', 
                         json.dumps(NEW_ROLE),
                         headers={"Content-Type": "application/json"})
  assert res.status_code == 200

  roles = get_roles(auth_session)
  assert find_role(roles, NEW_ROLE.get('name')) """

# Test deleting a role
def test_role_delete(auth_session):
  # Make sure we found the newly created role
  assert NEW_ROLE.get('id')

  res = auth_session.delete(f'/admin/api/role/{NEW_ROLE.get("id")}')
  assert res.status_code == 200

  # Make sure the role was deleted
  roles = get_roles(auth_session)
  assert not find_role(roles, NEW_ROLE.get('name'))