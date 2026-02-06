**변경 1: 상수 추가**  
파일: `finance_platform/server/config.py`
```diff
@@
 BALANCE_SNAPSHOT_INTERVAL_MINUTES = 60
 FEATURED_STOCK_TICKERS = [...]
 FEATURED_CRYPTO_TICKERS = [...]
 FEATURED_INDEX_SOURCES = {...}
 
+# mock investment auto-trade
+MOCK_INVESTMENT_INTERVAL_MINUTES = 10
+MOCK_INVESTMENT_MIN_CASH_RATIO = 0.10
+MOCK_INVESTMENT_STOP_LOSS_PCT = -0.08
+MOCK_INVESTMENT_TAKE_PROFIT_PCT = 0.15
+MOCK_INVESTMENT_REBALANCE_BAND = 0.15
+MOCK_INVESTMENT_PARTIAL_SELL_RATIO = 0.30
+MOCK_INVESTMENT_MIN_TRADE_KRW = 10000
```

**변경 2: 매매 실행 로직 추가**  
파일: `finance_platform/server/services/mock_investment.py`
```python
def _apply_sell(holdings, symbol, qty, price, reason, trade_log, timestamp):
    if qty <= 0 or price is None or price <= 0:
        return 0.0
    holding, index = _get_holding(holdings, symbol)
    if holding is None:
        return 0.0

    current_qty = _get_quantity(holding)
    sell_qty = min(current_qty, qty)
    if sell_qty <= 0:
        return 0.0

    remaining = current_qty - sell_qty
    if remaining <= 0:
        holdings.pop(index)
    else:
        avg_price = _get_avg_price(holding)
        name = holding.get('name') or symbol
        record = build_holding_record(CATEGORY, symbol, name, remaining, avg_price, 'KRW', holding)
        holdings[index] = record

    amount = sell_qty * price
    trade_log.append({
        'timestamp': timestamp,
        'action': 'sell',
        'symbol': symbol,
        'quantity': sell_qty,
        'price': price,
        'amount_krw': amount,
        'reason': reason
    })
    return amount


def _apply_buy(holdings, symbol, qty, price, reason, trade_log, timestamp):
    if qty <= 0 or price is None or price <= 0:
        return 0.0

    holding, index = _get_holding(holdings, symbol)
    current_qty = _get_quantity(holding)
    avg_price = _get_avg_price(holding)

    new_qty = current_qty + qty
    if current_qty <= 0 or avg_price <= 0:
        new_avg = price
    else:
        new_avg = (current_qty * avg_price + qty * price) / new_qty

    name = holding.get('name') if holding else symbol
    record = build_holding_record(CATEGORY, symbol, name, new_qty, new_avg, 'KRW', holding)

    if holding is None:
        holdings.append(record)
    else:
        holdings[index] = record

    amount = qty * price
    trade_log.append({
        'timestamp': timestamp,
        'action': 'buy',
        'symbol': symbol,
        'quantity': qty,
        'price': price,
        'amount_krw': amount,
        'reason': reason
    })
    return amount


def run_mock_investment_autotrade():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, account_name
        FROM account_balances
        WHERE category = ?
    ''', (CATEGORY,))
    accounts = cursor.fetchall()
    if not accounts:
        conn.close()
        return

    signals = build_mock_investment_signals(cursor)
    signal_by_symbol = {info['symbol']: info for info in signals.values() if info.get('symbol')}

    for account in accounts:
        account_id = account['id']
        account_name = account['account_name']
        metadata = read_account_metadata(CATEGORY, account_id) or {
            'account_id': account_id,
            'category': CATEGORY,
            'account_name': account_name,
            'holdings': [],
            'history': []
        }

        holdings = list(metadata.get('holdings', []))
        cash = parse_float(metadata.get('cash_krw') or metadata.get('cashKrw') or 0.0, 0.0)

        price_by_symbol = {symbol: info.get('price') for symbol, info in signal_by_symbol.items()}
        total_value = _estimate_total_value(holdings, cash, price_by_symbol)
        if total_value <= 0:
            continue

        min_cash = total_value * MOCK_INVESTMENT_MIN_CASH_RATIO
        investable = max(total_value - min_cash, 0.0)
        target_per_symbol = investable / max(1, len(signal_by_symbol))

        now_ts = datetime.now(KST).isoformat(timespec='seconds')
        trade_log = []

        for symbol, info in signal_by_symbol.items():
            price = info.get('price')
            if price is None or price <= 0:
                continue
            holding, _ = _get_holding(holdings, symbol)
            if not holding:
                continue
            avg_price = _get_avg_price(holding)
            if avg_price <= 0:
                continue
            pnl = (price - avg_price) / avg_price
            if pnl <= MOCK_INVESTMENT_STOP_LOSS_PCT:
                qty = _round_quantity(_get_quantity(holding))
                cash += _apply_sell(holdings, symbol, qty, price, 'stop_loss', trade_log, now_ts)
            elif pnl >= MOCK_INVESTMENT_TAKE_PROFIT_PCT:
                qty = _round_quantity(_get_quantity(holding))
                cash += _apply_sell(holdings, symbol, qty, price, 'take_profit', trade_log, now_ts)

        if cash < min_cash:
            needed = min_cash - cash
            candidates = []
            for symbol, info in signal_by_symbol.items():
                price = info.get('price')
                if price is None or price <= 0:
                    continue
                holding, _ = _get_holding(holdings, symbol)
                if not holding:
                    continue
                qty = _get_quantity(holding)
                value = qty * price
                if value <= 0:
                    continue
                decision = info.get('decision')
                candidates.append((decision == 'sell', value, symbol, price, qty))
            candidates.sort(reverse=True)

            for _, value, symbol, price, qty in candidates:
                if needed <= 0:
                    break
                sell_value = min(value, needed)
                if sell_value < MOCK_INVESTMENT_MIN_TRADE_KRW:
                    continue
                sell_qty = _round_quantity(sell_value / price)
                if sell_qty <= 0:
                    continue
                cash += _apply_sell(holdings, symbol, sell_qty, price, 'cash_floor', trade_log, now_ts)
                needed = max(0.0, min_cash - cash)

        for symbol, info in signal_by_symbol.items():
            if info.get('decision') != 'sell':
                continue
            price = info.get('price')
            if price is None or price <= 0:
                continue
            holding, _ = _get_holding(holdings, symbol)
            if not holding:
                continue
            qty = _get_quantity(holding)
            if qty <= 0:
                continue

            current_value = qty * price
            desired_value = target_per_symbol
            if current_value > desired_value * (1 + MOCK_INVESTMENT_REBALANCE_BAND):
                sell_value = current_value - desired_value
            else:
                sell_value = current_value * MOCK_INVESTMENT_PARTIAL_SELL_RATIO

            if sell_value < MOCK_INVESTMENT_MIN_TRADE_KRW:
                continue
            sell_qty = _round_quantity(sell_value / price)
            if sell_qty <= 0:
                continue
            cash += _apply_sell(holdings, symbol, sell_qty, price, 'signal_sell', trade_log, now_ts)

        for symbol, info in signal_by_symbol.items():
            if info.get('decision') != 'buy':
                continue
            price = info.get('price')
            if price is None or price <= 0:
                continue

            holding, _ = _get_holding(holdings, symbol)
            current_value = 0.0
            if holding:
                qty = _get_quantity(holding)
                if qty > 0:
                    current_value = qty * price

            if current_value >= target_per_symbol * (1 - MOCK_INVESTMENT_REBALANCE_BAND):
                continue

            available_cash = max(0.0, cash - min_cash)
            if available_cash < MOCK_INVESTMENT_MIN_TRADE_KRW:
                continue
            buy_value = min(target_per_symbol - current_value, available_cash)
            if buy_value < MOCK_INVESTMENT_MIN_TRADE_KRW:
                continue

            buy_qty = _round_quantity(buy_value / price)
            if buy_qty <= 0:
                continue
            cost = _apply_buy(holdings, symbol, buy_qty, price, 'signal_buy', trade_log, now_ts)
            cash -= cost

        if not trade_log:
            continue

        metadata['cash_krw'] = round(cash, 2)
        metadata['holdings'] = holdings
        auto_trade = metadata.get('auto_trade') or {}
        auto_trade['last_run_at'] = now_ts
        recent = auto_trade.get('recent_trades', [])
        recent.extend(trade_log)
        auto_trade['recent_trades'] = recent[-MAX_TRADE_LOG:]
        metadata['auto_trade'] = auto_trade

        write_account_metadata(CATEGORY, account_id, metadata)

        new_total = _estimate_total_value(holdings, cash, price_by_symbol)
        cursor.execute('''
            UPDATE account_balances
            SET balance = ?, last_updated = ?
            WHERE id = ? AND category = ?
        ''', (new_total, now_ts, account_id, CATEGORY))
        conn.commit()

        append_account_history(CATEGORY, account_id, account_name, new_total, source='auto-trade')
        print(f"[INFO] Mock investment auto-trade executed for {account_name} (trades={len(trade_log)})")

    conn.close()
```

