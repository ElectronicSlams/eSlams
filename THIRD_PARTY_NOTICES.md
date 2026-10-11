# Third-party dependency notices

The repository's LICENSE applies to eSlams Core source. Dependencies retain
their own licenses; Core's license does not replace them.

The required `python-chess>=1.999,<2` distribution is a compatibility package
that depends on `chess`. `python-chess` 1.999 and `chess` 1.11.2 declare
GPL-3.0-or-later. The chess arena imports `chess` for legal moves and rule
adjudication. See [python-chess metadata](https://pypi.org/project/python-chess/1.999/),
[chess metadata](https://pypi.org/project/chess/1.11.2/) and the
[upstream licensing section](https://python-chess.readthedocs.io/en/latest/#license).

This records the dependency and its declared license. It does not change
Core's license or determine legal obligations for a particular downstream
application. Review the actual resolved dependency licenses when redistributing
an environment, container or bundled application.
