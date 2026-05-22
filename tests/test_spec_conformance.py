"""Spec-conformance gate: frontend emits only declared node types; executor covers them all."""
import re
from pathlib import Path

SPEC = Path(__file__).parent.parent / "spec" / "plan.md"
PLANNER_SRC = Path(__file__).parent.parent / "frontend" / "planner.py"
EXECUTOR_SRC = Path(__file__).parent.parent / "engine" / "executor.py"


def _declared_node_types() -> set[str]:
    """Extract node type names from '### TypeName' headings in spec/plan.md."""
    text = SPEC.read_text()
    return set(re.findall(r"^### (\w+)", text, re.MULTILINE))


def _emitted_node_types_from_planner() -> set[str]:
    """Extract literal type strings from {"type": "..."} in planner.py source."""
    source = PLANNER_SRC.read_text()
    return set(re.findall(r'"type"\s*:\s*"(\w+)"', source))


def test_frontend_emits_only_declared_types():
    """Planner must not emit a node type absent from spec/plan.md."""
    declared = _declared_node_types()
    emitted = _emitted_node_types_from_planner()
    undeclared = emitted - declared
    assert not undeclared, (
        f"Frontend emits node type(s) not in spec: {undeclared}. "
        f"Add them to spec/plan.md or remove from planner.py."
    )


def test_executor_covers_all_declared_types():
    """Every node type declared in spec/plan.md must have a handler in executor.py."""
    declared = _declared_node_types()
    source = EXECUTOR_SRC.read_text()
    missing = {t for t in declared if t not in source}
    assert not missing, (
        f"Executor has no branch for spec type(s): {missing}. "
        f"Add a handler in engine/executor.py."
    )


def test_spec_has_at_least_one_node_type():
    """spec/plan.md must declare at least one node type (guards against empty spec)."""
    declared = _declared_node_types()
    assert declared, "spec/plan.md declares no node types (no '### TypeName' headings found)"


def test_no_cross_layer_imports():
    """frontend/ must not import engine/; engine/ must not import frontend/."""
    frontend_dir = Path(__file__).parent.parent / "frontend"
    engine_dir = Path(__file__).parent.parent / "engine"

    for py_file in frontend_dir.glob("*.py"):
        source = py_file.read_text()
        assert "import engine" not in source and "from engine" not in source, (
            f"{py_file.name} imports engine — frontend/engine boundary violated"
        )

    for py_file in engine_dir.glob("*.py"):
        source = py_file.read_text()
        assert "import frontend" not in source and "from frontend" not in source, (
            f"{py_file.name} imports frontend — engine/frontend boundary violated"
        )
