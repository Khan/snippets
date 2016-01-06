.PHONY: serve test cfg-check appcfg-update deploy

serve:
	dev_appserver.py --log_level=debug . --host=0.0.0.0

test check:
	python -m unittest discover -p '*_test.py'

cfg-check:
	@for cfg in hipchat.cfg slack-slash.cfg slack-webapi.cfg; \
	 do \
		if [ ! -f $$cfg ]; then \
			echo "Missing expected config file: $$cfg"; \
			echo " ...are you sure you want to deploy?"; \
			exit 1; \
		fi \
	done

appcfg-update:
	appcfg.py --oauth2 update .

deploy: cfg-check
	$(MAKE) appcfg-update
