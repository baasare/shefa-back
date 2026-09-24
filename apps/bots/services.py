import asyncio
import re
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN

from django.db import transaction
from django.utils import timezone

from apps.bots.events import record_bot_event
from apps.bots.llm import BotAIError, suggest_trade
from apps.bots.models import Bot, BotRun
from apps.brokers.models import BrokerConnection
from apps.brokers.services import get_broker_client
from apps.orders.models import Order


class BotExecutionError(Exception):
    pass


def paper_connection_for(bot):
    return BrokerConnection.objects.filter(
        user=bot.user,
        portfolio=bot.portfolio,
        broker='alpaca_paper',
        status='active',
        is_paper_trading=True,
    ).first()


def _as_aware(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone=timezone.utc)
    return value


def _validate_quote(quote):
    if not quote or not quote.get('bid') or not quote.get('ask') or not quote.get('timestamp'):
        raise BotExecutionError('Market quote is incomplete; no order was submitted.')
    bid = Decimal(quote['bid'])
    ask = Decimal(quote['ask'])
    if bid <= 0 or ask <= 0 or bid > ask:
        raise BotExecutionError('Market quote is invalid; no order was submitted.')
    timestamp = _as_aware(quote['timestamp'])
    if timezone.now() - timestamp > timedelta(minutes=5):
        raise BotExecutionError('Market quote is more than five minutes old; no order was submitted.')
    return bid, ask


def _order_quantity(action, max_order_value, quote, position):
    if action == 'buy':
        quantity = int((max_order_value / quote['ask']).to_integral_value(rounding=ROUND_DOWN))
        return max(0, quantity)
    if action == 'sell' and position:
        maximum_shares = int((max_order_value / quote['bid']).to_integral_value(rounding=ROUND_DOWN))
        return min(int(position['quantity']), max(0, maximum_shares))
    return 0


