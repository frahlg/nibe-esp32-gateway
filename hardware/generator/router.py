"""Small grid router for two-layer boards (A* with 45-degree moves and vias).

It is deliberately simple: copper of other nets is rasterised onto a 0.1 mm
grid, inflated by clearance + half the track width, and each connection is
found with A*. Results are always checked afterwards with KiCad's own DRC, so
the router only has to be good, not perfect.
"""
import heapq
import math

import numpy as np

DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


class Shape:
    """Copper on one or both layers. kind: rect | circle | seg."""

    def __init__(self, kind, net, layers, **g):
        self.kind, self.net, self.layers, self.g = kind, net, layers, g

    def dist_grid(self, X, Y):
        g = self.g
        if self.kind == "rect":
            dx = np.maximum(np.abs(X - g["cx"]) - g["hw"], 0)
            dy = np.maximum(np.abs(Y - g["cy"]) - g["hh"], 0)
            return np.hypot(dx, dy)
        if self.kind == "circle":
            return np.maximum(np.hypot(X - g["cx"], Y - g["cy"]) - g["r"], 0)
        if self.kind == "seg":
            x1, y1, x2, y2 = g["x1"], g["y1"], g["x2"], g["y2"]
            vx, vy = x2 - x1, y2 - y1
            L2 = vx * vx + vy * vy
            if L2 == 0:
                t = 0
            else:
                t = np.clip(((X - x1) * vx + (Y - y1) * vy) / L2, 0, 1)
            return np.maximum(np.hypot(X - (x1 + t * vx), Y - (y1 + t * vy)) - g["r"], 0)
        raise ValueError(self.kind)

    def bbox(self):
        g = self.g
        if self.kind == "rect":
            return g["cx"] - g["hw"], g["cy"] - g["hh"], g["cx"] + g["hw"], g["cy"] + g["hh"]
        if self.kind == "circle":
            return g["cx"] - g["r"], g["cy"] - g["r"], g["cx"] + g["r"], g["cy"] + g["r"]
        return (min(g["x1"], g["x2"]) - g["r"], min(g["y1"], g["y2"]) - g["r"],
                max(g["x1"], g["x2"]) + g["r"], max(g["y1"], g["y2"]) + g["r"])


