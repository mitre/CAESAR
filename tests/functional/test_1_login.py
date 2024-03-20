from bs4 import BeautifulSoup
import json
import os

from enferno.app import create_app

TEST_USERNAME = os.getenv('ADMIN_USERNAME')
TEST_PASSWORD = os.getenv('ADMIN_PASSWORD')

assert TEST_USERNAME, 'The `TEST_USERNAME` environment variable must be set and is blank'
assert TEST_PASSWORD, 'The `TEST_PASSWORD` environment variable must be set and is blank'

def test_login_page_load(test_client):
  """
  GIVEN a Flask application
  WHEN a user requests the login page
  THEN the login page should load
  """
  response = test_client.get('/login?next=%2Fdashboard%2F')
  assert response.status_code == 200
  assert b'id="loginForm"' in response.data
  
  parsed_html = BeautifulSoup(response.data)
  csrf = parsed_html.body.find('input', attrs={'id': 'csrf_token'}).get('value')
  assert csrf
  next_path = parsed_html.body.find('input', attrs={'id': 'next'}).get('value')
  assert next_path

def test_login_fail(test_client):
  """
  GIVEN a Flask application
  WHEN a user tries to login with the wrong password
  THEN the login should fail with a 400 status code
  """
  response = test_client.get('/login?next=%2Fdashboard%2F')
  assert response.status_code == 200
  assert b'id="loginForm"' in response.data
  
  parsed_html = BeautifulSoup(response.data)
  csrf = parsed_html.body.find('input', attrs={'id': 'csrf_token'}).get('value')
  assert csrf
  next_path = parsed_html.body.find('input', attrs={'id': 'next'}).get('value')
  assert next_path

  login_data = {
    'csrf_token': csrf,
    'next': next_path,
    'username': TEST_USERNAME,
    'password': 'fake password'
  }
  login_res = test_client.post('/login', data=json.dumps(login_data), headers={"Content-Type": "application/json"})
  assert login_res.status_code == 400

def test_login_pass(test_client):
  """
  GIVEN a Flask application
  WHEN a user tries to login with the correct credentials
  THEN the login should succeed with a 200 status code 
  """
  response = test_client.get('/login?next=%2Fdashboard%2F')
  assert response.status_code == 200
  assert b'id="loginForm"' in response.data
  
  parsed_html = BeautifulSoup(response.data)
  csrf = parsed_html.body.find('input', attrs={'id': 'csrf_token'}).get('value')
  assert csrf
  next_path = parsed_html.body.find('input', attrs={'id': 'next'}).get('value')
  assert next_path

  login_data = {
    'csrf_token': csrf,
    'next': next_path,
    'username': TEST_USERNAME,
    'password': TEST_PASSWORD
  }
  login_res = test_client.post('/login', data=json.dumps(login_data), headers={"Content-Type": "application/json"})
  assert login_res.status_code == 200

  test_client.get('/logout')
