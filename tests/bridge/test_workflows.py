import json
import pytest
from src.bridge import workflows

def test_load_workflow_reads_json(tmp_path):
    wf = {"3": {"class_type": "KSampler", "inputs": {"seed": 1}}}
    d = tmp_path / "wf"
    d.mkdir()
    (d / "txt2img.json").write_text(json.dumps(wf))
    got = workflows.load_workflow("txt2img", str(d))
    assert got == wf

def test_load_workflow_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        workflows.load_workflow("nope", str(tmp_path))

def test_apply_inputs_overrides_node_field():
    wf = {"3": {"class_type": "KSampler", "inputs": {"seed": 1}}}
    out = workflows.apply_inputs(wf, {"3.seed": 42})
    assert out["3"]["inputs"]["seed"] == 42
    # original not mutated
    assert wf["3"]["inputs"]["seed"] == 1

def test_apply_inputs_unknown_target_raises():
    wf = {"3": {"class_type": "KSampler", "inputs": {}}}
    with pytest.raises(KeyError):
        workflows.apply_inputs(wf, {"9.seed": 1})
