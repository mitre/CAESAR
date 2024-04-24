import pytest
import json
import uuid
from conftest import (TEST_USER_PASSWORD, ADMIN_ROLE_NAME, DA_ROLE_NAME, MOD_ROLE_NAME, CUSTOM_ROLE_NAME, SECOND_CUSTOM_ROLE_NAME, 
                      create_user_with_roles, delete_user_by_name, create_user_session)

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

def delete_bulletin(auth_session, bulletin_id):
  url = "/admin/api/bulletin/" + str(bulletin_id)
  response = auth_session.delete(url)
  assert response.status_code == 200

# check if roles restrict access to URLs properly
@pytest.mark.parametrize("required_roles, assigned_roles, expected_api_response_code", [
  # BELOW IS A LIST OF TEST CASE INPUTS. ABOVE IS THE FORMAT OF TEST CASE INPUTS
  # ([ADMIN_ROLE_NAME], [], 403),
  # ([ADMIN_ROLE_NAME], [MOD_ROLE_NAME], 403),
  # ([ADMIN_ROLE_NAME], [MOD_ROLE_NAME, CUSTOM_ROLE_NAME, DA_ROLE_NAME], 403),
  # ([ADMIN_ROLE_NAME], [ADMIN_ROLE_NAME], 200),
  # ([ADMIN_ROLE_NAME], [ADMIN_ROLE_NAME, MOD_ROLE_NAME], 200),
  # ([], [], 200),
  # ([], [CUSTOM_ROLE_NAME], 200),
  # ([CUSTOM_ROLE_NAME], [], 403),
  # ([CUSTOM_ROLE_NAME], [SECOND_CUSTOM_ROLE_NAME], 403),
  # ([CUSTOM_ROLE_NAME], [MOD_ROLE_NAME], 403),
  # ([CUSTOM_ROLE_NAME], [DA_ROLE_NAME], 403),
  # ([CUSTOM_ROLE_NAME], [ADMIN_ROLE_NAME], 200),
  ([CUSTOM_ROLE_NAME], [CUSTOM_ROLE_NAME], 200),
])
def test_getBulletin_withAssignedUserRolesAndRequiredBulletinAccessRestrictions(test_flask_app, auth_session, roles_by_role_name, required_roles, assigned_roles, expected_api_response_code):
  bulletin_roles = []
  for role_name in required_roles:
    bulletin_roles.append(roles_by_role_name[role_name])
  bulletin = create_bulletin_requiring_roles(auth_session, roles_by_role_name, required_roles)

  user_roles = []
  for role_name in assigned_roles:
    user_roles.append(roles_by_role_name[role_name])
  user = create_user_with_roles(auth_session, user_roles)
  user_session = create_user_session(test_flask_app, user['username'])

  response = user_session.get(F'/admin/api/bulletin/{bulletin}',
                               headers={"Content-Type": "application/json"})
  assert response.status_code == expected_api_response_code

  delete_bulletin(auth_session, bulletin)
  delete_user_by_name(auth_session, user['name'])
  return

def VOID_test_bulletinQuery_bulletinsAreRestrictedByRoles(test_flask_app, auth_session, roles_by_role_name):
  # bulletin_1 = create_bulletin_requiring_roles(auth_session, roles_by_role_name, [])
  # bulletin_2 = create_bulletin_requiring_roles(auth_session, roles_by_role_name, [DA_ROLE_NAME])
  # bulletin_3 = create_bulletin_requiring_roles(auth_session, roles_by_role_name, [DA_ROLE_NAME, CUSTOM_ROLE_NAME])
  # bulletin_4 = create_bulletin_requiring_roles(auth_session, roles_by_role_name, [DA_ROLE_NAME, SECOND_CUSTOM_ROLE_NAME])

  # username = create_user_with_roles(auth_session, [DA_ROLE_NAME, CUSTOM_ROLE_NAME])
  # user_session = create_user_session(test_flask_app, username)
  query_payload = {
    "q": [
      {
        "locTypes": [
            "locations",
            "geomarkers",
            "events"
        ]
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

  return
  
  # url = "/admin/api/bulletins/?page=1&per_page=10&sort_by=&sort_desc=false"
  # response = user_session.post(url,
  #                              data=json.dumps(query_payload),
  #                              headers={"Content-Type": "application/json"})
  # assert response.status_code == 200

  # response_body_ex = {
  #   "items": [
  #       {
  #           "_status": "Human Created",
  #           "assigned_to": {
  #               "active": True,
  #               "id": 1,
  #               "name": "Admin",
  #               "username": "admin"
  #           },
  #           "first_peer_reviewer": "",
  #           "id": 1,
  #           "name": "",
  #           "roles": [],
  #           "status": "Human Created",
  #           "title": "owen asdf"
  #       }
  #   ],
  #   "perPage": 10,
  #   "total": 1
  # }

# def test_actor_access_restrictions():
#   return



# consider views
# consider import/export
# consider UI components?


# check role CRUD operations


# test role assignment


# some endpoints e.g. @admin.post('/api/location/') are decorated with @roles_accepted('Admin', 'Mod', 'DA') that on its face appears to only consider built-in roles
# are these endpoints compatible with custom roles?


# looking via endpoint availability, which data types can have limited access via CAESAR roles?
