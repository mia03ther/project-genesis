from pathlib import Path

import pytest

from genesis.pet.state import PetState, local_endpoint, task_mood


def test_state_persists_interactions_but_not_grades(tmp_path: Path) -> None:
    path = tmp_path / "pet.json"
    pet = PetState.load(path)
    assert pet.interact("feed")[0] == "eat"
    assert pet.interact("pet")[0] == "loved"
    pet.save(path)
    assert PetState.load(path) == PetState(meals=1, cuddles=1)
    assert "passed" not in path.read_text()


def test_corrupt_state_does_not_prevent_launch(tmp_path: Path) -> None:
    path = tmp_path / "pet.json"
    for text in ('broken', '[]', '{"meals": -1}', '{"meals": true}'):
        path.write_text(text)
        assert PetState.load(path) == PetState()


@pytest.mark.parametrize("url", ["https://127.0.0.1:8000", "http://example.com:8000", "http://127.0.0.1:8000/path",
                                "http://user@127.0.0.1:8000", "http://127.0.0.1:8000#x"])
def test_pet_cannot_be_redirected_to_external_services(url: str) -> None:
    with pytest.raises(ValueError):
        local_endpoint(url)


def test_only_actual_backend_result_causes_success() -> None:
    assert task_mood(None, False)[0] == "offline"
    assert task_mood(None, True)[0] == "idle"
    assert task_mood({"stage": "diagnosed"}, True)[0] == "ready"
    assert task_mood({"stage": "investigating", "result": {"passed": True}}, True)[0] != "success"
    assert task_mood({"stage": "replayed", "result": {"passed": True}}, True)[0] == "success"
    assert task_mood({"stage": "replayed", "result": {"passed": False}}, True)[0] == "retry"
