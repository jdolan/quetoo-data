"""Raise the facet count of the rocket launcher's barrel without moving any original vertex.

The barrel (the connected part that reaches the muzzle) is a lathe: rings of corners at fixed X around
the bore axis, joined by quads. Each quad's angular sector is split into `factor` strips; new ring
points follow a centripetal Catmull-Rom curve through the ring's corners, so the slightly elliptical
rings keep their shape. UVs and normals are interpolated along each edge within the face that owns it.

Sectors narrower than MIN_SECTOR_DEG (around the sight bracket on the band) are left alone. Any other
face that shares a split edge (the muzzle annulus, the bore's back wall) is fanned onto the new points,
so no T-junctions remain.

All other lines of the file are preserved byte for byte; new v/vt/vn lines follow the existing ones.

usage: python3 tessellate_barrel.py mesh-baseline/tris.obj tris.obj [factor]
"""
import collections
import sys

import numpy as np

RING_EDGE_MAX_DEG = 45  # a ring edge joins angularly adjacent corners at the same X
GROUP_DEG = 4           # corners within this angle of each other are one sector end
MIN_SECTOR_DEG = 15     # narrower sectors (the bracket's footprint) are left alone


def load(path):
  lines = open(path).read().split("\n")
  v, vt, vn, faces = [], [], [], []
  for n, line in enumerate(lines):
    p = line.split()
    if not p:
      continue
    if p[0] == "v":
      v.append([float(x) for x in p[1:4]])
    elif p[0] == "vt":
      vt.append([float(x) for x in p[1:3]])
    elif p[0] == "vn":
      vn.append([float(x) for x in p[1:4]])
    elif p[0] == "f":
      faces.append((n, [tuple(int(y) - 1 for y in x.split("/")) for x in p[1:]]))
  return lines, np.array(v), np.array(vt), np.array(vn), faces


def centripetal(p0, p1, p2, p3, t):
  """Point at t in [0, 1] between p1 and p2 on the centripetal Catmull-Rom spline."""
  def knot(a, b, k):
    return k + max(np.linalg.norm(b - a), 1e-9) ** 0.5
  t0 = 0.0
  t1 = knot(p0, p1, t0)
  t2 = knot(p1, p2, t1)
  t3 = knot(p2, p3, t2)
  u = t1 + (t2 - t1) * t
  a1 = (t1 - u) / (t1 - t0) * p0 + (u - t0) / (t1 - t0) * p1
  a2 = (t2 - u) / (t2 - t1) * p1 + (u - t1) / (t2 - t1) * p2
  a3 = (t3 - u) / (t3 - t2) * p2 + (u - t2) / (t3 - t2) * p3
  b1 = (t2 - u) / (t2 - t0) * a1 + (u - t0) / (t2 - t0) * a2
  b2 = (t3 - u) / (t3 - t1) * a2 + (u - t1) / (t3 - t1) * a3
  return (t2 - u) / (t2 - t1) * b1 + (u - t1) / (t2 - t1) * b2


