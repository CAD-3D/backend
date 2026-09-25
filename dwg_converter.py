"""
dwg_converter.py
-----------------
Converts a .dwg file to .dxf using a precompiled LibreDWG `dwg2dxf` binary
(GNU LibreDWG, GPL-3.0-or-later), invoked as a subprocess. No Docker and no
compiler needed on the deploy target (Render) — the binary was compiled
once, ahead of time, and is committed into this repo under bin/.

WHY THIS APPROACH (vs Docker, vs aspose-cad):
- aspose-cad's free/evaluation mode was tested and found to destroy the
  exact data this app depends on: it flattens every entity into generic
  LWPOLYLINEs and strips layer/block names. Not usable here without a
  paid license.
- LibreDWG is not available via apt (Debian/Ubuntu don't package it) and
  compiling it requires a full build toolchain, which Render's native
  Python runtime doesn't provide without switching to Docker.
- Shipping a precompiled binary + its one shared library sidesteps both
  problems: no compiler needed at deploy time, no Docker needed either.

LICENSING NOTE (GPL-3.0):
LibreDWG is GPL-3.0-or-later. This code invokes the compiled `dwg2dxf`
binary as a separate subprocess (not linked into this Python process),
so this project's own code does not become a GPL "combined work" under
the standard interpretation of GPL's linking clause. The binary itself is
distributed unmodified; its source is publicly available at
https://github.com/LibreDWG/libredwg — keep that link in your repo's
README/NOTICE if you redistribute this binary, to satisfy GPL's source-
availability requirement.

PLATFORM NOTE:
The binary in bin/ was compiled for x86_64 Linux (glibc). This matches
Render's standard runtime. If you deploy somewhere with a different
architecture or OS, you'll need to recompile LibreDWG for that target.
"""

import os
import stat
import subprocess


class DwgConvertError(Exception):
    """Raised when a DWG file can't be converted to DXF."""
    pass


# Paths to the vendored binary + its shared library, relative to this file.
_BIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")
_DWG2DXF_PATH = os.path.join(_BIN_DIR, "dwg2dxf")


def convert_dwg_to_dxf(input_path: str, output_path: str, timeout: int = 60) -> str:
    """
    Convert a .dwg file at input_path into a .dxf file at output_path,
    using the vendored LibreDWG dwg2dxf binary.

    Returns output_path on success, or raises DwgConvertError on failure.
    """
    if not os.path.exists(_DWG2DXF_PATH):
        raise DwgConvertError(
            "dwg2dxf binary not found — make sure backend/bin/dwg2dxf and "
            "backend/bin/libredwg.so.0 were committed to the repo."
        )

    # The binary may have lost its executable bit if it was uploaded
    # through a plain web interface (e.g. GitHub's "Upload files" button)
    # rather than via `git` on a Unix machine, which is the whole point of
    # doing this here — it means you never have to run `chmod` or `git
    # update-index --chmod=+x` yourself. This is a no-op if the bit is
    # already set, so it's safe to call on every request.
    try:
        current_mode = os.stat(_DWG2DXF_PATH).st_mode
        os.chmod(_DWG2DXF_PATH, current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError as e:
        raise DwgConvertError(f"Could not set executable permission on dwg2dxf: {e}")

    # dwg2dxf writes relative to the *current directory* by default when
    # given a bare filename, so we pass an explicit -o output path and
    # -y to overwrite if it already exists (e.g. from a retry).
    cmd = [_DWG2DXF_PATH, "-y", "-o", output_path, input_path]

    env = os.environ.copy()
    # Point the dynamic linker at our vendored libredwg.so.0 without
    # requiring it to be installed system-wide.
    env["LD_LIBRARY_PATH"] = _BIN_DIR + os.pathsep + env.get("LD_LIBRARY_PATH", "")

    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise DwgConvertError("DWG conversion timed out — the file may be too large "
                               "or too complex.")
    except OSError as e:
        raise DwgConvertError(f"Could not run dwg2dxf: {e}")

    if result.returncode != 0:
        # dwg2dxf prints warnings to stderr even on success sometimes, so
        # only treat this as a hard error when the exit code is non-zero.
        raise DwgConvertError(
            f"dwg2dxf failed (exit code {result.returncode}): "
            f"{result.stderr.strip() or 'no error output'}"
        )

    if not os.path.exists(output_path):
        raise DwgConvertError("Conversion finished but no output DXF file was created.")

    return output_path
