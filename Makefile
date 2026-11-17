.PHONY: install test eval ablate demo freeze clean

install:
	python -m pip install -r requirements.txt

test:
	python -m pytest

eval:
	python scripts/run_eval.py

ablate:
	python scripts/run_eval.py --ablate

freeze:
	python scripts/run_eval.py --freeze-only

demo:
	python -m verdict --demo

clean:
	python -c "from verdict.cache import clear; print('cleared', clear(), 'cached reports')"
