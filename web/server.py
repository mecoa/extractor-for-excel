import os

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web.service import ProjectService


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def create_app(service: ProjectService | None = None) -> FastAPI:
    app = FastAPI(title="Extractor for Excel")
    svc = service or ProjectService()
    app.state.service = svc

    def _err(e: Exception):
        return JSONResponse(status_code=400, content={"detail": str(e)})

    # ---- models ----
    class PathBody(BaseModel):
        path: str = ""

    class FieldsBody(BaseModel):
        fields: list[dict]

    class MatchBody(BaseModel):
        pattern: str
        match_fields: list[str]
        pdf_folder: str = ""

    class RowsBody(BaseModel):
        rows: list[int]

    class MineruBody(BaseModel):
        provider: str = "mineru"
        token: str = ""
        precision: bool = False
        baidu_api_key: str = ""
        baidu_secret_key: str = ""

    class LlmBody(BaseModel):
        base_url: str
        api_key: str = ""
        model: str

    class FieldUpdateBody(BaseModel):
        row_index: int
        field_name: str
        value: str

    # ---- project ----
    @app.get("/api/state")
    def get_state():
        return svc.state()

    @app.post("/api/project/new")
    def new_project():
        svc.new_project()
        return svc.state()

    @app.post("/api/project/open")
    def open_project(body: PathBody):
        try:
            svc.open_project(body.path)
        except Exception as e:
            return _err(e)
        return svc.state()

    @app.post("/api/project/save")
    def save_project(body: PathBody):
        try:
            path = svc.save_project(body.path)
        except Exception as e:
            return _err(e)
        return {"path": path}

    # ---- step 1 ----
    @app.post("/api/excel/load")
    def load_excel(body: PathBody):
        try:
            headers = svc.load_excel(body.path)
        except Exception as e:
            return _err(e)
        return {"headers": headers, "fields": [f.to_dict() for f in svc.project.fields]}

    @app.post("/api/excel/upload")
    async def upload_excel(file: UploadFile = File(...)):
        try:
            content = await file.read()
            headers = svc.save_excel_upload(file.filename or "template.xlsx", content)
        except Exception as e:
            return _err(e)
        return {"headers": headers, "fields": [f.to_dict() for f in svc.project.fields]}

    @app.post("/api/fields")
    def set_fields(body: FieldsBody):
        svc.set_fields(body.fields)
        return {"fields": [f.to_dict() for f in svc.project.fields]}

    # ---- step 2 ----
    @app.get("/api/match/fields")
    def match_fields():
        return {"candidates": svc.match_field_candidates()}

    @app.post("/api/match/preview")
    def preview_match(body: MatchBody):
        try:
            results = svc.preview_match(body.pattern, body.match_fields, body.pdf_folder)
        except Exception as e:
            return _err(e)
        return {"results": results}

    @app.post("/api/pdf/upload")
    async def upload_pdfs(files: list[UploadFile] = File(...)):
        try:
            payload = [(f.filename or "file", await f.read()) for f in files]
            folder = svc.save_pdf_uploads(payload)
        except Exception as e:
            return _err(e)
        return {"folder": folder, "count": len(payload)}

    @app.post("/api/match/selected")
    def set_selected(body: RowsBody):
        svc.set_selected_rows(body.rows)
        return {"selected_rows": svc.project.selected_rows}

    # ---- step 3 ----
    @app.post("/api/mineru/config")
    def set_mineru(body: MineruBody):
        svc.set_ocr_config(
            provider=body.provider,
            token=body.token,
            precision=body.precision,
            baidu_api_key=body.baidu_api_key,
            baidu_secret_key=body.baidu_secret_key,
        )
        return {"ok": True}

    @app.get("/api/ocr/table")
    def ocr_table():
        return {"rows": svc.ocr_table()}

    @app.get("/api/ocr/preview/{row_index}")
    def ocr_preview(row_index: int):
        return {"markdown": svc.ocr_preview(row_index)}

    @app.post("/api/ocr/start")
    def start_ocr():
        try:
            job_id = svc.start_ocr()
        except Exception as e:
            return _err(e)
        return {"job_id": job_id}

    # ---- step 4 ----
    @app.post("/api/llm/config")
    def set_llm(body: LlmBody):
        svc.set_llm(body.base_url, body.api_key, body.model)
        return {"ok": True}

    @app.post("/api/extract/start")
    def start_extract():
        try:
            job_id = svc.start_extract()
        except Exception as e:
            return _err(e)
        return {"job_id": job_id}

    @app.get("/api/extract/table")
    def extract_table():
        return {"rows": svc.extract_table()}

    @app.get("/api/extract/detail/{row_index}")
    def row_detail(row_index: int):
        return {"detail": svc.row_detail(row_index)}

    @app.post("/api/extract/update")
    def update_field(body: FieldUpdateBody):
        svc.update_field(body.row_index, body.field_name, body.value)
        return {"ok": True}

    @app.post("/api/extract/export")
    def export(body: PathBody):
        try:
            path = svc.export(body.path)
        except Exception as e:
            return _err(e)
        return FileResponse(path, filename=os.path.basename(path))

    # ---- jobs ----
    @app.get("/api/job/{job_id}")
    def job_status(job_id: str):
        try:
            return svc.job_status(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")

    if os.path.isdir(STATIC_DIR):
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()
