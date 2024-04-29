import json
import uuid
from random import randint
import datetime

initial_title = 'title'

def new_incident():
  incident = {
      "title": str(uuid.uuid4()),
      "status": "Human Created",
      "description": str(uuid.uuid4()),
      "events": [],
      "incident_relations": [],
      "bulletin_relations": [],
      "actor_relations": [],
      "publish_date": datetime.date(randint(2005,2025), randint(1,12),randint(1,28)).strftime("%Y-%m-%dT%H:%M"),
      "documentation_date": datetime.date(randint(2005,2025), randint(1,12),randint(1,28)).strftime("%Y-%m-%dT%H:%M"),
      "check_br": True,
      "check_ir": True,
      "check_ar": True,
      "comments": str(uuid.uuid4())
    }
  return incident

# POST /api/incident
def create_incident(auth_session, incident):
  payload = json.dumps({"item": incident})
  response = auth_session.post('/admin/api/incident/',
                               data = payload,
                               headers={"Content-Type": "application/json"})
  incident_id = response.data.decode("utf-8").split('#')[1] #'Created incident #4' -> 4  
  assert response.status_code == 200
  return incident_id

# PUT /api/incident/{id}
def update_incident(auth_session, new_incident, incident_id):
  payload = json.dumps({"item": new_incident})
  url = '/admin/api/incident/' + str(incident_id)
  response = auth_session.put(url,
                               data = payload,
                               headers={"Content-Type": "application/json"})
  assert response.status_code == 200
  return

# GET /api/incident/{id}
def get_incident(auth_session, incident_id):
  url = '/admin/api/incident/' + str(incident_id)
  response = auth_session.get(url, headers={"Content-Type": "application/json"})
  assert response.status_code == 200
  return json.loads(response.data)

# GET /incidents/{id} (webpage)
def get_many_incidents(auth_session, search_term):
  query = {
    "q": {
      "tsv": search_term
    },
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
  url = "/admin/api/incidents/?page=1&per_page=10&sort_by=&sort_desc=false&cache=0"
  response = auth_session.get(url,
                              data = payload,
                              headers = {"Content-Type": "application/json"})
  assert response.status_code == 200
  incidents = json.loads(response.data)["items"]
  return incidents

# DELETE /api/incident/{id}
def delete_incident(auth_session, incident_id):
  url = "/admin/api/incident/" + str(incident_id)
  response = auth_session.delete(url)
  assert response.status_code == 200
  
def assert_incidents_match(first, second):
  assert first["title"] == second["title"]
  assert first["status"] == second["status"]

def test_incident_crud_sequence(auth_session):
  common_description = str(uuid.uuid4())
  first_incident = new_incident()
  first_incident["description"] = common_description 
  first_id = create_incident(auth_session, first_incident)

  second_incident = new_incident()
  second_incident["description"] = common_description 
  create_incident(auth_session, second_incident)

  incidents = get_many_incidents(auth_session, common_description)
  assert len(incidents) == 2

  read_first_incident = get_incident(auth_session, first_id)
  assert_incidents_match(first_incident, read_first_incident)

  updated_incident = new_incident()
  update_incident(auth_session, updated_incident, first_id)
  read_updated_incident = get_incident(auth_session, first_id)
  assert_incidents_match(updated_incident, read_updated_incident)

  delete_incident(auth_session, first_id)
