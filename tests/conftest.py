from bs4 import BeautifulSoup
import json
import os
import pytest
import requests

from enferno.app import create_app

TEST_USERNAME = os.getenv('TEST_USERNAME')
TEST_PASSWORD = os.getenv('TEST_PASSWORD')

assert TEST_USERNAME, 'The `TEST_USERNAME` environment variable must be set and is blank'
assert TEST_PASSWORD, 'The `TEST_PASSWORD` environment variable must be set and is blank'

@pytest.fixture(scope='session')
def test_flask_app():
  os.environ['CONFIG_TYPE'] = 'config.TestingConfig'
  flask_app = create_app()
  flask_app.testing = True
  yield flask_app

@pytest.fixture(scope='session')
def test_client(test_flask_app):
  testing_client = test_flask_app.test_client()
  test_flask_app.app_context()
  yield testing_client

@pytest.fixture(scope='session')
def auth_session(test_client):
  res = test_client.get('/login')
  parsed_html = BeautifulSoup(res.data)
  csrf = parsed_html.body.find('input', attrs={'id': 'csrf_token'}).get('value')

  login_data = {
    'csrf_token': csrf,
    'next': '/dashboard',
    'username': TEST_USERNAME,
    'password': TEST_PASSWORD
  }
  res = test_client.post('/login', data=json.dumps(login_data), headers={"Content-Type": "application/json"})
  assert res.status_code == 200
  yield test_client