import json

# POST, GET /api/bulletins/ (gets bulletin list with searching and paging enabled)
# happy path
# def test_login_pass(test_client):
#   return

# POST /api/bulletin
def test_create_bulletin(auth_session):
  bulletin = {
        "title": "asdgasd",
        "status": "Human Created",
        "description": "",
        "events": [],
        "medias": [],
        "bulletin_relations": [],
        "actor_relations": [],
        "incident_relations": [],
        "publish_date": "",
        "documentation_date": "2024-03-20T14:54",
        "sjac_title": "asdga",
        "comments": "asdgasd"
    }
  payload = json.dumps({"item": bulletin})
  response = auth_session.post('/admin/api/bulletin/',
                               data = payload,
                               headers={"Content-Type": "application/json"})
  print(response.data)
  assert response.status_code == 200

# PUT /api/bulletin/{id}
def update_bulletin():
  return

# GET /api/bulletin/{id}
def get_bulletin():
  return

# GET /bulletins/{id} (webpage)
def test_get_many_bulletins(auth_session):
  query = {
    "q": [
        {}
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
  payload = json.dumps(query)
  url = "/admin/api/bulletins/?page=1&per_page=10&sort_by=&sort_desc=false&cache=1"
  response = auth_session.get(url,
                              data = payload,
                              headers = {"Content-Type": "application/json"})
  assert response.status_code == 200

# DELETE /api/bulletin/{id}
def test_delete_bulletin(auth_session):
  url = "/admin/api/bulletin/10"
  response = auth_session.delete(url)
  assert response.status_code == 200

# Maybe run a test scenario that calls methods in a sequence to test all the bulletin endpoints
def test_bulletin_crud_sequence(test_client):
  return
#   create_bulletin(test_client)
#   update_bulletin()
#   get_bulletin()
#   get_many_bulletins(test_client)
#   delete_bulletin()

# PUT /api/bulletin/review/{id}
# PUT /api/bulletin/bulk
# GET /api/bulletin/relations/{id}
# POST /api/bulletin/import/
# PUT /api/bulletin/assignother/{id}
# PUT api/bulletin/assign/{id}
