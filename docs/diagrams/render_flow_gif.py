"""Cinematic end-to-end animation of the RAG system.

Renders a narrated walkthrough rather than a diagram with dots on it. The whole
point is that ingestion and querying share the same two components, so the
diagram has one Titan Embed and one OpenSearch that both flows pass through:
ingestion fills the index, the query reads it back.

    Act 1  ingestion   document -> S3 -> Lambda -> chunks -> embed -> index
    Act 2  query       user -> ALB -> FastAPI -> embed -> k-NN -> Nova -> answer
    Act 3  failure     repeated ingest failures land in the DLQ

Everything starts dim and stays lit once visited, so the final frame is the
complete picture. Glow is a real gaussian blur composited additively, which is
what stops it looking like clip art.

    python docs/diagrams/render_flow_gif.py
"""

from __future__ import annotations

import math
import pathlib

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

OUT = pathlib.Path(__file__).parent
W, H = 1280, 900
SCALE = 0.72
HOLD = 8           # frames per story step
FINALE_EXTRA = 14  # the finished picture holds a little longer
FRAME_MS = 70
CAP_TOP = H - 108

BG = (8, 13, 26)
PANEL = (17, 27, 46)
GRID = (16, 25, 44)
TEXT = (232, 238, 252)
DIM_TEXT = (96, 112, 145)
MUTED = (143, 163, 200)

ORANGE = (245, 166, 62)
BLUE = (86, 148, 255)
GREEN = (72, 200, 130)
PURPLE = (176, 110, 255)
RED = (235, 92, 100)
CYAN = (86, 220, 235)


def font(size: int, weight: str = "r"):
    files = {"r": "segoeui.ttf", "b": "seguisb.ttf", "k": "seguibl.ttf"}
    try:
        return ImageFont.truetype(f"C:/Windows/Fonts/{files[weight]}", size)
    except OSError:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()


F_NODE = font(17, "b")
F_SUB = font(13)
F_EDGE = font(12)
F_CAP = font(23, "b")
F_CAP2 = font(15)
F_STEP = font(13, "b")
F_PHASE = font(15, "k")
F_TITLE = font(16, "b")


class N:
    def __init__(self, nid, title, sub, x, y, w, h, color, icon=None):
        self.id, self.title, self.sub = nid, title, sub
        self.x, self.y, self.w, self.h = x, y, w, h
        self.color, self.icon = color, icon

    @property
    def box(self):
        return [self.x - self.w / 2, self.y - self.h / 2,
                self.x + self.w / 2, self.y + self.h / 2]

    def port(self, side):
        return {
            "t": (self.x, self.y - self.h / 2),
            "b": (self.x, self.y + self.h / 2),
            "l": (self.x - self.w / 2, self.y),
            "r": (self.x + self.w / 2, self.y),
        }[side]


# --------------------------------------------------------------- the diagram
NODES: dict[str, N] = {}


def node(*a, **k):
    n = N(*a, **k)
    NODES[n.id] = n
    return n


# ingestion column (left)
node("doc", "Document", ".txt  .md  .pdf", 190, 130, 210, 60, PURPLE)
node("s3", "S3", "uploads/", 190, 246, 210, 60, GREEN)
node("lambda", "Lambda ingest", "read + extract", 190, 372, 230, 64, ORANGE)
node("chunk", "Chunking", "1000 chars, 150 overlap", 190, 500, 250, 60, CYAN)

# shared core (centre) - both flows pass through these
node("titan", "Titan Embed v2", "1024-dim vectors", 640, 560, 250, 66, ORANGE)
node("os", "OpenSearch", "k-NN vector index", 640, 692, 250, 66, GREEN)

# query column (right)
node("user", "USER", "browser", 1090, 130, 200, 60, PURPLE)
node("alb", "Load balancer", ":80", 1090, 246, 220, 60, BLUE)
node("ecs", "ECS Fargate", "FastAPI  /query", 1090, 372, 230, 64, BLUE)
node("nova", "Bedrock Nova", "grounded answer", 1090, 560, 230, 64, ORANGE)

