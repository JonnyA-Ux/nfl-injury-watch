"""HTML dashboard for injury_watch. Writes dashboard.html and opens it."""
import html as _h
import json
import os
import webbrowser
from datetime import datetime, timezone

import pandas as pd
import requests

import injury_watch as iw

TS_URL = ("https://github.com/nflverse/nflverse-data/releases/"
          "download/injuries/timestamp.json")

RISK = {  # report_status -> (label, css class)
    "Out": ("Out", "r-out"),
    "Doubtful": ("Doubtful", "r-dbt"),
    "Questionable": ("Questionable", "r-qst"),
    "None": ("Monitor", "r-mon"),
}
PRACTICE_SHORT = {
    "Did Not Participate In Practice": "DNP",
    "Limited Participation in Practice": "Limited",
    "Full Participation in Practice": "Full",
}

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f2f4f7;color:#1b1f24;
 font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;
 -webkit-font-smoothing:antialiased}
.wrap{max-width:1240px;margin:0 auto;padding:26px 20px 70px}
.card{background:#fff;border:1px solid #dfe3e8;border-radius:8px;
 margin-bottom:20px;overflow:hidden}
.head{padding:18px 22px 14px;border-bottom:1px solid #eceff2}
h1{margin:0;font-size:25px;font-weight:700;letter-spacing:-.3px}
.sub{color:#697586;font-size:13px;margin-top:4px}
.sub b{color:#1b1f24;font-weight:600}
.warn{color:#b45309}
.bar{display:flex;gap:6px;padding:11px 22px;border-bottom:1px solid #eceff2;
 background:#fafbfc;flex-wrap:wrap;align-items:center}
.tab{padding:5px 13px;border-radius:15px;border:1px solid transparent;
 font-size:13px;font-weight:600;color:#5b6673;cursor:pointer;background:none}
.tab:hover{background:#eef1f4}
.tab.on{color:#1557c0;background:#e8f0fd}
.spacer{flex:1}
.hint{color:#8а94a1;font-size:12px}
table{width:100%;border-collapse:collapse}
thead th{font-size:11px;font-weight:700;color:#6b7684;text-align:left;
 padding:9px 12px;border-bottom:1px solid #dfe3e8;background:#fafbfc;
 white-space:nowrap;cursor:pointer;user-select:none}
thead th.grp{text-align:center;border-bottom:1px solid #eceff2;
 color:#98a2b0;font-weight:600;cursor:default;background:#fff}
thead th:hover:not(.grp){color:#1557c0}
thead th.num,td.num{text-align:right}
tbody td{padding:10px 12px;border-bottom:1px solid #f0f2f5;font-size:13.5px;
 white-space:nowrap}
tbody tr:hover{background:#f8fafc}
tbody tr.open{background:#f4f8ff}
.tm{color:#7c8794;font-size:12px;font-weight:600}
.pl{font-weight:600;color:#14418f;cursor:pointer}
.pl:hover{text-decoration:underline}
.pos{color:#6b7684;font-size:12px;font-weight:600}
.pill{display:inline-block;padding:2px 9px;border-radius:11px;font-size:11.5px;
 font-weight:700}
.r-out{background:#fde8e6;color:#b42318}
.r-dbt{background:#feecdc;color:#b54708}
.r-qst{background:#fef6d8;color:#8a6100}
.r-mon{background:#eef1f4;color:#5b6673}
.chg-worse{background:#fde8e6;color:#b42318}
.chg-better{background:#e3f5ea;color:#10713a}
.chg-new{background:#e8f0fd;color:#1557c0}
.meter{display:inline-block;width:46px;height:5px;background:#eceff2;
 border-radius:3px;vertical-align:middle;margin-left:7px;overflow:hidden}
.meter i{display:block;height:100%;background:#3b82f6}
.dim{color:#8b95a2;font-size:12px}
.up{color:#15803d;font-weight:600}
.flag{display:inline-block;padding:1px 7px;border-radius:4px;font-size:11px;
 font-weight:700;background:#fef3c7;color:#92400e}
.detail{display:none}
.detail.show{display:table-row}
.detail td{background:#f8fafc;padding:0 12px 16px 12px;border-bottom:2px solid #e6eaee}
.dh{font-size:11px;font-weight:700;color:#6b7684;padding:14px 0 6px}
.mini{width:100%;border-collapse:collapse}
.mini td{padding:5px 10px 5px 0;border:0;font-size:13px;white-space:nowrap}
.mini td:first-child{width:190px;font-weight:500}
.note{padding:14px 22px;color:#8b95a2;font-size:12px;line-height:1.6}
.empty{padding:26px 22px;color:#8b95a2;font-size:13.5px}
code{background:#eef1f4;padding:3px 7px;border-radius:4px;font-size:11.5px;
 color:#475467;font-family:ui-monospace,Menlo,monospace}
"""

JS = """
function pos(el,p){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  el.classList.add('on');
  document.querySelectorAll('#risk tbody tr[data-pos]').forEach(r=>{
    const m = (p==='ALL'||r.dataset.pos===p);
    r.style.display = m?'':'none';
    const d = document.getElementById('d-'+r.dataset.i);
    if(d && !m) d.classList.remove('show');
  });
}
function toggle(i){
  const d=document.getElementById('d-'+i), r=document.getElementById('r-'+i);
  d.classList.toggle('show'); r.classList.toggle('open');
}
function sortBy(th,i,numeric){
  const tb=th.closest('table').querySelector('tbody');
  const rows=[...tb.querySelectorAll('tr[data-pos]')];
  const asc = th.dataset.asc!=='1'; th.dataset.asc = asc?'1':'0';
  rows.sort((a,b)=>{
    let x=a.children[i].dataset.v ?? a.children[i].innerText;
    let y=b.children[i].dataset.v ?? b.children[i].innerText;
    if(numeric){x=parseFloat(x)||0;y=parseFloat(y)||0;return asc?x-y:y-x;}
    return asc?String(x).localeCompare(y):String(y).localeCompare(x);
  });
  rows.forEach(r=>{tb.appendChild(r);
    const d=document.getElementById('d-'+r.dataset.i); if(d) tb.appendChild(d);});
}
"""


def feed_time():
    try:
        return requests.get(TS_URL, timeout=12).json().get("last_updated", "unknown")
    except Exception as e:
        return f"unreachable ({type(e).__name__})"


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
                    changes.append(("WORSE" if r["severity"] > o["severity"]
                                    else "BETTER", r, o))
        changes.sort(key=lambda c: (c[1]["position"] not in iw.SKILL,
                                    -c[1]["severity"]))

    risk = cur[cur["position"].isin(iw.SKILL) & (cur["severity"] > 0)].copy()
    if not usage.empty:
        risk = risk.merge(
            usage[["team", "player", "snap_pct", "season"]].rename(
                columns={"season": "usage_season"}),
            left_on=["team", "full_name"], right_on=["team", "player"], how="left")
        risk["snap_pct"] = risk["snap_pct"].fillna(0)
        risk = risk[risk["snap_pct"] >= iw.USAGE_FLOOR]
    risk = risk.sort_values(["severity", "snap_pct"], ascending=False)

    lines = iw.load_lines()
    bpath = os.path.join(iw.CACHE_DIR, "beneficiaries.csv")
    bene = pd.read_csv(bpath) if os.path.exists(bpath) else pd.DataFrame()

    try:
        rost26 = iw.nfl.load_rosters_weekly(seasons=[iw.SEASON]).to_pandas()
    except Exception:
        rost26 = pd.DataFrame(columns=["team", "gsis_id"])

    unmoved = 0
    ft = feed_time()
    fresh = today in ft
    weeks = sorted(int(w) for w in cur["week"].dropna().unique())
    basis = shares["basis"].iloc[0] if not shares.empty else "n/a"

    H = [f"""<div class="card"><div class="head">
<h1>Injury watch</h1>
<div class="sub">Week {esc(weeks[-1] if weeks else '?')} &nbsp;&middot;&nbsp;
{esc(today)} &nbsp;&middot;&nbsp; source last updated
<b class="{'' if fresh else 'warn'}">{esc(ft)}</b> &nbsp;&middot;&nbsp;
usage basis: {esc(basis)} season</div></div>"""]

    # ---------- changes
    H.append('<div class="bar"><b style="font-size:13px">Changed since '
             f'{esc(prev_date or "n/a")}</b><div class="spacer"></div>'
             f'<span class="hint">{len(changes)} update(s)</span></div>')
    if prev is None:
        H.append('<div class="empty">First run today. Baseline saved. Run this '
                 'again tomorrow and changes will appear here.</div>')
    elif not changes:
        H.append('<div class="empty">No status changes since the last run.</div>')
    else:
        H.append('<table><thead><tr><th>Change</th><th>Team</th><th>Player</th>'
                 '<th>Pos</th><th>Injury</th><th>Practice</th><th>Status</th>'
                 '<th>Previously</th></tr></thead><tbody>')
        for tag, r, o in changes:
            cls = {"WORSE": "chg-worse", "BETTER": "chg-better"}.get(tag, "chg-new")
            was = ("&mdash;" if o is None else
                   f'{esc(PRACTICE_SHORT.get(o["practice_status"], o["practice_status"]))}'
                   f' / {esc(o["report_status"])}')
            H.append(
                f'<tr><td><span class="pill {cls}">{tag}</span></td>'
                f'<td class="tm">{esc(r["team"])}</td>'
                f'<td class="pl">{esc(r["full_name"])}</td>'
                f'<td class="pos">{esc(r["position"])}</td>'
                f'<td>{esc(r["ailment"])}</td>'
                f'<td>{esc(PRACTICE_SHORT.get(r["practice_status"], r["practice_status"]))}</td>'
                f'<td>{esc(r["report_status"])}</td>'
                f'<td class="dim">{was}</td></tr>')
        H.append("</tbody></table>")
    H.append("</div>")

    # ---------- risk board
    H.append('<div class="card"><div class="bar">'
             '<button class="tab on" onclick="pos(this,\'ALL\')">All</button>')
    for p in ("QB", "RB", "WR", "TE"):
        H.append(f'<button class="tab" onclick="pos(this,\'{p}\')">{p}</button>')
    H.append('<div class="spacer"></div><span class="hint">Click a player for '
             'volume redistribution</span></div>')

    H.append('<table id="risk"><thead>'
             '<tr><th class="grp" colspan="4"></th>'
             '<th class="grp" colspan="3">This week\'s report</th>'
             '<th class="grp" colspan="2">Usage</th></tr>'
             '<tr>'
             '<th onclick="sortBy(this,0,1)">#</th>'
             '<th onclick="sortBy(this,1,0)">Team</th>'
             '<th onclick="sortBy(this,2,0)">Player</th>'
             '<th onclick="sortBy(this,3,0)">Pos</th>'
             '<th onclick="sortBy(this,4,0)">Injury</th>'
             '<th onclick="sortBy(this,5,1)">Practice</th>'
             '<th onclick="sortBy(this,6,1)">Risk</th>'
             '<th class="num" onclick="sortBy(this,7,1)">Snap%</th>'
             '<th onclick="sortBy(this,8,1)">Volume at stake</th>'
             '</tr></thead><tbody>')

    if risk.empty:
        H.append('<tr><td colspan="9" class="empty">Nobody on the report clears '
                 'the usage floor.</td></tr>')

    for i, (_, r) in enumerate(risk.iterrows(), 1):
        team, nm, pos_ = r["team"], r["full_name"], r["position"]
        label, rcls = RISK.get(r["report_status"], ("Monitor", "r-mon"))
        sp = float(r.get("snap_pct", 0) or 0)
        stale = "" if r.get("usage_season", 0) == iw.SEASON else \
            '<span class="dim"> (prior yr)</span>'
        rest = ' <span class="flag">rest</span>' if r["rest_day"] else ""

        # volume at stake + projection rows
        inner, vol_at_stake = [], 0.0
        hit = names[(names["team"] == team)
                    & names["full_name"].str.contains(str(nm).split()[-1],
                                                      case=False, na=False)]
        if not shares.empty and not hit.empty:
            pid, ppos = hit.index[0], hit.iloc[0]["position"]
            ts = shares[shares["team"] == team].copy()
            ts["position"] = ts["player_id"].map(names["position"])
            ts["name"] = ts["player_id"].map(names["full_name"])
            ts = ts[ts["position"].isin(iw.SKILL)]
            if len(rost26):
                ts = ts[ts["player_id"].isin(
                    set(rost26.loc[rost26["team"] == team, "gsis_id"]))]
            for m in ("targets", "carries"):
                blk = ts[ts["metric"] == m]
                orow = blk[blk["player_id"] == pid]
                if orow.empty or float(orow["share"].iloc[0]) < 0.05:
                    continue
                vac = float(orow["share"].iloc[0])
                vol_at_stake = max(vol_at_stake, vac)
                rest_df = blk[blk["player_id"] != pid].copy()
                if rest_df.empty:
                    continue
                rest_df["w"] = [s * iw.DEFAULT_AFFINITY.get((ppos, p), 0.3)
                                for s, p in zip(rest_df["share"], rest_df["position"])]
                if rest_df["w"].sum() <= 0:
                    continue
                rest_df["gain"] = vac * rest_df["w"] / rest_df["w"].sum()
                inner.append(f'<div class="dh">Projected {m} if he sits '
                             f'&mdash; {vac:.1%} of team volume moves</div>'
                             '<table class="mini">')
                for _, b in rest_df.sort_values("gain", ascending=False).head(5).iterrows():
                    proj = b["share"] + b["gain"]
                    up = b["gain"] / b["share"] if b["share"] else 0
                    ln = iw.line_status(team, b["name"])
                    lc = ""
                    if ln:
                        f_, l_, dt, mk = ln
                        mv = l_ - f_
                        if abs(mv) < 0.01:
                            unmoved += 1
                            lc = f'<span class="flag">{esc(mk)} {l_} unmoved</span>'
                        else:
                            lc = f'<span class="dim">{esc(mk)} {f_} &rarr; {l_} ({mv:+.1f})</span>'
                    inner.append(
                        f'<tr><td>{esc(b["name"])}</td>'
                        f'<td class="pos">{esc(b["position"])}</td>'
                        f'<td class="num">{b["share"]:.1%}</td>'
                        f'<td class="num">&rarr; {proj:.1%}</td>'
                        f'<td class="num up">+{up:.0%}</td>'
                        f'<td>{lc}</td></tr>')
                inner.append("</table>")

        if not bene.empty:
            m = bene[(bene["team"] == team)
                     & bene["out_player"].str.contains(str(nm).split()[-1],
                                                       case=False, na=False)]
            if not m.empty:
                inner.append('<div class="dh">What actually happened in games '
                             'he missed</div><table class="mini">')
                for _, b in m.sort_values("delta", ascending=False).head(5).iterrows():
                    n = int(b["n_without"])
                    fl = ' &middot; <b>thin sample</b>' if n <= iw.MIN_GAMES else ""
                    gw = "game" if n == 1 else "games"
                    inner.append(
                        f'<tr><td>{esc(b["beneficiary"])}</td>'
                        f'<td class="pos">{esc(b["metric"])[:3]}</td>'
                        f'<td class="num">{b["share_with"]:.1%}</td>'
                        f'<td class="num">&rarr; {b["share_without"]:.1%}</td>'
                        f'<td class="num up">+{b["delta"]:.1%}</td>'
                        f'<td class="dim">{n} {gw} without, {int(b["n_with"])} with{fl}</td></tr>')
                inner.append("</table>")

        if not inner:
            inner.append('<div class="dh">No usage history for him on this '
                         'team. Check the depth chart.</div>')
        inner.append(f'<div class="dh">Log a beneficiary\'s line</div>'
                     f'<code>python3 injury_watch.py log --team {esc(team)} '
                     f'--player "NAME" --market rec_yds --line 0.0</code>')

        vs = (f'{vol_at_stake:.1%} of team volume' if vol_at_stake
              else '<span class="dim">no history</span>')
        H.append(
            f'<tr id="r-{i}" data-pos="{esc(pos_)}" data-i="{i}" '
            f'onclick="toggle({i})">'
            f'<td class="dim" data-v="{i}">{i}</td>'
            f'<td class="tm">{esc(team)}</td>'
            f'<td class="pl">{esc(nm)}</td>'
            f'<td class="pos">{esc(pos_)}</td>'
            f'<td>{esc(r["ailment"])}{rest}</td>'
            f'<td data-v="{r["p_rank"]}">'
            f'{esc(PRACTICE_SHORT.get(r["practice_status"], r["practice_status"]))}</td>'
            f'<td data-v="{r["r_rank"]}"><span class="pill {rcls}">{label}</span></td>'
            f'<td class="num" data-v="{sp}">{sp:.0%}{stale}'
            f'<span class="meter"><i style="width:{min(sp,1)*100:.0f}%"></i></span></td>'
            f'<td data-v="{vol_at_stake}">{vs}</td></tr>'
            f'<tr class="detail" id="d-{i}"><td colspan="9">{"".join(inner)}</td></tr>')

    H.append('</tbody></table><div class="note">Projections spread a player\'s '
             'share across teammates by existing usage and position. Coaches '
             'concentrate volume more than that, so where real games exist, '
             'those win.</div></div>')

    # ---------- lines
    H.append('<div class="card"><div class="bar"><b style="font-size:13px">'
             'Lines you are tracking</b><div class="spacer"></div>'
             f'<span class="hint">{unmoved} unmoved next to a flagged starter</span></div>')
    if lines.empty:
        H.append('<div class="empty">Nothing logged yet. Open any player above '
                 'and copy the command at the bottom.</div>')
    else:
        H.append('<table><thead><tr><th>Team</th><th>Player</th><th>Market</th>'
                 '<th class="num">First</th><th class="num">Latest</th>'
                 '<th>Move</th><th>Dates</th></tr></thead><tbody>')
        for (tm, pl, mk), g in lines.groupby(["team", "player", "market"]):
            f_, l_ = g.iloc[0], g.iloc[-1]
            mv = l_["line"] - f_["line"]
            cell = ('<span class="flag">unmoved</span>' if abs(mv) < 0.01
                    else f'<span class="up">{mv:+.1f}</span>')
            H.append(f'<tr><td class="tm">{esc(tm)}</td><td class="pl">{esc(pl)}</td>'
                     f'<td class="dim">{esc(mk)}</td>'
                     f'<td class="num">{f_["line"]}</td>'
                     f'<td class="num">{l_["line"]}</td><td>{cell}</td>'
                     f'<td class="dim">{esc(f_["date"])} &rarr; {esc(l_["date"])}</td></tr>')
        H.append("</tbody></table>")
    H.append("</div>")

    out = (f"<!doctype html><html><head><meta charset=utf-8>"
           f'<meta name=viewport content="width=device-width,initial-scale=1">'
           f"<title>Injury watch {today}</title><style>{CSS}</style></head>"
           f'<body><div class="wrap">{"".join(H)}</div>'
           f"<script>{JS}</script></body></html>")

    path = os.path.abspath("dashboard.html")
    with open(path, "w") as f:
        f.write(out)
    print(f"wrote {path}")
    if unmoved:
        print(f"{unmoved} tracked line(s) unmoved next to a flagged starter.")
    if open_browser:
        webbrowser.open("file://" + path)


if __name__ == "__main__":
    # Skip the browser when running on a server (GitHub Actions sets CI=true).
    build(open_browser=not os.environ.get("CI"))
