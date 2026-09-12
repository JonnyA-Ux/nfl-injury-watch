#!/usr/bin/env python3
"""
injury_watch.py - daily NFL injury monitoring, volume-beneficiary mapping,
and prop line tracking. Free nflverse data, no API keys.

  python injury_watch.py build-map          # weekly, builds with/without cache
  python injury_watch.py snapshot           # every morning
  python injury_watch.py beneficiaries --team LV --player "Brock Bowers"
  python injury_watch.py log --team LV --player "Michael Mayer" \
         --market rec_yds --line 34.5 --over -115 --under -115
  python injury_watch.py lines              # movement on everything you logged
"""

import argparse
import os
import re
from datetime import datetime, timezone

import nflreadpy as nfl
import pandas as pd

SEASON = 2026
PRIOR_SEASON = 2025
SNAP_DIR = "snapshots"
CACHE_DIR = "cache"
LINES_FILE = "lines.csv"

PRACTICE_RANK = {
    "Full Participation in Practice": 0,
    "Limited Participation in Practice": 1,
    "Did Not Participate In Practice": 2,
}
REPORT_RANK = {"Questionable": 1, "Doubtful": 2, "Out": 3}
SKILL = {"QB", "RB", "WR", "TE", "FB"}

MIN_GAMES = 2          # below this, a split is labelled anecdote
USAGE_FLOOR = 0.25     # snap share below which a player is ignored


# ------------------------------------------------------------------ helpers

def match_player(series, full_name):
    """Exact full-name match first. Surname only as a last resort, and never
    when it hits more than one player (Ja'Marr Chase vs Chase Brown)."""
    full = str(full_name).strip().lower()
    exact = series.astype(str).str.strip().str.lower() == full
    if exact.any():
        return exact
    surname = str(full_name).split()[-1]
    loose = series.astype(str).str.contains(rf"\b{re.escape(surname)}$",
                                            case=False, na=False, regex=True)
    return loose if loose.sum() == 1 else exact


def pbp_name(full_name):
    """'Brock Bowers' -> 'B.Bowers', matching how pbp stores names."""
    if not isinstance(full_name, str) or " " not in full_name:
        return full_name
    parts = full_name.split()
    return f"{parts[0][0]}.{' '.join(parts[1:])}"


def _norm(df):
    keep = ["season", "week", "team", "full_name", "position",
            "report_primary_injury", "report_status",
            "practice_primary_injury", "practice_secondary_injury",
            "practice_status"]
    for c in keep:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[keep].copy()
    df["practice_status"] = df["practice_status"].fillna("Unknown")
    df["report_status"] = df["report_status"].fillna("None")
    # The feed explicitly labels maintenance days. Those are not injuries.
    pri = df["practice_primary_injury"].fillna("").astype(str)
    sec = df["practice_secondary_injury"].fillna("").astype(str)
    rest_re = "Not injury related"
    df["rest_day"] = pri.str.contains(rest_re, case=False) | sec.str.contains(rest_re, case=False)
    pri = pri.where(~pri.str.contains(rest_re, case=False), "")
    sec = sec.where(~sec.str.contains(rest_re, case=False), "")
    df["ailment"] = (pri + " + " + sec).str.strip(" +").replace("", "none listed")
    df["p_rank"] = df["practice_status"].map(PRACTICE_RANK).fillna(0).astype(int)
    # Only a pure maintenance day is discounted. A rest day attached to a real
    # ailment (knee + resting player) still counts as a signal.
    df["rest_only"] = df["rest_day"] & (df["ailment"] == "none listed")
    df.loc[df["rest_only"] & (df["report_status"] == "None"), "p_rank"] = 0
    df["r_rank"] = df["report_status"].map(REPORT_RANK).fillna(0).astype(int)
    df["severity"] = df["p_rank"] + df["r_rank"] * 2
    # Key omits week, so a new week does not mark every player as NEW.
    df["key"] = df["team"].astype(str) + "|" + df["full_name"].astype(str)
    return df


def load_today():
    return _norm(nfl.load_injuries(seasons=[SEASON]).to_pandas())


def prior_snapshot(exclude):
    if not os.path.isdir(SNAP_DIR):
        return None, None
    files = sorted(f for f in os.listdir(SNAP_DIR)
                   if f.endswith(".csv") and f != exclude)
    if not files:
        return None, None
    return pd.read_csv(os.path.join(SNAP_DIR, files[-1])), files[-1][:-4]