def execute_paper_run(run_id):
    with transaction.atomic():
        run = BotRun.objects.select_for_update().select_related(
            'bot__user', 'bot__portfolio'
        ).get(id=run_id)
        if run.status != 'queued':
            return run
        bot = Bot.objects.select_for_update().get(id=run.bot_id)
        if bot.status != 'active':
            run.status = 'cancelled'
            run.completed_at = timezone.now()
            run.save(update_fields=['status', 'completed_at'])
            record_bot_event(bot, 'run_cancelled', 'Bot was paused or stopped before this run began.', run=run)
            return run
        connection = paper_connection_for(bot)
        if bot.portfolio.portfolio_type != 'paper' or not connection:
            raise BotExecutionError('A verified Alpaca paper connection is required; no order was submitted.')
        run.status = 'running'
        run.started_at = timezone.now()
        run.save(update_fields=['status', 'started_at'])

    record_bot_event(bot, 'run_started', 'AI paper-trading run started.', run=run)

    try:
        client = get_broker_client(connection)
        # Defense in depth: the connection's server-selected API base URL must be paper.
        if getattr(client, 'paper', False) is not True:
            raise BotExecutionError('Execution client is not paper-only; no order was submitted.')

        account, positions, clock = asyncio.run(_read_account_snapshot(client))
        if account.get('trading_blocked') or str(account.get('status', '')).lower() != 'active':
            raise BotExecutionError('The brokerage account is not eligible to trade; no order was submitted.')
        if not clock['is_open']:
            result = {'message': 'U.S. market is closed. No order was submitted.', 'decisions': []}
            _finish_run(bot, run, result=result)
            return run

        last_equity = Decimal(account['last_equity'])
        portfolio_value = Decimal(account['portfolio_value'])
        daily_pnl_pct = (
            ((portfolio_value - last_equity) / last_equity) * Decimal('100')
            if last_equity > 0 else Decimal('-100')
        )
        decisions = []
        held = {p['symbol']: p for p in positions if p.get('side') == 'long' and int(p.get('quantity', 0)) > 0}
        submitted_buy_value = Decimal('0')

        for symbol in bot.symbols:
            current_bot = Bot.objects.only('status').get(id=bot.id)
            if current_bot.status != 'active':
                record_bot_event(bot, 'run_cancelled', 'Bot was paused or stopped; no further orders will be submitted.', run=run)
                break

            try:
                quote = asyncio.run(client.get_quote(symbol))
                _, ask = _validate_quote(quote)
                bars = asyncio.run(client.get_daily_bars(symbol, limit=20))
                if len(bars) < 5:
                    raise BotExecutionError(f'Not enough recent market data for {symbol}; no order was submitted.')

                snapshot = {
                    'portfolio_value_usd': str(portfolio_value),
                    'daily_pnl_pct': str(daily_pnl_pct.quantize(Decimal('0.01'))),
                    'open_positions': len(held),
                    'position_symbols': list(held.keys()),
                }
                suggestion = suggest_trade(bot=bot, symbol=symbol, quote=quote, bars=bars, portfolio=snapshot)
                decision = {
                    'symbol': symbol,
                    'action': suggestion.action,
                    'explanation': suggestion.explanation,
                    'data_timestamp': _as_aware(quote['timestamp']).isoformat(),
                    'order_id': None,
                }

                record_bot_event(
                    bot,
                    'analysis_update',
                    f'AI suggested {suggestion.action.upper()} for {symbol}.',
                    run=run,
                    data=decision,
                )

                if suggestion.action == 'hold':
                    decisions.append(decision)
                    continue
                if daily_pnl_pct <= -Decimal(bot.daily_loss_limit_pct):
                    decision['blocked_reason'] = 'Daily loss limit reached.'
                    decisions.append(decision)
                    record_bot_event(bot, 'risk_check', decision['blocked_reason'], run=run, data=decision)
                    continue

                position = held.get(symbol)
                if suggestion.action == 'buy' and position:
                    decision['blocked_reason'] = 'A position in this symbol is already open.'
                elif suggestion.action == 'buy' and len(held) >= bot.max_open_positions:
                    decision['blocked_reason'] = 'Maximum open positions reached.'
                elif suggestion.action == 'sell' and not position:
                    decision['blocked_reason'] = 'There is no open position in this symbol to sell.'
                else:
                    current_bot = Bot.objects.only('status').get(id=bot.id)
                    if current_bot.status != 'active':
                        record_bot_event(bot, 'run_cancelled', 'Bot was paused or stopped before an order could be submitted.', run=run)
                        break
                    if suggestion.action == 'buy':
                        # Refresh buying power and holdings after each symbol so a
                        # multi-symbol run cannot spend the same cash repeatedly.
                        refreshed_account = asyncio.run(client.get_account_info())
                        refreshed_positions = asyncio.run(client.get_positions())
                        account['buying_power'] = refreshed_account['buying_power']
                        held = {
                            item['symbol']: item for item in refreshed_positions
                            if item.get('side') == 'long' and int(item.get('quantity', 0)) > 0
                        }
                        if symbol in held:
                            decision['blocked_reason'] = 'A position in this symbol is already open.'
                            decisions.append(decision)
                            record_bot_event(bot, 'risk_check', decision['blocked_reason'], run=run, data=decision)
                            continue
                        if len(held) >= bot.max_open_positions:
                            decision['blocked_reason'] = 'Maximum open positions reached.'
                            decisions.append(decision)
                            record_bot_event(bot, 'risk_check', decision['blocked_reason'], run=run, data=decision)
                            continue
                    else:
                        refreshed_positions = asyncio.run(client.get_positions())
                        held = {
                            item['symbol']: item for item in refreshed_positions
                            if item.get('side') == 'long' and int(item.get('quantity', 0)) > 0
                        }
                        position = held.get(symbol)
                        if not position:
                            decision['blocked_reason'] = 'There is no open position in this symbol to sell.'
                            decisions.append(decision)
                            record_bot_event(bot, 'risk_check', decision['blocked_reason'], run=run, data=decision)
                            continue
                    allowed_order_value = Decimal(bot.max_order_value)
                    if suggestion.action == 'buy':
                        allowed_order_value = min(
                            max(Decimal('0'), Decimal(bot.max_order_value) - submitted_buy_value),
                            Decimal(account['buying_power']),
                        )
                    quantity = _order_quantity(
                        suggestion.action,
                        allowed_order_value,
                        {'ask': ask, 'bid': _validate_quote(quote)[0]},
                        position,
                    )
                    if quantity < 1:
                        decision['blocked_reason'] = 'The order limit is below the price of one whole share.'
                    else:
                        order = _submit_paper_order(
                            client=client,
                            bot=bot,
                            run=run,
                            symbol=symbol,
                            action=suggestion.action,
                            quantity=quantity,
                            explanation=suggestion.explanation,
                        )
                        decision['order_id'] = str(order.id)
                        decision['order_status'] = order.status
                        if suggestion.action == 'buy':
                            held[symbol] = {'symbol': symbol, 'quantity': quantity, 'side': 'long'}
                            submitted_buy_value += Decimal(quantity) * ask
                        else:
                            held.pop(symbol, None)
                decisions.append(decision)
                if decision.get('blocked_reason'):
                    record_bot_event(bot, 'risk_check', decision['blocked_reason'], run=run, data=decision)
            except BotAIError:
                raise
            except Exception as exc:
                decisions.append({'symbol': symbol, 'action': 'none', 'error': str(exc)[:300]})
                record_bot_event(bot, 'error', f'No action taken for {symbol}: {str(exc)[:300]}', run=run)

        result = {'decisions': decisions}
        _finish_run(bot, run, result=result)
        return run
    except Exception as exc:
        _fail_run(bot, run, str(exc))
        return run


