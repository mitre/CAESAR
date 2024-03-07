def test_dashboard_load(auth_session):
  res = auth_session.get('/dashboard/')
  assert res.status_code == 200