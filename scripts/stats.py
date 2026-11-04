"""Builds themed stats SVGs for the profile README from the GitHub GraphQL API.

Runs in GitHub Actions (GITHUB_TOKEN is enough for public data). Set MOCK=1 to render with sample data.
"""
import datetime as dt
import html
import json
import math
import os
import random
import urllib.request

USER = os.environ.get("GH_USER", "shrenixcodes")
OUT = os.environ.get("OUT_DIR", "assets")

BG, INK, SIL, DIM = "#050507", "#f2f4fa", "#b8c2dc", "#5c6175"
RED, ICE, PERI, COB = "#ff2a2a", "#99ccff", "#6699ff", "#2424d9"
FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono','Liberation Mono',monospace"
e = html.escape

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    name login createdAt
    followers { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      nodes { stargazerCount forkCount primaryLanguage { name } languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
    }
    repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, ISSUE]) { totalCount }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions totalPullRequestContributions totalIssueContributions
      restrictedContributionsCount
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
  }
}"""


def fetch():
    if os.environ.get("MOCK"):
        rnd = random.Random(4)
        today = dt.date.today()
        days = [{"date": str(today - dt.timedelta(days=i)), "contributionCount": max(0, int(rnd.gauss(4, 4)))} for i in range(365)][::-1]
        return {
            "stars": 12, "forks": 3, "repos": 32, "followers": 18, "contributed": 4,
            "commits": 1203, "prs": 41, "issues": 9, "private": 220, "total": 1567,
            "langs": [("Python", 61), ("TypeScript", 18), ("JavaScript", 6), ("Kotlin", 5), ("Rust", 4), ("Java", 3), ("Lua", 2), ("CSS", 1)],
            "days": days,
        }
    to = dt.datetime.now(dt.timezone.utc)
    frm = to - dt.timedelta(days=365)
    body = json.dumps({"query": QUERY, "variables": {"login": USER, "from": frm.isoformat(), "to": to.isoformat()}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": f"bearer {os.environ['GITHUB_TOKEN']}", "Content-Type": "application/json", "User-Agent": "profile-stats"})
    data = json.load(urllib.request.urlopen(req, timeout=30))
    if "errors" in data:
        raise SystemExit(data["errors"])
    u = data["data"]["user"]
    repos = u["repositories"]["nodes"]
    # count each repo's main language (byte counts get skewed by vendored libraries)
    IGNORE = {"NASL", "Cython", "Makefile", "Batchfile", "PowerShell", "Dockerfile", "Procfile", "Smarty", "Roff"}
    RENAME = {"Jupyter Notebook": "Python"}
    sizes = {}
    for r in repos:
        lang = (r.get("primaryLanguage") or {}).get("name")
        if lang in IGNORE or not lang:
            edges = [ed for ed in r["languages"]["edges"] if ed["node"]["name"] not in IGNORE]
            lang = edges[0]["node"]["name"] if edges else None
        if lang:
            lang = RENAME.get(lang, lang)
            sizes[lang] = sizes.get(lang, 0) + 1
    tot = sum(sizes.values()) or 1
    langs = sorted(((k, 100 * v / tot) for k, v in sizes.items()), key=lambda x: -x[1])[:8]
    cc = u["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    return {
        "stars": sum(r["stargazerCount"] for r in repos), "forks": sum(r["forkCount"] for r in repos),
        "repos": u["repositories"]["totalCount"], "followers": u["followers"]["totalCount"],
        "contributed": u["repositoriesContributedTo"]["totalCount"],
        "commits": cc["totalCommitContributions"], "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"], "private": cc["restrictedContributionsCount"],
        "total": cc["contributionCalendar"]["totalContributions"], "langs": langs, "days": days,
    }


# ---------------------------------------------------------------- shared look
def star(cx, cy, r, fill=RED, glow=False, cls=""):
    rh = r * .72
    d = f"M{cx},{cy-r} Q{cx},{cy} {cx+rh},{cy} Q{cx},{cy} {cx},{cy+r} Q{cx},{cy} {cx-rh},{cy} Q{cx},{cy} {cx},{cy-r}Z"
    return f'<path class="{cls}" d="{d}" fill="{fill}" {"filter=\"url(#glow)\"" if glow else ""}/>'


def frame(W, H, title, body, extra_css=""):
    o = len(title) * 7.2 + 24
    corners = "".join(
        f'<path d="M{x},{y+22*sy} V{y} H{x+22*sx}" fill="none" stroke="{SIL}" stroke-width="1"/>'
        f'<rect x="{x+4*sx-(4 if sx<0 else 0)}" y="{y+4*sy-(4 if sy<0 else 0)}" width="4" height="4" fill="none" stroke="{PERI}" stroke-width=".8"/>'
        for x, y, sx, sy in [(14, 14, 1, 1), (W-14, 14, -1, 1), (14, H-14, 1, -1), (W-14, H-14, -1, -1)])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>text{{font-family:{FONT}}}
.in{{opacity:0;animation:in .45s ease-out both}}@keyframes in{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:none}}}}

{extra_css}</style>
<defs>
<linearGradient id="chrome" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="300" y2="100" spreadMethod="reflect">
<stop offset="0" stop-color="#3b3f63"/><stop offset=".35" stop-color="#f6f8ff"/><stop offset=".5" stop-color="#8fa6ff"/><stop offset=".7" stop-color="#ffffff"/><stop offset="1" stop-color="#4b55a8"/>
</linearGradient>
<linearGradient id="barb" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#99ccff"/><stop offset=".5" stop-color="#2424d9"/><stop offset="1" stop-color="#14148a"/></linearGradient>
<linearGradient id="barc" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset=".45" stop-color="#9aa0aa"/><stop offset=".55" stop-color="#6c717a"/><stop offset="1" stop-color="#d7dbe1"/></linearGradient>
<filter id="glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="3.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<filter id="gr"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" stitchTiles="stitch"/><feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 1.4 -.5"/></filter>
</defs>
<rect width="{W}" height="{H}" rx="12" fill="{BG}"/>
<rect x="10" y="10" width="{W-20}" height="{H-20}" rx="4" fill="none" stroke="{DIM}" stroke-opacity=".45" stroke-width=".8"/>
{corners}
<line x1="{max(34, W/2-o-90)}" y1="36" x2="{W/2-o}" y2="36" stroke="url(#chrome)" stroke-width=".9"/><line x1="{W/2+o}" y1="36" x2="{min(W-34, W/2+o+90)}" y2="36" stroke="url(#chrome)" stroke-width=".9"/>
{star(W/2-o+8, 36, 7, glow=True, cls="rp")}{star(W/2+o-8, 36, 7, glow=True, cls="rp")}
<text x="{W/2}" y="41" font-size="13.5" fill="url(#chrome)" text-anchor="middle" letter-spacing="5" font-weight="bold">{e(title)}</text>
{body}
<rect width="{W}" height="{H}" rx="12" filter="url(#gr)" opacity=".06"/>
</svg>'''


def fmt(n):
    return f"{n/1000:.1f}k" if n >= 10000 else f"{n:,}"


# ---------------------------------------------------------------- cards
def stats_card(s):
    W, H = 440, 220
    rows = [("contributions (1y)", s["total"]), ("commits (1y)", s["commits"]), ("pull requests", s["prs"]),
            ("issues", s["issues"]), ("public repos", s["repos"]), ("stars earned", s["stars"]), ("contributed to", s["contributed"])]
    body = []
    for i, (k, v) in enumerate(rows):
        y = 74 + i * 20
        body.append(f'<g class="in" style="animation-delay:{.15 + i*.1:.2f}s"><text x="36" y="{y}" font-size="12.5" fill="{DIM}">✦</text>'
                    f'<text x="54" y="{y}" font-size="12.5" fill="{SIL}">{e(k)}</text>'
                    f'<text x="270" y="{y}" font-size="13" fill="{INK}" text-anchor="end" font-weight="bold">{fmt(v)}</text></g>')
    # rank ring
    score = s["commits"] + 3 * s["prs"] + 2 * s["issues"] + 4 * s["stars"] + 2 * s["followers"]
    rank = "S+" if score > 3000 else "S" if score > 1500 else "A+" if score > 800 else "A" if score > 400 else "B+"
    pct = min(.97, .35 + score / 4000)
    cx, cy, r = 355, 132, 46
    C = 2 * math.pi * r
    body.append(f'''<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#15161f" stroke-width="7"/>
<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="url(#barb)" stroke-width="7" stroke-linecap="round" stroke-dasharray="{C:.1f}"
 stroke-dashoffset="{C:.1f}" transform="rotate(-90 {cx} {cy})" style="animation:ring 1.6s cubic-bezier(.2,.8,.2,1) .4s forwards"/>
<circle cx="{cx}" cy="{cy}" r="{r+11}" fill="none" stroke="{PERI}" stroke-opacity=".35" stroke-width=".7" stroke-dasharray="2 5"/>
<text x="{cx}" y="{cy+9}" font-size="26" fill="url(#chrome)" text-anchor="middle" font-weight="bold">{rank}</text>
<text x="{cx}" y="{cy+r+28}" font-size="10" fill="{DIM}" text-anchor="middle" letter-spacing="2">rank</text>''')
    css = f"@keyframes ring{{to{{stroke-dashoffset:{C*(1-pct):.1f}}}}}"
    return frame(W, H, "S T A T S", "".join(body), css)


def langs_card(s):
    W, H = 440, 220
    langs = s["langs"][:6]
    body = []
    x, y0 = 36, 62
    total_w = W - 72
    # stacked bar
    cx = x
    for i, (name, p) in enumerate(langs):
        w = total_w * p / sum(q for _, q in langs)
        fill = "url(#barb)" if i == 0 else ("url(#barc)" if i % 2 else PERI)
        body.append(f'<rect class="sb" x="{cx:.1f}" y="{y0}" width="{max(w-2,1):.1f}" height="9" fill="{fill}" style="animation-delay:{.2+i*.12:.2f}s"/>')
        cx += w
    for i, (name, p) in enumerate(langs):
        col, row = i % 2, i // 2
        lx, ly = 40 + col * 190, 104 + row * 34
        bw = 120 * p / langs[0][1]
        body.append(f'''<g class="in" style="animation-delay:{.3+i*.1:.2f}s">
{star(lx, ly-4, 5, fill=RED if i == 0 else PERI)}
<text x="{lx+12}" y="{ly}" font-size="12.5" fill="{INK}">{e(name)}</text>
<text x="{lx+170}" y="{ly}" font-size="11.5" fill="{SIL}" text-anchor="end">{p:.1f}%</text>
<rect x="{lx+12}" y="{ly+7}" width="158" height="3" fill="#15161f"/>
<rect class="lb" x="{lx+12}" y="{ly+7}" width="{bw*158/120:.1f}" height="3" fill="{'url(#barb)' if i == 0 else SIL}" style="animation-delay:{.4+i*.1:.2f}s"/></g>''')
    css = (".sb,.lb{transform-box:fill-box;transform-origin:left;animation:g 1s cubic-bezier(.2,.8,.2,1) both}"
           "@keyframes g{from{transform:scaleX(0)}to{transform:scaleX(1)}}")
    return frame(W, H, "S P E L L B O O K", "".join(body), css)


def activity_card(s):
    W, H = 900, 260
    days = s["days"][-31:]
    vals = [d["contributionCount"] for d in days]
    mx = max(vals + [1])
    x0, x1, y0, y1 = 60, W - 40, 96, H - 50
    step = (x1 - x0) / (len(vals) - 1)
    pts = [(x0 + i * step, y1 - (y1 - y0) * v / mx) for i, v in enumerate(vals)]
    # smooth path (catmull-rom -> bezier)
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[max(i-1, 0)]; p1 = pts[i]; p2 = pts[i+1]; p3 = pts[min(i+2, len(pts)-1)]
        c1 = (p1[0] + (p2[0]-p0[0])/6, min(y1, p1[1] + (p2[1]-p0[1])/6)); c2 = (p2[0] - (p3[0]-p1[0])/6, min(y1, p2[1] - (p3[1]-p1[1])/6))
        if p1[1] >= y1 or p2[1] >= y1:  # keep flat stretches on the baseline
            c1 = (c1[0], max(c1[1], min(p1[1], p2[1]))); c2 = (c2[0], max(c2[1], min(p1[1], p2[1])))
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    area = d + f" L{x1},{y1} L{x0},{y1}Z"
    L = sum(math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]) for i in range(len(pts)-1)) * 1.25
    grid = "".join(f'<line x1="{x0}" y1="{y1-(y1-y0)*k/4:.1f}" x2="{x1}" y2="{y1-(y1-y0)*k/4:.1f}" stroke="{DIM}" stroke-opacity=".25" stroke-dasharray="2 6"/>'
                   f'<text x="{x0-12}" y="{y1-(y1-y0)*k/4+4:.1f}" font-size="10" fill="{DIM}" text-anchor="end">{round(mx*k/4)}</text>' for k in range(5))
    labels = "".join(f'<text x="{pts[i][0]:.1f}" y="{y1+18}" font-size="9.5" fill="{DIM}" text-anchor="middle">{days[i]["date"][8:]}</text>'
                     for i in range(0, len(days), 3))
    best = max(range(len(vals)), key=lambda i: vals[i])
    dots = "".join(f'<circle class="in" cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="{ICE}" style="animation-delay:{1+i*.03:.2f}s"/>' for i, (x, y) in enumerate(pts))
    bx, by = pts[best]
    body = f'''<defs><linearGradient id="ar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{COB}" stop-opacity=".55"/><stop offset="1" stop-color="{COB}" stop-opacity="0"/></linearGradient></defs>
{grid}{labels}
<path d="{area}" fill="url(#ar)" class="in" style="animation-delay:.6s"/>
<path d="{d}" fill="none" stroke="{PERI}" stroke-width="2.2" stroke-dasharray="{L:.0f}" stroke-dashoffset="{L:.0f}" style="animation:draw 2.2s ease-out .2s forwards"/>
{dots}
{star(bx, by, 9, glow=True, cls="rp")}
<text x="{bx}" y="{by-14}" font-size="10.5" fill="{INK}" text-anchor="middle">peak · {vals[best]}</text>
<text x="{W-40}" y="72" font-size="10.5" fill="{DIM}" text-anchor="end">last 31 days · {sum(vals)} contributions</text>'''
    return frame(W, H, "D A I L Y   G R I N D", body, "@keyframes draw{to{stroke-dashoffset:0}}")


def main():
    s = fetch()
    os.makedirs(OUT, exist_ok=True)
    for name, fn in [("stats", stats_card), ("langs", langs_card), ("activity", activity_card)]:
        with open(os.path.join(OUT, f"{name}.svg"), "w") as f:
            f.write(fn(s))
    print("ok", {k: v for k, v in s.items() if k not in ("days", "langs")})


if __name__ == "__main__":
    main()
