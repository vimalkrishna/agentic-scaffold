.PHONY: install-cdk sync lint test synth ci all

# Global tool installations
install-cdk:
	npm install -g aws-cdk

# Python environment and dependency synchronization
sync:
	uv sync

# Code style and syntax verification
lint:
	uv run flake8 .

# Unit test execution
test:
	uv run pytest

# AWS CDK template synthesis
synth:
	uv run cdk synth --all

# Combined target for local pre-commit testing
ci: lint test synth

# Complete setup and execution target
all: install-cdk sync lint test synth