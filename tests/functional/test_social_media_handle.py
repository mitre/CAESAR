import json
from random import randint

RANDOM_INT = randint(1,9999999)
NEW_HANDLE = { 'handle_name': f'TestHandle{RANDOM_INT}' }
NEW_PLATFORM = { 'title': f'TestPlatform{RANDOM_INT}' }

def find_handle(handles, name):
  found_handle = None

  for handle in handles:
    if handle.get('handle_name') == name:
      found_handle = handle
      break
  return found_handle

def create_platform_handle(auth_session):
  res = auth_session.post('/admin/api/socialmediaplatform/', 
                            data=json.dumps({'item': NEW_PLATFORM}), 
                            headers={"Content-Type": "application/json"})
  NEW_HANDLE['platform_id'] = res.json.get('id')
  assert res.status_code == 200
  return res.json

def get_social_media_handles(auth_session):
  res = auth_session.get('/admin/api/socialmediahandles/')
  assert res.status_code == 200
  return res.json.get('items')

def get_social_media_handle(auth_session, id):
    res = auth_session.get(f'/admin/api/socialmediahandle/{id}', headers={"Content-Type": "application/json"})
    assert res.status_code == 200
    return res.json

# Test handle  creation
def test_social_media_handle_create(auth_session):
  create_platform_handle(auth_session)
  res = auth_session.post('/admin/api/socialmediahandle/', 
                          data=json.dumps({'item': NEW_HANDLE}), 
                          headers={"Content-Type": "application/json"})
  assert res.status_code == 200

  handles = get_social_media_handles(auth_session)

  # Find the handle that should have been created previously
  found_handle = find_handle(handles, NEW_HANDLE.get('handle_name'))
  assert found_handle
  NEW_HANDLE['id'] = found_handle.get('id')

# Test fetching handles
def test_social_media_handles_get(auth_session):
  handles = get_social_media_handles(auth_session)
  assert handles
  found_handle = find_handle(handles, NEW_HANDLE.get('handle_name'))
  assert found_handle

# Test getting a single handles
def test_social_media_handle_get_single(auth_session):
  assert NEW_HANDLE.get('id')
  handle = get_social_media_handle(auth_session, NEW_HANDLE.get('id'))
  assert handle.get('handle_name') == NEW_HANDLE.get('handle_name')
    
# Test editing a handle
def test_social_media_handle_edit(auth_session):
  global RANDOM_INT 
  RANDOM_INT += 1
  NEW_HANDLE['handle_name'] = f'TestHandle{RANDOM_INT}'
  body = {
    'item': NEW_HANDLE
  }
  res = auth_session.put(f'/admin/api/socialmediahandle/{NEW_HANDLE.get("id")}', 
                         data=json.dumps(body),
                         headers={"Content-Type": "application/json"})
  assert res.status_code == 200

  handles = get_social_media_handles(auth_session)
  assert find_handle(handles, NEW_HANDLE.get('handle_name')) 

# Test deleting a handle
def test_social_media_handle_delete(auth_session):
  # Make sure we found the newly created handle
  assert NEW_HANDLE.get('id')

  res = auth_session.delete(f'/admin/api/socialmediahandle/{NEW_HANDLE.get("id")}')
  assert res.status_code == 200

  # Make sure the handle was deleted
  handles = get_social_media_handles(auth_session)
  assert not find_handle(handles, NEW_HANDLE.get('handle_name'))
