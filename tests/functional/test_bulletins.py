import json
import uuid
from random import randint
import datetime

initial_title = 'title'

def new_bulletin():
  bulletin = {
        "title": str(uuid.uuid4()),
        "status": "Human Created",
        "description": str(uuid.uuid4()),
        "events": [],
        "medias": [],
        "bulletin_relations": [],
        "actor_relations": [],
        "incident_relations": [],
        "publish_date": datetime.date(randint(2005,2025), randint(1,12),randint(1,28)).strftime("%Y-%m-%d"),
        "publish_time": datetime.time(randint(0,24), randint(0,59),randint(0,59)).strftime("%H:%M:%S"),
        "sjac_title": str(uuid.uuid4()),
        "comments": str(uuid.uuid4()),
        "discovery_file_name": str(uuid.uuid4())
    }
  return bulletin

# POST /api/bulletin
def create_bulletin(auth_session, bulletin):
  payload = json.dumps({"item": bulletin})
  response = auth_session.post('/admin/api/bulletin/',
                               data = payload,
                               headers={"Content-Type": "application/json"})
  bulletin_id = response.data.decode("utf-8").split('#')[1] #'Created Bulletin #4' -> 4
  assert response.status_code == 200
  return bulletin_id

# PUT /api/bulletin/{id}
def update_bulletin(auth_session, new_bulletin, bulletin_id):
  payload = json.dumps({"item": new_bulletin})
  url = '/admin/api/bulletin/' + str(bulletin_id)
  response = auth_session.put(url,
                               data = payload,
                               headers={"Content-Type": "application/json"})
  assert response.status_code == 200
  return

# GET /api/bulletin/{id}
def get_bulletin(auth_session, bulletin_id):
  url = '/admin/api/bulletin/' + str(bulletin_id)
  response = auth_session.get(url, headers={"Content-Type": "application/json"})
  assert response.status_code == 200
  return json.loads(response.data)

# GET /bulletins/{id} (webpage)
def get_many_bulletins(auth_session, bulletin_id_list):
  query = {
    "q": [
        {"ids": bulletin_id_list}
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
  url = "/admin/api/bulletins/?page=1&per_page=10&sort_by=&sort_desc=false&cache=0"
  response = auth_session.get(url,
                              data = payload,
                              headers = {"Content-Type": "application/json"})
  assert response.status_code == 200
  bulletins = json.loads(response.data)["items"]
  return bulletins

# DELETE /api/bulletin/{id}
def delete_bulletin(auth_session, bulletin_id):
  url = "/admin/api/bulletin/" + str(bulletin_id)
  response = auth_session.delete(url)
  assert response.status_code == 200
  
def assert_bulletins_match(first, second):
  assert first["title"] == second["title"]
  assert first["status"] == second["status"]
  assert first["description"] == second["description"]
  assert first["publish_date"] == second["publish_date"]
  assert first["publish_time"] == second["publish_time"]
  assert first["sjac_title"] == second["sjac_title"]
  assert first["comments"] == second["comments"]
  assert first["discovery_file_name"] == second["discovery_file_name"]

def test_bulletin_crud_sequence(auth_session):
  first_bulletin = new_bulletin()
  first_id = create_bulletin(auth_session, first_bulletin)

  second_bulletin = new_bulletin()
  second_id = create_bulletin(auth_session, second_bulletin)

  read_first_bulletin = get_bulletin(auth_session, first_id)
  assert_bulletins_match(first_bulletin, read_first_bulletin)

  updated_bulletin = new_bulletin()
  update_bulletin(auth_session, updated_bulletin, first_id)
  read_updated_bulletin = get_bulletin(auth_session, first_id)
  assert_bulletins_match(updated_bulletin, read_updated_bulletin)

  bulletins = get_many_bulletins(auth_session, [first_id, second_id])
  assert len(bulletins) == 2

  read_first_bulletin = get_bulletin(auth_session, first_id)
  delete_bulletin(auth_session, first_id)
  read_first_bulletin = get_bulletin(auth_session, first_id)
  
