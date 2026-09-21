"""Renders the flow file as an animated diagram.

One node/edge model drives both outputs, so the SVG and the GIF cannot drift
apart:

    06-rag-flow-animated.svg   self-contained, SMIL animation, loops forever
    06-rag-flow-animated.gif   same frames rasterised with Pillow

The animation is a synchronised wave: every comet shares one cycle duration and
is positioned with keyTimes, which is what keeps the stages firing in order
rather than each edge animating independently.

Run:  python docs/diagrams/render_flow_animation.py
"""

from __future__ import annotations

import math
import pathlib
import xml.etree.ElementTree as ET

OUT = pathlib.Path(__file__).parent
W, H = 1660, 1085
CYCLE = 13.0  # seconds for one full pass of a flow

# ----------------------------------------------------------------- palette
BG = "#0a1020"
PANEL = "#111c31"
PANEL_EDGE = "#22355c"
TEXT = "#e8eefc"
MUTED = "#8fa3c8"
WIRE = "#2f4straight"  # replaced below; keeps linters honest about typos
WIRE = "#2f4569"

ACTOR = "#a855f7"
NET = "#4c8dff"
COMPUTE = "#4c8dff"
MODEL = "#f0a338"
STORE = "#3fa96b"
EVENT = "#ff9f45"
FAIL = "#e4585f"
SUPPORT = "#6b7f9e"


class Node:
    def __init__(self, nid, lines, cx, cy, w=260, h=66, color=NET, sub=None):
        self.id = nid
        self.lines = lines if isinstance(lines, list) else [lines]
        self.cx, self.cy, self.w, self.h = cx, cy, w, h
        self.color = color
        self.sub = sub

    @property
    def top(self):
        return (self.cx, self.cy - self.h / 2)

    @property
    def bottom(self):
        return (self.cx, self.cy + self.h / 2)

    @property
    def left(self):
        return (self.cx - self.w / 2, self.cy)

    @property
    def right(self):
        return (self.cx + self.w / 2, self.cy)


class Edge:
    """`kind` picks the routing: v/h straight, split/merge curve, elbow via a
    gutter, hop for a sideways jump between columns."""

    def __init__(self, a, b, label=None, kind="v", color=None, dashed=False, gutter=None):
        self.a, self.b, self.label, self.kind = a, b, label, kind
        self.color, self.dashed, self.gutter = color, dashed, gutter


# panels are declared once and drawn by both renderers
PANELS = [
    (40, 70, 640, 920, "QUERY FLOW", NET, "#0d1526", PANEL_EDGE),
    (720, 70, 520, 975, "DOCUMENT INGESTION", EVENT, "#0d1526", PANEL_EDGE),
    (1290, 300, 330, 420, "FAILURE PATH", FAIL, "#160d14", "#3d2430"),
    (1290, 790, 330, 170, "SUPPORTING", SUPPORT, "#0d1526", PANEL_EDGE),
]
GUTTER_A = 600  # right-hand return lane inside the query panel


# ------------------------------------------------------------------ model
nodes: dict[str, Node] = {}
QUERY: list[Edge] = []
INGEST: list[Edge] = []
FAILURE: list[Edge] = []


def node(*args, **kw):
    n = Node(*args, **kw)
    nodes[n.id] = n
    return n


# --- panel A: query path -------------------------------------------------
AX = 340
node("user", ["USER", "Browser"], AX, 138, w=230, color=ACTOR)
node("alb", ["Application Load Balancer", ":80"], AX, 268, w=310, color=NET)
node("ecs", ["ECS Fargate", "FastAPI  ·  RAG application"], AX, 400, w=330, h=76, color=COMPUTE)
node("titan_q", ["Titan Embed v2", "question -> vector"], 235, 560, w=200, h=64, color=MODEL)
node("os_q", ["OpenSearch", "vector search"], 445, 560, w=200, h=64, color=STORE)
node("chunks", ["Relevant chunks"], AX, 690, w=250, h=52, color=MUTED)
node("nova", ["Bedrock Nova", "generation"], AX, 806, w=260, color=MODEL)
node("answer", ["Answer + citations"], AX, 922, w=260, h=52, color=MODEL)

QUERY += [
    Edge("user", "alb", "POST /query"),
    Edge("alb", "ecs"),
    Edge("ecs", "titan_q", kind="split"),
    Edge("ecs", "os_q", kind="split"),
    Edge("titan_q", "chunks", kind="merge"),
    Edge("os_q", "chunks", kind="merge"),
    Edge("chunks", "nova", "context"),
    Edge("nova", "answer"),
    Edge("answer", "alb", "answer + citations", kind="elbow", gutter=GUTTER_A),
    Edge("alb", "user", "200 OK", kind="elbow", gutter=GUTTER_A),
]

