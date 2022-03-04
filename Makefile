black:
	black --check --diff .

black-format:
	black .

pylint:
	pylint --load-plugins pylint_django --django-settings-module=gdal_utils.settings gdal_utils utils

flake8:
	flake8

lint: black flake8 pylint

test:
	DJANGO_SETTINGS_MODULE=gdal_utils.settings coverage run -m pytest -vvv

install-hooks:
ifeq ($(detected_OS),Windows)
	cp hooks/pre-commit .git/hooks/pre-commit
else
	ln -s -f ${CURDIR}/hooks/pre-commit ${CURDIR}/.git/hooks/pre-commit
endif