# failure - sits to the right of the Lambda so the branch is one clean hop
node("dlq", "SQS dead letter queue", "investigate + replay", 600, 372, 250, 58, RED)


def route(a: str, b: str, kind: str) -> list[tuple[float, float]]:
    """Polyline for an edge. Curves are pre-sampled so the comet can ride them."""
    A, B = NODES[a], NODES[b]
    if kind == "v":
        return [A.port("b"), B.port("t")]
    if kind == "h":
        return [A.port("r"), B.port("l")]
    if kind == "hl":
        return [A.port("l"), B.port("r")]
    if kind in ("dr", "dl"):
        # smooth diagonal: down out of A, bezier across, into the top of B
        p0 = A.port("b")
        p2 = B.port("t")
        c = (p0[0], (p0[1] + p2[1]) / 2 + 30)
        pts = [p0]
        for i in range(1, 19):
            t = i / 18
            u = 1 - t
            pts.append((u * u * p0[0] + 2 * u * t * c[0] + t * t * p2[0],
                        u * u * p0[1] + 2 * u * t * c[1] + t * t * p2[1]))
        return pts
    if kind == "up":
        # right-hand return lane, well clear of the node column
        g = 1240
        p0 = B.port("r")
        return [A.port("r"), (g, A.y), (g, B.y), p0]
    raise ValueError(kind)


class Step:
    def __init__(self, a, b, kind, edge_label, phase, caption, detail,
                 flourish=None, finale=False):
        self.a, self.b, self.kind = a, b, kind
        self.edge_label = edge_label
        self.phase, self.caption, self.detail = phase, caption, detail
        self.flourish, self.finale = flourish, finale
        self.pts = [] if finale else route(a, b, kind)


ING, QRY, FAIL = ("INGESTION", ORANGE), ("QUERY", BLUE), ("FAILURE PATH", RED)
DONE = ("END TO END", GREEN)

STORY = [
    Step("doc", "s3", "v", "upload", ING,
         "A document is uploaded",
         "Any .txt, .md or .pdf dropped under uploads/ in the documents bucket."),
    Step("s3", "lambda", "v", "ObjectCreated", ING,
         "S3 fires an event",
         "The ObjectCreated notification invokes the ingest Lambda once per object."),
    Step("lambda", "chunk", "v", "text", ING,
         "Text is extracted",
         "pypdf for PDFs, straight UTF-8 decode for text and markdown."),
    Step("chunk", "titan", "dr", "chunks", ING,
         "Split into overlapping chunks",
         "1000 characters with 150 of overlap, so a sentence is never cut in half.",
         flourish="chunks"),
    Step("titan", "os", "v", "vectors", ING,
         "Embedded and indexed",
         "Each chunk becomes a 1024-dim vector, written with a deterministic id.",
         flourish="index"),
    Step("user", "alb", "v", "POST /query", QRY,
         "A question arrives",
         "The browser posts a question to the public load balancer."),
    Step("alb", "ecs", "v", "forward", QRY,
         "Routed to the API",
         "The ALB forwards to the FastAPI task running on ECS Fargate."),
    Step("ecs", "titan", "dl", "question", QRY,
         "The question is embedded",
         "Same model as ingestion, so question and chunks share one vector space."),
    Step("titan", "os", "v", "k-NN", QRY,
         "Nearest chunks retrieved",
         "Hybrid search: vector k-NN fused with keyword matching by RRF.",
         flourish="search"),
    Step("os", "nova", "h", "top chunks", QRY,
         "Context is assembled",
         "Highest scoring passages are numbered and passed as grounded context."),
    Step("nova", "user", "up", "answer + citations", QRY,
         "The answer comes back",
         "Nova answers only from the retrieved context, citing each passage."),
    Step("lambda", "dlq", "h", "on repeated error", FAIL,
         "Failures are not lost",
         "After Lambda exhausts its retries the event lands in the dead letter queue."),
    Step(None, None, None, None, DONE,
         "Documents in, cited answers out",
         "One embedding model and one index serve both halves of the system.",
         finale=True),
]


