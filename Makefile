.PHONY: serve test_deps test check appcfg-update deploy

serve:
	dev_appserver.py --log_level=debug . --host=0.0.0.0

test_deps:
	pip install -r requirements-dev.txt

test check:
	python -m unittest discover -p '*_test.py'

appcfg-update deploy:
	gcloud app deploy

create-indexes:
	gcloud datastore indexes create index.yaml
