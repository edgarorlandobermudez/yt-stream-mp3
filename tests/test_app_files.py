from pathlib import Path

import app as app_module
import pytest


@pytest.fixture()
def client_and_downloads(tmp_path, monkeypatch):
    downloads = tmp_path / "descargas"
    downloads.mkdir()

    monkeypatch.setattr(app_module, "DOWNLOADS_DIR", downloads)
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        yield client, downloads


def _create_mp3(path: Path, data: bytes = b"mp3-data"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_list_files_is_recursive(client_and_downloads):
    client, downloads = client_and_downloads
    _create_mp3(downloads / "root.mp3")
    _create_mp3(downloads / "playlist" / "nested.mp3")

    response = client.get("/files")

    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, list)
    assert {item["path"] for item in payload} == {
        "root.mp3",
        "playlist/nested.mp3",
    }


def test_clear_files_deletes_only_mp3(client_and_downloads):
    client, downloads = client_and_downloads
    _create_mp3(downloads / "one.mp3")
    _create_mp3(downloads / "folder" / "two.mp3")
    (downloads / "keep.txt").write_text("do not delete", encoding="utf-8")

    response = client.post("/files/clear")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["removed"] == 2
    assert payload["errors"] == 0

    assert not (downloads / "one.mp3").exists()
    assert not (downloads / "folder" / "two.mp3").exists()
    assert (downloads / "keep.txt").exists()


def test_clear_files_reports_empty(client_and_downloads):
    client, _ = client_and_downloads

    response = client.post("/files/clear")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {"removed": 0, "errors": 0}


def test_delete_file_removes_target_mp3(client_and_downloads):
    client, downloads = client_and_downloads
    _create_mp3(downloads / "keep.mp3")
    _create_mp3(downloads / "playlist" / "delete-me.mp3")

    response = client.post(
        "/files/delete",
        json={"path": "playlist/delete-me.mp3"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {"deleted": "playlist/delete-me.mp3"}
    assert not (downloads / "playlist" / "delete-me.mp3").exists()
    assert (downloads / "keep.mp3").exists()


def test_delete_file_rejects_invalid_path(client_and_downloads):
    client, downloads = client_and_downloads
    _create_mp3(downloads / "safe.mp3")

    response = client.post(
        "/files/delete",
        json={"path": "../safe.mp3"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "path inválido"
    assert (downloads / "safe.mp3").exists()
