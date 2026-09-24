# -*- coding: utf-8 -*-
"""
train-plan 图搜索: 在铁路走廊图上枚举 直达 / 中转 / 买长乘短 / 买短乘长 方案
候选段模型: e=(j, r, q, a, b) —— 车次 j 实际乘坐 r→q, 购票区间 a→b, 约束 a<=r<b 且区间当前可购。
  b<q 为买短乘长(车上补票, 补票费 12306 无公开接口, 不计总价);
  a<r 为买长乘短(票面覆盖上车站, 保证能上车); 两者同时成立为买长又买短。
换乘约束: 同车分段 τ=2min(不计换乘次数) / 同站 τ=15min / 同城簇跨站 τ=40min / 其余禁止。
用法示例:
  python search.py --from-city 上海 --to-city 武汉 --date YYYY-MM-DD --after 18:00 \
      --arrive-by "YYYY-MM-DD 12:00" --people 2 --budget 800 --out report.html
查询预算默认 260 次(串行限速 3 秒/次, 全程约 15 分钟), 可用 --max-queries 调整。
"""
import argparse, datetime as dt, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib12306 as L
import fares
from coords import coord_of

HERE = os.path.dirname(os.path.abspath(__file__))
SEATS = ("sw", "zy", "ze", "yw", "yz", "rw", "gr", "wz")
SEAT_CN = {"sw": "商务座", "zy": "一等座", "ze": "二等座", "yw": "硬卧", "yz": "硬座",
           "rw": "软卧", "gr": "高级软卧", "wz": "无座"}
SEAT_COMFORT = {"sw": 1.0, "gr": 0.8, "zy": 0.6, "rw": 0.5, "yw": 0.3, "ze": 0.2, "yz": -0.6, "wz": -1.8}
BUDGET = {"n": 0}
FARES_RESERVE = 50          # 留给票价核验的查询额度
EDGE_RESERVE = FARES_RESERVE + 60
TRANSFER_FLOOR = {"同车分段": 2, "同站换乘": 15, "跨站换乘": 40}

def qbudget(max_q):
    BUDGET["n"] += 1
    if BUDGET["n"] > max_q:
        raise RuntimeError("查询预算(%d)用尽, 已基于当前数据出报告" % max_q)

def tickets(date, frm, to, max_q):
    qbudget(max_q)
    return L.tickets(date, frm, to)

def sched(train_no, frm, to, date, max_q):
    qbudget(max_q)
    return L.schedule(train_no, frm, to, date)

def seat_count(v):
    """余票张数: '有' 视为充足; 候补/无/空 不可购。"""
    if v == "有":
        return 99
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0

def row_seats(r):
    return {k: seat_val(r[k]) for k in SEATS if r.get(k) not in (None, "", "无", "候补", "0", 0)}

def seat_val(v):
    return None if v in ("", "无") else ("候补" if v == "候补" else v)

def has_seat(r, people=1, classes=SEATS):
    """当前可直接购买, 且可买张数合计覆盖 people(不同席别可拆单购买)。"""
    if r["buy"] != "Y":
        return False
    total = 0
    for k in classes:
        v = r.get(k)
        if v in (None, "", "无", "候补"):
            continue
        total += seat_count(v)
        if total >= people:
            return True
    return total >= people

def parse_hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)

def lishi_min(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)

def dep_dt(date, hhmm):
    d = dt.date.fromisoformat(date)
    mins = parse_hhmm(hhmm)
    return dt.datetime.combine(d, dt.time()) + dt.timedelta(minutes=mins)

def arr_dt(dep, lishi):
    return dep + dt.timedelta(minutes=lishi)

def corridor_hubs(o_city, d_city, cap=14):
    """用站点坐标挑出 O→D 走廊带内的候选枢纽: 按城市去重(优先 东 站), 离目的地由近到远"""
    import coords as C
    a, b = C.coord_of(o_city), C.coord_of(d_city)
    if not a or not b:
        return []
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return []
    cand = []
    for st, (x, y) in C.COORDS.items():
        t = ((x - ax) * dx + (y - ay) * dy) / L2
        if not (0.06 <= t <= 0.97):
            continue
        px, py = ax + t * dx, ay + t * dy
        if (x - px) ** 2 + (y - py) ** 2 < 1.2 ** 2:
            city = next((c for c in C.CITY_FALLBACK if st.startswith(c)), st[:2])
            cand.append((t, city, st))
    best = {}
    for t, city, st in sorted(cand, key=lambda kv: -kv[0]):
        if city in best:
            continue
        def pref(suffix):
            m = [s for tt, c, s in cand if c == city and s.endswith(suffix)]
            return m[0] if m else None
        best[city] = pref("东") or pref("南") or pref("北") or st
    return [best[c] for c in sorted(best, key=lambda c: -max(t for t, cc, s in cand if cc == c))][:cap]

