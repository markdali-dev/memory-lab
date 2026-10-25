# Memory Lab

A small, lean memory layer for AI agents, tested with an analyst agent over the free [Chinook](https://github.com/lerocha/chinook-database) sample database. A learning project; see `CLAUDE.md` for the design and plan.

No installs needed: Python 3 standard library only.

```bash
python3 -m unittest -v              # run the tests
python3 -m memlab.cli --help        # see commands
python3 -m memlab.cli schema        # the database tables
python3 -m memlab.cli index         # what every agent loads first
```
