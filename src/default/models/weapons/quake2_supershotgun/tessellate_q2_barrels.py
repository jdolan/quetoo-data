"""Subdivide the Quake II super shotgun's 10-sided barrels (outer shells, inner bores, the muzzle face
plates joining them and any end caps).

Every original edge of a barrel ring is subdivided along a closed Catmull-Rom curve through the
original corners in cross-section (the axial coordinate is linear between corners), so the corners, the curved muzzle crown and the corner UVs are all kept. U and V
are interpolated along each edge between the original corners, with the texture seam preserved.
Tube normals are perpendicular to the curve, on the same side as the originals (outward for the
shells, inward for the bores). Face plates and caps keep their original normals and take UVs from an
affine fit of the original UVs. Windings agree with the normals, as in the original. Everything
else is copied unchanged.

usage: tessellate_q2_barrels.py <in.obj> <out.obj> [subdivisions]
"""
import collections
import sys

import numpy as np

EPSILON = 1e-3


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


def catmull_rom(points, steps):
  """Closed Catmull-Rom curve through points: [(edge, t, position, tangent)]."""
  n = len(points)
  out = []
  for i in range(n):
    p0, p1, p2, p3 = (points[(i + k) % n] for k in (-1, 0, 1, 2))
    for j in range(steps):
      t = j / steps
      a, b, c = 2 * p0 - 5 * p1 + 4 * p2 - p3, p2 - p0, 3 * p1 - p0 - 3 * p2 + p3
      out.append((i, t, 0.5 * (2 * p1 + b * t + a * t * t + c * t ** 3), 0.5 * (b + 2 * a * t + 3 * c * t * t)))
  return out


class Ring:
  """One end of a barrel tube: its distinct corners, in seam order, with their UVs."""

  def __init__(self, v, vt, vn, idx, center):
    distinct = []
    for i in idx:
      for d in distinct:
        if np.linalg.norm(v[d[0]] - v[i]) < EPSILON:
          d.append(i)
          break
      else:
        distinct.append([i])
    angle = lambda d: np.arctan2(*(v[d[0], 1:] - center)[::-1])
    distinct.sort(key=angle)
    seam = [k for k, d in enumerate(distinct) if np.ptp(vt[d, 0]) > EPSILON]
    assert len(seam) == 1, "expected exactly one texture seam corner"
    k = seam[0]
    n = len(distinct)
    u_min = vt[distinct[k], 0].min()
    # Walk away from the seam in the direction in which U rises from its minimum.
    step = 1 if vt[distinct[(k + 1) % n][0], 0] - u_min < vt[distinct[(k - 1) % n][0], 0] - u_min else -1
    self.corners = [distinct[(k + step * j) % n] for j in range(n)]
    self.positions = [v[c[0]] for c in self.corners]
    self.u = [u_min] + [vt[c[0], 0] for c in self.corners[1:]] + [vt[self.corners[0], 0].max()]
    self.v = [vt[c, 1].mean() for c in self.corners] + [vt[self.corners[0], 1].mean()]
    self.inward = np.dot(vn[self.corners[1][0], 1:], v[self.corners[1][0], 1:] - center) < 0
    self.center = center
    assert all(np.all(np.diff(self.u) > 0) for _ in [0]), "U must rise monotonically around the ring"

  def samples(self, steps):
    """[(position, uv, normal)] around the ring, with the seam corner repeated at the end."""
    out = []
    for i, t, pos, tan in catmull_rom(self.positions, steps):
      normal = np.array([0.0, tan[2], -tan[1]])
      normal /= np.linalg.norm(normal)
      if (np.dot(normal[1:], pos[1:] - self.center) < 0) != self.inward:
        normal = -normal
      # The axial coordinate (the muzzle crown) is linear between corners, so it cannot overshoot.
      pos = np.array([self.positions[i][0] + (self.positions[(i + 1) % len(self.positions)][0] - self.positions[i][0]) * t,
                      pos[1], pos[2]])
      uv = [self.u[i] + (self.u[i + 1] - self.u[i]) * t, self.v[i] + (self.v[i + 1] - self.v[i]) * t]
      out.append((pos, uv, normal))
    first = out[0]
    out.append((first[0], [self.u[-1], self.v[-1]], first[2]))
    return out

  def holds(self, v, i):
    return any(np.linalg.norm(p - v[i]) < EPSILON for p in self.positions)


