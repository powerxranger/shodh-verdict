import json

from scripts.make_demo import make_bundle
from verdict.cache import cache_key, clear, load, store
from verdict.config import ReviewConfig
from verdict.model_client import FakeModelClient, ModelRequest
from verdict.pipeline import review_bundle
from verdict.validation import validate_model_response


def make_request(config, scenario):
    return ModelRequest(system="sys", prompt="data", config=config,
                        known_refs=["R1", "R2", "R3"],
                        known_anchors=["policy.md@v2:p1:L3"])


def validate(scenario, required=False, coverage_mode="exhaustive"):
    config = ReviewConfig.from_env(model_scenario=scenario, model_required=required)
    request = make_request(config, scenario)
    response = FakeModelClient(scenario).generate(request)
    result, _ = validate_model_response(
        response, "fake", request, config, {"R1", "R2", "R3"},
        {"policy.md@v2:p1:L3"}, coverage_mode, {"R1"})
    return config, result, response


def test_valid_clean_response():
    _, result, _ = validate("valid_clean")
    assert result.parse_ok and not result.findings and not result.accepted


def test_truncated_json_rejected():
    _, result, _ = validate("truncated")
    assert not result.parse_ok
    assert any(f.kind == "MODEL_JSON_INVALID" for f in result.findings)


def test_malformed_json_rejected():
    _, result, _ = validate("malformed")
    assert not result.parse_ok


def test_invented_reference_rejected():
    _, result, _ = validate("invented_ref")
    assert any(f.kind == "INVENTED_REFERENCE" for f in result.findings)
    assert result.accepted == []


def test_conflicting_claims_rejected():
    _, result, _ = validate("conflicting")
    assert any(f.kind == "CONFLICTING_MODEL_CLAIMS" for f in result.findings)


def test_coverage_overclaim_rejected():
    _, result, _ = validate("overclaim", coverage_mode="partial")
    assert any(f.kind == "COVERAGE_OVERCLAIM" for f in result.findings)


def test_prompt_injection_in_model_output_is_ignored():
    _, result, _ = validate("injection")
    assert any(f.kind == "PROMPT_INJECTION" for f in result.findings)


def test_timeout_bounded():
    config, result, response = validate("timeout", required=True)
    assert response.attempts == config.max_model_retries + 1
    assert any(f.kind == "MODEL_TIMEOUT" for f in result.findings)


def test_cache_invalidated_by_changed_approvals():
    clear()
    bundle = make_bundle("pass")
    config = ReviewConfig.from_env()
    key1 = cache_key(bundle, config)
    report = review_bundle(bundle, config, use_cache=False)
    store(key1, report)
    assert load(key1) is not None

    changed = make_bundle("approved_25_pass")
    key2 = cache_key(changed, config)
    assert key2 != key1
    assert load(key2) is None
