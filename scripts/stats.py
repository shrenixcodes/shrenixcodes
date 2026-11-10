"""Builds the dynamic parts of the profile README from the GitHub GraphQL API.

Outputs
  assets/signal.svg    headline numbers, streaks and language mix
  assets/activity.svg  daily contributions over the last 31 days
  README.md            the block between <!-- recent:start --> and <!-- recent:end -->

Runs in GitHub Actions with the built-in GITHUB_TOKEN. Set MOCK=1 to render sample data
locally (README.md is left alone in mock mode). Standard library only, Python 3.8+.

If the API is unreachable or returns incomplete data the script exits non-zero before
writing anything, so the last good assets stay in place.
"""
import datetime as dt
import html
import json
import math
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

USER = os.environ.get("GH_USER", "shrenixcodes")
OUT = os.environ.get("OUT_DIR", "assets")
README = os.environ.get("README_PATH", "README.md")
MOCK = bool(os.environ.get("MOCK"))

# palette (shared with the hand-made SVGs in assets/)
BG, LINE, PANEL = "#07080b", "#1d2130", "#0d0f15"
INK, SIL, MUTED, DIM = "#eef1f8", "#b8c2dc", "#8a92a8", "#5c6175"
RED, ICE, PERI, COB = "#ff2a2a", "#99ccff", "#6699ff", "#2424d9"
LANG_RAMP = [COB, PERI, ICE, SIL, MUTED, DIM]
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono','Liberation Mono',monospace"
SANS = "Inter,'Segoe UI',-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif"
e = html.escape

