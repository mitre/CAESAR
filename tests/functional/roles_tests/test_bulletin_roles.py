import pytest
import json
import uuid
from conftest import (ADMIN_ROLE_NAME, DA_ROLE_NAME, MOD_ROLE_NAME, CUSTOM_ROLE_NAME, SECOND_CUSTOM_ROLE_NAME, 
                      create_user_with_roles, create_user_session)

def create_bulletin_requiring_roles(auth_session, roles_by_role_name, required_role_names):
  bulletin = bulletin = {
        "title": str(uuid.uuid4()),
        "status": "Human Created",
        "description": str(uuid.uuid4())
    }
  payload = json.dumps({"item": bulletin})
  response = auth_session.post('/admin/api/bulletin/',
                               data = payload,
                               headers={"Content-Type": "application/json"})
  bulletin_id = str(response.data).split('#')[1].strip("'") #'Created Bulletin #4' -> 4
  assert response.status_code == 200

  roles = []
  for role_name in required_role_names:
    roles.append(roles_by_role_name[role_name])

  # right now, the only way to assign roles is via bulk updates, both in the UI and in the API
  payload = json.dumps(
    {
      "items": [
        bulletin_id
      ],
      "bulk": {
        "comments": "comments",
        "roles": roles
      }
    }
  )
  response = auth_session.put('/admin/api/bulletin/bulk/',
                               data = payload,
                               headers={"Content-Type": "application/json"})
  assert response.status_code == 200
  return bulletin_id

# check if roles restrict access to URLs properly
@pytest.mark.parametrize("required_roles, assigned_roles, expected_api_response_code", [
  # BELOW IS A LIST OF TEST CASE INPUTS. ABOVE IS THE FORMAT OF TEST CASE INPUTS
  ([ADMIN_ROLE_NAME], [], 403),
  ([ADMIN_ROLE_NAME], [MOD_ROLE_NAME], 403),
  ([ADMIN_ROLE_NAME], [MOD_ROLE_NAME, CUSTOM_ROLE_NAME, DA_ROLE_NAME], 403),
  ([ADMIN_ROLE_NAME], [ADMIN_ROLE_NAME], 200),
  ([ADMIN_ROLE_NAME], [ADMIN_ROLE_NAME, MOD_ROLE_NAME], 200),
  ([], [], 200),
  ([], [CUSTOM_ROLE_NAME], 200),
  ([CUSTOM_ROLE_NAME], [], 403),
  ([CUSTOM_ROLE_NAME], [SECOND_CUSTOM_ROLE_NAME], 403),
  ([CUSTOM_ROLE_NAME], [MOD_ROLE_NAME], 403),
  ([CUSTOM_ROLE_NAME], [DA_ROLE_NAME], 403),
  ([CUSTOM_ROLE_NAME], [ADMIN_ROLE_NAME], 200),
  ([CUSTOM_ROLE_NAME], [CUSTOM_ROLE_NAME], 200),
])
def test_getBulletin_withAssignedUserRolesAndRequiredBulletinAccessRestrictions(test_flask_app, auth_session, roles_by_role_name, required_roles, assigned_roles, expected_api_response_code):
  bulletin_id = create_bulletin_requiring_roles(auth_session, roles_by_role_name, required_roles)
  user_roles = []
  for role_name in assigned_roles:
    user_roles.append(roles_by_role_name[role_name])
  username = create_user_with_roles(auth_session, user_roles)
  user_session = create_user_session(test_flask_app, username)
  response = user_session.get(F'/admin/api/bulletin/{bulletin_id}',
                               headers={"Content-Type": "application/json"})
  assert response.status_code == expected_api_response_code

@pytest.mark.parametrize("assigned_roles, expected_api_response_code", [
  ([ADMIN_ROLE_NAME], 200),
  ([MOD_ROLE_NAME], 403),
  ([DA_ROLE_NAME], 403),
  ([CUSTOM_ROLE_NAME], 403),
  ([], 403)
])
def test_deleteBulletin_withAssignedUserRoles(test_flask_app, auth_session, roles_by_role_name, assigned_roles, expected_api_response_code):
  bulletin_id = create_bulletin_requiring_roles(auth_session, {}, [])
  user_roles = []
  for role_name in assigned_roles:
    user_roles.append(roles_by_role_name[role_name])
  username = create_user_with_roles(auth_session, user_roles)
  user_session = create_user_session(test_flask_app, username)
  response = user_session.delete(F'/admin/api/bulletin/{bulletin_id}')
  assert response.status_code == expected_api_response_code

