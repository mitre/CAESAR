import json
import uuid
from random import randint
import datetime

initial_title = 'title'

def new_actor():
  actor = {
      "description": str(uuid.uuid4()),
      "status": "Human Created",
      "events": [],
      "medias": [],
      "actor_relations": [],
      "bulletin_relations": [],
      "incident_relations": [],
      "publish_date": datetime.date(randint(2005,2025), randint(1,12),randint(1,28)).strftime("%Y-%m-%dT%H:%M"),
      "documentation_date": datetime.date(randint(2005,2025), randint(1,12),randint(1,28)).strftime("%Y-%m-%dT%H:%M"),
      "name": str(uuid.uuid4()),
      "comments": str(uuid.uuid4())
    }
  return actor

# POST /api/actor
def create_actor(auth_session, actor):
  payload = json.dumps({"item": actor})
  response = auth_session.post('/admin/api/actor/',
                               data = payload,
                               headers={"Content-Type": "application/json"})
  actor_id = str(response.data).split('#')[1].strip("'") #'Created actor #4' -> 4
  assert response.status_code == 200
  return actor_id

# PUT /api/actor/{id}
def update_actor(auth_session, new_actor, actor_id):
  payload = json.dumps({"item": new_actor})
  url = '/admin/api/actor/' + str(actor_id)
  response = auth_session.put(url,
                               data = payload,
                               headers={"Content-Type": "application/json"})
  assert response.status_code == 200
  return

# GET /api/actor/{id}
def get_actor(auth_session, actor_id):
  url = '/admin/api/actor/' + str(actor_id)
  response = auth_session.get(url, headers={"Content-Type": "application/json"})
  assert response.status_code == 200
  return json.loads(response.data)

# GET /actors/{id} (webpage)
def get_many_actors(auth_session, search_term):
  query = {
    "q": [
        {"tsv": search_term}
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
  url = "/admin/api/actors/?page=1&per_page=10&sort_by=&sort_desc=false&cache=0"
  response = auth_session.get(url,
                              data = payload,
                              headers = {"Content-Type": "application/json"})
  assert response.status_code == 200
  actors = json.loads(response.data)["items"]
  return actors

# DELETE /api/actor/{id}
def delete_actor(auth_session, actor_id):
  url = "/admin/api/actor/" + str(actor_id)
  response = auth_session.delete(url)
  assert response.status_code == 200
  
def assert_actors_match(first, second):
  assert first["name"] == second["name"]
  assert first["status"] == second["status"]

# Maybe run a test scenario that calls methods in a sequence to test all the actor endpoints
def test_actor_crud_sequence(auth_session):
  common_description = str(uuid.uuid4())
  first_actor = new_actor()
  first_actor["description"] = common_description 
  first_id = create_actor(auth_session, first_actor)

  second_actor = new_actor()
  second_actor["description"] = common_description 
  create_actor(auth_session, second_actor)

  actors = get_many_actors(auth_session, common_description)
  assert len(actors) == 2

  read_first_actor = get_actor(auth_session, first_id)
  assert_actors_match(first_actor, read_first_actor)

  updated_actor = new_actor()
  update_actor(auth_session, updated_actor, first_id)
  read_updated_actor = get_actor(auth_session, first_id)
  assert_actors_match(updated_actor, read_updated_actor)

  delete_actor(auth_session, first_id)
