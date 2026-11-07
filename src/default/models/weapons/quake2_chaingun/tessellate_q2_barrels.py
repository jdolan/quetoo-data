"""Rebuild the Quake II chaingun's octagonal barrels (tubes and muzzle caps) with more sides.

Each barrel tube is refitted per end (center and corner radius), its texture U is interpolated
around the original corners by angle so the strip maps as before, and its muzzle cap's UVs follow
an affine fit of the original cap. Tube normals are radial, cap normals keep the original direction.
Winding follows the original triangles. Everything else in the OBJ is copied unchanged.

The two irregular 12-sided clamp rings that bind the barrels, and their side discs, are subdivided
by a closed Catmull-Rom curve through their original corners, so the corners, outline and corner
UVs are kept. Their discs take the same outline, with UVs from an affine fit of the original disc.

usage: tessellate_q2_barrels.py <in.obj> <out.obj> [sides] [clamp subdivisions]
"""
import collections
import sys

import numpy as np


def load(path):
  v, vt, vn, groups, header = [], [], [], [], []
  for line in open(path):
    p = line.split()
    if not p:
      continue
    if p[0] == "v":
      v.append([float(x) for x in p[1:4]])
    elif p[0] == "vt":
      vt.append([float(x) for x in p[1:3]])
    elif p[0] == "vn":
      vn.append([float(x) for x in p[1:4]])
    elif p[0] == "usemtl":
      groups.append([p[1], []])
    elif p[0] == "f":
      face = [tuple(int(y) - 1 for y in x.split("/")) for x in p[1:]]
      assert all(a == b == c for a, b, c in face)
      groups[-1][1].append([a for a, _, _ in face])
    elif line.startswith("#") and not v:
      header.append(line.rstrip("\n"))
  return np.array(v), np.array(vt), np.array(vn), groups, header


def components(faces):
  parent = {}

  def find(a):
    parent.setdefault(a, a)
    while parent[a] != a:
      parent[a] = parent[parent[a]]
      a = parent[a]
    return a

  for f in faces:
    for a in f[1:]:
      parent[find(a)] = find(f[0])
  out = collections.defaultdict(list)
  for f in faces:
    out[find(f[0])].append(f)
  return list(out.values())


def outward(v, f, center_of):
  a, b, c = v[f[0]], v[f[1]], v[f[2]]
  n = np.cross(b - a, c - a)
  return np.dot(n, (a + b + c) / 3 - center_of((a + b + c) / 3))


def catmull_rom(points, steps):
  """Closed Catmull-Rom curve through points: (positions, unit outward normals, edge index, t)."""
  n = len(points)
  out = []
  for i in range(n):
    p0, p1, p2, p3 = (points[(i + k) % n] for k in (-1, 0, 1, 2))
    for j in range(steps):
      t = j / steps
      pos = 0.5 * ((2 * p1) + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                   + (3 * p1 - p0 - 3 * p2 + p3) * t ** 3)
      tan = 0.5 * ((p2 - p0) + 2 * (2 * p0 - 5 * p1 + 4 * p2 - p3) * t + 3 * (3 * p1 - p0 - 3 * p2 + p3) * t * t)
      out.append((pos, tan, i, t))
  center = np.mean(points, axis=0)
  result = []
  for pos, tan, i, t in out:
    normal = np.array([tan[1], -tan[0]]) / np.linalg.norm(tan)
    if np.dot(normal, pos - center) < 0:
      normal = -normal
    result.append((pos, normal, i, t))
  return result