# --- panel B: ingestion --------------------------------------------------
BX = 980
node("doc", ["Document", ".txt  ·  .md  ·  .pdf"], BX, 138, w=250, h=58, color=ACTOR)
node("s3", ["S3", "uploads/"], BX, 262, w=230, color=STORE)
node("lambda", ["Lambda ingest"], BX, 396, w=250, color=EVENT)
node("read", ["Read S3 object"], BX, 508, w=220, h=44, color=MUTED)
node("extract", ["Extract text"], BX, 584, w=220, h=44, color=MUTED)
node("chunking", ["Chunking"], BX, 660, w=220, h=44, color=MUTED)
node("titan_i", ["Titan Embed v2"], BX, 756, w=240, h=58, color=MODEL)
node("os_i", ["OpenSearch"], BX, 876, w=240, h=58, color=STORE)
node("indexed", ["Indexed chunks"], BX, 980, w=240, h=46, color=STORE)

INGEST += [
    Edge("doc", "s3", "upload"),
    Edge("s3", "lambda", "ObjectCreated"),
    Edge("lambda", "read"),
    Edge("read", "extract"),
    Edge("extract", "chunking"),
    Edge("chunking", "titan_i"),
    Edge("titan_i", "os_i", "embeddings"),
    Edge("os_i", "indexed"),
]

# --- panel C: failure path ----------------------------------------------
# Sits beside the Lambda it belongs to, so the "on error" branch is one short
# horizontal hop instead of a line dragged across the whole canvas.
CX = 1455
node("retry", ["Lambda retry"], CX, 396, w=220, h=52, color=FAIL)
node("dlq", ["SQS dead letter", "queue"], CX, 520, w=220, h=58, color=FAIL)
node("invest", ["Investigation /", "reprocessing"], CX, 640, w=220, h=58, color=FAIL)

FAILURE += [
    Edge("lambda", "retry", "on error", kind="h", dashed=True, color=FAIL),
    Edge("retry", "dlq", "still fails", color=FAIL),
    Edge("dlq", "invest", color=FAIL),
]

SUPPORTING = [
    ("ECR", "container images"),
    ("Secrets Manager", "API secrets"),
    ("IAM roles", "permissions"),
    ("CloudWatch", "logs"),
]


# ------------------------------------------------------------------ paths
Pt = tuple[float, float]


def _quad(p0: Pt, p1: Pt, p2: Pt, steps: int = 14) -> list[Pt]:
    """Sample a quadratic bezier so SVG and Pillow trace the same curve."""
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append(
            (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
             u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])
        )
    return out


def edge_points(e: Edge) -> list[Pt]:
    """Every edge is a polyline; curves are pre-sampled. One geometry feeding
    two renderers, so the GIF cannot disagree with the SVG."""
    a, b = nodes[e.a], nodes[e.b]
    if e.kind == "v":
        return [a.bottom, b.top]
    if e.kind == "h":
        return [a.right, b.left]
    if e.kind in ("split", "merge"):
        x1, y1 = a.bottom
        x2, y2 = b.top
        if abs(x2 - x1) < 4:
            return [(x1, y1), (x2, y2)]
        my = (y1 + y2) / 2
        pts = [(x1, y1), (x1, my)]
        pts += _quad((x1, my), (x1, y2), (x2, y2))
        return pts
    if e.kind == "elbow":
        gut = e.gutter or (max(a.right[0], b.right[0]) + 78)
        return [a.right, (gut, a.cy), (gut, b.cy), b.right]
    raise ValueError(e.kind)


def edge_path(e: Edge) -> str:
    pts = edge_points(e)
    return f"M {pts[0][0]:.1f} {pts[0][1]:.1f}" + "".join(
        f" L {x:.1f} {y:.1f}" for x, y in pts[1:]
    )


def polyline_len(pts: list[Pt]) -> float:
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) or 1.0


def point_at(pts: list[Pt], frac: float) -> Pt:
    """Position a fraction along a polyline, measured by arc length."""
    total = polyline_len(pts)
    want = max(0.0, min(1.0, frac)) * total
    run = 0.0
    for i in range(len(pts) - 1):
        seg = math.dist(pts[i], pts[i + 1])
        if run + seg >= want:
            t = (want - run) / seg if seg else 0.0
            return (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t,
                    pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t)
        run += seg
    return pts[-1]


