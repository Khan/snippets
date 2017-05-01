.PHONY: serve test check appcfg-update deploy

serve:
	dev_appserver.py --log_level=debug . --host=0.0.0.0

test check:
	python -m unittest discover -p '*_test.py'

appcfg-update deploy:
	gcloud app deploy
