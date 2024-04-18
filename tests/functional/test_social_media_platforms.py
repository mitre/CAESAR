import json
from random import randint

RANDOM_INT = randint(1,9999999)
NEW_PLATFORM = { 'title': f'TestPlatform{RANDOM_INT}' }

def find_platform(platforms, title):
  found_platform = None

  for platform in platforms:
    if platform.get('title') == title:
      found_platform = platform
      break
  return found_platform

def get_social_media_platforms(auth_session):
  res = auth_session.get('/admin/api/socialmediaplatforms/')
  assert res.status_code == 200
  return res.json.get('items')

def get_social_media_platform(auth_session, id):
    res = auth_session.get(f'/admin/api/socialmediaplatform/{id}', headers={"Content-Type": "application/json"})
    assert res.status_code == 200
    return res.json

# Test platform creation
def test_social_media_platform_create(auth_session):
  res = auth_session.post('/admin/api/socialmediaplatform/', 
                          data=json.dumps({'item': NEW_PLATFORM}), 
                          headers={"Content-Type": "application/json"})
  assert res.status_code == 200

  platforms = get_social_media_platforms(auth_session)

  # Find the platform that should have been created previously
  found_platform = find_platform(platforms, NEW_PLATFORM.get('title'))
  assert found_platform

  # Set the ID for NEW_PLATFORM so we can delete it later
  NEW_PLATFORM['id'] = found_platform.get('id')

# Test fetching platforms
def test_social_media_platform_get(auth_session):
  platforms = get_social_media_platforms(auth_session)
  assert platforms
  found_platform = find_platform(platforms, NEW_PLATFORM.get('title'))
  assert found_platform

# Test getting a single platform
def test_social_media_platform_get_single(auth_session):
  assert NEW_PLATFORM.get('id')
  platform = get_social_media_platform(auth_session, NEW_PLATFORM.get('id'))
  assert platform.get('title') == NEW_PLATFORM.get('title')
    
# Test editing a platform
def test_social_media_platform_edit(auth_session):
  global RANDOM_INT 
  RANDOM_INT += 1
  NEW_PLATFORM['title'] = f'TestPlatform{RANDOM_INT}'
  body = {
    'item': NEW_PLATFORM
  }
  res = auth_session.put(f'/admin/api/socialmediaplatform/{NEW_PLATFORM.get("id")}', 
                         data=json.dumps(body),
                         headers={"Content-Type": "application/json"})
  assert res.status_code == 200

  platforms = get_social_media_platforms(auth_session)
  assert find_platform(platforms, NEW_PLATFORM.get('title')) 

# Test deleting a platform
def test_social_media_platform_delete(auth_session):
  # Make sure we found the newly created platform
  assert NEW_PLATFORM.get('id')

  res = auth_session.delete(f'/admin/api/socialmediaplatform/{NEW_PLATFORM.get("id")}')
  assert res.status_code == 200

  # Make sure the platform was deleted
  platforms = get_social_media_platforms(auth_session)
  assert not find_platform(platforms, NEW_PLATFORM.get('title'))