def main(src, dst, factor):
  lines, v, vt, vn, faces = load(src)

  # Weld coincident positions, then take the connected part holding the muzzle (the max X vertex).
  index = {}
  wid = np.array([index.setdefault(tuple(x), len(index)) for x in v.round(4)])
  W = np.zeros((len(index), 3))
  W[wid] = v
  parent = list(range(len(index)))

  def find(a):
    while parent[a] != a:
      parent[a] = parent[parent[a]]
      a = parent[a]
    return a

  for _, f in faces:
    for a in f[1:]:
      parent[find(wid[a[0]])] = find(wid[f[0][0]])
  root = find(wid[int(np.argmax(v[:, 0]))])
  barrel = [i for i, (_, f) in enumerate(faces) if find(wid[f[0][0]]) == root]

  # The bore axis: centre of the muzzle's bore ring (the vertices at max X).
  muzzle = W[np.abs(W[:, 0] - W[:, 0].max()) < 1e-3]
  axis = (muzzle[:, 1:].min(0) + muzzle[:, 1:].max(0)) / 2
  theta = np.degrees(np.arctan2(W[:, 2] - axis[1], W[:, 1] - axis[0]))

  def dtheta(a, b):
    return (theta[b] - theta[a] + 180) % 360 - 180

  def ws(i):
    return [wid[a[0]] for a in faces[i][1]]

  # Ring edges: same X, angularly adjacent.
  ring = collections.defaultdict(set)
  edge_faces = collections.defaultdict(set)
  for i in barrel:
    w = ws(i)
    for a, b in ((0, 1), (1, 2), (2, 0)):
      p, q = w[a], w[b]
      if abs(W[p, 0] - W[q, 0]) < 1e-3 and 0 < abs(dtheta(p, q)) < RING_EDGE_MAX_DEG:
        ring[p].add(q)
        ring[q].add(p)
  for i in barrel:
    w = ws(i)
    for a, b in ((0, 1), (1, 2), (2, 0)):
      if w[b] in ring[w[a]]:
        edge_faces[frozenset((w[a], w[b]))].add(i)

  def sector(i):
    """For a lathe triangle: its quad's two ring edges as ((p0, p1), (q0, q1)), else None."""
    w = ws(i)
    groups = []
    for x in w:
      for g in groups:
        if abs(dtheta(g[0], x)) < GROUP_DEG:
          g.append(x)
          break
      else:
        groups.append([x])
    if len(groups) != 2 or abs(dtheta(groups[0][0], groups[1][0])) < MIN_SECTOR_DEG:
      return None
    g0, g1 = groups
    edges = []
    for a in g0:
      for b in g1:
        if b in ring[a]:
          edges.append((a, b))
    lone = [x for x in w if not any(x in e for e in edges)]
    if len(edges) != 1 or len(lone) != 1:
      return None
    x = lone[0]
    # The lone corner's ring neighbour at the other end completes the quad.
    other = g1 if x in g0 else g0
    cands = [y for y in ring[x] if abs(dtheta(other[0], y)) < GROUP_DEG]
    if len(cands) != 1:
      return None
    e2 = (x, cands[0]) if x in g0 else (cands[0], x)
    return tuple(sorted((edges[0], e2)))

  quads = {}
  for i in barrel:
    s = sector(i)
    if s:
      quads.setdefault(s, []).append(i)
  split = {s: fs for s, fs in quads.items() if len(fs) == 2}
  split_edges = {frozenset(e) for s in split for e in s}
  quad_faces = {f for fs in split.values() for f in fs}

  new_v, new_vt, new_vn = [], [], []
  v_index, vt_index, vn_index = {}, {}, {}

  def add(table, store, base, value):
    k = tuple(np.round(value, 5))
    if k not in table:
      table[k] = base + len(store)
      store.append(value)
    return table[k]

  def neighbour(p, away):
    """p's ring neighbour on the side opposite away, or p reflected past away."""
    side = np.sign(dtheta(p, away))
    cands = [y for y in ring[p] if y != away and np.sign(dtheta(p, y)) == -side]
    if cands:
      return W[min(cands, key=lambda y: abs(dtheta(p, y)))]
    return 2 * W[p] - W[away]

  def ring_point(p, q, t):
    """The point at t from p to q; evaluated in a fixed direction so both sides agree exactly."""
    if p > q:
      p, q, t = q, p, 1 - t
    if t in (0, 1):
      return W[p if t == 0 else q]
    return centripetal(neighbour(p, q), W[p], W[q], neighbour(q, p), t)

  def edge_ref(i, ka, kb, t):
    """A reference to the point at t along face i's edge from corner ka to kb."""
    A, B = faces[i][1][ka], faces[i][1][kb]
    if t == 0:
      return A
    if t == 1:
      return B
    uv = (1 - t) * vt[A[1]] + t * vt[B[1]]
    n = (1 - t) * vn[A[2]] + t * vn[B[2]]
    return (add(v_index, new_v, len(v), ring_point(wid[A[0]], wid[B[0]], t)),
            add(vt_index, new_vt, len(vt), uv),
            add(vn_index, new_vn, len(vn), n / np.linalg.norm(n)))

  replaced = {}
  for s, fs in split.items():
    # Each triangle has one ring edge of the quad and one corner of the other; split both evenly.
    for i in fs:
      w = ws(i)
      e = next(k for k in range(3) if frozenset((w[k], w[(k + 1) % 3])) in split_edges)
      x = (e + 2) % 3
      # The lone corner's ring edge runs toward whichever end of edge e is at its angle.
      ka, kb = e, (e + 1) % 3
      toward_a = abs(dtheta(w[ka], w[x])) < GROUP_DEG
      target = w[kb] if toward_a else w[ka]
      lone, = [y for y in ring[w[x]] if frozenset((w[x], y)) in split_edges
               and abs(dtheta(target, y)) < GROUP_DEG]
      tris = []
      for j in range(factor):
        t0, t1 = j / factor, (j + 1) / factor
        p0, p1 = edge_ref(i, ka, kb, t0), edge_ref(i, ka, kb, t1)
        # Lone corner sits at the a end (t = 0) or the b end (t = 1) of its own sector edge.
        def lone_at(t):
          tt = t if toward_a else 1 - t
          if tt == 0:
            return faces[i][1][x]
          A = faces[i][1][x]
          quad_other = next(f for f in fs if f != i)
          B = next(a for a in faces[quad_other][1] if wid[a[0]] == lone)
          uv = (1 - tt) * vt[A[1]] + tt * vt[B[1]]
          n = (1 - tt) * vn[A[2]] + tt * vn[B[2]]
          return (add(v_index, new_v, len(v), ring_point(w[x], lone, tt)),
                  add(vt_index, new_vt, len(vt), uv),
                  add(vn_index, new_vn, len(vn), n / np.linalg.norm(n)))
        # Triangle (a, b, x) with x at a's angle: strip j is (p0, p1, x_j) and, for x at b's angle,
        # mirrored. Each original triangle keeps its own half of every strip.
        if toward_a:
          tris.append([p0, p1, lone_at(t0)])
        else:
          tris.append([p0, p1, lone_at(t1)])
      replaced[i] = tris

  # Any other face on a split edge is refined to match, so no T-junctions remain.
  for i in barrel:
    if i in quad_faces:
      continue
    w = ws(i)
    edges = [k for k in range(3) if frozenset((w[k], w[(k + 1) % 3])) in split_edges]
    if not edges:
      continue
    poly = []
    for k in range(3):
      poly.append(faces[i][1][k])
      if k in edges:
        poly += [edge_ref(i, k, (k + 1) % 3, j / factor) for j in range(1, factor)]
    if len(edges) == 1:
      k = edges[0]
      apex = faces[i][1][(k + 2) % 3]
      start = poly.index(faces[i][1][k])
      chain = poly[start:] + poly[:start]
      chain = chain[:chain.index(apex)]
      replaced[i] = [[apex, chain[m], chain[m + 1]] for m in range(len(chain) - 1)]
    else:
      P = np.array([v[r[0]] if r[0] < len(v) else new_v[r[0] - len(v)] for r in poly])
      UV = np.array([vt[r[1]] if r[1] < len(vt) else new_vt[r[1] - len(vt)] for r in poly])
      N = np.array([vn[a[2]] for a in faces[i][1]]).mean(0)
      c = (add(v_index, new_v, len(v), P.mean(0)), add(vt_index, new_vt, len(vt), UV.mean(0)),
           add(vn_index, new_vn, len(vn), N / np.linalg.norm(N)))
      replaced[i] = [[c, poly[m], poly[(m + 1) % len(poly)]] for m in range(len(poly))]

  # Corners keep their exact positions; original v/vt/vn lines are untouched.
  out = list(lines)
  for i, tris in replaced.items():
    n, _ = faces[i]
    out[n] = "\n".join("f " + " ".join(f"{a + 1}/{b + 1}/{c + 1}" for a, b, c in t) for t in tris)
  last = {k: max(n for n, l in enumerate(lines) if l.startswith(k + " ")) for k in ("v", "vt", "vn")}
  extra = {"v": [f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in new_v],
           "vt": [f"vt {u:.6f} {w:.6f}" for u, w in new_vt],
           "vn": [f"vn {x:.6f} {y:.6f} {z:.6f}" for x, y, z in new_vn]}
  for k in sorted(last, key=lambda k: -last[k]):
    if extra[k]:
      out[last[k]] += "\n" + "\n".join(extra[k])
  open(dst, "w").write("\n".join(out))

  print(f"split {len(split)} quads {factor} ways, refined {len(replaced) - len(quad_faces)} adjoining faces, "
        f"left {len(barrel) - len(replaced)} barrel triangles; +{len(new_v)} v, +{len(new_vt)} vt, +{len(new_vn)} vn")


if __name__ == "__main__":
  main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 3)