def main(src, dst, steps):
  v, vt, vn, groups, header = load(src)
  new_v, new_vt, new_vn = [], [], []

  def emit(pos, uv, normal):
    new_v.append(list(pos)); new_vt.append(list(uv)); new_vn.append(list(normal))
    return len(v) + len(new_v) - 1

  def facing(tri, normal):
    allv = np.vstack([v, new_v])
    n = np.cross(allv[tri[1]] - allv[tri[0]], allv[tri[2]] - allv[tri[0]])
    return list(tri) if np.dot(n, normal) > 0 else [tri[0], tri[2], tri[1]]

  faces = groups[0][1]
  parts = components(faces)
  tubes = [p for p in parts if len(p) == 20 and len({a for f in p for a in f}) == 22
           and v[sorted({a for f in p for a in f}), 0].max() > 29]
  assert len(tubes) == 4, len(tubes)

  removed, new_faces, rings = set(), [], []
  for tube in tubes:
    idx = sorted({a for f in tube for a in f})
    center = v[idx, 1:].mean(axis=0)
    ends = [Ring(v, vt, vn, [i for i in idx if v[i, 0] < 0], center),
            Ring(v, vt, vn, [i for i in idx if v[i, 0] > 0], center)]
    assert len(ends[0].corners) == len(ends[1].corners) == 10
    columns = [[emit(*s) for s in end.samples(steps)] for end in ends]
    for k in range(len(columns[0]) - 1):
      a, b, c, d = columns[0][k], columns[0][k + 1], columns[1][k + 1], columns[1][k]
      normal = np.mean([new_vn[i - len(v)] for i in (a, b, c, d)], axis=0)
      new_faces += [facing((a, b, c), normal), facing((a, c, d), normal)]
    removed |= {id(f) for f in tube}
    rings += ends

  def ring_of(i):
    return [r for r in rings if r.holds(v, i)]

  plates = caps = 0
  for part in parts:
    if any(id(f) in removed for f in part):
      continue
    idx = sorted({a for f in part for a in f})
    touched = {id(r) for i in idx for r in ring_of(i)}
    if not touched:
      continue
    on_rings = [i for i in idx if ring_of(i)]
    normal = vn[idx].mean(axis=0); normal /= np.linalg.norm(normal)
    A = np.column_stack([v[on_rings, 1:], np.ones(len(on_rings))])
    fit, *_ = np.linalg.lstsq(A, vt[on_rings], rcond=None)
    assert np.abs(A @ fit - vt[on_rings]).max() < 4e-3, "face UVs are not planar"
    uv_at = lambda pos: list(np.array([pos[1], pos[2], 1.0]) @ fit)
    members = [r for r in rings if id(r) in touched]
    if len(members) == 2:
      # Face plate between a shell's and a bore's muzzle rings, matched corner to corner by angle.
      assert len(on_rings) == len(idx) == 20 and len(part) == 20
      outer, inner = sorted(members, key=lambda r: r.inward)
      angle = lambda r, p: np.arctan2(*(p[1:] - r.center)[::-1])
      rings_pts = []
      for r in (outer, inner):
        pts = [s[0] for s in r.samples(steps)[:-1]]
        rings_pts.append(pts)
      a0 = angle(outer, rings_pts[0][0])
      offset = min(range(len(rings_pts[1])), key=lambda j: abs(np.angle(np.exp(1j * (angle(inner, rings_pts[1][j]) - a0)))))
      inner_pts = rings_pts[1][offset:] + rings_pts[1][:offset]
      d0 = np.angle(np.exp(1j * (angle(inner, inner_pts[1]) - angle(inner, inner_pts[0]))))
      d1 = np.angle(np.exp(1j * (angle(outer, rings_pts[0][1]) - a0)))
      assert np.sign(d0) == np.sign(d1), "rings run in opposite directions"
      o = [emit(p, uv_at(p), normal) for p in rings_pts[0]]
      n_ = [emit(p, uv_at(p), normal) for p in inner_pts]
      count = len(o)
      for k in range(count):
        a, b, c, d = o[k], o[(k + 1) % count], n_[(k + 1) % count], n_[k]
        new_faces += [facing((a, b, c), normal), facing((a, c, d), normal)]
      plates += 1
    else:
      # End cap: a fan over the ring, about its original interior vertex (or centroid).
      ring = members[0]
      interior = [i for i in idx if not ring_of(i)]
      assert len(interior) <= 1 and len(on_rings) + len(interior) == len(idx)
      mid = v[interior[0]] if interior else np.mean(ring.positions, axis=0)
      m = emit(mid, uv_at(mid), normal)
      outline = [emit(p, uv_at(p), normal) for p, _, _ in ring.samples(steps)[:-1]]
      for k in range(len(outline)):
        new_faces.append(facing((m, outline[k], outline[(k + 1) % len(outline)]), normal))
      caps += 1
    removed |= {id(f) for f in part}

  # Every rebuilt original face's winding agrees with its normals; the rebuild keeps that invariant.
  for f in faces:
    if id(f) in removed:
      assert np.dot(np.cross(v[f[1]] - v[f[0]], v[f[2]] - v[f[0]]), vn[f].mean(0)) > 0

  groups[0][1] = [f for f in faces if id(f) not in removed] + new_faces

  all_v, all_vt, all_vn = np.vstack([v, new_v]), np.vstack([vt, new_vt]), np.vstack([vn, new_vn])
  remap = {}
  for _, fs in groups:
    for f in fs:
      for a in f:
        remap.setdefault(a, len(remap))
  order = sorted(remap, key=remap.get)
  with open(dst, "w") as out:
    for line in header:
      out.write(line + "\n")
    out.write(f"# Barrels subdivided {steps}x by tessellate_q2_barrels.py\n\n")
    written = 0
    for name, fs in groups:
      out.write(f"usemtl {name}\n")
      used = range(written, max(remap[a] for f in fs for a in f) + 1)
      written = used.stop
      for i in used:
        out.write("v %g %g %g\n" % tuple(all_v[order[i]]))
      for i in used:
        out.write("vt %g %g\n" % tuple(all_vt[order[i]]))
      for i in used:
        out.write("vn %g %g %g\n" % tuple(all_vn[order[i]]))
      for f in fs:
        out.write("f " + " ".join(f"{remap[a] + 1}/{remap[a] + 1}/{remap[a] + 1}" for a in f) + "\n")
      out.write("\n")
  print(f"tubes {len(tubes)}, face plates {plates}, caps {caps}, faces {sum(len(f) for _, f in groups)}")


if __name__ == "__main__":
  main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 3)
