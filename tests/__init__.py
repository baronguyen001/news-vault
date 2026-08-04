"""Test package.

`tests/test_db.py` imports `tests.make_fixture`, which only resolves when this directory
is a package: bare `pytest` (as CI runs it) does not put the working directory on
`sys.path` the way `python -m pytest` does.
"""
