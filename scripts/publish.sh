#!/usr/bin/env bash
set -e

# Publish script - Upload claude-sdk-lite to PyPI
# Usage:
#   ./scripts/publish.sh          # Publish to production PyPI
#   ./scripts/publish.sh test     # Publish to TestPyPI first

echo "🚀 Starting claude-sdk-lite publication to PyPI..."

# Check argument
TARGET=${1:-"pypi"}

# Color definitions
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Clean previous build artifacts
echo -e "\n${YELLOW}📦 Step 1: Cleaning previous build artifacts...${NC}"
rm -rf dist/ build/ *.egg-info
echo -e "${GREEN}✓ Cleanup complete${NC}"

# Step 2: Build distribution packages
echo -e "\n${YELLOW}📦 Step 2: Building distribution packages...${NC}"
uv run --group test python -m build
echo -e "${GREEN}✓ Build complete${NC}"

# Step 3: Check package integrity
echo -e "\n${YELLOW}📦 Step 3: Checking package integrity...${NC}"
uv run --group test twine check dist/*
echo -e "${GREEN}✓ Validation passed${NC}"

# Step 4: Show files to be uploaded
echo -e "\n${YELLOW}📦 Step 4: Files to be uploaded:${NC}"
ls -lh dist/

# Step 5: Confirm publication
echo -e "\n${YELLOW}⚠️  Ready to publish to ${TARGET}...${NC}"
read -p "Confirm publication? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo -e "${RED}❌ Publication cancelled${NC}"
    exit 1
fi

# Step 6: Publish
if [ "$TARGET" = "test" ]; then
    echo -e "\n${YELLOW}📦 Publishing to TestPyPI...${NC}"
    uv run --group test twine upload --repository testpypi dist/*
    echo -e "${GREEN}✓ Published to TestPyPI${NC}"
    echo -e "\nTest installation with:"
    echo "pip install --index-url https://test.pypi.org/simple/ claude-sdk-lite"
else
    echo -e "\n${YELLOW}📦 Publishing to PyPI...${NC}"
    uv run --group test twine upload dist/*
    echo -e "${GREEN}✓ Published to PyPI${NC}"
    echo -e "\nInstall with:"
    echo "pip install claude-sdk-lite"
fi

echo -e "\n${GREEN}🎉 Publication complete!${NC}"
