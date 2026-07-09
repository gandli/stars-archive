#!/bin/bash
# run_tests.sh - 测试运行脚本
set -e

cd "$(dirname "$0")"

# 清理旧覆盖率
rm -rf .coverage htmlcov .pytest_cache

# 运行测试 (with pyproject.toml for config)
echo "🧪 Running unit tests..."
.venv/bin/python -m pytest tests/ -v --tb=short

# 单独运行覆盖率 (如果安装了 coverage)
echo ""
echo "📊 Running coverage..."
.venv/bin/python -m coverage run -m pytest tests/ -q
.venv/bin/python -m coverage report -m --include="scripts/*" --fail-under=70

echo ""
echo "✅ All tests passed"