# ---------- 城市展开 ----------
def load_city_stations():
    raw = L.station_data_text()
    by_city = {}
    for chunk in raw.split("@")[1:]:
        f = chunk.split("|")
        if len(f) >= 8 and f[2]:
            by_city.setdefault(f[7], []).append((f[1], f[2]))
    return by_city

def build_city_clusters(by_city, max_degree=0.35):
    """同城且坐标相近(<=约20km)的车站归为一个换乘簇: 返回 电报码 -> 簇成员元组(含自身)。"""
    import coords as C
    cluster = {}
    for stations in by_city.values():
        if len(stations) < 2:
            continue
        pts = [(name, code, C.coord_of(name)) for name, code in stations]
        for name1, code1, xy1 in pts:
            if not xy1:
                continue
            members = {code1}
            for name2, code2, xy2 in pts:
                if code2 == code1 or not xy2:
                    continue
                if abs(xy1[0] - xy2[0]) + abs(xy1[1] - xy2[1]) <= max_degree:
                    members.add(code2)
            if len(members) > 1:
                cluster[code1] = tuple(sorted(members))
    return cluster

def primary_station(stations):
    name0, code0 = stations[0]
    for suf in ("东", "南"):
        for name, code in stations:
            if name.endswith(suf):
                return name, code
    return name0, code0

# ---------- 方案构造 ----------
def leg_info(r, date):
    return {
        "date": date, "train": r["code"], "train_no": r["train_no"],
        "from": r["from"], "from_cn": L.STATION.get(r["from"], r["from"]),
        "to": r["to"], "to_cn": L.STATION.get(r["to"], r["to"]),
        "dep": r["dep"], "arr": r["arr"], "lishi": r["lishi"],
        "seats": {SEAT_CN[k]: v for k, v in row_seats(r).items() if v},
        "qfrom": r["qfrom"], "qto": r["qto"], "seat_types": r["seat_types"],
    }

