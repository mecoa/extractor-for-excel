import os

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from web.server import create_app
from web.service import ProjectService


@pytest.fixture
def excel_file(tmp_path):
    path = tmp_path / "template.xlsx"
    df = pd.DataFrame({
        "年": ["2024", "2024"],
        "月": ["01", "02"],
        "号": ["001", "002"],
        "金额": ["", ""],
    })
    df.to_excel(path, index=False)
    return str(path)


@pytest.fixture
def pdf_folder(tmp_path):
    folder = tmp_path / "pdfs"
    folder.mkdir()
    (folder / "2024-01-001#.pdf").write_bytes(b"%PDF-1.4 fake")
    return str(folder)


@pytest.fixture
def client():
    return TestClient(create_app(ProjectService()))


def test_state_empty(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    data = r.json()
    assert data["excel_path"] == ""
    assert data["mineru_token_set"] is False
    assert data["llm_key_set"] is False


def test_load_excel(client, excel_file):
    r = client.post("/api/excel/load", json={"path": excel_file})
    assert r.status_code == 200
    data = r.json()
    assert data["headers"] == ["年", "月", "号", "金额"]
    assert len(data["fields"]) == 4


def test_load_excel_missing(client):
    r = client.post("/api/excel/load", json={"path": "/nonexistent.xlsx"})
    assert r.status_code == 400


def test_upload_excel(client, excel_file):
    with open(excel_file, "rb") as f:
        r = client.post("/api/excel/upload", files={"file": ("template.xlsx", f.read())})
    assert r.status_code == 200
    assert r.json()["headers"] == ["年", "月", "号", "金额"]


def test_upload_pdfs_and_match(client, excel_file):
    with open(excel_file, "rb") as f:
        client.post("/api/excel/upload", files={"file": ("template.xlsx", f.read())})
    r = client.post("/api/pdf/upload", files=[
        ("files", ("2024-01-001#.pdf", b"%PDF-1.4 fake")),
        ("files", ("other.pdf", b"%PDF-1.4 fake")),
    ])
    assert r.status_code == 200
    assert r.json()["count"] == 2

    r2 = client.post("/api/match/preview", json={
        "pattern": "{年}-{月}-{号}#", "match_fields": ["年", "月", "号"],
    })
    assert r2.status_code == 200
    results = r2.json()["results"]
    assert results[0]["matched"] is True


def test_set_fields(client, excel_file):
    client.post("/api/excel/load", json={"path": excel_file})
    fields = [
        {"name": "年", "annotation": "", "examples": [], "is_context": False, "selected": True},
        {"name": "金额", "annotation": "总金额", "examples": [], "is_context": False, "selected": True},
    ]
    r = client.post("/api/fields", json={"fields": fields})
    assert r.status_code == 200
    assert len(r.json()["fields"]) == 2


def test_match_field_candidates(client, excel_file):
    client.post("/api/excel/load", json={"path": excel_file})
    r = client.get("/api/match/fields")
    assert "年" in r.json()["candidates"]


def test_preview_match(client, excel_file, pdf_folder):
    client.post("/api/excel/load", json={"path": excel_file})
    body = {"pattern": "{年}-{月}-{号}#", "match_fields": ["年", "月", "号"], "pdf_folder": pdf_folder}
    r = client.post("/api/match/preview", json=body)
    assert r.status_code == 200
    results = r.json()["results"]
    assert results[0]["matched"] is True
    assert results[1]["matched"] is False


def test_preview_match_invalid_folder(client, excel_file):
    client.post("/api/excel/load", json={"path": excel_file})
    body = {"pattern": "{年}", "match_fields": ["年"], "pdf_folder": "/nope"}
    r = client.post("/api/match/preview", json=body)
    assert r.status_code == 400


def test_selected_rows_and_ocr_table(client, excel_file, pdf_folder):
    client.post("/api/excel/load", json={"path": excel_file})
    client.post("/api/match/preview", json={
        "pattern": "{年}-{月}-{号}#", "match_fields": ["年", "月", "号"], "pdf_folder": pdf_folder,
    })
    client.post("/api/match/selected", json={"rows": [0]})
    r = client.get("/api/ocr/table")
    rows = r.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["selected"] is True


def test_start_ocr_no_files_fails(client, excel_file, pdf_folder):
    client.post("/api/excel/load", json={"path": excel_file})
    client.post("/api/match/preview", json={
        "pattern": "{年}-{月}-{号}#", "match_fields": ["年", "月", "号"], "pdf_folder": pdf_folder,
    })
    client.post("/api/match/selected", json={"rows": [1]})
    r = client.post("/api/ocr/start")
    assert r.status_code == 400


def test_extract_without_llm_fails(client, excel_file, pdf_folder):
    client.post("/api/excel/load", json={"path": excel_file})
    client.post("/api/match/preview", json={
        "pattern": "{年}-{月}-{号}#", "match_fields": ["年", "月", "号"], "pdf_folder": pdf_folder,
    })
    r = client.post("/api/extract/start")
    assert r.status_code == 400


def test_project_save_and_open(client, excel_file, tmp_path):
    client.post("/api/excel/load", json={"path": excel_file})
    proj_path = str(tmp_path / "proj.json")
    r = client.post("/api/project/save", json={"path": proj_path})
    assert r.status_code == 200
    assert os.path.exists(proj_path)
    r2 = client.post("/api/project/open", json={"path": proj_path})
    assert r2.status_code == 200
    assert r2.json()["excel_path"] == excel_file
    assert r2.json()["mineru_token_set"] is False


def test_save_project_as(client, excel_file, tmp_path):
    client.post("/api/excel/load", json={"path": excel_file})
    proj_dir = str(tmp_path / "my_project")
    r = client.post("/api/project/save-as", json={"path": proj_dir})
    assert r.status_code == 200
    assert os.path.isdir(proj_dir)
    assert os.path.isfile(os.path.join(proj_dir, "project.json"))
    assert os.path.isfile(os.path.join(proj_dir, "template.xlsx"))
    loaded_path = os.path.join(proj_dir, "project.json")
    r2 = client.post("/api/project/open", json={"path": loaded_path})
    assert r2.status_code == 200
    expected = os.path.join(proj_dir, "template.xlsx")
    assert r2.json()["excel_path"] == expected


def test_save_project_as_keys_persist(client, excel_file, tmp_path):
    client.post("/api/excel/load", json={"path": excel_file})
    proj_dir = str(tmp_path / "key_test")
    client.post("/api/project/save-as", json={"path": proj_dir})
    client.post("/api/mineru/config", json={
        "provider": "mineru", "token": "sk-test-token", "precision": False,
        "baidu_api_key": "baidu-key", "baidu_secret_key": "baidu-secret",
    })
    keys_file = os.path.join(proj_dir, "project.keys.json")
    assert os.path.isfile(keys_file)
    loaded_path = os.path.join(proj_dir, "project.json")
    r = client.post("/api/project/open", json={"path": loaded_path})
    assert r.status_code == 200
    data = r.json()
    assert data["mineru_token_set"] is True
    assert data["baidu_api_key_set"] is True
    assert data["baidu_secret_key_set"] is True


def test_export_no_results_fails(client, excel_file):
    client.post("/api/excel/load", json={"path": excel_file})
    r = client.post("/api/extract/export", json={"path": "out.xlsx"})
    assert r.status_code == 400


def test_service_update_field():
    svc = ProjectService()
    svc.update_field(0, "金额", "100")
    assert svc.results[0]["金额"]["value"] == "100"


def test_new_project_as(client):
    r = client.post("/api/project/new-as", json={"path": "my-proj"})
    assert r.status_code == 200
    path = r.json()["path"]
    assert "my-proj" in path
    assert path.endswith("project.json")
    assert "Documents/extractor-projects" in path
    assert os.path.isdir(os.path.dirname(path))
    s = client.get("/api/state").json()
    assert s["path"] == path

def test_open_project_upload(client, excel_file, tmp_path):
    client.post("/api/excel/load", json={"path": excel_file})
    proj_dir = str(tmp_path / "open_upload_test")
    client.post("/api/project/save-as", json={"path": proj_dir})
    proj_json = os.path.join(proj_dir, "project.json")
    with open(proj_json) as f:
        import json; data = json.load(f)
    r = client.post("/api/project/open/upload", files=[
        ("files", ("imported/project.json", json.dumps(data).encode("utf-8"))),
    ])
    assert r.status_code == 200
    state = r.json()
    assert state["excel_path"] != ""
    assert "Documents/extractor-projects" in state["path"]

def test_fs_list(client, tmp_path):
    r = client.post("/api/fs/list", json={"path": str(tmp_path)})
    assert r.status_code == 200
    data = r.json()
    assert data["current"] == str(tmp_path)
    assert "entries" in data

def test_fs_list_nonexistent(client):
    r = client.post("/api/fs/list", json={"path": "/i_dont_exist_xyz"})
    assert r.status_code == 400

def test_fs_list_home(client):
    r = client.post("/api/fs/list", json={"path": ""})
    assert r.status_code == 200
    assert r.json()["current"] != ""

def test_key_manager_fallback(tmp_path):
    from core.keyring_manager import KeyManager
    km = KeyManager(str(tmp_path))
    km.set("mineru_token", "sk-test")
    assert km.get("mineru_token") == "sk-test"
    keys_file = os.path.join(str(tmp_path), "project.keys.json")
    assert os.path.isfile(keys_file)
    km2 = KeyManager(str(tmp_path))
    assert km2.get("mineru_token") == "sk-test"
    assert km2.get("nonexistent") is None