# languages that describe build glue or vendored code rather than the project itself
IGNORE = {"NASL", "Cython", "Makefile", "Batchfile", "PowerShell", "Dockerfile", "Procfile", "Smarty", "Roff", "Shell", "Mako"}
RENAME = {"Jupyter Notebook": "Python"}

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      nodes {
        name url description pushedAt isArchived stargazerCount
        primaryLanguage { name }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { node { name } } }
      }
    }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions totalPullRequestContributions
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
  }
}"""


# ---------------------------------------------------------------- data
def graphql(variables, attempts=4):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is not set (use MOCK=1 for a local preview)")
    body = json.dumps({"query": QUERY, "variables": variables}).encode()
    for i in range(attempts):
        req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
            "Authorization": "bearer " + token, "Content-Type": "application/json", "User-Agent": "shrenixcodes-profile"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            if data.get("errors"):
                raise SystemExit("GraphQL errors: %s" % data["errors"])
            return data["data"]
        except urllib.error.HTTPError as err:
            # 403/429 = rate limited, 5xx = GitHub having a moment; anything else won't fix itself
            if err.code not in (403, 429, 500, 502, 503, 504) or i == attempts - 1:
                raise SystemExit("GitHub API returned HTTP %s" % err.code)
            wait = int(err.headers.get("Retry-After") or 0) or 10 * 2 ** i
        except (urllib.error.URLError, TimeoutError) as err:
            if i == attempts - 1:
                raise SystemExit("GitHub API unreachable: %s" % err)
            wait = 10 * 2 ** i
        print("retrying in %ss" % wait, file=sys.stderr)
        time.sleep(min(wait, 120))


def mock():
    rnd = random.Random(4)
    today = dt.date.today()
    days = [{"date": str(today - dt.timedelta(days=i)), "contributionCount": max(0, int(rnd.gauss(4, 4)))} for i in range(365)][::-1]
    repos = [{"name": n, "url": "https://github.com/%s/%s" % (USER, n), "description": "sample repository",
              "pushedAt": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=k)).isoformat(),
              "isArchived": False, "primaryLanguage": {"name": l}, "languages": {"edges": []}}
             for k, (n, l) in enumerate([("alpha", "Python"), ("beta", "TypeScript"), ("gamma", "Rust"), ("delta", "Python"),
                                         ("epsilon", "Kotlin"), ("zeta", "Lua"), ("eta", "Java"), ("theta", "Python")])]
    return {"repos": repos, "repo_count": 34, "total": 1567, "commits": 1203, "prs": 41, "days": days}


def fetch():
    if MOCK:
        return mock()
    to = dt.datetime.now(dt.timezone.utc)
    frm = to - dt.timedelta(days=365)
    u = graphql({"login": USER, "from": frm.isoformat(), "to": to.isoformat()}).get("user")
    if not u:
        raise SystemExit("user %r not found" % USER)
    cc = u["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    if len(days) < 31:
        raise SystemExit("contribution calendar looks incomplete (%d days); keeping previous assets" % len(days))
    return {"repos": u["repositories"]["nodes"], "repo_count": u["repositories"]["totalCount"],
            "total": cc["contributionCalendar"]["totalContributions"], "commits": cc["totalCommitContributions"],
            "prs": cc["totalPullRequestContributions"], "days": days}


def languages(repos):
    """Share of repositories per main language; byte counts get skewed by vendored libraries."""
    counts = {}
    for r in repos:
        lang = (r.get("primaryLanguage") or {}).get("name")
        if not lang or lang in IGNORE:
            edges = [ed["node"]["name"] for ed in r["languages"]["edges"] if ed["node"]["name"] not in IGNORE]
            lang = edges[0] if edges else None
        if lang:
            lang = RENAME.get(lang, lang)
            counts[lang] = counts.get(lang, 0) + 1
    total = sum(counts.values())
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top, rest = ranked[:5], sum(v for _, v in ranked[5:])
    if rest:
        top.append(("other", rest))
    return [(k, 100 * v / total) for k, v in top], total


def streaks(days):
    vals = [d["contributionCount"] for d in days]
    longest = run = 0
    for v in vals:
        run = run + 1 if v else 0
        longest = max(longest, run)
    # today still counts as "in progress", so an empty today doesn't break the streak yet
    i = len(vals) - 1
    if vals and vals[i] == 0:
        i -= 1
    current = 0
    while i >= 0 and vals[i]:
        current, i = current + 1, i - 1
    return current, longest


# ---------------------------------------------------------------- drawing
def star(cx, cy, r, fill=RED):
    """Four-point sparkle used across the profile."""
    k = r * .72
    return ('<path d="M{0:.1f},{1:.1f} Q{2:.1f},{3:.1f} {4:.1f},{3:.1f} Q{2:.1f},{3:.1f} {2:.1f},{5:.1f} '
            'Q{2:.1f},{3:.1f} {6:.1f},{3:.1f} Q{2:.1f},{3:.1f} {2:.1f},{1:.1f}Z" fill="{7}"/>').format(
        cx, cy - r, cx, cy, cx + k, cy + r, cx - k, fill)


def frame(W, H, title, note, body, css=""):
    ticks = "".join(
        '<path d="M{0},{1} V{2} H{3}" fill="none" stroke="{4}" stroke-width="1"/>'.format(x, y + 12 * sy, y, x + 12 * sx, SIL)
        for x, y, sx, sy in [(8, 8, 1, 1), (W - 8, 8, -1, 1), (8, H - 8, 1, -1), (W - 8, H - 8, -1, -1)])
    return """<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{title}">
