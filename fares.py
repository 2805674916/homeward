"""Resolve each distinct ticketed segment once and reuse it across itineraries."""
from collections import Counter


def ticket_key(leg):
    return (leg['train_no'], leg['qfrom'], leg['qto'], leg['seat_types'], leg['date'])


def hydrate(plans, fetch, choose, max_queries, remaining_queries, retry=None):
    groups = {}
    usage = Counter()
    for plan in plans:
        for leg in plan['legs']:
            key = ticket_key(leg)
            groups.setdefault(key, leg)
            usage[key] += 1
    ranks = {key: min(len(plan['legs']) for plan in plans
                       if any(ticket_key(x) == key for x in plan['legs']))
             for key in groups}
    ordered = sorted(groups, key=lambda key: (-usage[key], ranks[key], key))
    results, failures, used = {}, {}, 0
    for key in ordered:
        if used >= max_queries or remaining_queries() <= 0:
            failures[key] = '查询额度不足'
            continue
        leg = groups[key]
        used += 1
        try:
            payload = fetch(leg)
        except (RuntimeError, ValueError, KeyError):
            payload = None
        if not payload and retry is not None and used < max_queries and remaining_queries() > 0:
            used += 1
            try:
                payload = retry(leg)
            except (RuntimeError, ValueError, KeyError):
                payload = None
        if payload:
            results[key] = payload
        else:
            failures[key] = '12306 未返回票价'
    for plan in plans:
        total, all_priced = 0.0, True
        for leg in plan['legs']:
            key = ticket_key(leg)
            value = choose(results.get(key), leg['seats'])
            leg['price'] = value
            if value is None:
                all_priced = False
                leg['price_status'] = failures.get(key, '可买席别没有对应报价')
            else:
                total += value
                leg['price_status'] = '已核价'
        plan['price_pp'] = round(total, 1) if all_priced and not plan.get('buy_short') else None
        plan['price_status'] = ('车上补票区间不可预先核价' if plan.get('buy_short') else
                                '已核价' if all_priced else '部分区间待核价')
    return {'unique_legs': len(groups), 'requests': used,
            'priced_legs': len(results),
            'priced_plans': sum(p['price_pp'] is not None for p in plans),
            'unpriced': failures}
