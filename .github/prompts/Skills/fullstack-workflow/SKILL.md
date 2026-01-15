---
name: fullstack-workflow
description: Orchestrates full-stack feature development by coordinating API design, Frontend implementation, and Testing.
---

# FullStack Development Workflow

This skill guides the implementation of features defined in OpenSpec (`openspec/specs/*.md`) by leveraging specialized sub-skills.

## 1. Backend & API Strategy (The Logic Layer)
**Reference Skill**: `tools/mcp-builder/SKILL.md`
**Context**: Your backend is in `backend/src/` (FastAPI).
**Action**:
- Treat FastAPI endpoints like MCP Tools: Define strict Pydantic Input/Output models first.
- Before writing logic, define the API contract in `backend/src/app.py` or new routers.
- **Rule**: Create a mock response capability to unblock frontend development immediately.

## 2. Frontend Implementation (The Visual Layer)
**Reference Skill**: `tools/frontend-design/SKILL.md`
**Context**: Your frontend is in `frontend/` (HTML/CSS/JS).
**Action**:
- Read the "Frontend Aesthetics Guidelines" in the reference skill explicitly.
- Implement the UI in `frontend/index.html` or components.
- Connect to the Backend API defined in Phase 1.
- **Style**: Use the aesthetic principles from `frontend-design` (Bold, Intentional, Production-grade).

## 3. Validation & Testing (The Quality Layer)
**Reference Skill**: `tools/webapp-testing/SKILL.md`
**Context**: Testing scripts go in `tests/`.
**Action**:
- Create a Playwright script (`tests/verify_feature.py`) based on the `webapp-testing` patterns.
- The script should interact with the local server (e.g., http://localhost:8188).
- Verify that the `openspec` Requirements are met.

## Workflow Execution Steps
1. **Analyze Spec**: Read the target `openspec/specs/xxx.md`.
2. **Design API**: Draft the Python Pydantic models.
3. **Draft UI**: Generate the HTML/CSS structure.
4. **Implement**: Write the functional code.
5. **Verify**: Generate the test script.