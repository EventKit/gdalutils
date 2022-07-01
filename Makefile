black:
	black --check --diff .

black-format:
	black .

pylint:
	pylint gdal_utils utils

flake8:
	flake8

isort:
	isort .

mypy:
	mypy gdal_utils.py

lint: black flake8 mypy pylint

test:
	coverage run -m pytest -vvv

install-hooks:
ifeq ($(detected_OS),Windows)
	cp hooks/pre-commit .git/hooks/pre-commit
else
	ln -s -f ${CURDIR}/hooks/pre-commit ${CURDIR}/.git/hooks/pre-commit
endif
