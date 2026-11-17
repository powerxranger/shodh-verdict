from verdict.config import ROUTE_ESCALATION, ROUTE_MANUAL, ROUTE_NORMAL, ROUTE_PRIORITY
from verdict.models import PythonSnippet, Ticket
from verdict.programs import eval_program
from verdict.python_subset import inspect_snippet


def snippet(code, function="route_ticket"):
    return PythonSnippet(version="1", artifact_id="code", path="routes.py",
                         function=function, code=code)


BASE = """def route_ticket(category, urgent, waiting_minutes):
    if category is None:
        return 'manual_review'
    elif urgent:
        return 'priority_queue'
    elif waiting_minutes >= 30:
        return 'escalation'
    else:
        return 'normal_queue'
"""


def test_base_snippet_compiles_and_routes():
    parsed = inspect_snippet(snippet(BASE))
    assert parsed.ok, parsed.error
    program = parsed.program
    assert eval_program(program, Ticket(category=None)) == ROUTE_MANUAL
    assert eval_program(program, Ticket(category="billing", urgent=True)) == ROUTE_PRIORITY
    assert eval_program(program, Ticket(category="billing", urgent=False,
                                        waiting_minutes=31)) == ROUTE_ESCALATION
    assert eval_program(program, Ticket(category="billing", urgent=False,
                                        waiting_minutes=10)) == ROUTE_NORMAL


def test_nested_if_is_supported():
    code = """def route_ticket(category, urgent, waiting_minutes):
    if waiting_minutes >= 30:
        if category == 'vip':
            return 'priority_queue'
        return 'escalation'
    return 'normal_queue'
"""
    parsed = inspect_snippet(snippet(code))
    assert parsed.ok, parsed.error
    program = parsed.program
    assert eval_program(program, Ticket(category="vip", waiting_minutes=40)) == ROUTE_PRIORITY
    assert eval_program(program, Ticket(category="billing", waiting_minutes=40)) == ROUTE_ESCALATION


def test_imports_and_calls_are_rejected_visibly():
    code = """import os
def route_ticket(category, urgent, waiting_minutes):
    return os.environ.get('ROUTE')
"""
    parsed = inspect_snippet(snippet(code))
    assert not parsed.ok
    assert parsed.unsupported or parsed.error


def test_syntax_error_is_separate_from_inspection():
    parsed = inspect_snippet(snippet("def route_ticket(: pass"))
    assert not parsed.syntax_ok