**변경 3: 백그라운드 스레드 추가**  
파일: `finance_platform/server/jobs/background.py`
```diff
@@
 from ..config import (
     BALANCE_SNAPSHOT_INTERVAL_MINUTES,
     FEATURED_CRYPTO_TICKERS,
     FEATURED_INDEX_SOURCES,
     FEATURED_STOCK_TICKERS,
     KST,
+    MOCK_INVESTMENT_INTERVAL_MINUTES,
 )
@@
 from ..services.settings import get_data_collection_settings, get_hourly_snapshot_enabled
 from ..services.snapshots import record_hourly_snapshot
 from ..services.realtime import broadcast_event
+from ..services.mock_investment import run_mock_investment_autotrade
@@
 def _next_interval_mark(now, interval_minutes):
@@
     return next_run
+
+
+def mock_investment_autotrade_worker():
+    time.sleep(10)
+    while True:
+        try:
+            now = datetime.now(KST)
+            next_run = _next_interval_mark(now, MOCK_INVESTMENT_INTERVAL_MINUTES)
+            sleep_seconds = max(0, (next_run - now).total_seconds())
+            if sleep_seconds > 0:
+                print(
+                    f"[INFO] Next mock investment auto-trade at {next_run.strftime('%H:%M:%S')} "
+                    f"(in {sleep_seconds:.0f} seconds)"
+                )
+                time.sleep(sleep_seconds)
+
+            run_mock_investment_autotrade()
+
+            next_run = _next_interval_mark(datetime.now(KST) + timedelta(seconds=1), MOCK_INVESTMENT_INTERVAL_MINUTES)
+            print(f"[INFO] Next mock investment auto-trade scheduled for {next_run.strftime('%H:%M:%S')}")
+
+        except Exception as exc:
+            print(f"[ERROR] Error in mock_investment_autotrade_worker: {exc}")
+            import traceback
+            traceback.print_exc()
+            time.sleep(60)
@@
 def start_minute_data_collection_thread():
     """Start background thread for 5-minute data collection."""
     thread = threading.Thread(target=minute_data_collection_worker, daemon=True)
     thread.start()
     print("[INFO] Started 5-minute data collection background thread")
+
+
+def start_mock_investment_autotrade_thread():
+    thread = threading.Thread(target=mock_investment_autotrade_worker, daemon=True)
+    thread.start()
+    print("[INFO] Started mock investment auto-trade background thread")
```