@pytest.mark.parametrize("required_roles, assigned_roles, expected_api_response_code", [
  # BELOW IS A LIST OF TEST CASE INPUTS. ABOVE IS THE FORMAT OF TEST CASE INPUTS
  ([ADMIN_ROLE_NAME], [], 403),
  ([ADMIN_ROLE_NAME], [MOD_ROLE_NAME], 403),
  ([ADMIN_ROLE_NAME], [MOD_ROLE_NAME, CUSTOM_ROLE_NAME, DA_ROLE_NAME], 403),
  ([ADMIN_ROLE_NAME], [ADMIN_ROLE_NAME], 200),
  ([ADMIN_ROLE_NAME], [ADMIN_ROLE_NAME, MOD_ROLE_NAME], 200),
  ([], [], 403), # read only users do not have write permissions
  ([], [CUSTOM_ROLE_NAME], 403), # read only users do not have write permissions
  ([CUSTOM_ROLE_NAME], [], 403),
  ([CUSTOM_ROLE_NAME], [SECOND_CUSTOM_ROLE_NAME], 403),
  ([CUSTOM_ROLE_NAME], [MOD_ROLE_NAME], 403),
  ([CUSTOM_ROLE_NAME], [DA_ROLE_NAME], 403),
  ([CUSTOM_ROLE_NAME], [ADMIN_ROLE_NAME], 200),
  ([CUSTOM_ROLE_NAME], [CUSTOM_ROLE_NAME], 403), # read only users do not have write permisisons
])
def test_updateBulletin_withAssignedUserRolesAndRequiredBulletinAccessRestrictions(test_flask_app, auth_session, roles_by_role_name, required_roles, assigned_roles, expected_api_response_code):
  bulletin_id = create_bulletin_requiring_roles(auth_session, roles_by_role_name, required_roles)
  user_roles = []
  for role_name in assigned_roles:
    user_roles.append(roles_by_role_name[role_name])
  username = create_user_with_roles(auth_session, user_roles)
  user_session = create_user_session(test_flask_app, username)
  bulletin = bulletin = {
    "title": str(uuid.uuid4()),
    "status": "Human Created",
    "description": str(uuid.uuid4())
  }
  payload = json.dumps({"item": bulletin})
  response = user_session.put(F'/admin/api/bulletin/{bulletin_id}',
                               data = payload,
                               headers={"Content-Type": "application/json"})
  assert response.status_code == expected_api_response_code

def test_bulletinQuery_bulletinsAreRestrictedByRoles(test_flask_app, auth_session, roles_by_role_name):
  bulletin_1_id = create_bulletin_requiring_roles(auth_session, roles_by_role_name, [])
  bulletin_2_id = create_bulletin_requiring_roles(auth_session, roles_by_role_name, [DA_ROLE_NAME])
  bulletin_3_id = create_bulletin_requiring_roles(auth_session, roles_by_role_name, [DA_ROLE_NAME, CUSTOM_ROLE_NAME])
  bulletin_4_id = create_bulletin_requiring_roles(auth_session, roles_by_role_name, [DA_ROLE_NAME, SECOND_CUSTOM_ROLE_NAME])

  assigned_roles = [DA_ROLE_NAME, CUSTOM_ROLE_NAME]
  user_roles = []
  for role_name in assigned_roles:
    user_roles.append(roles_by_role_name[role_name])
  username = create_user_with_roles(auth_session, user_roles)
  user_session = create_user_session(test_flask_app, username)
  url = "/admin/api/bulletins/?page=1&per_page=500"
  query_payload = {
    "q": [
        {
            "tsv": "%"
        }
    ],
    "options": {
        "page": 1,
        "itemsPerPage": 10,
        "sortBy": [],
        "sortDesc": [
            False
        ],
        "groupBy": [],
        "groupDesc": [],
        "mustSort": False,
        "multiSort": False
    }
  }
  response = user_session.post(url,
                               data = json.dumps(query_payload),
                               headers={"Content-Type": "application/json"})
  assert response.status_code == 200
  bulletins = json.loads(response.data)['items']
  bulletin_1_found = False
  bulletin_2_found = False
  bulletin_3_found = False
  bulletin_4_found = False
  for bulletin in bulletins:
    if int(bulletin['id']) == int(bulletin_1_id):
      bulletin_1_found = True
    if int(bulletin['id']) == int(bulletin_2_id):
      bulletin_2_found= True
    if int(bulletin['id']) == int(bulletin_3_id):
      bulletin_3_found = True
    if int(bulletin['id']) == int(bulletin_4_id):
      bulletin_4_found = True
  
  assert bulletin_1_found
  assert bulletin_2_found
  assert bulletin_3_found
  assert bulletin_4_found == False

# check role CRUD operations
# test role assignment

# some endpoints e.g. @admin.post('/api/location/') are decorated with @roles_accepted('Admin', 'Mod', 'DA') that on its face appears to only consider built-in roles
# are these endpoints compatible with custom roles?
