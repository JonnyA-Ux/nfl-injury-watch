"""HTML dashboard for injury_watch. Writes dashboard.html, opens in a browser."""
import html as _h
import json
import os
import urllib.request
import webbrowser
from datetime import datetime, timezone

import pandas as pd

import injury_watch as iw

TS_URL = ("https://github.com/nflverse/nflverse-data/releases/"
          "download/injuries/timestamp.json")

CSS = """
:root{
  --bg:#131a21; --panel:#1b242d; --edge:#2b3742;
  --ink:#e8edf0; --dim:#8496a3; --faint:#5d6e7b;
  --worse:#e5644a; --better:#4da57e; --hold:#e0a63c;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:32px 24px 80px}
header{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;
  padding-bottom:14px;border-bottom:1px solid var(--edge)}
h1{font-size:21px;font-weight:600;margin:0;letter-spacing:-.2px}
.meta{color:var(--dim);font-size:13px}
.meta b{color:var(--ink);font-weight:500}
.stale{color:var(--hold)}
h2{font-size:13px;font-weight:600;color:var(--dim);margin:38px 0 12px;
  letter-spacing:.02em}
.empty{color:var(--faint);padding:14px 0;font-size:14px}
.row{background:var(--panel);border-left:3px solid var(--edge);
  padding:11px 16px;margin-bottom:3px;display:flex;gap:14px;
  align-items:baseline;flex-wrap:wrap}
.row.worse{border-left-color:var(--worse)}
.row.better{border-left-color:var(--better)}
.row.hold{border-left-color:var(--hold)}
.tm{color:var(--dim);width:42px;flex:none;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
.nm{font-weight:500;min-width:170px}
.ps{color:var(--dim);font-size:13px;width:30px;flex:none}
.ail{color:var(--ink);font-size:13px;min-width:120px}
.st{color:var(--dim);font-size:13px;margin-left:auto;text-align:right}
.tag{font-size:11px;padding:1px 7px;border-radius:2px;font-weight:600;
  letter-spacing:.04em}
.tag.worse{background:var(--worse);color:#12181d}
.tag.better{background:var(--better);color:#12181d}
.tag.hold{background:var(--hold);color:#12181d}
.tag.rest{background:transparent;color:var(--faint);border:1px solid var(--edge);
  font-weight:400}
details{background:var(--panel);margin-bottom:3px;border-left:3px solid var(--edge)}
details[open]{border-left-color:var(--dim)}
summary{padding:11px 16px;cursor:pointer;display:flex;gap:14px;
  align-items:baseline;flex-wrap:wrap;list-style:none}
summary::-webkit-details-marker{display:none}
summary:hover{background:#212c36}
.inner{padding:4px 16px 18px 16px;border-top:1px solid var(--edge)}
.sub{color:var(--dim);font-size:12px;margin:14px 0 7px}
table{width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed}
td{padding:5px 10px 5px 0;overflow:hidden;text-overflow:ellipsis}
td:first-child{width:200px}
table td.ps{width:52px}
td.n{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-variant-numeric:tabular-nums;text-align:right;width:80px}
td.gain{color:var(--better)}
.thin{color:var(--faint);font-size:11px}
.note{color:var(--faint);font-size:12px;margin-top:12px;max-width:70ch}
.cmd{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--faint);
  background:#10161c;padding:7px 10px;margin-top:10px;display:block;
  overflow-x:auto;white-space:nowrap;border:1px solid var(--edge)}
a{color:var(--ink)}
@media(max-width:640px){.st{margin-left:0;width:100%;text-align:left}}
"""


def feed_time():
    try:
        with urllib.request.urlopen(TS_URL, timeout=10) as r:
            return json.load(r).get("last_updated", "unknown")
    except Exception:
        return "unreachable"


def esc(x):
    return _h.escape(str(x))