**변경 4: 부트스트랩에서 스레드 시작**  
파일: `finance_platform/server/bootstrap.py`
```diff
@@
-from .jobs.background import start_hourly_snapshot_thread, start_minute_data_collection_thread
+from .jobs.background import (
+    start_hourly_snapshot_thread,
+    start_minute_data_collection_thread,
+    start_mock_investment_autotrade_thread,
+)
@@
         start_hourly_snapshot_thread()
         start_minute_data_collection_thread()
+        start_mock_investment_autotrade_thread()
         print("[INFO] Background threads started in main worker process")
```

**동작 요약**
1. 10분마다(KST, 00/10/20/30/40/50분 기준) 자동 수행.
2. MACD/RSI/볼린저 중 **2개 이상 일치 시 매수/매도**.
3. **현금 10% 최소 유지**. 부족하면 현금 확보용 매도 수행.
4. **손절 -8%, 익절 +15%** 기본 적용.
5. **리밸런싱 밴드 15%**와 **부분 매도 30%**로 과열/과매도 구간에서 비중 조절.
6. 관심 4종목(`BTC/ETH/XRP/SOL`)만 거래.

**바로 진행하려면**
1. `finance_platform`를 `/home/dinya/Personal-Finance-Manager/codex_agent` 아래로 복사/이동해 주세요. 그러면 제가 직접 수정하고 적용까지 끝낼게요.
2. 아니면 위 패치를 그대로 적용해 주시면 되고, 적용 후 알려주시면 제가 빠르게 검증 포인트와 로그 확인 방법까지 정리해드릴게요.

덧붙여, 현재 권한 제한으로 `/home/dinya/Personal-Finance-Manager/history.md`에 기록을 못 해서 같은 요약을 `codex_agent/history_pending.md`에 남겨두었습니다.
User: 이전의 답변 내용을 md 파일로 저장해줘.
Assistant: 그 요청, 깔끔하게 정리해두는 게 딱 맞아요. 이전 답변 내용을 `previous_response.md`로 저장해두었습니다.

파일: `previous_response.md`

원하시면 파일명 변경이나 다른 위치로 이동도 바로 도와줄게요.  
다음으로 원하시는 작업이 있을까요?  
1. 파일명 변경  
2. 다른 경로로 이동  
3. 내용 일부 수정
