.PHONY: help deploy deploy-fast verify test-roadmap install

help:
	@echo "DietCode plugin — common targets"
	@echo ""
	@echo "  make deploy       Sync to ~/.hermes, reinstall Hermes, enable, verify"
	@echo "  make deploy-fast  Sync + verify only (skip Hermes pip reinstall)"
	@echo "  make verify       Roadmap smoke, audit, operator smoke, and unit tests"
	@echo "  make install      Run install.py wizard in this checkout"
	@echo ""
	@echo "Env: HERMES_SRC, HERMES_VENV, HERMES_HOME, DIETCODE_PLUGIN_SRC"

deploy:
	./scripts/hermes_deploy.sh

deploy-fast:
	./scripts/hermes_deploy.sh --skip-hermes-reinstall

verify test-roadmap:
	python3 scripts/roadmap_smoke.py
	python3 scripts/roadmap_audit.py
	python3 scripts/roadmap_operator_smoke.py
	python3 -m unittest tests.test_roadmap_checkpoint tests.test_kernel_cockpit -q

install:
	python3 install.py