def load_snaps(seasons):
    frames = []
    for s in seasons:
        try:
            print(f"  snap counts {s}...", flush=True)
            d = nfl.load_snap_counts(seasons=[s]).to_pandas()
            if len(d):
                d["season"] = s
                frames.append(d)
        except Exception:
            pass
    if not frames:
        return pd.DataFrame()
    sc = pd.concat(frames, ignore_index=True)
    return sc[sc["position"].isin(SKILL) & (sc["offense_pct"] > 0)]


def usage_table():
    """Snap share, preferring the current season when the player has data there."""
    sc = load_snaps([SEASON, PRIOR_SEASON])
    if sc.empty:
        return pd.DataFrame()
    agg = (sc.groupby(["season", "team", "player", "position"], as_index=False)
             .agg(snap_pct=("offense_pct", "mean"), games=("week", "count")))
    agg = agg.sort_values("season", ascending=False)
    return agg.drop_duplicates(subset=["team", "player"], keep="first")


# ------------------------------------------------------------ with / without

def _shares(seasons):
    print(f"  downloading play-by-play for {seasons} "
          f"(first run pulls a few hundred MB, be patient)...", flush=True)
    pbp = nfl.load_pbp(seasons=seasons).to_pandas()
    print(f"  got {len(pbp):,} plays", flush=True)

    def build(mask, id_col, name_col, label):
        d = pbp[mask & pbp[id_col].notna()]
        if d.empty:
            return pd.DataFrame(columns=["season", "week", "team", "player_id", "share", "metric"])
        d = d.groupby(["season", "week", "posteam", id_col],
                      as_index=False).size()
        d = d.rename(columns={"size": "n", "posteam": "team", id_col: "player_id"})
        tot = d.groupby(["season", "week", "team"], as_index=False)["n"].sum()
        tot = tot.rename(columns={"n": "team_n"})
        d = d.merge(tot, on=["season", "week", "team"])
        d["share"] = d["n"] / d["team_n"]
        d["metric"] = label
        return d[["season", "week", "team", "player_id", "share", "metric"]]

    tgt = build(pbp["play_type"] == "pass", "receiver_player_id",
                "receiver_player_name", "targets")
    rsh = build(pbp["play_type"] == "run", "rusher_player_id",
                "rusher_player_name", "carries")
    return pd.concat([tgt, rsh], ignore_index=True)


def _roster_status(seasons):
    """Weekly roster with explicit status: ACT / INA (inactive) / RES (IR)."""
    frames = []
    for s in seasons:
        try:
            d = nfl.load_rosters_weekly(seasons=[s]).to_pandas()
            if len(d):
                frames.append(d[["season", "week", "team", "gsis_id",
                                 "full_name", "position", "status"]])
        except Exception:
            pass
    if not frames:
        return pd.DataFrame()
    r = pd.concat(frames, ignore_index=True)
    return r[r["position"].isin(SKILL)].drop_duplicates(
        subset=["season", "week", "team", "gsis_id"])


