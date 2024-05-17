from bs4 import BeautifulSoup
import json
import os
import pytest
import subprocess
import datetime
from enferno.app import create_app
import time

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
SHOULD_REMOVE_TEST_CONTAINERS_AFTER_TEST_RUN = os.getenv('CLEANUP_TEST_CONTAINERS')

assert ADMIN_USERNAME, 'The `ADMIN_USERNAME` environment variable must be set and is blank'
assert ADMIN_PASSWORD, 'The `ADMIN_PASSWORD` environment variable must be set and is blank'

def deploy_test_containers():
  print(datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
  time.sleep(10)
  subprocess.call("/app/tests/test_deployment.sh", shell=True)
  # subprocess.call(f"docker compose up -d -p test_run_{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}", shell=True)

def reset_system():
  # subprocess.call("pwd", shell=True)
  subprocess.call("/app/tests/test_cleanup.sh", shell=True)
  # rebuild default initial resources
  # subprocess.call('/app/flask/bin/entrypoint.sh')

@pytest.fixture(scope='session')
def test_flask_app():
  deploy_test_containers()
  os.environ['CONFIG_TYPE'] = 'config.TestingConfig'
  flask_app = create_app()
  flask_app.testing = True
  yield flask_app
  if SHOULD_REMOVE_TEST_CONTAINERS_AFTER_TEST_RUN:
    reset_system()

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
    'username': ADMIN_USERNAME,
    'password': ADMIN_PASSWORD
  }
  res = test_client.post('/login', data=json.dumps(login_data), headers={"Content-Type": "application/json"})
  assert res.status_code == 200
  yield test_client