test_run_project_name="test_run_"`date +"%m_%d_%Y_%H_%M"`
BAYANAT_EXTERNAL_PORT=5001 POSTGRES_EXTERNAL_PORT=5433 REDIS_EXTERNAL_PORT=6380 docker compose -p $test_run_project_name up -d
sleep 10
docker exec -it --user root $test_run_project_name-bayanat-1 pip install -r tests/requirements-test.txt
docker exec -it --user root $test_run_project_name-bayanat-1 python -m pytest tests/functional_within_test_container
docker compose -p $test_run_project_name down -v