# ------------------------------------------------------------------- SVG
def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_node(n: Node, active_times: str | None) -> str:
    x, y = n.cx - n.w / 2, n.cy - n.h / 2
    rx = min(14, n.h / 2)
    out = [f'<g class="node">']
    out.append(
        f'<rect x="{x}" y="{y}" width="{n.w}" height="{n.h}" rx="{rx}" '
        f'fill="{PANEL}" stroke="{n.color}" stroke-width="1.6" opacity="0.98"/>'
    )
    # the ring that lights up as the wave arrives
    if active_times:
        out.append(
            f'<rect x="{x - 5}" y="{y - 5}" width="{n.w + 10}" height="{n.h + 10}" rx="{rx + 5}" '
            f'fill="none" stroke="{n.color}" stroke-width="2.4" opacity="0" filter="url(#glow)">'
            f"{active_times}</rect>"
        )
    n_lines = len(n.lines)
    for i, line in enumerate(n.lines):
        dy = n.cy + (i - (n_lines - 1) / 2) * 19 + 6
        weight = "600" if i == 0 else "400"
        size = 15 if i == 0 else 12.5
        fill = TEXT if i == 0 else MUTED
        out.append(
            f'<text x="{n.cx}" y="{dy}" text-anchor="middle" font-family="Segoe UI,Inter,sans-serif" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}">{esc(line)}</text>'
        )
    out.append("</g>")
    return "".join(out)


def key_window(slot_start: float, slot_end: float) -> tuple[str, str]:
    """keyTimes/values for a comet that waits, travels its slot, then hides."""
    s = max(0.0, min(1.0, slot_start))
    e = max(0.0, min(1.0, slot_end))
    if e <= s:
        e = min(1.0, s + 0.01)
    key_times = f"0;{s:.4f};{e:.4f};1"
    key_points = "0;0;1;1"
    return key_times, key_points


