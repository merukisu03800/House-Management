#!/usr/bin/env python3
"""住宅購入シミュレーター（標準ライブラリのみ）

使い方:
    python3 sim/loan_simulator.py                 # params.py の内容で全レポート
    python3 sim/loan_simulator.py --price 6000    # 物件価格(万円)を上書き
    python3 sim/loan_simulator.py --help

前提・簡略化:
- 元利均等返済。ボーナス払いなし。
- 変動金利の「5年ルール・125%ルール」は考慮しない（毎年再計算する厳しめの試算）。
- 住宅ローン控除・税金・団信保険料の差は考慮しない。
"""
import argparse
import copy

from params import PARAMS


def monthly_payment(principal: float, annual_rate_pct: float, years: int) -> float:
    """元利均等返済の月額（principal と同じ単位で返す）"""
    n = years * 12
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return principal / n
    return principal * r * (1 + r) ** n / ((1 + r) ** n - 1)


def max_loan(monthly: float, annual_rate_pct: float, years: int) -> float:
    """月額 monthly で返せる最大借入額"""
    return monthly / monthly_payment(1.0, annual_rate_pct, years)


def rising_rate_total(principal: float, start_rate: float, step: float,
                      every_years: int, cap: float, years: int):
    """変動金利が every_years 年ごとに step% 上がる場合の、年ごとの月額と総返済額"""
    balance = principal
    total = 0.0
    schedule = []
    for y in range(years):
        rate = min(start_rate + step * (y // every_years), cap)
        pay = monthly_payment(balance, rate, years - y)
        r = rate / 100 / 12
        for _ in range(12):
            interest = balance * r
            balance -= pay - interest
            total += pay
        schedule.append((y + 1, rate, pay))
    return schedule, total


def man(x: float) -> str:
    """万円表記"""
    return f"{x:,.0f}万円"


def yen(x_man: float) -> str:
    """万円 → 円表記（月額表示用）"""
    return f"{x_man * 10000:,.0f}円"


def report(p: dict) -> None:
    price = p["price_man"]
    cost = price * p["purchase_cost_ratio"]
    down = price * p["down_payment_ratio"]
    loan = price - down
    years = p["loan_years"]
    income = p["income_after_child_man"]

    print("=" * 60)
    print(f"■ 前提: 物件 {man(price)} / 頭金 {man(down)} / 借入 {man(loan)} / {years}年")
    print("=" * 60)

    # 1. 必要な自己資金
    print("\n[1] 購入時に必要な現金")
    need = down + cost
    print(f"  頭金          {man(down)}  (価格の{p['down_payment_ratio']:.0%})")
    print(f"  諸費用        {man(cost)}  (価格の{p['purchase_cost_ratio']:.0%})")
    print(f"  合計          {man(need)}")
    months = p["months_until_purchase"]
    gap = need - p["current_savings_man"]
    if gap > 0:
        print(f"  → 現在の貯金 {man(p['current_savings_man'])} から {months}ヶ月で"
              f" 月 {man(gap / months)} の積立が必要")
    else:
        print("  → 現在の貯金で到達済み")

    # 1b. 頭金比率 × 期間 の逆算表
    print("\n[1b] 目標額の逆算（頭金比率 × 貯める期間 → 毎月の積立額）")
    plan_months = p["saving_months_options"]
    print(f"  {'頭金':>10} {'必要な現金':>10} " + " ".join(f"{str(m) + 'ヶ月':>9}" for m in plan_months))
    for ratio in p["down_payment_options"]:
        target = price * ratio + cost
        remain = max(target - p["current_savings_man"], 0)
        cells = " ".join(f"{man(remain / m):>9}" for m in plan_months)
        print(f"  {ratio:>4.0%}({man(price * ratio):>7}) {man(target):>10} {cells}")
    print(f"  ※必要な現金 = 頭金 + 諸費用。現在の貯金 {man(p['current_savings_man'])} を差し引いて計算")

    # 2. 金利別の月返済額
    print("\n[2] 金利別の月返済額・総返済額")
    print(f"  {'金利':>6} {'月返済':>12} {'総返済':>12} {'うち利息':>10} {'返済負担率':>8}")
    for rate in p["rate_scenarios"]:
        m = monthly_payment(loan, rate, years)
        total = m * 12 * years
        ratio = m * 12 / income
        print(f"  {rate:>5.2f}% {yen(m):>12} {man(total):>12} {man(total - loan):>10}"
              f" {ratio:>8.1%}")
    print(f"  ※返済負担率は 子供誕生後の年収 {man(income)}(額面) 基準")

    # 3. 年収から見た借入上限
    print("\n[3] 年収から逆算した借入上限（額面年収基準）")
    print(f"  {'金利':>6} " + " ".join(f"{'負担率'+format(r, '.0%'):>12}" for r in p["burden_ratios"]))
    for rate in p["rate_scenarios"]:
        cells = []
        for br in p["burden_ratios"]:
            cells.append(f"{man(max_loan(income * br / 12, rate, years)):>12}")
        print(f"  {rate:>5.2f}% " + " ".join(cells))

    # 4. 変動金利の上昇シナリオ
    s = p["rising_scenario"]
    print(f"\n[4] 変動金利上昇シナリオ: {s['start_rate']}%から{s['every_years']}年ごとに"
          f"+{s['step']}%（上限{s['cap']}%）")
    sched, total = rising_rate_total(loan, s["start_rate"], s["step"],
                                     s["every_years"], s["cap"], years)
    for y, rate, pay in sched:
        if y == 1 or (y - 1) % s["every_years"] == 0:
            print(f"  {y:>2}年目  金利{rate:.2f}%  月返済 {yen(pay)}")
    fixed = p["fixed_rate_compare"]
    fixed_total = monthly_payment(loan, fixed, years) * 12 * years
    print(f"  総返済: 変動シナリオ {man(total)} / 全期間固定{fixed}% {man(fixed_total)}")

    # 5. 毎月の住居費 vs 現在
    print("\n[5] 毎月の住居費（購入後） vs 現在の家賃")
    base_rate = p["base_rate"]
    m = monthly_payment(loan, base_rate, years)
    mgmt = p["management_fee_man"] + p["repair_reserve_man"]
    tax = p["property_tax_annual_man"] / 12
    print(f"  ローン({base_rate}%)  {yen(m)}")
    print(f"  管理費+修繕積立 {yen(mgmt)}  ※修繕積立金は将来上がる前提で見ること")
    print(f"  固定資産税等    {yen(tax)}  (年{man(p['property_tax_annual_man'])}÷12)")
    print(f"  合計            {yen(m + mgmt + tax)}")
    print(f"  現在の家賃      {yen(p['current_rent_man'])}")


def main() -> None:
    p = copy.deepcopy(PARAMS)
    ap = argparse.ArgumentParser(description="住宅購入シミュレーター")
    ap.add_argument("--price", type=float, help="物件価格(万円)")
    ap.add_argument("--down", type=float, help="頭金比率 (例: 0.1)")
    ap.add_argument("--years", type=int, help="返済年数")
    ap.add_argument("--savings", type=float, help="現在の貯金(万円)")
    args = ap.parse_args()
    if args.savings is not None:
        p["current_savings_man"] = args.savings
    if args.price is not None:
        p["price_man"] = args.price
    if args.down is not None:
        p["down_payment_ratio"] = args.down
    if args.years is not None:
        p["loan_years"] = args.years
    report(p)


if __name__ == "__main__":
    main()