def build(open_browser=True):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cur = iw.load_today()
    usage = iw.usage_table()
    shares = iw._current_shares()
    names = iw._names()

    fname = f"{today}.csv"
    os.makedirs(iw.SNAP_DIR, exist_ok=True)
    cur.to_csv(os.path.join(iw.SNAP_DIR, fname), index=False)
    prev, prev_date = iw.prior_snapshot(fname)

    # ---- changes
    changes = []
    if prev is not None:
        p = prev.drop_duplicates(subset="key").set_index("key")
        for _, r in cur.drop_duplicates(subset="key").iterrows():
            k = r["key"]
            if k not in p.index:
                changes.append(("NEW", r, None))
            else:
                o = p.loc[k]
                if (r["practice_status"] != o["practice_status"]
                        or r["report_status"] != o["report_status"]):
                    changes.append((
                        "WORSE" if r["severity"] > o["severity"] else "BETTER", r, o))
        changes.sort(key=lambda c: (c[1]["position"] not in iw.SKILL,
                                    -c[1]["severity"]))

    # ---- at risk
    risk = cur[cur["position"].isin(iw.SKILL) & (cur["severity"] > 0)].copy()
    if not usage.empty:
        risk = risk.merge(
            usage[["team", "player", "snap_pct", "season"]].rename(
                columns={"season": "usage_season"}),
            left_on=["team", "full_name"], right_on=["team", "player"], how="left")
        risk["snap_pct"] = risk["snap_pct"].fillna(0)
        risk = risk[risk["snap_pct"] >= iw.USAGE_FLOOR]
    risk = risk.sort_values("severity", ascending=False)

    lines = iw.load_lines()
    bpath = os.path.join(iw.CACHE_DIR, "beneficiaries.csv")
    bene = pd.read_csv(bpath) if os.path.exists(bpath) else pd.DataFrame()

    unmoved = 0
    body = []

    # ---- header
    ft = feed_time()
    fresh = today.replace("-", "") in ft.replace("-", "")
    body.append(f"""<header>
<h1>Injury watch</h1>
<div class="meta">{esc(today)} &nbsp; feed updated
<b class="{'' if fresh else 'stale'}">{esc(ft)}</b> &nbsp;
week {esc(sorted(int(w) for w in cur['week'].dropna().unique()))}</div>
</header>""")

    # ---- change feed
    body.append("<h2>Changed since " + esc(prev_date or "n/a") + "</h2>")
    if prev is None:
        body.append('<div class="empty">First run today. Baseline saved, '
                    'nothing to compare against yet.</div>')
    elif not changes:
        body.append('<div class="empty">No status changes. If this holds all '
                    'week the feed is not refreshing and you should read team '
                    'reports directly.</div>')
    else:
        for tag, r, o in changes:
            cls = tag.lower() if tag != "NEW" else "hold"
            rest = ' <span class="tag rest">rest</span>' if r["rest_day"] else ""
            was = ("" if o is None else
                   f'<span class="st">was {esc(o["practice_status"])} / '
                   f'{esc(o["report_status"])}</span>')
            body.append(
                f'<div class="row {cls}"><span class="tag {cls}">{tag}</span>'
                f'<span class="tm">{esc(r["team"])}</span>'
                f'<span class="nm">{esc(r["full_name"])}</span>'
                f'<span class="ps">{esc(r["position"])}</span>'
                f'<span class="ail">{esc(r["ailment"])}{rest}</span>'
                f'<span class="st">{esc(r["practice_status"])} / '
                f'{esc(r["report_status"])}</span>{was}</div>')

    # ---- at risk with projections
    body.append(f"<h2>Skill players at risk "
                f"(snap share {iw.USAGE_FLOOR:.0%} or more)</h2>")
    if risk.empty:
        body.append('<div class="empty">Nobody on the report clears the '
                    'usage floor.</div>')
    for _, r in risk.iterrows():
        team, nm = r["team"], r["full_name"]
        stale = " · prior yr usage" if r.get("usage_season", 0) != iw.SEASON else ""
        rest = ' <span class="tag rest">rest</span>' if r["rest_day"] else ""
        cls = "worse" if r["severity"] >= 4 else ("hold" if r["severity"] >= 2 else "")
        inner = []

        # projection
        if not shares.empty:
            hit = names[(names["team"] == team)
                        & names["full_name"].str.contains(esc(nm).split()[-1],
                                                          case=False, na=False)]
            if not hit.empty:
                pid, pos = hit.index[0], hit.iloc[0]["position"]
                ts = shares[shares["team"] == team].copy()
                ts["position"] = ts["player_id"].map(names["position"])
                ts["name"] = ts["player_id"].map(names["full_name"])
                ts = ts[ts["position"].isin(iw.SKILL)]
                try:
                    now = iw.nfl.load_rosters_weekly(seasons=[iw.SEASON]).to_pandas()
                    ts = ts[ts["player_id"].isin(
                        set(now.loc[now["team"] == team, "gsis_id"]))]
                except Exception:
                    pass
                for m in ("targets", "carries"):
                    blk = ts[ts["metric"] == m]
                    orow = blk[blk["player_id"] == pid]
                    if orow.empty or float(orow["share"].iloc[0]) < 0.05:
                        continue
                    vac = float(orow["share"].iloc[0])
                    rest_df = blk[blk["player_id"] != pid].copy()
                    if rest_df.empty:
                        continue
                    rest_df["w"] = [
                        s * iw.DEFAULT_AFFINITY.get((pos, p), 0.3)
                        for s, p in zip(rest_df["share"], rest_df["position"])]
                    if rest_df["w"].sum() <= 0:
                        continue
                    rest_df["gain"] = vac * rest_df["w"] / rest_df["w"].sum()
                    rest_df["proj"] = rest_df["share"] + rest_df["gain"]
                    inner.append(f'<div class="sub">Projected {m} if out '
                                 f'&mdash; {vac:.1%} of team volume moves</div>'
                                 '<table>')
                    for _, b in rest_df.sort_values("gain", ascending=False).head(5).iterrows():
                        up = b["gain"] / b["share"] if b["share"] else 0
                        ln = iw.line_status(team, b["name"])
                        lcell = ""
                        if ln:
                            f_, l_, dt, mk = ln
                            mv = l_ - f_
                            if abs(mv) < 0.01:
                                unmoved += 1
                                lcell = (f'<span class="tag hold">line '
                                         f'{mk} {l_} unmoved</span>')
                            else:
                                lcell = (f'<span class="thin">{mk} {f_} &rarr; '
                                         f'{l_} ({mv:+.1f})</span>')
                        inner.append(
                            f'<tr><td>{esc(b["name"])}</td>'
                            f'<td class="ps">{esc(b["position"])}</td>'
                            f'<td class="n">{b["share"]:.1%}</td>'
                            f'<td class="n">&rarr; {b["proj"]:.1%}</td>'
                            f'<td class="n gain">+{up:.0%}</td>'
                            f'<td>{lcell}</td></tr>')
                    inner.append("</table>")

        # empirical history
        if not bene.empty:
            m = bene[(bene["team"] == team)
                     & bene["out_player"].str.contains(str(nm).split()[-1],
                                                       case=False, na=False)]
            if not m.empty:
                inner.append('<div class="sub">Actual games without him</div><table>')
                for _, b in m.sort_values("delta", ascending=False).head(5).iterrows():
                    n = int(b["n_without"])
                    flag = ' <span class="thin">anecdote</span>' if n <= iw.MIN_GAMES else ""
                    inner.append(
                        f'<tr><td>{esc(b["beneficiary"])}</td>'
                        f'<td class="ps">{esc(b["metric"])[:3]}</td>'
                        f'<td class="n">{b["share_with"]:.1%}</td>'
                        f'<td class="n">&rarr; {b["share_without"]:.1%}</td>'
                        f'<td class="n gain">+{b["delta"]:.1%}</td>'
                        f'<td class="thin">n={n}/{int(b["n_with"])}{flag}</td></tr>')
                inner.append("</table>")

        if not inner:
            inner.append('<div class="note">No usage history for this player '
                         'on this team. Check the depth chart.</div>')
        inner.append(f'<code class="cmd">python3 injury_watch.py log --team {esc(team)} '
                     f'--player "NAME" --market rec_yds --line 0.0</code>')

        body.append(
            f'<details><summary class="row {cls}" style="margin:0;border:0">'
            f'<span class="tm">{esc(team)}</span>'
            f'<span class="nm">{esc(nm)}</span>'
            f'<span class="ps">{esc(r["position"])}</span>'
            f'<span class="ail">{esc(r["ailment"])}{rest}</span>'
            f'<span class="st">{r.get("snap_pct",0):.0%} snaps{stale} &nbsp;&middot;&nbsp; '
            f'{esc(r["practice_status"])} / {esc(r["report_status"])}</span>'
            f'</summary><div class="inner">{"".join(inner)}</div></details>')

    # ---- lines
    body.append("<h2>Lines you are tracking</h2>")
    if lines.empty:
        body.append('<div class="empty">Nothing logged. Use the command inside '
                    'any player above once his beneficiary\'s prop posts.</div>')
    else:
        body.append("<table>")
        for (tm, pl, mk), g in lines.groupby(["team", "player", "market"]):
            f_, l_ = g.iloc[0], g.iloc[-1]
            mv = l_["line"] - f_["line"]
            cell = (f'<span class="tag hold">unmoved</span>' if abs(mv) < 0.01
                    else f'<span class="thin">{mv:+.1f}</span>')
            body.append(f'<tr><td class="tm">{esc(tm)}</td><td>{esc(pl)}</td>'
                        f'<td class="thin">{esc(mk)}</td>'
                        f'<td class="n">{f_["line"]}</td>'
                        f'<td class="n">&rarr; {l_["line"]}</td>'
                        f'<td>{cell}</td>'
                        f'<td class="thin">{esc(f_["date"])} &rarr; {esc(l_["date"])}</td></tr>')
        body.append("</table>")

    body.append('<div class="note">Projections redistribute volume by existing '
                'share and position. Coaches concentrate volume more than this. '
                'Where actual games exist, trust those.</div>')

    out = (f"<!doctype html><html><head><meta charset=utf-8>"
           f'<meta name=viewport content="width=device-width,initial-scale=1">'
           f"<title>Injury watch {today}</title><style>{CSS}</style></head>"
           f'<body><div class="wrap">{"".join(body)}</div></body></html>')

    path = os.path.abspath("dashboard.html")
    with open(path, "w") as f:
        f.write(out)
    print(f"wrote {path}")
    if unmoved:
        print(f"{unmoved} tracked line(s) unmoved despite a flagged starter.")
    if open_browser:
        webbrowser.open("file://" + path)


if __name__ == "__main__":
    build()
