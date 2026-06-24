"""Enable ``python -m delphesprod`` (used by setup/env.sh before install)."""

from delphesprod.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