# ------------------------------------------------------------------ drawing
def rr(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def blend(c, t, f):
    return tuple(int(c[i] + (t[i] - c[i]) * f) for i in range(3))


def draw_node(d, n: N, level: str, glow: ImageDraw.ImageDraw | None = None):
    """level: dim (not reached), lit (visited), hot (active this step)."""
    if level == "dim":
        fill, out, w = PANEL, blend(PANEL, n.color, 0.28), 1
        tc, sc = DIM_TEXT, (70, 84, 112)
    elif level == "lit":
        fill, out, w = blend(PANEL, n.color, 0.10), blend(PANEL, n.color, 0.8), 2
        tc, sc = TEXT, MUTED
    else:
        fill, out, w = blend(PANEL, n.color, 0.22), n.color, 3
        tc, sc = (255, 255, 255), blend(MUTED, n.color, 0.6)

    rr(d, n.box, 14, fill=fill, outline=out, width=w)
    d.text((n.x, n.y - (9 if n.sub else 0)), n.title, font=F_NODE, fill=tc, anchor="mm")
    if n.sub:
        d.text((n.x, n.y + 12), n.sub, font=F_SUB, fill=sc, anchor="mm")

    if level == "hot" and glow is not None:
        b = n.box
        rr(glow, [b[0] - 3, b[1] - 3, b[2] + 3, b[3] + 3], 17, outline=n.color, width=4)


def draw_wire(d, pts, color, width, dash=None):
    if dash is None:
        d.line(pts, fill=color, width=width, joint="curve")
        return
    on, off, phase = dash
    total = 0.0
    for i in range(len(pts) - 1):
        seg = math.dist(pts[i], pts[i + 1])
        steps = max(1, int(seg / 3))
        for s in range(steps):
            t0, t1 = s / steps, (s + 1) / steps
            if ((total + seg * t0 + phase) % (on + off)) < on:
                p0 = (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t0,
                      pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t0)
                p1 = (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t1,
                      pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t1)
                d.line([p0, p1], fill=color, width=width)
        total += seg


def arrow(d, pts, color, size=9, width=3):
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    a = math.atan2(y2 - y1, x2 - x1)
    for s in (1, -1):
        d.line([(x2, y2), (x2 - size * math.cos(a - s * 0.42),
                          y2 - size * math.sin(a - s * 0.42))], fill=color, width=width)


def plen(pts):
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) or 1.0


def walk(pts, frac):
    """Point at `frac` along the polyline, plus the prefix up to there."""
    want = max(0.0, min(1.0, frac)) * plen(pts)
    run, out = 0.0, [pts[0]]
    for i in range(len(pts) - 1):
        seg = math.dist(pts[i], pts[i + 1])
        if run + seg >= want:
            t = (want - run) / seg if seg else 0.0
            p = (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t,
                 pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t)
            out.append(p)
            return p, out
        out.append(pts[i + 1])
        run += seg
    return pts[-1], list(pts)