def build_map():
    """Teammate share with vs without each regular.

    Absence comes from weekly roster status (INA = inactive, RES = IR), so
    mid-season signings and season-ending injuries are both handled correctly.
    Everything is keyed on gsis_id, so no name matching is involved.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    seasons = [PRIOR_SEASON, SEASON]
    print("building beneficiary map. this takes a few minutes.", flush=True)
    shares = _shares(seasons)
    print("  downloading weekly rosters...", flush=True)
    ros = _roster_status(seasons)
    print("  computing with/without splits...", flush=True)
    if shares.empty or ros.empty:
        print("missing data")
        return

    names = (ros.sort_values("week").drop_duplicates(subset="gsis_id", keep="last")
                .set_index("gsis_id")[["full_name", "position"]])

    rows = []
    for (season, team), rg in ros.groupby(["season", "team"]):
        sh = shares[(shares["season"] == season) & (shares["team"] == team)]
        if sh.empty:
            continue

        for pid, pg in rg.groupby("gsis_id"):
            present = sorted(pg.loc[pg["status"] == "ACT", "week"].unique())
            absent = sorted(pg.loc[pg["status"].isin(["INA", "RES"]), "week"].unique())
            if not absent or len(present) < 3:
                continue
            # Must have been a real contributor when active.
            own = sh[(sh["player_id"] == pid) & sh["week"].isin(present)]
            if own.empty or own["share"].mean() < 0.08:
                continue

            for metric, msh in sh.groupby("metric"):
                a = msh[msh["week"].isin(present)].groupby(
                    "player_id")["share"].agg(["mean", "count"])
                b = msh[msh["week"].isin(absent)].groupby(
                    "player_id")["share"].agg(["mean", "count"])
                j = a.join(b, lsuffix="_with", rsuffix="_without", how="inner")
                j = j[j.index != pid]
                j["delta"] = j["mean_without"] - j["mean_with"]
                j = j[j["delta"] > 0.01]
                for mate, r in j.sort_values("delta", ascending=False).head(5).iterrows():
                    rows.append({
                        "season": season, "team": team,
                        "out_player": names.loc[pid, "full_name"] if pid in names.index else pid,
                        "out_pos": names.loc[pid, "position"] if pid in names.index else "",
                        "metric": metric,
                        "beneficiary": names.loc[mate, "full_name"] if mate in names.index else mate,
                        "benef_pos": names.loc[mate, "position"] if mate in names.index else "",
                        "share_with": round(r["mean_with"], 4),
                        "share_without": round(r["mean_without"], 4),
                        "delta": round(r["delta"], 4),
                        "n_with": int(r["count_with"]),
                        "n_without": int(r["count_without"]),
                    })

    out = pd.DataFrame(rows)
    path = os.path.join(CACHE_DIR, "beneficiaries.csv")
    out.to_csv(path, index=False)
    print(f"wrote {len(out)} rows -> {path}")
    if len(out):
        thin = (out["n_without"] <= MIN_GAMES).mean()
        print(f"{thin:.0%} of rows rest on {MIN_GAMES} games or fewer.")


# ------------------------------------------------------------- line tracking

def log_line(team, player, market, line, over, under, note):
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = pd.DataFrame([{
        "date": date, "team": team, "player": player, "market": market,
        "line": line, "over": over, "under": under, "note": note or "",
    }])
    if os.path.exists(LINES_FILE):
        row.to_csv(LINES_FILE, mode="a", header=False, index=False)
    else:
        row.to_csv(LINES_FILE, index=False)
    print(f"logged {player} {market} {line} ({date})")


def load_lines():
    if not os.path.exists(LINES_FILE):
        return pd.DataFrame()
    d = pd.read_csv(LINES_FILE)
    return d.sort_values("date")


def show_lines():
    d = load_lines()
    if d.empty:
        print("no lines logged yet. use: log --team X --player Y --market rec_yds --line 34.5")
        return
    print("\n--- LINE MOVEMENT ---")
    for (team, player, market), g in d.groupby(["team", "player", "market"]):
        first, last = g.iloc[0], g.iloc[-1]
        move = last["line"] - first["line"]
        arrow = "flat" if abs(move) < 0.01 else (f"+{move:.1f}" if move > 0 else f"{move:.1f}")
        print(f"  {team:4} {player:22} {market:10} "
              f"{first['line']:6.1f} ({first['date']}) -> "
              f"{last['line']:6.1f} ({last['date']})  {arrow}  [{len(g)} logs]")
    print()


def line_status(team, player):
    d = load_lines()
    if d.empty:
        return None
    m = d[(d["team"] == team) & (d["player"].str.lower() == str(player).lower())]
    if m.empty:
        return None
    first, last = m.iloc[0], m.iloc[-1]
    return first["line"], last["line"], last["date"], last["market"]


# ------------------------------------------------------------------ reports

def _beneficiaries(team, surname, limit=3, indent=8):
    path = os.path.join(CACHE_DIR, "beneficiaries.csv")
    if not os.path.exists(path):
        print(" " * indent + "(run build-map first)")
        return []
    b = pd.read_csv(path)
    m = b[(b["team"] == team) & match_player(b["out_player"], surname)]
    if m.empty:
        print(" " * indent + "no absence on record - check depth chart instead")
        return []
    names = []
    for _, r in m.sort_values("delta", ascending=False).head(limit).iterrows():
        n = int(r["n_without"])
        flag = "  [anecdote]" if n <= MIN_GAMES else ""
        print(" " * indent + f"-> {r['beneficiary']:18} {r['metric']:8} "
              f"{r['share_with']:.1%} -> {r['share_without']:.1%} "
              f"(+{r['delta']:.1%}, n={n}/{int(r['n_with'])}){flag}")
        names.append(r["beneficiary"])
        st = line_status(team, r["beneficiary"])
        if st:
            f_, l_, dt, mk = st
            move = l_ - f_
            if abs(move) < 0.01:
                print(" " * (indent + 3) + f"LINE UNMOVED: {mk} {l_} as of {dt}  <-- actionable")
            else:
                print(" " * (indent + 3) + f"line {mk} {f_} -> {l_} ({move:+.1f}) as of {dt}")
    return names


def snapshot():
    os.makedirs(SNAP_DIR, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fname = f"{today}.csv"
    cur = load_today()
    cur.to_csv(os.path.join(SNAP_DIR, fname), index=False)

    prev, prev_date = prior_snapshot(fname)
    weeks = sorted(int(w) for w in cur["week"].dropna().unique())
    print(f"\n=== INJURY BRIEF {today} (vs {prev_date or 'first run'}) ===")
    print(f"{len(cur)} rows, week {weeks}\n")

    usage = usage_table()

    if prev is None:
        print("Baseline saved, nothing to diff yet.\n")
    else:
        prev = prev.drop_duplicates(subset="key").set_index("key")
        changes = []
        for _, row in cur.drop_duplicates(subset="key").iterrows():
            k = row["key"]
            if k not in prev.index:
                changes.append(("NEW", row, None))
                continue
            p = prev.loc[k]
            if (row["practice_status"] != p["practice_status"]
                    or row["report_status"] != p["report_status"]):
                tag = "WORSE" if row["severity"] > p["severity"] else "BETTER"
                changes.append((tag, row, p))

        if not changes:
            print("No status changes since last snapshot.")
            print("If this repeats all week, the feed is not refreshing daily "
                  "and you should pull team reports manually.\n")
        else:
            changes.sort(key=lambda c: (c[1]["position"] not in SKILL,
                                        -c[1]["severity"]))
            for tag, row, p in changes:
                mark = "*" if row["position"] in SKILL else " "
                was = "" if p is None else (f"   was {p['practice_status']}"
                                            f" / {p['report_status']}")
                rest = "  (rest day)" if row["rest_day"] else ""  # noqa
                print(f"{mark}[{tag:6}] {row['team']:4} {row['full_name']:24} "
                      f"{row['position']:3} {row['ailment']:22} "
                      f"{row['practice_status']} / {row['report_status']}"
                      f"{rest}{was}")
                if (row["position"] in SKILL and tag in ("WORSE", "NEW")
                        and not (row["rest_only"] and row["report_status"] == "None")):
                    _beneficiaries(row["team"], str(row["full_name"]))
            print()

    _at_risk(cur, usage)
    show_lines()


def _at_risk(cur, usage):
    s = cur[cur["position"].isin(SKILL) & (cur["severity"] > 0)].copy()
    if s.empty:
        print("No skill players on the report.")
        return
    if not usage.empty:
        s = s.merge(usage[["team", "player", "snap_pct", "season"]].rename(
                        columns={"season": "usage_season"}),
                    left_on=["team", "full_name"], right_on=["team", "player"],
                    how="left")
        s["snap_pct"] = s["snap_pct"].fillna(0)
        s["stale"] = s["usage_season"].fillna(0) != SEASON
        s = s[s["snap_pct"] >= USAGE_FLOOR]
    s = s.sort_values("severity", ascending=False)
    print(f"--- SKILL PLAYERS AT RISK (snap share >= {USAGE_FLOOR:.0%}) ---")
    for _, r in s.iterrows():
        tag = " (prior yr usage)" if r.get("stale") else ""
        rest = "  (rest day)" if r["rest_day"] else ""
        print(f"  {r['team']:4} {r['full_name']:24} {r['position']:3} "
              f"{r['snap_pct']:.0%}{tag:18} {r['ailment']:22} "
              f"{r['practice_status']} / {r['report_status']}{rest}")
    print()



# --------------------------------------------------------- redistribution

def _current_shares():
    """Current-season share by player, falling back to prior season."""
    for seasons, tag in (([SEASON], "current"), ([PRIOR_SEASON], "prior")):
        sh = _shares(seasons)
        if sh.empty:
            continue
        agg = (sh.groupby(["team", "player_id", "metric"], as_index=False)
                 .agg(share=("share", "mean"), games=("week", "nunique")))
        if len(agg) > 200:
            agg["basis"] = tag
            return agg
    return pd.DataFrame()


def _names():
    frames = []
    for s in (SEASON, PRIOR_SEASON):
        try:
            d = nfl.load_rosters_weekly(seasons=[s]).to_pandas()
            if len(d):
                frames.append(d[["week", "team", "gsis_id", "full_name", "position"]])
        except Exception:
            pass
    r = pd.concat(frames, ignore_index=True).sort_values("week")
    return r.drop_duplicates(subset="gsis_id", keep="last").set_index("gsis_id")


# How vacated volume flows between positions. These are judgment weights, not
# fitted values. I tried calibrating them from the absence data and the result
# was confounded: the cache keeps only the top 5 beneficiaries per event, and
# mean delta per player favours position groups with fewer players in them.
# Adjust these by hand as you learn what each offence actually does.
DEFAULT_AFFINITY = {
    ("WR", "WR"): 1.00, ("WR", "TE"): 0.55, ("WR", "RB"): 0.30,
    ("TE", "TE"): 1.00, ("TE", "WR"): 0.70, ("TE", "RB"): 0.35,
    ("RB", "RB"): 1.00, ("RB", "WR"): 0.45, ("RB", "TE"): 0.40,
    ("QB", "QB"): 1.00,
}


def project(team, player_name, metric=None):
    """Estimate where an injured player's volume goes, for any player."""
    shares = _current_shares()
    if shares.empty:
        print("no share data")
        return
    names = _names()
    basis = shares["basis"].iloc[0]

    roster = names[names["team"] == team]
    hit = roster[match_player(roster["full_name"], player_name)]
    if hit.empty:
        hit = roster[roster["full_name"].str.contains(player_name, case=False,
                                                      na=False)]
    if hit.empty:
        print(f"no {player_name} found on {team}")
        return
    pid = hit.index[0]
    pos = hit.iloc[0]["position"]
    print(f"\nIf {hit.iloc[0]['full_name']} ({team}, {pos}) is out "
          f"[{basis}-season usage]:\n")

    aff = DEFAULT_AFFINITY
    ts = shares[shares["team"] == team].copy()
    ts["position"] = ts["player_id"].map(names["position"])
    ts["name"] = ts["player_id"].map(names["full_name"])
    ts = ts[ts["position"].isin(SKILL)]
    # Prior-season shares include players who have since left. Keep only men
    # currently rostered by this team.
    try:
        now = nfl.load_rosters_weekly(seasons=[SEASON]).to_pandas()
        if len(now):
            on_team = set(now.loc[now["team"] == team, "gsis_id"])
            dropped = ts[~ts["player_id"].isin(on_team)]["name"].dropna().unique()
            ts = ts[ts["player_id"].isin(on_team)]
            if len(dropped):
                print(f"  (excluded, no longer on {team}: {', '.join(sorted(dropped)[:6])})\n")
    except Exception:
        pass

    for m in ([metric] if metric else sorted(ts["metric"].unique())):
        block = ts[ts["metric"] == m]
        out_row = block[block["player_id"] == pid]
        if out_row.empty or out_row["share"].iloc[0] < 0.02:
            continue
        vacated = float(out_row["share"].iloc[0])
        rest = block[block["player_id"] != pid].copy()
        if rest.empty:
            continue
        rest["w"] = rest.apply(
            lambda r: r["share"] * aff.get((pos, r["position"]), 0.3), axis=1)
        if rest["w"].sum() <= 0:
            continue
        rest["gain"] = vacated * rest["w"] / rest["w"].sum()
        rest["projected"] = rest["share"] + rest["gain"]
        rest["pct_up"] = rest["gain"] / rest["share"].replace(0, pd.NA)

        print(f"  {m}: {vacated:.1%} of team volume to redistribute")
        for _, r in rest.sort_values("gain", ascending=False).head(5).iterrows():
            up = f"+{r['pct_up']:.0%}" if pd.notna(r["pct_up"]) else "  n/a"
            print(f"    {str(r['name']):22} {r['position']:3} "
                  f"{r['share']:5.1%} -> {r['projected']:5.1%}  ({up} volume)")
        print()

    print("  Model assumption: volume flows to existing share, weighted by")
    print("  position. Real coaches are lumpier than this. Cross-check against")
    print("  the beneficiaries command where that player has absence history.\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot")
    sub.add_parser("build-map")
    sub.add_parser("lines")
    pr = sub.add_parser("project")
    pr.add_argument("--team", required=True)
    pr.add_argument("--player", required=True)
    pr.add_argument("--metric", default=None)
    b = sub.add_parser("beneficiaries")
    b.add_argument("--team", required=True)
    b.add_argument("--player", required=True)
    lg = sub.add_parser("log")
    for f in ("team", "player", "market"):
        lg.add_argument(f"--{f}", required=True)
    lg.add_argument("--line", required=True, type=float)
    lg.add_argument("--over", default="")
    lg.add_argument("--under", default="")
    lg.add_argument("--note", default="")
    a = ap.parse_args()

    if a.cmd == "snapshot":
        snapshot()
    elif a.cmd == "build-map":
        build_map()
    elif a.cmd == "lines":
        show_lines()
    elif a.cmd == "project":
        project(a.team, a.player, a.metric)
    elif a.cmd == "log":
        log_line(a.team, a.player, a.market, a.line, a.over, a.under, a.note)
    else:
        print(f"\nIf {a.player} ({a.team}) is out:")
        _beneficiaries(a.team, a.player, limit=8, indent=4)
        print()


if __name__ == "__main__":
    main()
