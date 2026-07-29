.PHONY: build serve serve-live admin

build:
	python build.py

serve: build
	python -m http.server 8001 --directory dist

serve-live:
	python build.py --serve

admin:
	python admin.py
