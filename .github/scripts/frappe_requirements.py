"""Print the runtime dependencies of a Frappe branch as a requirements file.

Usage: python frappe_requirements.py version-16 > frappe.txt
"""

import sys
import urllib.request

import tomllib

URL = "https://raw.githubusercontent.com/frappe/frappe/{branch}/pyproject.toml"


def main() -> None:
    branch = sys.argv[1]
    with urllib.request.urlopen(URL.format(branch=branch), timeout=60) as response:  # noqa: S310
        project = tomllib.load(response)["project"]
    for requirement in project["dependencies"]:
        print(requirement)  # noqa: T201


if __name__ == "__main__":
    main()