def make_plan(ptype, legs, dates, notes=(), buy_short_info=None, ext_info=None, city_cluster=None):
    dep0 = dep_dt(dates[0], legs[0]["dep"])
    arrN = arr_dt(dep_dt(dates[-1], legs[-1]["dep"]), lishi_min(legs[-1]["lishi"]))
    transfers = []
    for i in range(len(legs) - 1):
        a = arr_dt(dep_dt(dates[i], legs[i]["dep"]), lishi_min(legs[i]["lishi"]))
        b = dep_dt(dates[i + 1], legs[i + 1]["dep"])
        buf = int((b - a).total_seconds() // 60)
        same = legs[i]["to"] == legs[i + 1]["from"]
        if same and legs[i]["train_no"] == legs[i + 1]["train_no"]:
            kind = "同车分段"
        elif same:
            kind = "同站换乘"
        elif city_cluster and legs[i]["to"] in city_cluster.get(legs[i + 1]["from"], ()):
            kind = "跨站换乘"
        else:
            return None  # 非同城衔接, 物理上不可达
        if buf < TRANSFER_FLOOR[kind]:
            return None  # 换乘时间不足
        transfers.append({"station": L.STATION.get(legs[i]["to"], legs[i]["to"]),
                          "buffer_min": buf, "same_station": same, "kind": kind})
    return {"type": ptype, "legs": legs, "dates": dates, "transfers": transfers,
            "dep_dt": dep0.isoformat(sep=" "), "arr_dt": arrN.isoformat(sep=" "),
            "duration_min": int((arrN - dep0).total_seconds() // 60),
            "notes": list(notes), "buy_short": buy_short_info, "ext": ext_info,
            "price_pp": None, "prices": [], "comfort": None}

def comfort_score(plan, people):
    c = 7.0
    for leg in plan["legs"]:
        dur_share = lishi_min(leg["lishi"]) / max(plan["duration_min"], 1)
        inv = {v: k for k, v in SEAT_CN.items()}
        best = max([SEAT_COMFORT.get(inv.get(s), -0.5) for s, v in leg["seats"].items()], default=-1.5)
        c += best * dur_share * 1.6
        if "无座" in leg["seats"]:
            c -= 1.0 * lishi_min(leg["lishi"]) / 60.0 * dur_share
    for t in plan["transfers"]:
        c -= 1.0
        if t["buffer_min"] < 20: c -= 1.0
        if not t["same_station"]: c -= 0.5
    if plan["arr_dt"][11:16] <= "06:30": c -= 1.0
    return round(max(0.0, min(10.0, c)), 1)

PRICE_KEY = {"商务座": ("A9",), "一等座": ("M",), "二等座": ("O",), "硬座": ("A1",),
             "硬卧": ("A3",), "软卧": ("A4",), "高级软卧": ("A6",), "无座": ("WZ",), "动卧": ("F",)}

def _price_for_available(d_price, seats_avail):
    """仅用有余票席别的票价；接口缺少对应席别时保持未知。"""
    if not isinstance(d_price, dict):
        return None
    candidates = []
    for name, available in seats_avail.items():
        if available in (None, "", "无", "候补", "0", 0):
            continue
        for key in PRICE_KEY.get(name, ()):
            value = d_price.get(key)
            try:
                number = float(str(value).strip().replace("¥", "").replace("￥", ""))
            except (TypeError, ValueError):
                continue
            if number > 0:
                candidates.append(number)
    return min(candidates) if candidates else None

# ---------- 候选段枚举(纯函数, 可单测) ----------
def classify_split(ai, bi, i_board, i_alight):
    """购票区间 (ai,bi) 对实际乘坐 (i_board,i_alight) 的方案类型。"""
    supp = bi < i_alight        # 买短乘长: 车上补票
    long_a = ai < i_board       # 票面起点早于上车站
    if supp and long_a:
        return "买长又买短"
    if supp:
        return "买短乘长"
    return "买长乘短"

def split_candidates(seq, i_board, i_alight, max_attempts=8):
    """有界枚举购票区间候选 (a_idx,b_idx): 票面覆盖上车站 a<=r<b, 补票最短/保上车站优先。"""
    out, seen = [], set()
    last = len(seq) - 1
    def add(ai, bi):
        if (ai, bi) in seen or (ai, bi) == (i_board, i_alight):
            return
        if not (0 <= ai <= i_board < bi <= last):
            return
        seen.add((ai, bi))
        out.append((ai, bi))
    add(i_board, i_alight - 1)   # 补最后一小段
    add(i_board, i_alight + 1)   # 买到下一站提前下
    add(i_board - 1, i_alight)   # 前一站买, 保上车站
    add(i_board, last)           # 买到终点
    add(i_board, i_board + 1)    # 最近站短买
    add(i_board, (i_board + i_alight) // 2)
    add(i_board - 2, i_alight)
    add(i_board - 1, last)
    add(i_board - 1, i_alight - 1)
    return out[:max_attempts]

def plan_transfers_k(plan):
    """模型意义上的换乘数: 同车分段不计。"""
    return sum(1 for t in plan["transfers"] if t.get("kind") != "同车分段")

def pareto_filter(plans):
    """按 (票价, 历时, 换乘数, 补票标志) 剔除被支配方案; 未核价方案不与已核价方案互比。"""
    def dims(p):
        return (p.get("price_pp"), p["duration_min"], plan_transfers_k(p),
                1 if p.get("buy_short") else 0)
    keep = []
    for i, p in enumerate(plans):
        dp = dims(p)
        dominated = False
        for j, q in enumerate(plans):
            if i == j:
                continue
            dq = dims(q)
            if dp[0] is None or dq[0] is None:
                continue
            if all(y <= x for y, x in zip(dq, dp)) and any(y < x for y, x in zip(dq, dp)):
                dominated = True
                break
        if not dominated:
            keep.append(p)
    return keep

# ---------- 主搜索 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-city", required=True)
    ap.add_argument("--to-city", required=True)
    ap.add_argument("--date", required=True, help="最早出发日期 YYYY-MM-DD")
    ap.add_argument("--after", default="00:00", help="最早可出发时刻 HH:MM")
    ap.add_argument("--arrive-by", required=True, help="到达截止 'YYYY-MM-DD HH:MM'")
    ap.add_argument("--people", type=int, default=1)
    ap.add_argument("--budget", type=float, default=None, help="单人预算(元)")
    ap.add_argument("--max-transfers", type=int, default=3)
    ap.add_argument("--max-queries", type=int, default=260)
    ap.add_argument("--max-hubs", type=int, default=14)
    ap.add_argument("--out", default="report.html")
    a = ap.parse_args()

    by_city = load_city_stations()
    if a.from_city not in by_city or a.to_city not in by_city:
        print("!! 城市不在站表中:", a.from_city, a.to_city); sys.exit(1)
    O = by_city[a.from_city]; D = by_city[a.to_city]
    city_cluster = build_city_clusters(by_city)
    (o_name, o_code), (d_name, d_code) = primary_station(O), primary_station(D)
    next_day = (dt.date.fromisoformat(a.date) + dt.timedelta(days=1)).isoformat()
    windows = [(a.date, a.after, "23:59"), (next_day, "00:00", "23:59")]  # 出发日+次日全天, 由 arrive-by 兜底过滤
    deadline = dt.datetime.fromisoformat(a.arrive_by)
    plans = []
    network_rows = {}
    def query_edge(day, frm, to):
        key = (day, frm, to)
        if key not in network_rows:
            network_rows[key] = tickets(day, frm, to, a.max_queries)
        return network_rows[key]

    stops_cache = {}
    def train_stops(train_no, frm, to, day):
        key = (train_no, day)
        if key not in stops_cache:
            stops_cache[key] = sched(train_no, frm, to, day, a.max_queries)
        return [s["station"] for s in stops_cache[key]]

    # ---- 0. 直达 ----
    print(">> 直达扫描 %s(%s)→%s(%s), 按 %d 人核验余票" % (o_name, o_code, d_name, d_code, a.people))
    direct_rows = []
    for w_date, w_from, w_to in windows:
        rows = query_edge(w_date, o_code, d_code)
        for r in rows:
            if w_from <= r["dep"] <= w_to:
                r2 = dict(r); r2["_date"] = w_date
                direct_rows.append(r2)
    for r in direct_rows:
        dep = dep_dt(r["_date"], r["dep"])
        if dep < dt.datetime.combine(dt.date.fromisoformat(a.date), dt.time()) + dt.timedelta(minutes=parse_hhmm(a.after)): continue
        arr = arr_dt(dep, lishi_min(r["lishi"]))
        if arr > deadline: continue
        if has_seat(r, a.people):
            plans.append(make_plan("直达", [leg_info(r, r["_date"])], [r["_date"]]))
    plans = [p for p in plans if p]
    print("   直达可行: %d" % len(plans))

    # ---- 中转 hub 采集: 时刻表中间站 + 坐标走廊内插(双保险, 不依赖单一数据源) ----
    hub_freq = {}
    sample = sorted(direct_rows, key=lambda r: lishi_min(r["lishi"]))[:6]
    for r in sample:
        try:
            stops = sched(r["train_no"], r["from"], r["to"], r["_date"], a.max_queries)
        except Exception:
            continue
        seq = [s["station"] for s in stops]
        try:
            i0 = seq.index(L.STATION.get(r["from"], r["from"]))
            i1 = seq.index(L.STATION.get(r["to"], r["to"]))
        except ValueError:
            continue
        for h in seq[i0 + 1: i1]:
            hub_freq[h] = hub_freq.get(h, 0) + 1
    sched_hubs = [h for h, _ in sorted(hub_freq.items(), key=lambda kv: -kv[1])]
    geo_hubs = corridor_hubs(a.from_city, a.to_city)
    merged = list(dict.fromkeys(list(geo_hubs[:3]) + sched_hubs + list(geo_hubs[3:])))[: max(a.max_hubs, 6)]
    hubs = merged
    print(">> 候选中转枢纽:", hubs)

    # ---- 拆票工具: 候选段 e=(j,r,q,a,b) 的购票区间尝试 ----
    def attempt_split_leg(full, day, seq, ai, bi):
        """查询购票区间 seq[ai]→seq[bi] 上该车次是否可购; 命中返回 (leg, a_name, b_name)。
        leg 的 dep/arr/lishi/from/to 已覆盖为实际乘坐区间, qfrom/qto 保留票面区间供核价。"""
        a_name, b_name = seq[ai], seq[bi]
        a_code, b_code = L.NAME.get(a_name), L.NAME.get(b_name)
        if not a_code or not b_code or a_code == b_code:
            return None
        rows = query_edge(day, a_code, b_code)   # 预算耗尽会抛 RuntimeError
        hit = next((x for x in rows if x["train_no"] == full["train_no"]
                    and has_seat(x, a.people)), None)
        if hit is None:
            return None
        leg = leg_info(hit, day)
        leg["from"], leg["to"] = full["from"], full["to"]
        leg["from_cn"] = L.STATION.get(full["from"], full["from"])
        leg["to_cn"] = L.STATION.get(full["to"], full["to"])
        leg["dep"], leg["arr"], leg["lishi"] = full["dep"], full["arr"], full["lishi"]
        return leg, a_name, b_name

    def split_notes(a_name, b_name, board_cn, alight_cn, ai, bi, ib, iq):
        out = []
        if ai < ib:
            out.append("票面 %s→%s：在 %s 上车（票面起点早于实际上车站，保证有票可乘）" % (a_name, b_name, board_cn))
        if bi < iq:
            out.append("票面买到 %s，%s→%s 车上补票（无座，按公布票价，风险自担）" % (b_name, b_name, alight_cn))
        if bi > iq:
            out.append("票面买到 %s，在 %s 提前下车（差价不退）" % (b_name, alight_cn))
        return out

    # ---- 1. 走廊边装载 + 时序 BFS(同车分段不计换乘次数) ----
    soldout = {}
    if a.max_transfers >= 1:
        hub_codes = [L.NAME[h] for h in hubs if h in L.NAME]
        corridor = list(reversed(hub_codes))  # 按出发→到达方向排列
        edges, seen_edges = [], set()

        def add_edge(src, dst):
            if src != dst and (src, dst) not in seen_edges:
                seen_edges.add((src, dst))
                edges.append((src, dst))

        for h in hub_codes:
            add_edge(o_code, h)
            add_edge(h, d_code)
        for idx, src in enumerate(corridor):
            for dst in corridor[idx + 1: idx + 4]:
                add_edge(src, dst)
        adjacency = {}  # 按实际上车站(电报码)存行: 同城合并查询的行可能从簇内任一站发车
        for src, dst in edges:
            if BUDGET["n"] >= a.max_queries - EDGE_RESERVE: break
            for day, low, high in windows:
                try:
                    rows = query_edge(day, src, dst)
                except RuntimeError:
                    break
                pool = soldout.setdefault((src, dst), [])
                for row in rows:
                    if not (low <= row["dep"] <= high):
                        continue
                    depart = dep_dt(day, row["dep"])
                    arrive = arr_dt(depart, lishi_min(row["lishi"]))
                    if arrive > deadline:
                        continue
                    if has_seat(row, a.people):
                        adjacency.setdefault(row["from"], []).append((row, day, depart, arrive))
                    elif len(pool) < 3:
                        pool.append((row, day))

        # BFS: 状态 (站, legs, dates, 前段到达, visited, 已用换乘数k) —— k 只在更换车次时 +1
        frontier = [(o_code, [], [], None, frozenset([o_code]), 0)]
        leg_cap = a.max_transfers + 3
        while frontier:
            following = []
            for station, legs, dates, prior_arrival, visited, kch in frontier:
                prev = legs[-1] if legs else None
                for member in city_cluster.get(station, (station,)):
                    for row, day, depart, arrive in adjacency.get(member, []):
                        if row["from"] != member or row["to"] in visited: continue
                        nk = kch
                        if prev is not None:
                            buffer_min = int((depart - prior_arrival).total_seconds() // 60)
                            if member == prev["to"] and row["train_no"] == prev["train_no"]:
                                if buffer_min < 2: continue          # 同车分段(车内换座)
                            elif member == prev["to"]:
                                if buffer_min < 15: continue         # 同站换乘
                            elif member in city_cluster.get(prev["to"], ()):
                                if buffer_min < 40: continue         # 跨站换乘(同城)
                            else:
                                continue                              # 非同城, 禁止
                            if row["train_no"] != prev["train_no"]:
                                nk += 1
                                if nk > a.max_transfers: continue
                        elif depart < dep_dt(a.date, a.after):
                            continue
                        leg = leg_info(row, day)
                        path, days = legs + [leg], dates + [day]
                        if len(path) > leg_cap: continue
                        reached = row["to"] == d_code or row["to"] in city_cluster.get(d_code, ())
                        if reached:
                            if len(path) >= 2:
                                plan = make_plan("中转", path, days, city_cluster=city_cluster)
                                if plan: plans.append(plan)
                        else:
                            following.append((row["to"], path, days, arrive,
                                              visited | {row["to"]}, nk))
            frontier = following[:8000]
        dedup = {}
        for plan in plans:
            key = tuple((leg["train_no"], leg["from"], leg["to"], leg["date"]) for leg in plan["legs"])
            dedup.setdefault(key, plan)
        plans = list(dedup.values())
    print("   中转枚举后方案: %d" % len(plans))

    # ---- 2. 直达拆票: 对售罄直达车全区间尝试 (a,b) ----
    print(">> 直达拆票扫描(买短乘长/买长乘短/买长又买短) ...")
    pool_direct = sorted((r for r in direct_rows if not has_seat(r, a.people)),
                         key=lambda x: lishi_min(x["lishi"]))
    for r in pool_direct[:8]:
        if a.max_queries - BUDGET["n"] <= FARES_RESERVE + 10: break
        try:
            seq = train_stops(r["train_no"], r["from"], r["to"], r["_date"])
        except Exception:
            continue
        try:
            ib = seq.index(L.STATION.get(r["from"], r["from"]))
            iq = seq.index(L.STATION.get(r["to"], r["to"]))
        except ValueError:
            continue
        board_cn = L.STATION.get(r["from"], r["from"])
        alight_cn = L.STATION.get(r["to"], r["to"])
        for ai, bi in split_candidates(seq, ib, iq, 8):
            if a.max_queries - BUDGET["n"] <= FARES_RESERVE: break
            try:
                got = attempt_split_leg(r, r["_date"], seq, ai, bi)
            except RuntimeError:
                break
            if not got: continue
            leg, a_name, b_name = got
            kind = classify_split(ai, bi, ib, iq)
            p = make_plan(kind, [leg], [r["_date"]],
                          notes=split_notes(a_name, b_name, board_cn, alight_cn, ai, bi, ib, iq),
                          buy_short_info=({"split": b_name, "rest": "%s→%s" % (b_name, alight_cn)}
                                          if bi < iq else None),
                          ext_info=({"beyond": b_name} if bi > iq else None))
            if p: plans.append(p)
    print("   拆票后方案总数: %d" % len(plans))

    # ---- 3. 中转链拆票救援: 售罄的 o→h / h→d 边按拆票重建一程中转 ----
    print(">> 中转链拆票救援 ...")
    d_cluster = city_cluster.get(d_code, (d_code,))
    o_cluster = city_cluster.get(o_code, (o_code,))
    rescue_used = 0
    def rescue_budget():
        return a.max_queries - BUDGET["n"] > FARES_RESERVE - 10 and rescue_used < 24

    def rescue_edge_pool(predicate):
        items = [(k, v) for k, v in soldout.items() if predicate(k) and v]
        return sorted(items, key=lambda kv: lishi_min(kv[1][0][0]["lishi"]))

    def indices_of(full, day):
        try:
            seq = train_stops(full["train_no"], full["from"], full["to"], day)
            ib = seq.index(L.STATION.get(full["from"], full["from"]))
            iq = seq.index(L.STATION.get(full["to"], full["to"]))
            return seq, ib, iq
        except (Exception, ValueError):
            return None, None, None

    # 3a 终点方向售罄(h→d): 前缀取已装载的 o→h 可用行
    for (src, dst), pool in rescue_edge_pool(lambda k: k[1] == d_code or k[1] in d_cluster):
        if not rescue_budget(): break
        for full, day in pool[:1]:
            if not rescue_budget(): break
            seq, ib, iq = indices_of(full, day)
            if seq is None: continue
            src_cn = L.STATION.get(full["from"], full["from"])
            dst_cn = L.STATION.get(full["to"], full["to"])
            made = 0
            for ai, bi in split_candidates(seq, ib, iq, 4):
                if not rescue_budget(): break
                try:
                    got = attempt_split_leg(full, day, seq, ai, bi)
                except RuntimeError:
                    break
                rescue_used += 1
                if not got: continue
                leg2, a_name, b_name = got
                notes = split_notes(a_name, b_name, src_cn, dst_cn, ai, bi, ib, iq)
                for member in city_cluster.get(o_code, (o_code,)):
                    if made >= 6: break
                    for row1, day1, dep1, arr1 in adjacency.get(member, []):
                        if made >= 6: break
                        if row1["to"] != src and row1["to"] not in city_cluster.get(src, ()):
                            continue
                        p = make_plan("中转", [leg_info(row1, day1), leg2], [day1, day],
                                      city_cluster=city_cluster)
                        if not p: continue
                        p["notes"] = p.get("notes", []) + notes
                        if bi < iq:
                            p["buy_short"] = {"split": b_name, "rest": "%s→%s" % (b_name, dst_cn)}
                        plans.append(p); made += 1

    # 3b 出发方向售罄(o→h): 后段取已装载的 h→d 可用行
    for (src, dst), pool in rescue_edge_pool(
            lambda k: (k[0] == o_code or k[0] in o_cluster)
            and not (k[1] == d_code or k[1] in d_cluster)):
        if not rescue_budget(): break
        for full, day in pool[:1]:
            if not rescue_budget(): break
            seq, ib, iq = indices_of(full, day)
            if seq is None: continue
            src_cn = L.STATION.get(full["from"], full["from"])
            dst_cn = L.STATION.get(full["to"], full["to"])
            made = 0
            for ai, bi in split_candidates(seq, ib, iq, 4):
                if not rescue_budget(): break
                try:
                    got = attempt_split_leg(full, day, seq, ai, bi)
                except RuntimeError:
                    break
                rescue_used += 1
                if not got: continue
                leg1, a_name, b_name = got
                notes = split_notes(a_name, b_name, src_cn, dst_cn, ai, bi, ib, iq)
                for member in city_cluster.get(dst, (dst,)):
                    if made >= 6: break
                    for row2, day2, dep2, arr2 in adjacency.get(member, []):
                        if made >= 6: break
                        if row2["to"] != d_code and row2["to"] not in d_cluster:
                            continue
                        p = make_plan("中转", [leg1, leg_info(row2, day2)], [day, day2],
                                      city_cluster=city_cluster)
                        if not p: continue
                        p["notes"] = p.get("notes", []) + notes
                        if bi < iq:
                            p["buy_short"] = {"split": b_name, "rest": "%s→%s" % (b_name, dst_cn)}
                        plans.append(p); made += 1
    print("   救援后方案总数: %d" % len(plans))

    # ---- 4. 核价(按唯一票段去重复用) ----
    def fetch_fare(leg):
        qbudget(a.max_queries)
        return L.price(leg["train_no"], leg["qfrom"], leg["qto"], leg["seat_types"], leg["date"])

    def retry_fare(leg):
        qbudget(a.max_queries)
        url = (L.BASE + "/otn/leftTicket/queryTicketPrice?train_no=%s&from_station_no=%s"
               "&to_station_no=%s&seat_types=%s&train_date=%s"
               % (leg["train_no"], leg["qfrom"], leg["qto"], leg["seat_types"], leg["date"]))
        return L.http_json(url, ttl=0, label="票价重试 " + leg["train_no"]).get("data")

    summary = fares.hydrate(plans, fetch_fare, _price_for_available,
                            a.max_queries - BUDGET["n"],
                            lambda: a.max_queries - BUDGET["n"], retry_fare)
    print("   票价: %d 个唯一票段, %d 次查询, %d/%d 方案完整核价" %
          (summary["unique_legs"], summary["requests"], summary["priced_plans"], len(plans)))

    # ---- 5. Pareto 过滤 + 展示字段 ----
    plans = pareto_filter(plans)
    print(">> Pareto 过滤后 %d 个方案" % len(plans))
    for p in plans:
        p["comfort"] = comfort_score(p, a.people)
        p["over_budget"] = bool(a.budget is not None and p["price_pp"] is not None
                                and p["price_pp"] > a.budget)
        if p["price_pp"] is None:
            reasons = sorted({leg.get("price_status", "") for leg in p["legs"]
                              if leg.get("price") is None})
            if p.get("buy_short"):
                reasons.append("车上补票区间价格未知")
            p.setdefault("notes", []).append("未能完整核价：" + "、".join(reasons))
    plans.sort(key=lambda p: (p["price_pp"] is None, p["price_pp"] or 9e9))
    result = {"params": vars(a), "from_city": a.from_city, "to_city": a.to_city,
              "plans": plans, "generated_at": dt.datetime.now().isoformat(sep=" ", timespec="seconds")}
    print(">> 方案 %d 个" % len(plans))
    import render
    render.render(result, os.path.abspath(a.out))
    print(">> 报告 →", os.path.abspath(a.out))

if __name__ == "__main__":
    main()
