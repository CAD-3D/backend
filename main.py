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
    Upload a .dxf file, parse it, and return its geometry plus any
    matched "objects" (filtered by target_layer / target_block).

    DWG note: if you add DWG support later, check the extension here,
    convert DWG -> DXF into a temp file first (e.g. via a dwg_converter.py
    module wrapping LibreDWG), then feed that temp DXF path into
    parse_dxf()/get_doc() exactly as below.
    """
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()

    if ext != ".dxf":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Only .dxf is supported right now. "
                   f"If you have a .dwg file, please export/save it as .dxf first "
                   f"(e.g. in AutoCAD, LibreCAD, DraftSight, or Open CAD Studio) and re-upload."
        )

    # Save the upload to a temp file so ezdxf can read it from disk.
    tmp_dir = tempfile.mkdtemp(prefix="cad_upload_")
    tmp_path = os.path.join(tmp_dir, f"{uuid.uuid4().hex}.dxf")

    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        try:
            parsed = parse_dxf(tmp_path)
        except DxfParseError as e:
            raise HTTPException(status_code=422, detail=f"Failed to parse DXF file: {e}")

        objects_found = []
        if target_layer or target_block:
            try:
                doc = get_doc(tmp_path)
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
