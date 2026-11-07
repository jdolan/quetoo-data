"""Regenerate the imported Quake II diffuse skins from their preserved baselines.

1. Brighten: gamma exponent 0.75 per sRGB byte.
2. Remove baked specular: within the texels the mesh actually uses, luminance above a robust local
   baseline is removed from unsaturated (white/grey) pixels. Two terms are measured: glints, above
   a small Gaussian baseline; and streaks, bands that hold bright along one texture axis (painted
   cylinder highlights), above a wide lower-percentile baseline. Coloured detail is kept.

A skin with an edited_baseline (a hand edit of its brightened output) starts from that instead and
is not brightened again.

Skins that are lights (their own or another material's glow source), and skins no surface uses,
are only brightened. Always regenerate from the baselines; never process an output again.

usage: python3 quake2-skins.py   (from anywhere; paths are relative to this repository)
"""
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

DATA = Path(__file__).resolve().parents[3]
TARGET = DATA / "target/default"
REPORT = DATA / "src/default/models/quake2-import.json"

GAMMA = 0.75
DELIGHT = {"glint_size": 0.03, "streak": 0.2, "percentile": 25, "keep": 0.0, "saturation": 0.35}


def material_diffuse(material):
  path = TARGET / "models" / f"{material}.mat"
  match = re.search(r"^\s*diffusemap\s+(\S+)", path.read_text(), re.M) if path.exists() else None
  return match.group(1) if match else material


def glow_sources():
  out = set()
  for mat in (TARGET / "models").glob("*/quake2_*/*.mat"):
    out.update(re.findall(r"^\s*texture\s+(\S+)", mat.read_text(), re.M))
  return out


def uv_mask(obj, texture, size):
  """Texels covered by every surface of obj whose material's diffusemap is texture."""
  vt, faces, current = [], [], None
  for line in open(obj):
    p = line.split()
    if not p:
      continue
    if p[0] == "vt":
      vt.append((float(p[1]), float(p[2])))
    elif p[0] == "usemtl":
      current = material_diffuse(p[1]) == texture
    elif p[0] == "f" and current:
      faces.append([int(x.split("/")[1]) - 1 for x in p[1:]])
  w, h = size
  mask = Image.new("L", size, 0)
  draw = ImageDraw.Draw(mask)
  for f in faces:
    draw.polygon([((vt[i][0] % 1) * w, (-vt[i][1] % 1) * h) for i in f], fill=255)
  return ndimage.binary_dilation(np.asarray(mask) > 0, iterations=2)


def fill(y, mask):
  """Extend the used texels over the unused background so filters near island edges are unbiased."""
  _, (iy, ix) = ndimage.distance_transform_edt(~mask, return_indices=True)
  return y[iy, ix]


def delight(rgb, mask, glint_size, streak, percentile, keep, saturation):
  img = rgb.astype(float) / 255
  y = img @ np.array([0.2126, 0.7152, 0.0722])
  n = max(y.shape)
  yf = fill(y, mask)
  glint = np.maximum(y - ndimage.gaussian_filter(yf, glint_size * n), 0)
  w = max(3, int(streak * n) | 1)
  base = ndimage.gaussian_filter(ndimage.percentile_filter(yf, percentile, size=w), w / 4)
  local = ndimage.gaussian_filter(yf, 1.5)
  streaks = []
  for axis in (0, 1):
    s = [1.0, 1.0]
    s[axis] = streak * n
    streaks.append(np.maximum(np.minimum(ndimage.gaussian_filter(yf, s), local) - base, 0))
  excess = np.maximum(glint, np.maximum(*streaks))
  sat = (img.max(2) - img.min(2)) / np.maximum(img.max(2), 1e-4)
  weight = np.clip(1 - sat / saturation, 0, 1) * mask
  target = np.maximum(y - np.minimum(excess, y) * (1 - keep) * weight, 0)
  return np.clip(img * (target / np.maximum(y, 1e-4))[..., None] * 255, 0, 255).round().astype(np.uint8)


def main():
  report = json.loads(REPORT.read_text())
  lut = np.array([round(255 * (v / 255) ** GAMMA) for v in range(256)], dtype=np.uint8)
  glows = glow_sources()
  counts = {"delit": 0, "light": 0, "unused": 0}
  for model in report["models"]:
    obj = DATA / model["destination"]
    for texture in model["textures"]:
      target = obj.parent / texture["output"]
      name = str(target.relative_to(TARGET / "models").with_suffix(""))
      if "edited_baseline" in texture:
        # A hand edit of the brightened skin: it is already brightened.
        with Image.open(DATA / texture["edited_baseline"]) as im:
          rgb = np.asarray(im.convert("RGB"))
      else:
        with Image.open(DATA / texture["brightening_baseline"]) as im:
          rgb = lut[np.asarray(im.convert("RGB"))]
      mask = uv_mask(obj, name, (rgb.shape[1], rgb.shape[0]))
      if name in glows:
        mode = "light"
      elif not mask.any():
        mode = "unused"
      else:
        mode = "delit"
        rgb = delight(rgb, mask, **DELIGHT)
      if "alpha" in texture:
        # A blended surface: alpha from the brightest channel, smoothstep between low and high.
        lo, hi = texture["alpha"]["low"], texture["alpha"]["high"]
        t = np.clip((rgb.max(2).astype(float) - lo) / (hi - lo), 0, 1)
        alpha = np.round(t * t * (3 - 2 * t) * 255).astype(np.uint8)
        Image.fromarray(np.dstack([rgb, alpha]), "RGBA").save(target, optimize=True)
      else:
        Image.fromarray(rgb).save(target, quality=95, subsampling=0)
      texture["specular_removal"] = mode
      texture["output_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
      texture.pop("brightened_sha256", None)
      counts[mode] += 1
  report["diffuse_brightening"]["status"] = "Superseded by diffuse_regeneration"
  report["diffuse_regeneration"] = {
    "script": "src/default/models/quake2-skins.py",
    "input": "Each texture's brightening_baseline, or its edited_baseline when hand edited after brightening; never compound",
    "steps": [f"Brighten: round(255 * (input / 255) ** {GAMMA}) per sRGB byte",
              f"Remove baked specular (strong) with {DELIGHT}, only within texels used by the mesh"],
    "skipped": "Lights/glow sources (specular_removal: light) and textures no surface uses (unused) are only brightened",
    "output": "RGB JPEG, original dimensions, Pillow quality=95, subsampling=0; "
              "RGBA PNG where a texture specifies alpha (smoothstep of the brightest channel)",
    "counts": counts,
    "status": "User chose strong removal for all Q2 item skins, without brightness compensation; needs in-game review"}
  REPORT.write_text(json.dumps(report, indent=2) + "\n")
  print(counts)


if __name__ == "__main__":
  main()
