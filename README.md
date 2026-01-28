## Overview

This repository contains configurations to set up a Python development environment using VSCode's Dev Container feature.
The environment includes uv, and Ruff.

### Getting started
First install the [uv package/project manager](https://docs.astral.sh/uv/getting-started/installation). Then run the below commands in the project root folder to install all dependendencies and creating a virtual environment at `.venv`.

```sh
# Install also include develop dependencies
uv sync
uv run pre-commit install
```

#### Info
```sh
# If you do not want dev dependencies to be installed
uv sync --no-dev

# Use the add command to add dependencies to your project
uv add <package-name>
uv remove <package-name>

```
