"""Load a local `.env` into the process environment, once, at an entrypoint.

A dev convenience only: every var is still read with `os.getenv` at its point of use, and
the fail-loud checks (a missing required var raises) are unchanged — `.env` just populates
the environment first. `override=False` so a real environment variable set by the shell,
container, or orchestrator always wins over a stray file; production need not ship a `.env`
at all. `find_dotenv` walks up from the caller to the repo-root `.env`, so it works
regardless of which app's process is starting.
"""

from dotenv import find_dotenv, load_dotenv


def load_env() -> None:
    load_dotenv(find_dotenv(usecwd=True), override=False)
