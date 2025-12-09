#!/usr/bin/env bash
set -e

# Activate virtual environment
if [ -d ".venv" ]; then
  source .venv/bin/activate
else
  echo "Virtual environment .venv not found. Create it with: python3 -m venv .venv"
  exit 1
fi

# Install dependencies
if [ -f "pyproject.toml" ]; then
  echo "Using pyproject.toml for dependencies. Add dependencies using your chosen tool (poetry, pip, etc)."
elif [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
else
  echo "No dependency file found. Create pyproject.toml or requirements.txt."
fi