class Router:
    def __init__(self, x0, y0, x1, y1, res=0.1, clearance=0.2, edge_clearance=0.4,
                 via_d=0.6, layer_cost=(1.0, 2.5), via_cost=25, turn_cost=2.0):
        self.x0, self.y0, self.res = x0, y0, res
        self.nx = int(round((x1 - x0) / res)) + 1
        self.ny = int(round((y1 - y0) / res)) + 1
        xs = x0 + np.arange(self.nx) * res
        ys = y0 + np.arange(self.ny) * res
        self.X, self.Y = np.meshgrid(xs, ys, indexing="xy")  # shape (ny, nx)
        self.clr, self.edge_clr, self.via_r = clearance, edge_clearance, via_d / 2
        self.layer_cost, self.via_cost, self.turn_cost = layer_cost, via_cost, turn_cost
        self.shapes = []          # all copper
        self.keepout = [np.zeros((self.ny, self.nx), bool) for _ in range(2)]
        self.edge = np.zeros((self.ny, self.nx), bool)
        self.tracks = []          # (net, layer, x1, y1, x2, y2, width)
        self.vias = []            # (net, x, y)

    # --------------------------------------------------------------- geometry
    def idx(self, x, y):
        return int(round((x - self.x0) / self.res)), int(round((y - self.y0) / self.res))

    def pos(self, ix, iy):
        return self.x0 + ix * self.res, self.y0 + iy * self.res

    def set_outline(self, inside_fn):
        """inside_fn(X, Y) -> bool grid of points inside the board edge minus edge clearance."""
        self.edge = ~inside_fn(self.X, self.Y)

    def add_keepout(self, layer, x1, y1, x2, y2):
        m = (self.X >= x1) & (self.X <= x2) & (self.Y >= y1) & (self.Y <= y2)
        for l in ([0, 1] if layer is None else [layer]):
            self.keepout[l] |= m

    def add(self, shape):
        self.shapes.append(shape)

    def _window(self, shape, r):
        bx0, by0, bx1, by1 = shape.bbox()
        i0 = max(int((bx0 - r - self.x0) / self.res) - 1, 0)
        j0 = max(int((by0 - r - self.y0) / self.res) - 1, 0)
        i1 = min(int((bx1 + r - self.x0) / self.res) + 2, self.nx)
        j1 = min(int((by1 + r - self.y0) / self.res) + 2, self.ny)
        return j0, j1, i0, i1

    def blocked(self, net, layer, r_extra):
        """Grid of cells where a track centre (radius r_extra) would violate clearance."""
        b = self.edge.copy() | self.keepout[layer]
        r = self.clr + r_extra
        for s in self.shapes:
            if s.net == net or layer not in s.layers:
                continue
            j0, j1, i0, i1 = self._window(s, r)
            if j0 >= j1 or i0 >= i1:
                continue
            d = s.dist_grid(self.X[j0:j1, i0:i1], self.Y[j0:j1, i0:i1])
            b[j0:j1, i0:i1] |= d < r - 1e-9
        return b

    def own(self, net, layer, shrink):
        """Cells inside own-net copper deep enough that a track centred there stays inside it."""
        m = np.zeros((self.ny, self.nx), bool)
        for s in self.shapes:
            if s.net != net or layer not in s.layers:
                continue
            j0, j1, i0, i1 = self._window(s, 0)
            if s.kind == "rect":
                g = s.g
                X, Y = self.X[j0:j1, i0:i1], self.Y[j0:j1, i0:i1]
                m[j0:j1, i0:i1] |= ((np.abs(X - g["cx"]) <= max(g["hw"] - shrink, 0.02)) &
                                    (np.abs(Y - g["cy"]) <= max(g["hh"] - shrink, 0.02)))
            else:
                # centre distance must leave room for half the new track inside the copper
                g = s.g
                X, Y = self.X[j0:j1, i0:i1], self.Y[j0:j1, i0:i1]
                if s.kind == "circle":
                    dc = np.hypot(X - g["cx"], Y - g["cy"])
                else:
                    x1, y1, x2, y2 = g["x1"], g["y1"], g["x2"], g["y2"]
                    vx, vy = x2 - x1, y2 - y1
                    L2 = vx * vx + vy * vy
                    t = 0 if L2 == 0 else np.clip(((X - x1) * vx + (Y - y1) * vy) / L2, 0, 1)
                    dc = np.hypot(X - (x1 + t * vx), Y - (y1 + t * vy))
                m[j0:j1, i0:i1] |= dc <= max(g["r"] - shrink, self.res * 0.51)
        return m

    # --------------------------------------------------------------- routing
    def route(self, net, start, goals, width, layers=(0, 1), goal_any_via=False, max_expand=3_000_000,
              own_targets=True, goal_shapes=None):
        """A* from start (x, y, layer-set) to any goal cell.

        goals: list of (x, y, layer-set) points; cells of own-net copper on the
        given layers are also accepted as goals.
        Returns list of (layer, ix, iy).
        """
        r = width / 2
        blk = [self.blocked(net, l, r) for l in range(2)]
        vblk = [self.blocked(net, l, self.via_r) for l in range(2)]
        own = [self.own(net, l, r) for l in range(2)]
        free = [~blk[l] | own[l] for l in range(2)]
        via_ok = ~vblk[0] & ~vblk[1]
        for l in range(2):
            if l not in layers:
                free[l][:] = False
        target = [np.zeros((self.ny, self.nx), bool) for _ in range(2)]
        gx = gy = None
        for (x, y, ls) in goals:
            ix, iy = self.idx(x, y)
            gx, gy = ix, iy
            for l in ls:
                target[l][iy, ix] = True
        sx, sy, sls = start
        six, siy = self.idx(sx, sy)
        if goal_shapes is not None:
            # only the copper that is already part of this net's tree counts as a goal
            saved = self.shapes
            self.shapes = goal_shapes
            tree = [self.own(net, l, r) for l in range(2)]
            self.shapes = saved
            for l in range(2):
                target[l] |= tree[l] & free[l]
        elif own_targets:
            start_own = [self.own_component(own[l], six, siy) if l in sls else None for l in range(2)]
            for l in range(2):
                t = own[l].copy()
                if start_own[l] is not None:
                    t &= ~start_own[l]
                target[l] |= t & free[l]
        if goal_any_via:
            gx = gy = None
        heur_pts = np.array([self.idx(x, y) for (x, y, _) in goals]) if goals else None

        def h(ix, iy):
            if heur_pts is None or gx is None:
                return 0.0
            dx = np.abs(heur_pts[:, 0] - ix)
            dy = np.abs(heur_pts[:, 1] - iy)
            return float(np.min(np.maximum(dx, dy) + 0.4142 * np.minimum(dx, dy)))

        lc = self.layer_cost
        openq = []
        best = {}
        came = {}
        for l in sls:
            if l in layers:
                st = (l, six, siy, -1)
                best[st] = 0.0
                heapq.heappush(openq, (h(six, siy), 0.0, st))
        expanded = 0
        while openq:
            f, g, st = heapq.heappop(openq)
            if best.get(st, 1e18) < g:
                continue
            l, ix, iy, d = st
            expanded += 1
            if expanded > max_expand:
                return None
            if target[l][iy, ix] or (goal_any_via and l == 1):
                path = [(l, ix, iy)]
                while st in came:
                    st = came[st]
                    path.append((st[0], st[1], st[2]))
                return path[::-1]
            for k, (dx, dy) in enumerate(DIRS):
                jx, jy = ix + dx, iy + dy
                if not (0 <= jx < self.nx and 0 <= jy < self.ny) or not free[l][jy, jx]:
                    continue
                if dx and dy and not (free[l][iy, jx] or free[l][jy, ix]):
                    continue
                step = (1.4142 if dx and dy else 1.0) * lc[l]
                if d >= 0 and d != k:
                    turn = (k - d) % 8
                    if turn in (3, 4, 5):
                        continue  # no sharp corners
                    step += self.turn_cost * (1 if turn in (1, 7) else 3)
                ng = g + step
                ns = (l, jx, jy, k)
                if ng < best.get(ns, 1e18):
                    best[ns] = ng
                    came[ns] = st
                    heapq.heappush(openq, (ng + h(jx, jy), ng, ns))
            # via
            ol = 1 - l
            if ol in layers and via_ok[iy, ix] and free[ol][iy, ix]:
                ng = g + self.via_cost
                ns = (ol, ix, iy, -1)
                if ng < best.get(ns, 1e18):
                    best[ns] = ng
                    came[ns] = st
                    heapq.heappush(openq, (ng + h(ix, iy), ng, ns))
        return None

    @staticmethod
    def own_component(mask, ix, iy):
        """Flood fill of a boolean mask from (ix, iy)."""
        comp = np.zeros_like(mask)
        if not mask[iy, ix]:
            return comp
        stack = [(ix, iy)]
        ny, nx = mask.shape
        while stack:
            x, y = stack.pop()
            if comp[y, x]:
                continue
            comp[y, x] = True
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b = x + dx, y + dy
                if 0 <= a < nx and 0 <= b < ny and mask[b, a] and not comp[b, a]:
                    stack.append((a, b))
        return comp

    def commit(self, net, path, width, start_xy=None, end_xy=None):
        """Turn a cell path into straight segments and vias; register as copper."""
        pts = []  # (layer, x, y)
        for (l, ix, iy) in path:
            x, y = self.pos(ix, iy)
            pts.append((l, round(x, 4), round(y, 4)))
        if start_xy is not None:
            pts.insert(0, (pts[0][0], start_xy[0], start_xy[1]))
        if end_xy is not None:
            pts.append((pts[-1][0], end_xy[0], end_xy[1]))
        # split into runs per layer, insert vias
        segs, vias = [], []
        run = [pts[0]]
        for p in pts[1:]:
            if p[0] != run[-1][0]:
                vias.append((p[1], p[2]))
                segs.append(run)
                run = [p]
            else:
                run.append(p)
        segs.append(run)
        out = []
        for run in segs:
            l = run[0][0]
            # merge collinear points
            simp = [run[0]]
            for i in range(1, len(run) - 1):
                a, b, c = simp[-1], run[i], run[i + 1]
                if abs((b[1] - a[1]) * (c[2] - b[2]) - (b[2] - a[2]) * (c[1] - b[1])) < 1e-9:
                    continue
                simp.append(b)
            if len(run) > 1:
                simp.append(run[-1])
            for a, b in zip(simp, simp[1:]):
                if (a[1], a[2]) == (b[1], b[2]):
                    continue
                out.append((net, l, a[1], a[2], b[1], b[2], width))
        for (x, y) in vias:
            if any(n == net and (vx - x) ** 2 + (vy - y) ** 2 < (2 * self.via_r) ** 2 for (n, vx, vy) in self.vias):
                continue  # an existing via of this net already sits here
            self.vias.append((net, x, y))
            self.add(Shape("circle", net, (0, 1), cx=x, cy=y, r=self.via_r))
        for t in out:
            self.tracks.append(t)
            self.add(Shape("seg", net, (t[1],), x1=t[2], y1=t[3], x2=t[4], y2=t[5], r=width / 2))
        return out, vias