def build_svg() -> str:
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Segoe UI,Inter,sans-serif">'
    )
    parts.append(
        "<defs>"
        '<filter id="glow" x="-60%" y="-60%" width="220%" height="220%">'
        '<feGaussianBlur stdDeviation="5" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        "</filter>"
        '<filter id="soft" x="-60%" y="-60%" width="220%" height="220%">'
        '<feGaussianBlur stdDeviation="2.4"/>'
        "</filter>"
        f'<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{WIRE}"/></marker>'
        f'<marker id="arrowfail" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{FAIL}"/></marker>'
        "<style><![CDATA["
        "  .wire{fill:none;stroke-width:2;}"
        "  .march{fill:none;stroke-width:2.2;stroke-linecap:round;"
        "         animation:march 1.1s linear infinite;}"
        "  @keyframes march{to{stroke-dashoffset:-16;}}"
        "  .title{font-size:19px;font-weight:700;letter-spacing:.14em;}"
        "  .lbl{font-size:12px;}"
        "]]></style>"
        "</defs>"
    )
    parts.append(f'<rect width="{W}" height="{H}" fill="{BG}"/>')

    # panels, from the shared declaration
    for x, y, w, h, title, col, fill, stroke in PANELS:
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="20" fill="{fill}" stroke="{stroke}"/>'
            f'<text x="{x + 20}" y="{y - 18}" class="title" fill="{col}">{esc(title)}</text>'
        )

    node_windows: dict[str, str] = {}

    # edges, one synchronised wave per flow
    for flow in (QUERY, INGEST, FAILURE):
        n = len(flow)
        for i, e in enumerate(flow):
            d = edge_path(e)
            col = e.color or WIRE
            marker = "arrowfail" if e.color == FAIL else "arrow"
            dash = 'stroke-dasharray="7 7"' if e.dashed else 'stroke-dasharray="7 9"'
            parts.append(
                f'<path class="wire" d="{d}" stroke="{col}" opacity="0.55" '
                f'marker-end="url(#{marker})"/>'
            )
            parts.append(f'<path class="march" d="{d}" stroke="{col}" opacity="0.33" {dash}/>')

            s, en = i / n, (i + 0.82) / n
            kt, kp = key_window(s, en)
            fade = f"0;{max(0.0, s - 0.004):.4f};{s:.4f};{en:.4f};{min(1.0, en + 0.02):.4f};1"
            parts.append(
                f'<circle r="6" fill="{col}" filter="url(#glow)" opacity="0">'
                f'<animateMotion dur="{CYCLE}s" repeatCount="indefinite" path="{d}" '
                f'keyTimes="{kt}" keyPoints="{kp}" calcMode="linear"/>'
                f'<animate attributeName="opacity" dur="{CYCLE}s" repeatCount="indefinite" '
                f'values="0;0;1;1;0;0" keyTimes="{fade}"/>'
                f"</circle>"
            )
            # the node the comet lands on lights up for its slot
            a_s, a_e = en, min(1.0, en + 0.14)
            node_windows[e.b] = (
                f'<animate attributeName="opacity" dur="{CYCLE}s" repeatCount="indefinite" '
                f'values="0;0;0.95;0;0" keyTimes="0;{a_s:.4f};{min(1.0, a_s + 0.02):.4f};{a_e:.4f};1"/>'
            )

            if e.label:
                lx, ly = label_pos(e, d)
                parts.append(
                    f'<rect x="{lx - len(e.label) * 3.5 - 8}" y="{ly - 13}" width="{len(e.label) * 7 + 16}" '
                    f'height="19" rx="9" fill="{BG}" opacity="0.92"/>'
                    f'<text x="{lx}" y="{ly}" text-anchor="middle" class="lbl" fill="{MUTED}">{esc(e.label)}</text>'
                )

    for nid, n in nodes.items():
        parts.append(svg_node(n, node_windows.get(nid)))

    for i, (name, sub) in enumerate(SUPPORTING):
        y = 838 + i * 32
        parts.append(
            f'<circle cx="1316" cy="{y - 4}" r="4" fill="{SUPPORT}"/>'
            f'<text x="1330" y="{y}" font-size="13" font-weight="600" fill="{TEXT}">{esc(name)}</text>'
            f'<text x="1450" y="{y}" font-size="12" fill="{MUTED}">{esc(sub)}</text>'
        )

    parts.append(
        f'<text x="{W - 40}" y="{H - 24}" text-anchor="end" font-size="12" fill="{MUTED}">'
        f"Amazon Bedrock + OpenSearch RAG  ·  generated from flow</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def label_pos(e: Edge, d: str = "") -> tuple[float, float]:
    a, b = nodes[e.a], nodes[e.b]
    if e.kind == "h":
        return (a.right[0] + b.left[0]) / 2, a.cy - 12
    if e.kind == "elbow":
        gut = e.gutter or (max(a.right[0], b.right[0]) + 78)
        return gut + 30, (a.cy + b.cy) / 2
    return (a.cx + b.cx) / 2, (a.bottom[1] + b.top[1]) / 2 + 5


def main() -> None:
    svg = build_svg()
    ET.fromstring(svg)  # fails loudly if the markup is malformed
    target = OUT / "06-rag-flow-animated.svg"
    target.write_text(svg, encoding="utf-8")
    print(f"wrote {target.name}  ({len(svg) / 1024:.0f} KB, {len(nodes)} nodes, "
          f"{len(QUERY) + len(INGEST) + len(FAILURE)} edges)")
    render_gif()


# ------------------------------------------------------------------- GIF
GIF_SCALE = 0.62
GIF_FRAMES = 72
GIF_MS = 90


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    for name in (("seguisb.ttf", "segoeuib.ttf") if bold else ("segoeui.ttf",)):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except OSError:
            continue
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _mix(c: str, over: str, amount: float) -> tuple[int, int, int]:
    a, b = _rgb(c), _rgb(over)
    return tuple(int(a[i] + (b[i] - a[i]) * amount) for i in range(3))


def _base_frame(s: float):
    """Everything that does not move, drawn once and reused per frame."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (int(W * s), int(H * s)), _rgb(BG))
    d = ImageDraw.Draw(img)
    f_title = _font(int(17 * s), bold=True)
    f_node = _font(int(15 * s), bold=True)
    f_sub = _font(int(12 * s))
    f_lbl = _font(int(11 * s))

    def box(x, y, w, h, r, fill, outline, width=2):
        d.rounded_rectangle([x * s, y * s, (x + w) * s, (y + h) * s], radius=r * s,
                            fill=fill, outline=outline, width=max(1, int(width * s)))

    for x, y, w, h, title, col, fill, stroke in PANELS:
        box(x, y, w, h, 20, _rgb(fill), _rgb(stroke), 1)
        d.text(((x + 20) * s, (y - 32) * s), title, font=f_title, fill=_rgb(col))

    # wires
    for flow in (QUERY, INGEST, FAILURE):
        for e in flow:
            pts = [(x * s, y * s) for x, y in edge_points(e)]
            col = _mix(BG, e.color or WIRE, 0.75)
            d.line(pts, fill=col, width=max(1, int(2 * s)))
            # arrow head
            (x1, y1), (x2, y2) = pts[-2], pts[-1]
            ang = math.atan2(y2 - y1, x2 - x1)
            for sign in (1, -1):
                d.line([(x2, y2),
                        (x2 - 9 * s * math.cos(ang - sign * 0.45),
                         y2 - 9 * s * math.sin(ang - sign * 0.45))],
                       fill=col, width=max(1, int(2 * s)))

    # edge labels
    for flow in (QUERY, INGEST, FAILURE):
        for e in flow:
            if not e.label:
                continue
            lx, ly = label_pos(e, "")
            tw = d.textlength(e.label, font=f_lbl)
            d.rounded_rectangle(
                [lx * s - tw / 2 - 6 * s, (ly - 13) * s, lx * s + tw / 2 + 6 * s, (ly + 4) * s],
                radius=8 * s, fill=_rgb(BG))
            d.text((lx * s - tw / 2, (ly - 12) * s), e.label, font=f_lbl, fill=_rgb(MUTED))

    # nodes
    for n in nodes.values():
        box(n.cx - n.w / 2, n.cy - n.h / 2, n.w, n.h, min(14, n.h / 2), _rgb(PANEL), _rgb(n.color), 1.6)
        for i, line in enumerate(n.lines):
            font = f_node if i == 0 else f_sub
            fill = _rgb(TEXT) if i == 0 else _rgb(MUTED)
            tw = d.textlength(line, font=font)
            dy = n.cy + (i - (len(n.lines) - 1) / 2) * 19 - 8
            d.text((n.cx * s - tw / 2, dy * s), line, font=font, fill=fill)

    for i, (name, sub) in enumerate(SUPPORTING):
        y = 830 + i * 32
        d.ellipse([1312 * s, (y + 2) * s, 1320 * s, (y + 10) * s], fill=_rgb(SUPPORT))
        d.text((1330 * s, y * s), name, font=_font(int(13 * s), bold=True), fill=_rgb(TEXT))
        d.text((1450 * s, y * s), sub, font=f_sub, fill=_rgb(MUTED))

    return img


def render_gif() -> None:
    from PIL import Image, ImageDraw

    s = GIF_SCALE
    base = _base_frame(s)
    frames = []

    # precompute geometry and each edge's slot inside the cycle
    timed = []
    for flow in (QUERY, INGEST, FAILURE):
        n = len(flow)
        for i, e in enumerate(flow):
            timed.append((e, [(x * s, y * s) for x, y in edge_points(e)], i / n, (i + 0.82) / n))

    for fi in range(GIF_FRAMES):
        t = fi / GIF_FRAMES
        img = base.copy()
        d = ImageDraw.Draw(img)
        for e, pts, t0, t1 in timed:
            if not (t0 <= t <= t1):
                continue
            frac = (t - t0) / (t1 - t0)
            col = _rgb(e.color or "#7fb2ff")
            # a trailing comet: fading dots behind the head
            for k, (back, rad) in enumerate(((0.0, 6.0), (0.035, 4.2), (0.07, 2.8))):
                fp = max(0.0, frac - back)
                x, y = point_at(pts, fp)
                r = rad * s
                fade = 1.0 - k * 0.3
                d.ellipse([x - r, y - r, x + r, y + r],
                          fill=_mix(BG, "#ffffff" if k == 0 else f"#{col[0]:02x}{col[1]:02x}{col[2]:02x}", fade))
            # light the destination node as the comet lands
            if frac > 0.82:
                n = nodes[e.b]
                glow = _mix(PANEL, e.color or NET, 0.55)
                d.rounded_rectangle(
                    [(n.cx - n.w / 2 - 4) * s, (n.cy - n.h / 2 - 4) * s,
                     (n.cx + n.w / 2 + 4) * s, (n.cy + n.h / 2 + 4) * s],
                    radius=(min(14, n.h / 2) + 4) * s, outline=glow, width=max(2, int(2.6 * s)))
        frames.append(img.convert("P", palette=Image.ADAPTIVE, colors=128))

    target = OUT / "06-rag-flow-animated.gif"
    frames[0].save(target, save_all=True, append_images=frames[1:], loop=0,
                   duration=GIF_MS, optimize=True, disposal=2)
    kb = target.stat().st_size / 1024
    print(f"wrote {target.name}  ({kb:.0f} KB, {GIF_FRAMES} frames, "
          f"{base.width}x{base.height}, {GIF_FRAMES * GIF_MS / 1000:.1f}s loop)")
    _base_frame(s).save(OUT / "06-rag-flow-still.png")
    print("wrote 06-rag-flow-still.png  (static reference frame)")


if __name__ == "__main__":
    main()
