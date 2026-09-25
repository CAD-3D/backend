"""
main.py
-------
FastAPI backend for Step 1 of the CAD web app:
  - Accepts a .dxf file upload
  - Parses it with ezdxf (dxf_parser.py)
  - Optionally filters for specific "objects" by layer/block name
    (object_detector.py)
  - Returns everything as JSON for the frontend to render on a canvas

DWG support is intentionally NOT included yet (kept simple per project
scope). See the "DWG note" comment near the top for how to add it later.
"""

import os
import shutil
import tempfile
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from dxf_parser import parse_dxf, get_doc, DxfParseError
from object_detector import find_objects, find_objects_by_layer_only
from dwg_converter import convert_dwg_to_dxf, DwgConvertError

app = FastAPI(title="CAD Drawing Analyzer API")

# ---------------------------------------------------------------------------
# CORS: allow the frontend (hosted on a different domain, e.g. GitHub Pages
# or Vercel) to call this API. For now this allows any origin, which is
# fine while you're building — tighten it to your real frontend URL before
# going to production (see ALLOWED_ORIGINS below).
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = ["*"]  # e.g. ["https://your-frontend.vercel.app"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "service": "cad-drawing-analyzer"}


@app.get("/health")
def health():
    """Lightweight endpoint for uptime pings (e.g. UptimeRobot) so the
    Render free instance doesn't spin down from inactivity."""
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_drawing(
    file: UploadFile = File(...),
    target_layer: Optional[str] = Query(None, description="Layer name to filter objects by"),
    target_block: Optional[str] = Query(None, description="Block name to filter objects by"),
):
    """
    Upload a .dxf or .dwg file, parse it, and return its geometry plus any
    matched "objects" (filtered by target_layer / target_block).

    .dwg files are converted to .dxf first using a vendored LibreDWG
    binary (see dwg_converter.py), then parsed the same way as a native
    .dxf upload.
    """
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()

    if ext not in (".dxf", ".dwg"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Only .dxf and .dwg are supported."
        )

    # Save the upload to a temp file so it can be read from disk.
    tmp_dir = tempfile.mkdtemp(prefix="cad_upload_")
    uploaded_path = os.path.join(tmp_dir, f"{uuid.uuid4().hex}{ext}")

    try:
        with open(uploaded_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        if ext == ".dwg":
            dxf_path = os.path.join(tmp_dir, f"{uuid.uuid4().hex}.dxf")
            try:
                convert_dwg_to_dxf(uploaded_path, dxf_path)
            except DwgConvertError as e:
                raise HTTPException(status_code=422, detail=f"Failed to convert DWG file: {e}")
        else:
            dxf_path = uploaded_path

        try:
            parsed = parse_dxf(dxf_path)
        except DxfParseError as e:
            raise HTTPException(status_code=422, detail=f"Failed to parse DXF file: {e}")

        objects_found = []
        if target_layer or target_block:
            try:
                doc = get_doc(dxf_path)
                objects_found = find_objects(doc, target_layer=target_layer, target_block=target_block)
                # If no block matched but a layer was given, also try a
                # plain-geometry-by-layer match as a fallback.
                if not objects_found and target_layer and not target_block:
                    objects_found = find_objects_by_layer_only(doc, target_layer)
            except DxfParseError as e:
                raise HTTPException(status_code=422, detail=f"Failed to analyze DXF file: {e}")

        return {
            "bounds": parsed["bounds"],
            "entities": parsed["entities"],
            "objects_found": objects_found,
        }

    finally:
        # Always clean up the temp file/dir, even if something failed above.
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    # For local testing: `python main.py`
    # On Render, the Start Command should instead be:
    #   uvicorn main:app --host 0.0.0.0 --port $PORT
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