async def _read_account_snapshot(client):
    account = await client.get_account_info()
    positions = await client.get_positions()
    clock = client.get_market_clock()
    return account, positions, clock


def _submit_paper_order(*, client, bot, run, symbol, action, quantity, explanation):
    client_order_id = f"sf3-{run.id.hex[:28]}-{symbol[:6]}"
    prior = Order.objects.filter(portfolio=bot.portfolio, broker_order_id=client_order_id).first()
    if prior:
        return prior

    order = Order.objects.create(
        portfolio=bot.portfolio,
        symbol=symbol,
        order_type='market',
        side=action,
        quantity=quantity,
        agent_rationale=explanation,
        status='pending',
        broker_order_id=client_order_id,
    )
    record_bot_event(
        bot,
        'order_created',
        f'{action.title()} {quantity} {symbol} submitted to Alpaca paper.',
        run=run,
        data={'order_id': str(order.id), 'symbol': symbol, 'side': action, 'quantity': quantity, 'mode': 'alpaca_paper'},
    )

    try:
        response = asyncio.run(client.submit_order(
            symbol=symbol,
            quantity=quantity,
            side=action,
            order_type='market',
            time_in_force='day',
            client_order_id=client_order_id,
        ))
    except Exception:
        # A timeout can happen after the provider accepted an order. Look it up
        # by the stable client ID; never blindly retry a possibly accepted order.
        try:
            response = client.get_order_by_client_id(client_order_id)
        except Exception as lookup_exc:
            order.status = 'failed'
            order.error_message = 'Provider response uncertain; lookup failed. Manual review required.'
            order.save(update_fields=['status', 'error_message', 'updated_at'])
            record_bot_event(bot, 'error', order.error_message, run=run, data={'order_id': str(order.id)})
            raise BotExecutionError('Order submission result is uncertain; automatic retry was prevented.') from lookup_exc

    order.broker_order_id = response['broker_order_id']
    order.status = response['status']
    order.submitted_at = response.get('submitted_at') or timezone.now()
    order.filled_qty = response.get('filled_qty') or 0
    order.filled_avg_price = response.get('filled_avg_price')
    if response.get('filled_at'):
        order.filled_at = response['filled_at']
    order.save(update_fields=[
        'broker_order_id', 'status', 'submitted_at', 'filled_qty',
        'filled_avg_price', 'filled_at', 'updated_at',
    ])
    record_bot_event(
        bot,
        'order_updated',
        f'Order {order.status} at Alpaca paper.',
        run=run,
        data={'order_id': str(order.id), 'broker_order_id': order.broker_order_id, 'status': order.status},
    )
    return order


def _finish_run(bot, run, *, result):
    run.status = 'completed'
    run.result = result
    run.completed_at = timezone.now()
    run.save(update_fields=['status', 'result', 'completed_at'])
    Bot.objects.filter(id=bot.id).update(
        last_run_at=run.completed_at,
        next_run_at=run.completed_at + timedelta(minutes=bot.run_frequency_minutes),
    )
    record_bot_event(bot, 'run_completed', 'Paper bot run completed.', run=run, data={'decision_count': len(result.get('decisions', []))})


def _fail_run(bot, run, message):
    safe_message = message[:450]
    run.status = 'failed'
    run.error_message = safe_message
    run.completed_at = timezone.now()
    run.save(update_fields=['status', 'error_message', 'completed_at'])
    Bot.objects.filter(id=bot.id, status='active').update(status='error', next_run_at=None)
    record_bot_event(bot, 'error', safe_message, run=run)
    record_bot_event(bot, 'bot_status', 'Bot paused because a run needs attention.', run=run)