<style>
.m{{font-family:{MONO}}} .s{{font-family:{SANS}}}
.in{{animation:in .5s ease-out both}} @keyframes in{{from{{opacity:0;transform:translateY(3px)}}}}
{css}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>
<rect x=".5" y=".5" width="{W1}" height="{H1}" rx="10" fill="{BG}" stroke="{LINE}"/>
{ticks}
{star}
<text x="44" y="38" class="m" font-size="12" letter-spacing="3" fill="{SIL}">{title}</text>
<text x="{NX}" y="38" class="m" font-size="12" fill="{MUTED}" text-anchor="end">{note}</text>
<line x1="24" y1="56" x2="{LX}" y2="56" stroke="{LINE}"/>
{body}
</svg>
""".format(W=W, H=H, W1=W - 1, H1=H - 1, NX=W - 28, LX=W - 24, MONO=MONO, SANS=SANS, css=css, BG=BG, LINE=LINE,
           SIL=SIL, MUTED=MUTED, ticks=ticks, star=star(30, 34, 6), title=e(title.upper()), note=e(note), body=body)


def fmt(n):
    return "{:.1f}k".format(n / 1000) if n >= 10000 else "{:,}".format(n)


def signal_card(s, today):
    W, H = 900, 270
    cur, longest = streaks(s["days"])
    metrics = [(fmt(s["total"]), "contributions · 12 mo"), (fmt(s["commits"]), "commits · 12 mo"),
               ("%d d" % cur, "current streak"), ("%d d" % longest, "longest streak · 12 mo"),
               (fmt(s["repo_count"]), "public repositories")]
    colw = (W - 48) / len(metrics)
    out = []
    for i, (val, label) in enumerate(metrics):
        x = 24 + i * colw + 16
        if i:
            out.append('<line x1="{0:.1f}" y1="80" x2="{0:.1f}" y2="146" stroke="{1}"/>'.format(24 + i * colw, LINE))
        out.append('<g class="in" style="animation-delay:{d:.2f}s"><text x="{x:.1f}" y="118" class="s" font-size="34" font-weight="700" fill="{INK}">{v}</text>'
                   '<text x="{x:.1f}" y="140" class="m" font-size="12.5" fill="{MUTED}">{l}</text></g>'.format(
                       d=.1 + i * .08, x=x, INK=INK, v=e(val), MUTED=MUTED, l=e(label)))

    langs, counted = languages(s["repos"])
    out.append('<text x="40" y="186" class="m" font-size="12.5" fill="{0}">languages · main language of {1} public repos</text>'.format(MUTED, counted))
    bar_x, bar_w, x = 40, W - 80, 40.0
    for i, (name, pct) in enumerate(langs):
        w = bar_w * pct / 100
        out.append('<rect class="g" x="{0:.1f}" y="198" width="{1:.1f}" height="8" fill="{2}" style="animation-delay:{3:.2f}s"/>'.format(
            x, max(w - 2, 1), LANG_RAMP[i % len(LANG_RAMP)], .3 + i * .08))
        x += w
    lx = 40.0
    for i, (name, pct) in enumerate(langs):
        label = "{} {:.0f}%".format(name, pct)
        out.append('<rect x="{0:.1f}" y="227" width="9" height="9" fill="{1}"/><text x="{2:.1f}" y="236" class="m" font-size="12.5" fill="{3}">{4}</text>'.format(
            lx, LANG_RAMP[i % len(LANG_RAMP)], lx + 15, SIL, e(label)))
        lx += 15 + len(label) * 7.6 + 24
    if not langs:
        out.append('<text x="40" y="214" class="m" font-size="12.5" fill="{0}">no language data</text>'.format(MUTED))
    css = (".g{transform-box:fill-box;transform-origin:left;animation:g .9s cubic-bezier(.2,.8,.2,1) both}"
           "@keyframes g{from{transform:scaleX(0)}}")
    return frame(W, H, "signal", "updated " + today, "\n".join(out), css)


def activity_card(s):
    W, H = 900, 270
    days = s["days"][-31:]
    vals = [d["contributionCount"] for d in days]
    mx = max(vals + [1])
    x0, x1, y0, y1 = 64, W - 40, 86, H - 52
    if len(vals) < 2:
        return frame(W, H, "activity", "last 31 days", '<text x="40" y="140" class="m" font-size="13" fill="{0}">no activity data</text>'.format(MUTED))
    step = (x1 - x0) / (len(vals) - 1)
    pts = [(x0 + i * step, y1 - (y1 - y0) * v / mx) for i, v in enumerate(vals)]
    # catmull-rom -> bezier; control points are clamped so the curve never dips below zero
    d = "M{:.1f},{:.1f}".format(*pts[0])
    for i in range(len(pts) - 1):
        p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(y1, p1[1] + (p2[1] - p0[1]) / 6))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, min(y1, p2[1] - (p3[1] - p1[1]) / 6))
        if p1[1] >= y1 or p2[1] >= y1:  # keep flat stretches on the baseline
            lo = min(p1[1], p2[1])
            c1, c2 = (c1[0], max(c1[1], lo)), (c2[0], max(c2[1], lo))
        d += " C{:.1f},{:.1f} {:.1f},{:.1f} {:.1f},{:.1f}".format(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])
    area = d + " L{},{} L{},{}Z".format(x1, y1, x0, y1)
    length = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1)) * 1.3

    out = ['<defs><linearGradient id="ar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{0}" stop-opacity=".45"/>'
           '<stop offset="1" stop-color="{0}" stop-opacity="0"/></linearGradient></defs>'.format(COB)]
    for k in range(5):
        y = y1 - (y1 - y0) * k / 4
        out.append('<line x1="{0}" y1="{1:.1f}" x2="{2}" y2="{1:.1f}" stroke="{3}" stroke-dasharray="{4}"/>'
                   '<text x="{5}" y="{6:.1f}" class="m" font-size="11" fill="{7}" text-anchor="end">{8}</text>'.format(
                       x0, y, x1, LINE, "none" if k == 0 else "2 6", x0 - 12, y + 4, MUTED, round(mx * k / 4)))
    for i in range(0, len(days), 5):
        out.append('<text x="{0:.1f}" y="{1}" class="m" font-size="11" fill="{2}" text-anchor="middle">{3}</text>'.format(
            pts[i][0], y1 + 22, MUTED, dt.date.fromisoformat(days[i]["date"]).strftime("%b %d").lower()))
    out.append('<path d="{0}" fill="url(#ar)" class="in" style="animation-delay:.5s"/>'.format(area))
    out.append('<path class="ln" d="{0}" fill="none" stroke="{1}" stroke-width="2" stroke-linejoin="round"/>'.format(d, PERI))
    best = max(range(len(vals)), key=lambda i: (vals[i], i))
    bx, by = pts[best]
    if vals[best]:
        out.append('<g class="in" style="animation-delay:1.4s">{0}<text x="{1:.1f}" y="{2:.1f}" class="m" font-size="11.5" fill="{3}" text-anchor="middle">peak {4}</text></g>'.format(
            star(bx, by, 7), bx, by - 13, INK, vals[best]))
    tx, ty = pts[-1]
    out.append('<circle cx="{0:.1f}" cy="{1:.1f}" r="3.5" fill="{2}" class="in" style="animation-delay:1.6s"/>'.format(tx, ty, ICE))
    css = (".ln{{stroke-dasharray:{L:.0f};animation:draw 2s ease-out .2s both}}"
           "@keyframes draw{{from{{stroke-dashoffset:{L:.0f}}}to{{stroke-dashoffset:0}}}}").format(L=length)
    return frame(W, H, "activity", "last 31 days · {} contributions".format(sum(vals)), "\n".join(out), css)


# ---------------------------------------------------------------- readme block
def recent_block(repos, n=3):
    picks = [r for r in repos if r["name"].lower() != USER.lower() and not r.get("isArchived")][:n]
    if not picks:
        return None
    parts = []
    for r in picks:
        when = dt.datetime.fromisoformat(r["pushedAt"].replace("Z", "+00:00")).strftime("%b %d").lower()
        lang = (r.get("primaryLanguage") or {}).get("name")
        meta = " · ".join(x for x in (lang, when) if x)
        parts.append("[{}]({}) {}".format(r["name"], r["url"], meta))
    return "<sub>lately pushed to &nbsp; " + " &nbsp;·&nbsp; ".join(parts) + "</sub>"


def patch_readme(text, block):
    pat = re.compile(r"(<!-- recent:start -->\n).*?(<!-- recent:end -->)", re.S)
    if not pat.search(text):
        print("README markers not found; skipping recent block", file=sys.stderr)
        return text
    return pat.sub(lambda m: m.group(1) + block + "\n" + m.group(2), text)


# ---------------------------------------------------------------- main
def write(path, content):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.replace(tmp, path)


def main():
    s = fetch()
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    files = {os.path.join(OUT, "signal.svg"): signal_card(s, today),
             os.path.join(OUT, "activity.svg"): activity_card(s)}
    block = recent_block(s["repos"])
    if block and not MOCK and os.path.exists(README):
        with open(README, encoding="utf-8") as f:
            files[README] = patch_readme(f.read(), block)
    # everything rendered successfully; only now touch the disk
    os.makedirs(OUT, exist_ok=True)
    for path, content in files.items():
        write(path, content)
    print("ok", {"total": s["total"], "commits": s["commits"], "repos": s["repo_count"], "streaks": streaks(s["days"])})


if __name__ == "__main__":
    main()
