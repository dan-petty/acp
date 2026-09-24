# AGENTS.md — AI Agent Instructions & Engineering Best Practices

This document provides foundational context, architectural principles, and operational best practices for AI coding assistants working on the `dan-petty/atp` codebase.

---

## 1. Core Engineering Philosophy & Objectives

- **High Reliability & Quality First**: Build robust, resilient protocol and agentic automation tooling with defensive error handling, bounded timeouts, and zero tolerance for flaky tests.
- **Poetic Conciseness, Expressive Integration & Zero Boilerplate**:
  - The codebase must read as an expressive, poetically concise integration of protocols, models, schemas, and automation rather than procedural loops or boilerplate.
  - **Strict Complexity & Nesting Caps**: Strictly enforce cyclomatic complexity $M \le 10$ and maximum nesting depth $\le 5$ (< 6 indentation levels) project-wide. Maintain proactive headroom ($M \le 6$, depth $\le 3$). Continuous compliance is validated by `python3 tools/sentinel.py --preset strict`.
  - **Structural Tuple Equality Consolidation in Test Suites**:
    - Under Python AST semantics, every `assert expr` compiles to `if not (expr): raise AssertionError`, adding $+1$ to McCabe complexity.
    - When asserting multiple object attributes or properties in test suites, developers and AI agents **MUST CONSOLIDATE LINEAR ASSERTIONS INTO STRUCTURAL TUPLE EQUALITY CHECKS** (`assert (actual_a, actual_b) == (expected_a, expected_b)`).
- **Negative Tool Schema Invariants**:
  - Models and tool schemas MUST enforce strict parameter boundaries by forbidding undefined or hallucinated parameters (`extra="forbid"` in Pydantic v2).
- **Zero-Trust Security & Egress Safety**:
  - Never store plaintext secrets or tokens in code, configuration files, or logs.
  - Never leak or record private RFC 1918 IP addresses (`192.168.0.0/16`, `10.0.0.0/8`, `172.16.0.0/12`) or internal hostnames (`*.lan`, `*.local`).
  - Standardized mock hostnames: Use `example.com` (with no subdomains) for all dummy test values.
  - Bounded string truncation: Always enforce bounded length caps on external inputs.
  - Subprocess safety: Always use explicit argument lists and isolate execution into dedicated POSIX process groups (`start_new_session=True`).
- **Modern Python Ecosystem**: Track Python 3.12+ (and 3.14+) runtime features, typing standards (`pydantic v2`, `pytest`, `ruff`, `mypy`).
- **Strict Quality Thresholds**: Minimum 90% code coverage, strict static type checks, zero unhandled deprecation warnings.
- **Zero Zombie Code**: Ruthlessly remove obsolete code, unused variables, and compatibility shims.

---

## 2. Testing & Quality Verification

Before committing or pushing any change, execute the full local validation suite:

```bash
# 1. Run unit test suite with coverage enforcement
python3 -m pytest tests/ -v --cov=src/atp --cov-report=term-missing --cov-fail-under=90

# 2. Verify architectural invariants
python3 tools/sentinel.py src/ tools/ tests/ --preset strict

# 3. Check code style, modernization, and imports
ruff check .

# 4. Check formatting
ruff format --check .
```
