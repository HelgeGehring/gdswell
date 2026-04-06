# Execute all notebooks and build docs
docs:
    rm -f docs/*.ipynb
    uv run python -m ipykernel install --user --name python3
    PYTHON_GIL=0 uv run jupytext docs/*.py --to ipynb --execute --set-kernel python3
    cd docs && uv run myst build

# Start dev server
start:
    rm -f docs/*.ipynb
    uv run python -m ipykernel install --user --name python3
    PYTHON_GIL=0 uv run jupytext docs/*.py --to ipynb --execute --set-kernel python3
    cd docs && uv run myst start

# Clean all files in gitignore
clean:
    git clean -fdX

# Run all checks
check:
    set -x
    pre-commit run --all
    PYTHON_GIL=0 uv run pytest

check-docs:
    for file in docs/*.py; do PYTHON_GIL=0 uv run python "$file"; done

# Sync all packages
sync:
    uv sync --all-extras --all-packages