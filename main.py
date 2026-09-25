"""
main.py
-------
FastAPI backend for the CAD Drawing Analyzer.

Responsibilities:
- Accept DXF uploads.
- Parse DXF using dxf_parser.py.
- Detect objects using object_detector.py.
- Return geometry + bounds + statistics + warnings.
"""

import os
import shutil
import tempfile
import uuid

from typing import Optional

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
    Query,
)

from fastapi.middleware.cors import CORSMiddleware

from dxf_parser import (
    parse_dxf,
    get_doc,
    DxfParseError,
)

from object_detector import (
    find_objects,
    find_objects_by_layer_only,
)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CAD Drawing Analyzer API",
    version="2.0.0",
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

ALLOWED_ORIGINS = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "cad-drawing-analyzer",
        "version": "2.0.0",
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
    }


# ---------------------------------------------------------------------------
# DXF upload
# ---------------------------------------------------------------------------

@app.post("/api/upload")
async def upload_drawing(
    file: UploadFile = File(...),

    target_layer: Optional[str] = Query(
        None,
        description="Layer name used for object detection",
    ),

    target_block: Optional[str] = Query(
        None,
        description="Block name used for object detection",
    ),

    expand_blocks: bool = Query(
        False,
        description=(
            "Expand INSERT block geometry. "
            "Disabled by default for performance."
        ),
    ),

    max_entities: int = Query(
        500_000,
        ge=1,
        le=2_000_000,
        description="Maximum number of modelspace entities to parse.",
    ),
):
    """
    Upload and analyze a DXF file.
    """

    filename = file.filename or ""

    extension = os.path.splitext(
        filename
    )[1].lower()

    # -----------------------------------------------------------------------
    # Validate file
    # -----------------------------------------------------------------------

    if extension != ".dxf":

        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{extension}'. "
                "Only .dxf is supported."
            ),
        )

    # -----------------------------------------------------------------------
    # Temporary storage
    # -----------------------------------------------------------------------

    tmp_dir = tempfile.mkdtemp(
        prefix="cad_upload_"
    )

    tmp_path = os.path.join(
        tmp_dir,
        f"{uuid.uuid4().hex}.dxf",
    )

    try:

        with open(
            tmp_path,
            "wb",
        ) as output:

            shutil.copyfileobj(
                file.file,
                output,
            )

        # -------------------------------------------------------------------
        # Parse DXF
        # -------------------------------------------------------------------

        try:

            parsed = parse_dxf(
                tmp_path,
                expand_blocks=expand_blocks,
                max_entities=max_entities,
            )

        except DxfParseError as exc:

            raise HTTPException(
                status_code=422,
                detail=f"Failed to parse DXF: {exc}",
            ) from exc

        # -------------------------------------------------------------------
        # Object detection
        # -------------------------------------------------------------------

        objects_found = []

        if target_layer or target_block:

            try:

                doc = get_doc(
                    tmp_path
                )

                objects_found = find_objects(
                    doc,
                    target_layer=target_layer,
                    target_block=target_block,
                )

                # Layer-only fallback.
                if (
                    not objects_found
                    and target_layer
                    and not target_block
                ):

                    objects_found = (
                        find_objects_by_layer_only(
                            doc,
                            target_layer,
                        )
                    )

            except DxfParseError as exc:

                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Failed to analyze DXF: "
                        f"{exc}"
                    ),
                ) from exc

        # -------------------------------------------------------------------
        # Response
        # -------------------------------------------------------------------

        return {
            "filename": filename,

            "bounds": parsed["bounds"],

            "entities": parsed["entities"],

            "objects_found": objects_found,

            "stats": parsed["stats"],

            "warnings": parsed["warnings"],
        }

    finally:

        shutil.rmtree(
            tmp_dir,
            ignore_errors=True,
        )


# ---------------------------------------------------------------------------
# Local development
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.environ.get(
            "PORT",
            8000,
        )
    )

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )
