from sqlalchemy.orm import Session
from sqlalchemy import text


def get_live_pnl(db: Session) -> list:
    query = text("""
        SELECT
            p.ticker,
            p.shares,
            p.avg_buy_price,
            sp.close   AS ltp,
            sp.date    AS price_date
        FROM portfolio p
        LEFT JOIN stock_prices sp ON sp.ticker = p.ticker
          AND sp.date = (
              SELECT MAX(date) FROM stock_prices WHERE ticker = p.ticker
          )
        ORDER BY p.ticker
    """)

    rows = db.execute(query).fetchall()
    results = []

    for row in rows:
        invested = round(row.shares * row.avg_buy_price, 2)

        if row.ltp is None:
            results.append({
                "ticker": row.ticker, "shares": row.shares,
                "avg_buy_price": row.avg_buy_price, "ltp": None,
                "invested": invested, "current_value": None,
                "pnl": None, "pnl_pct": None, "price_date": None,
            })
            continue

        current_value = round(row.shares * row.ltp, 2)
        pnl = round(current_value - invested, 2)
        pnl_pct = round((pnl / invested) * 100, 2) if invested else 0

        results.append({
            "ticker": row.ticker,
            "shares": row.shares,
            "avg_buy_price": round(row.avg_buy_price, 2),
            "ltp": round(row.ltp, 2),
            "invested": invested,
            "current_value": current_value,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "price_date": str(row.price_date)[:10],
        })

    return results


def print_pnl_table(results: list):
    print("\n" + "=" * 84)
    print(f"{'Ticker':<16} {'Shares':>7} {'Avg Cost':>10} {'LTP':>10} "
          f"{'Invested':>12} {'Value':>12} {'P&L':>10} {'P&L%':>7}")
    print("-" * 84)

    total_invested = total_value = 0

    for r in results:
        if r["ltp"] is None:
            print(f"{r['ticker']:<16} {r['shares']:>7.2f} "
                  f"{r['avg_buy_price']:>10.2f} {'N/A':>10} "
                  f"{r['invested']:>12.2f} {'N/A':>12} {'N/A':>10} {'N/A':>7}")
            continue

        sign = "+" if r["pnl"] >= 0 else ""
        print(f"{r['ticker']:<16} {r['shares']:>7.2f} "
              f"{r['avg_buy_price']:>10.2f} {r['ltp']:>10.2f} "
              f"{r['invested']:>12.2f} {r['current_value']:>12.2f} "
              f"{sign}{r['pnl']:>9.2f} {sign}{r['pnl_pct']:>5.2f}%")

        total_invested += r["invested"]
        total_value += r["current_value"]

    total_pnl = round(total_value - total_invested, 2)
    total_pct = round((total_pnl / total_invested) * 100, 2) if total_invested else 0
    sign = "+" if total_pnl >= 0 else ""

    print("=" * 84)
    print(f"{'TOTAL':<55} {total_invested:>12.2f} {total_value:>12.2f} "
          f"{sign}{total_pnl:>9.2f} {sign}{total_pct:>5.2f}%")
    print("=" * 84)