def main(src, dst, sides, clamp_steps):
  v, vt, vn, groups, header = load(src)
  barrel = next(g for g in groups if g[0].endswith("/chaingun_barrel"))
  parts = components(barrel[1])
  tubes = [p for p in parts if len(p) == 16]
  caps = [p for p in parts if len(p) == 6]
  assert len(tubes) == 6 and len(caps) == 6, (len(tubes), len(caps))

  new_v, new_vt, new_vn, new_faces = [], [], [], []

  def emit(pos, uv, normal):
    new_v.append(pos); new_vt.append(uv); new_vn.append(normal)
    return len(v) + len(new_v) - 1

  removed = []
  for tube in tubes:
    idx = sorted({a for f in tube for a in f})
    x0, x1 = v[idx, 0].min(), v[idx, 0].max()
    ends = []
    for x in (x0, x1):
      ring = [i for i in idx if abs(v[i, 0] - x) < 1e-3]
      corners = np.unique(v[ring][:, 1:].round(5), axis=0)
      assert len(corners) == 8, len(corners)
      center = corners.mean(axis=0)
      radius = np.linalg.norm(corners - center, axis=1).mean()
      # angle -> u samples around the ring, unwrapped across the texture seam
      samples = sorted((np.arctan2(*(v[i, 1:] - center)[::-1]), vt[i, 0], vt[i, 1]) for i in ring)
      ends.append((x, center, radius, samples))

    # The U seam: the corner that appears twice with different U values.
    angles = np.array([s[0] for s in ends[0][3]])
    us = np.array([s[1] for s in ends[0][3]])
    u_min, u_max = us.min(), us.max()
    seam_angle = angles[np.argmin(us)]
    direction = np.sign(np.polyfit(np.unwrap(np.sort(angles)), us[np.argsort(angles)], 1)[0]) or 1

    def seam_of(samples):
      return min(samples, key=lambda s: s[1])[0]

    def u_at(samples, theta):
      pts = {}
      for a, u, _ in samples:
        t = (direction * (a - seam_of(samples))) % (2 * np.pi)
        if t > 2 * np.pi - 1e-3:
          t = 0.0
        if abs(u - u_max) < 1e-4 and t < 1e-3:
          t = 2 * np.pi
        pts[round(t, 4)] = u
      ts = np.array(sorted(pts)); uu = np.array([pts[t] for t in ts])
      if ts[0] > 1e-3:
        ts = np.insert(ts, 0, 0.0); uu = np.insert(uu, 0, u_min)
      if ts[-1] < 2 * np.pi - 1e-3:
        ts = np.append(ts, 2 * np.pi); uu = np.append(uu, u_max)
      return float(np.interp(theta, ts, uu))

    rings = []
    for x, center, radius, samples in ends:
      vv = float(np.mean([s[2] for s in samples]))
      ring = []
      for k in range(sides + 1):
        t = 2 * np.pi * k / sides
        theta = seam_of(samples) + direction * t
        d = np.array([np.cos(theta), np.sin(theta)])
        pos = [x, *(center + radius * d)]
        ring.append(emit(pos, [u_at(samples, t), vv], [0.0, *d]))
      rings.append(ring)

    sign = np.sign(outward(v, tube[0], lambda p: np.array([p[0], *ends[0][1]])))
    for k in range(sides):
      a, b, c, d = rings[0][k], rings[0][k + 1], rings[1][k + 1], rings[1][k]
      for tri in ((a, b, c), (a, c, d)):
        all_v = np.vstack([v, new_v])
        s = np.sign(outward(all_v, tri, lambda p: np.array([p[0], *ends[0][1]])))
        new_faces.append(list(tri) if s == sign else [tri[0], tri[2], tri[1]])
    removed.extend(map(id, tube))

  for cap in caps:
    idx = sorted({a for f in cap for a in f})
    pos = v[idx]
    x = pos[:, 0].mean()
    center = pos[:, 1:].mean(axis=0)
    radius = np.linalg.norm(pos[:, 1:] - center, axis=1).mean()
    A = np.column_stack([pos[:, 1:], np.ones(len(idx))])
    fit, *_ = np.linalg.lstsq(A, vt[idx], rcond=None)
    normal = vn[idx].mean(axis=0); normal /= np.linalg.norm(normal)
    ring = []
    for k in range(sides):
      t = 2 * np.pi * k / sides
      p = center + radius * np.array([np.cos(t), np.sin(t)])
      ring.append(emit([x, *p], list(np.array([*p, 1.0]) @ fit), list(normal)))
    mid = emit([x, *center], list(np.array([*center, 1.0]) @ fit), list(normal))
    want = np.sign(np.dot(np.cross(v[cap[0][1]] - v[cap[0][0]], v[cap[0][2]] - v[cap[0][0]]), normal))
    all_v = np.vstack([v, new_v])
    for k in range(sides):
      tri = [mid, ring[k], ring[(k + 1) % sides]]
      s = np.sign(np.dot(np.cross(all_v[tri[1]] - all_v[tri[0]], all_v[tri[2]] - all_v[tri[0]]), normal))
      new_faces.append(tri if s == want else [tri[0], tri[2], tri[1]])
    removed.extend(map(id, cap))

  rings = [p for p in parts if len(p) == 24 and len({a for f in p for a in f}) == 26]
  discs = [p for p in parts if len(p) == 10]
  assert len(rings) == 2 and len(discs) == 4, (len(rings), len(discs))
  for ring in rings if clamp_steps > 1 else []:
    idx = sorted({a for f in ring for a in f})
    xs = sorted({round(float(v[i, 0]), 4) for i in idx})
    assert len(xs) == 2
    center = v[idx, 1:].mean(axis=0)
    # Corners with their V around the band, ordered from the seam (V nearest 0) outward.
    near = [i for i in idx if abs(v[i, 0] - xs[0]) < 1e-3]
    by_v = sorted(near, key=lambda i: -vt[i, 1])
    seam = by_v[0]
    corners = [seam] + [i for i in by_v[1:] if not np.allclose(v[i], v[seam])]
    seam_end_v = min(vt[i, 1] for i in near if np.allclose(v[i], v[seam]))
    pts = [v[i, 1:] for i in corners]
    vs = [vt[i, 1] for i in corners] + [seam_end_v]
    curve = catmull_rom(pts, clamp_steps) + [None]
    columns = []
    for x in xs:
      u = float(np.mean([vt[i, 0] for i in idx if abs(v[i, 0] - x) < 1e-3]))
      column = []
      for k, sample in enumerate(curve):
        pos, normal, i, t = sample if sample else curve[0][:2] + (len(pts) - 1, 1.0)
        column.append(emit([x, *pos], [u, vs[i] + (vs[i + 1] - vs[i]) * t], [0.0, *normal]))
      columns.append(column)
    sign = np.sign(outward(v, ring[0], lambda p: np.array([p[0], *center])))
    for k in range(len(curve) - 1):
      a, b, c, d = columns[0][k], columns[0][k + 1], columns[1][k + 1], columns[1][k]
      for tri in ((a, b, c), (a, c, d)):
        all_v = np.vstack([v, new_v])
        s = np.sign(outward(all_v, tri, lambda p: np.array([p[0], *center])))
        new_faces.append(list(tri) if s == sign else [tri[0], tri[2], tri[1]])
    removed.extend(map(id, ring))
    for disc in discs:
      didx = sorted({a for f in disc for a in f})
      x = float(v[didx, 0].mean())
      if not any(abs(x - rx) < 1e-3 for rx in xs):
        continue
      A = np.column_stack([v[didx, 1:], np.ones(len(didx))])
      fit, residual, *_ = np.linalg.lstsq(A, vt[didx], rcond=None)
      assert np.abs(A @ fit - vt[didx]).max() < 4e-3, "disc UVs are not planar"
      normal = vn[didx].mean(axis=0); normal /= np.linalg.norm(normal)
      outline = [emit([x, *pos], list(np.array([*pos, 1.0]) @ fit), list(normal)) for pos, *_ in curve[:-1]]
      mid = emit([x, *center], list(np.array([*center, 1.0]) @ fit), list(normal))
      all_v = np.vstack([v, new_v])
      for k in range(len(outline)):
        tri = [mid, outline[k], outline[(k + 1) % len(outline)]]
        s = np.sign(np.dot(np.cross(all_v[tri[1]] - all_v[tri[0]], all_v[tri[2]] - all_v[tri[0]]), normal))
        new_faces.append(tri if s > 0 else [tri[0], tri[2], tri[1]])
      removed.extend(map(id, disc))

  removed = set(removed)
  barrel[1] = [f for f in barrel[1] if id(f) not in removed] + new_faces

  # Compact: keep only referenced vertices, in first-use order.
  all_v, all_vt, all_vn = np.vstack([v, new_v]), np.vstack([vt, new_vt]), np.vstack([vn, new_vn])
  remap = {}
  for _, faces in groups:
    for f in faces:
      for a in f:
        remap.setdefault(a, len(remap))
  order = sorted(remap, key=remap.get)

  with open(dst, "w") as out:
    for line in header:
      out.write(line + "\n")
    out.write(f"# Barrels rebuilt with {sides} sides, clamps subdivided {clamp_steps}x by tessellate_q2_barrels.py\n\n")
    written = 0
    for name, faces in groups:
      out.write(f"usemtl {name}\n")
      used = range(written, max(remap[a] for f in faces for a in f) + 1)
      written = used.stop
      for i in used:
        out.write("v %g %g %g\n" % tuple(all_v[order[i]]))
      for i in used:
        out.write("vt %g %g\n" % tuple(all_vt[order[i]]))
      for i in used:
        out.write("vn %g %g %g\n" % tuple(all_vn[order[i]]))
      for f in faces:
        out.write("f " + " ".join(f"{remap[a] + 1}/{remap[a] + 1}/{remap[a] + 1}" for a in f) + "\n")
      out.write("\n")
  print(f"tubes {len(tubes)}, caps {len(caps)}, barrel faces {len(barrel[1])}")


if __name__ == "__main__":
  main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 24,
       int(sys.argv[4]) if len(sys.argv) > 4 else 3)