def edge_label_xy(st: Step):
    pts = st.pts
    if st.kind in ("v",):
        a, b = NODES[st.a], NODES[st.b]
        return (a.x + 16, (a.port("b")[1] + b.port("t")[1]) / 2), "lm"
    if st.kind == "h":
        return ((pts[0][0] + pts[-1][0]) / 2, pts[0][1] - 12), "mm"
    if st.kind == "hl":
        return ((pts[0][0] + pts[-1][0]) / 2, pts[0][1] - 12), "mm"
    if st.kind == "up":
        return (1240 - 10, (pts[0][1] + pts[-1][1]) / 2), "rm"
    mid = pts[len(pts) // 2]
    return (mid[0] + 10, mid[1] - 6), "lm"


def background():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for x in range(0, W, 80):
        d.line([(x, 0), (x, CAP_TOP)], fill=GRID)
    for y in range(0, CAP_TOP, 80):
        d.line([(0, y), (W, y)], fill=GRID)
    d.text((34, 26), "Amazon Bedrock  +  OpenSearch    RAG on AWS", font=F_TITLE, fill=MUTED)
    d.text((W - 34, 26), "end to end", font=F_SUB, fill=(74, 92, 124), anchor="ra")
    d.line([(34, 52), (W - 34, 52)], fill=(30, 44, 74))
    # shared-core callout, the point of the whole diagram
    rr(d, [488, 508, 792, 740], 20, outline=(34, 50, 82), width=1)
    d.text((640, 496), "SHARED BY BOTH FLOWS", font=F_STEP, fill=(78, 100, 138), anchor="mm")
    return img


def caption_bar(d, st: Step, i: int, prog: float):
    top = CAP_TOP
    d.rectangle([0, top, W, H], fill=(11, 17, 32))
    d.line([(0, top), (W, top)], fill=(30, 44, 74))

    name, col = st.phase
    tw = d.textlength(name, font=F_PHASE)
    rr(d, [34, top + 24, 34 + tw + 26, top + 50], 13, fill=blend(BG, col, 0.22), outline=col, width=1)
    d.text((34 + 13 + tw / 2, top + 37), name, font=F_PHASE, fill=col, anchor="mm")

    d.text((34, top + 62), f"STEP {i + 1} OF {len(STORY)}", font=F_STEP, fill=(84, 102, 138))
    x = 34 + tw + 56
    d.text((x, top + 30), st.caption, font=F_CAP, fill=TEXT)
    d.text((x, top + 62), st.detail, font=F_CAP2, fill=MUTED)

    # progress
    bar = [34, top + 12, W - 34, top + 15]
    d.rectangle(bar, fill=(28, 40, 66))
    d.rectangle([34, top + 12, 34 + (W - 68) * prog, top + 15], fill=col)


def flourish(d, glow, kind, f):
    """Small visual asides that make each stage legible at a glance."""
    if kind == "chunks":
        n = NODES["chunk"]
        for k in range(6):
            if f > k / 7:
                x = n.x + n.w / 2 + 22 + k * 17
                a = min(1.0, (f - k / 7) * 5)
                s = 6
                d.rectangle([x, n.y - s, x + s * 1.6, n.y + s], fill=blend(BG, CYAN, 0.35 + 0.5 * a))
    elif kind == "index":
        n = NODES["os"]
        for k in range(9):
            ang = -math.pi / 2 + (k - 4) * 0.30
            r = 52 + 46 * min(1.0, f * 1.25)
            x, y = n.x + math.cos(ang) * r * 1.5, n.y + math.sin(ang) * r * 0.55
            d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=blend(BG, GREEN, 0.9))
    elif kind == "search":
        n = NODES["os"]
        for k in range(3):
            r = (f * 1.3 + k * 0.33) % 1.0
            rad = 24 + r * 120
            col = blend(BG, CYAN, max(0.0, 0.75 * (1 - r)))
            glow.ellipse([n.x - rad * 1.5, n.y - rad * 0.55,
                          n.x + rad * 1.5, n.y + rad * 0.55], outline=col, width=2)


