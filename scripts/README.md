# Scripts

This directory contains utility scripts for the claude-sdk-lite project.

## format-python.sh

Python code formatting script that uses autoflake, isort, black, and flake8.

### Prerequisites

- [uv](https://github.com/astral-sh/uv) must be installed
- Run `uv sync --group test` to install formatting dependencies

### Usage

```bash
# Format all Python files
./scripts/format-python.sh

# Check code format without modifying files (useful for CI)
./scripts/format-python.sh --check

# Show detailed output
./scripts/format-python.sh --verbose

# Show help
./scripts/format-python.sh --help
```

### What it does

1. **autoflake** - Removes unused imports and variables
2. **isort** - Sorts imports according to PEP 8
3. **black** - Formats code to consistent style
4. **flake8** - Checks for code quality issues (warnings only)

### Exit codes

- `0` - All checks passed
- `1` - Formatting or linting issues found (in --check mode)
