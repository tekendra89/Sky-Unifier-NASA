"""
Sky Unifier - FastAPI backend (improved)
- Better error handling and logging
- Optional pixel_scale for higher quality
- Survey discovery endpoint
- Request-level caching (filesystem)
- Safeguards: max pixels cap to prevent runaway requests

Dependencies:
fastapi, uvicorn, pillow, numpy, astropy, astroquery, reproject
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from pathlib import Path
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import hashlib
import time

# Astronomy libs
from astropy.io import fits
from astropy.wcs import WCS
from astroquery.skyview import SkyView
from astroquery.mast import Observations
import astropy.units as u
import numpy as np
from reproject import reproject_interp
from PIL import Image, ImageOps

# -----------------------------
# Config
# -----------------------------
BASE_DIR = Path("./data").absolute()
LAYER_DIR = BASE_DIR / "layers"
CACHE_DIR = BASE_DIR / "cache"
LAYER_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Concurrency
EXECUTOR = ThreadPoolExecutor(max_workers=4)

# Image safeguards
MAX_PIXELS = 2500  # maximum width/height in pixels (npix capped to prevent huge images)
DEFAULT_PIXEL_SCALE = 1.0  # arcsec/pixel (smaller -> higher resolution)
MAX_SIZE_DEG = 2.0  # prevent requesting huge sky areas accidentally

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sky-unifier")

# FastAPI app
app = FastAPI(title="Sky Unifier API", version="0.4") 

# Allow your frontend origin
origins = ["*"]  # Allow all origins for simplicity; restrict in production
# origins = [
#     "http://localhost:5173",   # Frontend local dev
#     # "https://your-production-domain.com"  # Add when you deploy
#     "https://special-space-happiness-xj75j4rjg6jc96x-5173.app.github.dev"
# ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],       # GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],       # Allow all headers like Authorization
)

# -----------------------------
# Models
# -----------------------------
class RenderRequest(BaseModel):
    ra: float = Field(..., description="Right ascension in degrees")
    dec: float = Field(..., description="Declination in degrees")
    size_deg: float = Field(0.1, description="Image size in degrees (square) - default 0.1")
    surveys: List[str] = Field(..., description="List of survey names, e.g. 'DSS', 'WISE 3.4', 'JWST:F200W'")
    stretch: Optional[str] = Field("sqrt", description="Stretch: linear, sqrt, log")
    pixel_scale: Optional[float] = Field(DEFAULT_PIXEL_SCALE, description="Arcsec per pixel (smaller -> higher resolution)")

class LayerInfo(BaseModel):
    id: str
    survey: str
    url: str
    min: float
    max: float

# -----------------------------
# Utilities
# -----------------------------
def _request_hash(payload: Dict[str, Any]) -> str:
    """Create a stable hash for the render request to enable caching."""
    key = f"{payload.get('ra'):.6f}_{payload.get('dec'):.6f}_{payload.get('size_deg'):.6f}_" \
            f"{','.join(payload.get('surveys', []))}_{payload.get('stretch')}_{payload.get('pixel_scale')}"
    return hashlib.sha1(key.encode()).hexdigest()

def get_common_wcs_and_shape(center_ra, center_dec, size_deg, pixel_scale=DEFAULT_PIXEL_SCALE):
    """
    Create a TAN WCS and shape for target image.
    pixel_scale: arcsec/pixel
    caps on npix to prevent huge allocations.
    """
    if size_deg <= 0:
        raise ValueError("size_deg must be positive")
    if size_deg > MAX_SIZE_DEG:
        raise ValueError(f"size_deg too large (max {MAX_SIZE_DEG} deg)")

    size_arcsec = size_deg * 3600.0
    npix = int(np.ceil(size_arcsec / pixel_scale))

    if npix < 10:
        npix = 10
    if npix > MAX_PIXELS:
        logger.warning("Requested resolution would exceed cap (%d px). Capping to %d px.", npix, MAX_PIXELS)
        npix = MAX_PIXELS

    w = WCS(naxis=2)
    w.wcs.crval = [center_ra, center_dec]
    w.wcs.crpix = [npix / 2.0, npix / 2.0]
    w.wcs.cdelt = np.array([-pixel_scale / 3600.0, pixel_scale / 3600.0])
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return w, (npix, npix)

def normalize_to_8bit(data, stretch='sqrt'):
    """Normalize a 2D numpy array to 8-bit (0-255)."""
    arr = np.array(data, dtype=np.float64)
    # handle constant arrays or NaNs gracefully
    if np.all(np.isnan(arr)):
        return np.zeros(arr.shape, dtype=np.uint8)
    arr = np.nan_to_num(arr, nan=np.nanmedian(arr))
    # compute robust percentiles
    try:
        vmin = np.nanpercentile(arr, 1)
        vmax = np.nanpercentile(arr, 99)
    except Exception:
        vmin = float(np.nanmin(arr))
        vmax = float(np.nanmax(arr))
    if vmax == vmin:
        # flat image
        scaled = np.zeros_like(arr)
    else:
        arr = np.clip(arr, vmin, vmax)
        arr = arr - vmin
        arr = arr / (vmax - vmin)
        if stretch == 'sqrt':
            arr = np.sqrt(arr)
        elif stretch == 'log':
            arr = np.log1p(arr * 9.0) / np.log1p(9.0)
        # linear otherwise
        scaled = np.clip(arr * 255.0, 0, 255)
    return scaled.astype(np.uint8)

def save_png_from_array(arr8bit, outpath: Path, mode='L'):
    """Save PNG with small optimizations."""
    img = Image.fromarray(arr8bit, mode=mode)
    img = ImageOps.autocontrast(img)
    # optimize=True reduces file size for PNG; keep default compression
    img.save(outpath, format='PNG', optimize=True)

# -----------------------------
# Data fetchers (with friendly errors)
# -----------------------------
def skyview_get_fits(position, survey, size):
    """Fetch FITS for a given survey from SkyView with unit-aware width/height."""
    try:
        width = size * u.deg
        height = size * u.deg
        images = SkyView.get_images(
            position=position,
            survey=[survey],
            coordinates="J2000",
            width=width,
            height=height
        )
        if not images:
            raise RuntimeError("SkyView returned no images")
        return images[0]
    except Exception as e:
        raise RuntimeError(f"SkyView error for '{survey}': {str(e)}")

def get_jwst_fits(center_ra, center_dec, size_deg, filter_name="F200W"):
    """Query JWST observations from MAST at given RA/Dec."""
    try:
        obs = Observations.query_region(f"{center_ra} {center_dec}", radius=f"{size_deg} deg")
    except Exception as e:
        raise RuntimeError(f"MAST query failed: {e}")

    jwst = obs[obs['obs_collection'] == 'JWST']
    if len(jwst) == 0:
        raise RuntimeError("No JWST observations found at this location")

    products = Observations.get_product_list(jwst[0])
    if filter_name and 'filters' in products.colnames:
        products = products[products['filters'] == filter_name]

    if len(products) == 0:
        raise RuntimeError(f"No JWST products with filter '{filter_name}'")

    try:
        data = Observations.download_products(products[0:1], mrp_only=False)
    except Exception as e:
        raise RuntimeError(f"Failed to download JWST product: {e}")

    # data is an astropy.table with 'Local Path'
    filepath = None
    for c in ['Local Path', 'LocalPath', 'local_path']:
        if c in data.colnames:
            filepath = data[c][0]
            break
    if not filepath:
        # fallback: return error
        raise RuntimeError("Downloaded JWST product missing local path")

    return fits.open(filepath)

# -----------------------------
# Core rendering logic (per-survey safe)
# -----------------------------
def prepare_layer_for_survey(center_ra, center_dec, size_deg, survey, target_wcs, target_shape, stretch='sqrt'):
    """Fetch, reproject, normalize and save PNG for one survey. Returns dict with success or error."""
    pos = f"{center_ra},{center_dec}"
    start = time.time()
    try:
        # special-case JWST
        if survey.upper().startswith("JWST"):
            parts = survey.split(":")
            filter_name = parts[1] if len(parts) > 1 else "F200W"
            hdul = get_jwst_fits(center_ra, center_dec, size_deg, filter_name)
        else:
            hdul = skyview_get_fits(pos, survey, size_deg)

        # find first HDU with data
        image_hdu = next((h for h in hdul if getattr(h, 'data', None) is not None), None)
        if image_hdu is None:
            raise RuntimeError("No image data found in FITS")

        data = image_hdu.data
        header = image_hdu.header
        try:
            source_wcs = WCS(header)
        except Exception:
            # Some FITS may have incomplete WCS, try primary header
            source_wcs = None

        # If no valid source_wcs, try using primary HDU header
        if source_wcs is None or source_wcs.wcs is None:
            try:
                source_wcs = WCS(hdul[0].header)
            except Exception:
                # still None -> raise
                raise RuntimeError("FITS WCS not parseable")

        # reproject
        reprojected, _ = reproject_interp((data, source_wcs), target_wcs, shape_out=target_shape)

        arr8 = normalize_to_8bit(reprojected, stretch=stretch)

        layer_id = uuid.uuid4().hex
        outpath = LAYER_DIR / f"{layer_id}.png"
        save_png_from_array(arr8, outpath)

        duration = time.time() - start
        logger.info("Rendered survey '%s' -> %s (%.2f s, %dx%d)", survey, outpath.name, duration, target_shape[0], target_shape[1])

        return {
            'id': layer_id,
            'survey': survey,
            'path': str(outpath),
            'min': float(np.nanmin(reprojected)),
            'max': float(np.nanmax(reprojected)),
        }

    except Exception as e:
        logger.warning("Survey '%s' failed: %s", survey, str(e))
        return {"survey": survey, "error": str(e)}

# -----------------------------
# Async orchestration & caching
# -----------------------------
async def render_layers_async(center_ra, center_dec, size_deg, surveys, stretch='sqrt', pixel_scale=DEFAULT_PIXEL_SCALE):
    # build WCS/shape once
    target_wcs, target_shape = get_common_wcs_and_shape(center_ra, center_dec, size_deg, pixel_scale)

    loop = asyncio.get_running_loop()
    tasks = []
    for survey in surveys:
        # check basic local cache: hashed request + survey
        tasks.append(loop.run_in_executor(EXECUTOR, prepare_layer_for_survey,
                                          center_ra, center_dec, size_deg,
                                          survey, target_wcs, target_shape, stretch))
    results = []
    for coro in asyncio.as_completed(tasks):
        res = await coro
        results.append(res)
    return results

# -----------------------------
# Helper: list SkyView surveys (cached)
# -----------------------------
_SURVEYS_CACHE = None
def list_skyview_surveys() -> List[str]:
    global _SURVEYS_CACHE
    if _SURVEYS_CACHE is None:
        try:
            _SURVEYS_CACHE = SkyView.list_surveys()
        except Exception as e:
            logger.warning("Failed to list SkyView surveys: %s", e)
            _SURVEYS_CACHE = []
    return _SURVEYS_CACHE

# -----------------------------
# Endpoints
# -----------------------------
@app.get('/layer/{layer_id}.png')
def get_layer(layer_id: str):
    path = LAYER_DIR / f"{layer_id}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Layer not found")
    return FileResponse(path, media_type='image/png')

@app.post('/render')
async def render_endpoint(req: RenderRequest):
    """
    Render multiple survey layers for requested position.
    Returns: { layers: [...], errors: [...] }
    """
    logger.info("Received render request: ra=%s dec=%s size_deg=%s surveys=%s stretch=%s pixel_scale=%s",
                req.ra, req.dec, req.size_deg, req.surveys, req.stretch, req.pixel_scale)

    # Validate
    if not req.surveys:
        raise HTTPException(status_code=400, detail="No surveys requested")
    if req.size_deg <= 0:
        raise HTTPException(status_code=400, detail="size_deg must be positive")
    if req.size_deg > MAX_SIZE_DEG:
        raise HTTPException(status_code=400, detail=f"size_deg too large (max {MAX_SIZE_DEG} deg)")

    # Build request hash for caching (simple caching of identical requests)
    payload = {
        "ra": req.ra, "dec": req.dec, "size_deg": req.size_deg,
        "surveys": req.surveys, "stretch": req.stretch, "pixel_scale": req.pixel_scale
    }
    req_hash = _request_hash(payload)
    cache_marker = CACHE_DIR / f"{req_hash}.json"
    # NOTE: We do not persist layer metadata in this version — we rely on saved PNG files to remain.
    # If a cached JSON exists, we still re-run to ensure up-to-date (you can change this behavior).
    results = await render_layers_async(req.ra, req.dec, req.size_deg, req.surveys, req.stretch, req.pixel_scale or DEFAULT_PIXEL_SCALE)

    layers = []
    errors = []
    for r in results:
        if 'error' in r:
            errors.append({'survey': r.get('survey', 'unknown'), 'error': r.get('error')})
            continue
        layers.append({
            'id': r['id'],
            'survey': r['survey'],
            'url': f"/layer/{r['id']}.png",
            'min': r['min'],
            'max': r['max']
        })

    response = {"layers": layers, "errors": errors}
    return JSONResponse(status_code=200, content=response)

# router = APIRouter()

@app.get("/surveys")
async def list_surveys():
    try:
        survey_dict = SkyView.survey_dict

        if not survey_dict:
            raise HTTPException(status_code=404, detail="No surveys found")

        categories = {}
        all_surveys = []

        # force-convert everything into plain strings
        for category, surveys in survey_dict.items():
            cat = str(category)
            surveys_list = [str(s) for s in surveys]
            categories[cat] = surveys_list
            all_surveys.extend(surveys_list)

        return JSONResponse(
            status_code=200,
            content={
                "count": len(all_surveys),
                "categories": categories,  # grouped
                "all_surveys": all_surveys # flat
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving surveys: {str(e)}")

@app.get('/health')
def health():
    return {"status": "ok", "version": app.version}

# -----------------------------
# Run if main
# -----------------------------
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)