def render():
    base = background()
    frames: list[Image.Image] = []
    total = len(STORY) * HOLD + FINALE_EXTRA

    for i, st in enumerate(STORY):
        for h in range(HOLD + (FINALE_EXTRA if st.finale else 0)):
            span = HOLD + (FINALE_EXTRA if st.finale else 0)
            f = (h + 1) / span                      # progress through this step
            img = base.copy()
            d = ImageDraw.Draw(img)
            gl = Image.new("RGB", (W, H), (0, 0, 0))
            g = ImageDraw.Draw(gl)

            visited = set()
            for p in STORY[:i]:
                if not p.finale:
                    visited.add(p.a)
                    visited.add(p.b)
            if not st.finale:
                visited.add(st.a)

            # wires: done ones stay lit, future ones sit dim
            for j, p in enumerate(STORY):
                if p.finale:
                    continue
                col = p.phase[1]
                if j < i or st.finale:
                    draw_wire(d, p.pts, blend(BG, col, 0.5), 2)
                    arrow(d, p.pts, blend(BG, col, 0.55), width=2)
                elif j > i:
                    draw_wire(d, p.pts, blend(BG, col, 0.16), 2)

            if st.finale:
                # everything lit, the shared core breathing
                for n in NODES.values():
                    draw_node(d, n, "lit")
                pulse = 0.5 + 0.5 * math.sin(f * math.pi * 2)
                for nid in ("titan", "os"):
                    n = NODES[nid]
                    b = n.box
                    rr(g, [b[0] - 3, b[1] - 3, b[2] + 3, b[3] + 3], 17,
                       outline=blend((0, 0, 0), n.color, 0.35 + 0.65 * pulse), width=4)
            else:
                # the active wire fills in behind the comet
                col = st.phase[1]
                head, prefix = walk(st.pts, f)
                draw_wire(d, st.pts, blend(BG, col, 0.2), 2)
                if len(prefix) > 1:
                    draw_wire(d, prefix, col, 3)
                    draw_wire(g, prefix, col, 3)
                draw_wire(d, st.pts, blend(BG, col, 0.42), 1, dash=(7, 11, -i * 6 - h * 7))

                for nid, n in NODES.items():
                    if nid == st.b and f > 0.72:
                        draw_node(d, n, "hot", g)
                    elif nid == st.a:
                        draw_node(d, n, "hot", g)
                    elif nid in visited:
                        draw_node(d, n, "lit")
                    else:
                        draw_node(d, n, "dim")

                # comet with a fading tail
                for k, (back, rad) in enumerate(((0.0, 8.0), (0.045, 5.5), (0.09, 3.4), (0.14, 2.0))):
                    p, _ = walk(st.pts, max(0.0, f - back))
                    c = (255, 255, 255) if k == 0 else col
                    a = 1.0 - k * 0.22
                    d.ellipse([p[0] - rad, p[1] - rad, p[0] + rad, p[1] + rad], fill=blend(BG, c, a))
                    g.ellipse([p[0] - rad * 1.4, p[1] - rad * 1.4,
                               p[0] + rad * 1.4, p[1] + rad * 1.4],
                              fill=blend((0, 0, 0), c, a * 0.8))

                if st.flourish:
                    flourish(d, g, st.flourish, f)

                if st.edge_label:
                    (lx, ly), anc = edge_label_xy(st)
                    d.text((lx, ly), st.edge_label, font=F_EDGE,
                           fill=blend(MUTED, col, 0.5), anchor=anc)

                arrow(d, st.pts, col, size=10, width=3)

            caption_bar(d, st, i, min(1.0, (i * HOLD + h + 1) / total))

            img = ImageChops.add(img, gl.filter(ImageFilter.GaussianBlur(9)))
            if SCALE != 1.0:
                img = img.resize((int(W * SCALE), int(H * SCALE)), Image.LANCZOS)
            frames.append(img)

    # GIF for universal support, WebP because a 256-colour palette cannot hold
    # smooth glow gradients: same frames, a fraction of the size, no banding.
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=96) for f in frames]
    gif = OUT / "07-rag-end-to-end.gif"
    pal[0].save(gif, save_all=True, append_images=pal[1:], loop=0,
                duration=FRAME_MS, optimize=True, disposal=2)

    webp = OUT / "07-rag-end-to-end.webp"
    frames[0].save(webp, format="WEBP", save_all=True, append_images=frames[1:],
                   duration=FRAME_MS, loop=0, quality=82, method=4)

    frames[len(frames) // 2].save(OUT / "07-rag-end-to-end-frame.png")
    for name, p in (("gif", gif), ("webp", webp)):
        mb = p.stat().st_size / 1024 / 1024
        print(f"wrote {p.name:28} {mb:5.1f} MB  ({name})")
    print(f"       {len(frames)} frames, {frames[0].width}x{frames[0].height}, "
          f"{len(frames) * FRAME_MS / 1000:.1f}s, {len(STORY)} narrated steps")


if __name__ == "__main__":
    render()
