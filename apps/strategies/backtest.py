"""
Backtesting engine for strategy validation and optimization.

Simulates strategy execution on historical data to evaluate performance.
"""
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, date, timedelta
from django.utils import timezone
from dataclasses import dataclass, field
import logging
import statistics

from .models import Strategy, Backtest
from .services import StrategyEvaluator
from apps.market_data.provider_manager import get_provider_manager

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """Represents a trade in backtest."""
    symbol: str
    entry_date: date
    entry_price: Decimal
    quantity: int
    side: str  # 'buy' or 'sell'
    exit_date: Optional[date] = None
    exit_price: Optional[Decimal] = None
    pnl: Optional[Decimal] = None
    pnl_pct: Optional[Decimal] = None
    is_open: bool = True
    entry_reason: List[str] = field(default_factory=list)
    exit_reason: List[str] = field(default_factory=list)


@dataclass
class BacktestState:
    """Represents backtest state at a point in time."""
    date: date
    cash: Decimal
    positions_value: Decimal
    total_value: Decimal
    open_positions: int
    trades_count: int


class BacktestEngine:
    """
    Backtesting engine that simulates strategy execution on historical data.
    """

    def __init__(
        self,
        strategy: Strategy,
        start_date: date,
        end_date: date,
        initial_capital: Decimal
    ):
        """
        Initialize backtest engine.

        Args:
            strategy: Strategy to backtest
            start_date: Start date for backtest
            end_date: End date for backtest
            initial_capital: Starting capital
        """
        self.strategy = strategy
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital

        self.cash = initial_capital
        self.positions: Dict[str, BacktestTrade] = {}  # symbol -> open trade
        self.closed_trades: List[BacktestTrade] = []
        self.equity_curve: List[BacktestState] = []

        self.evaluator = StrategyEvaluator(strategy)

        logger.info(f"Initialized BacktestEngine for {strategy.name} ({start_date} to {end_date})")

    async def run(self) -> Backtest:
        """
        Run backtest and return results.

        Returns:
            Backtest instance with results
        """
        try:
            logger.info(f"Starting backtest for strategy {self.strategy.id}")

            # Fetch historical data for all symbols
            historical_data = await self._fetch_historical_data()

            if not historical_data:
                raise Exception("No historical data available")

            # Get all trading dates
            trading_dates = sorted(set(
                bar['date']
                for bars in historical_data.values()
                for bar in bars
            ))

            # Simulate trading for each date
            for current_date in trading_dates:
                await self._simulate_trading_day(current_date, historical_data)

            # Close any remaining open positions
            await self._close_all_positions(trading_dates[-1], historical_data)

            # Calculate metrics
            metrics = self._calculate_metrics()

            # Create backtest record
            backtest = await self._create_backtest_record(metrics)

            logger.info(f"Backtest completed: {len(self.closed_trades)} trades, {metrics['total_return']:.2f}% return")

            return backtest

        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            # Create failed backtest record
            backtest = Backtest.objects.create(
                strategy=self.strategy,
                start_date=self.start_date,
                end_date=self.end_date,
                initial_capital=self.initial_capital,
                status='failed',
                error_message=str(e)
            )
            raise

    async def _fetch_historical_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch historical data for all symbols in watchlist.

        Returns:
            Dictionary mapping symbol to list of bars
        """
        provider_manager = get_provider_manager()
        historical_data = {}

        for symbol in self.strategy.watchlist:
            try:
                bars = await provider_manager.get_historical_bars(
                    symbol=symbol,
                    start_date=self.start_date,
                    end_date=self.end_date,
                    timeframe='1d',
                    use_cache=True
                )

                if bars:
                    # Add date field for easier lookup
                    for bar in bars:
                        if 'date' not in bar:
                            bar['date'] = bar.get('timestamp', self.start_date).date() if hasattr(bar.get('timestamp', self.start_date), 'date') else bar.get('timestamp', self.start_date)

                    historical_data[symbol] = bars
                    logger.debug(f"Fetched {len(bars)} bars for {symbol}")

            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}")

        return historical_data

    async def _simulate_trading_day(
        self,
        current_date: date,
        historical_data: Dict[str, List[Dict[str, Any]]]
    ):
        """
        Simulate trading for a single day.

        Args:
            current_date: Date to simulate
            historical_data: Historical price data
        """
        # Update equity curve
        self._record_equity_state(current_date, historical_data)

        # Check exit conditions for open positions
        await self._check_exit_conditions(current_date, historical_data)

        # Check entry conditions for new positions
        if len(self.positions) < self.strategy.max_positions:
            await self._check_entry_conditions(current_date, historical_data)

    async def _check_entry_conditions(
        self,
        current_date: date,
        historical_data: Dict[str, List[Dict[str, Any]]]
    ):
        """Check entry conditions and open new positions."""
        for symbol in self.strategy.watchlist:
            # Skip if already have position
            if symbol in self.positions:
                continue

            # Skip if max positions reached
            if len(self.positions) >= self.strategy.max_positions:
                break

            # Get data up to current date
            bars = self._get_bars_up_to_date(symbol, current_date, historical_data)
            if not bars:
                continue

            # Evaluate strategy (simplified - using last 30 days of data)
            recent_bars = bars[-30:] if len(bars) >= 30 else bars
            current_price = Decimal(str(bars[-1]['close']))

            # Calculate indicators
            indicators = await self.evaluator._calculate_indicators(recent_bars)

            # Evaluate entry rules
            entry_signal, entry_reasons = self.evaluator._evaluate_entry_rules(
                indicators, current_price
            )

            if entry_signal:
                # Calculate position size
                quantity = self._calculate_position_size(current_price)

                if quantity > 0:
                    # Open position
                    trade = BacktestTrade(
                        symbol=symbol,
                        entry_date=current_date,
                        entry_price=current_price,
                        quantity=quantity,
                        side='buy',
                        entry_reason=entry_reasons
                    )

                    cost = current_price * quantity
                    if cost <= self.cash:
                        self.cash -= cost
                        self.positions[symbol] = trade
                        logger.debug(f"Opened position: {symbol} @ ${current_price} ({quantity} shares)")

    async def _check_exit_conditions(
        self,
        current_date: date,
        historical_data: Dict[str, List[Dict[str, Any]]]
    ):
        """Check exit conditions and close positions."""
        symbols_to_close = []

        for symbol, trade in self.positions.items():
            bars = self._get_bars_up_to_date(symbol, current_date, historical_data)
            if not bars:
                continue

            current_price = Decimal(str(bars[-1]['close']))

            # Check exit rules
            should_exit, exit_reasons = await self._evaluate_exit_conditions(
                trade, current_price, bars
            )

            if should_exit:
                # Close position
                trade.exit_date = current_date
                trade.exit_price = current_price
                trade.pnl = (current_price - trade.entry_price) * trade.quantity
                trade.pnl_pct = ((current_price - trade.entry_price) / trade.entry_price) * 100
                trade.is_open = False
                trade.exit_reason = exit_reasons

                # Add cash
                self.cash += current_price * trade.quantity

                self.closed_trades.append(trade)
                symbols_to_close.append(symbol)

                logger.debug(f"Closed position: {symbol} @ ${current_price}, P&L: ${trade.pnl:.2f}")

        # Remove closed positions
        for symbol in symbols_to_close:
            del self.positions[symbol]

    async def _evaluate_exit_conditions(
        self,
        trade: BacktestTrade,
        current_price: Decimal,
        bars: List[Dict[str, Any]]
    ) -> Tuple[bool, List[str]]:
        """Evaluate exit conditions for a trade."""
        exit_rules = self.strategy.exit_rules
        if not exit_rules:
            return False, []

        reasons = []
        should_exit = False

        # Profit target
        if 'profit_target' in exit_rules:
            target_pct = Decimal(str(exit_rules['profit_target'].get('percentage', 5.0)))
            profit_pct = ((current_price - trade.entry_price) / trade.entry_price) * 100

            if profit_pct >= target_pct:
                should_exit = True
                reasons.append(f"Profit target reached ({profit_pct:.2f}%)")

        # Stop loss
        if 'stop_loss' in exit_rules:
            stop_pct = Decimal(str(exit_rules['stop_loss'].get('percentage', 2.0)))
            loss_pct = ((trade.entry_price - current_price) / trade.entry_price) * 100

            if loss_pct >= stop_pct:
                should_exit = True
                reasons.append(f"Stop loss hit ({loss_pct:.2f}%)")

        # RSI exit
        if 'rsi_exit' in exit_rules and len(bars) >= 14:
            from apps.market_data.indicators import calculate_rsi
            closes = [bar['close'] for bar in bars[-30:]]
            rsi_values = calculate_rsi(closes, 14)

            if rsi_values:
                rsi = rsi_values[-1]
                threshold = exit_rules['rsi_exit'].get('threshold', 70)

                if rsi > threshold:
                    should_exit = True
                    reasons.append(f"RSI exit ({rsi:.2f} > {threshold})")

        return should_exit, reasons

    async def _close_all_positions(
        self,
        final_date: date,
        historical_data: Dict[str, List[Dict[str, Any]]]
    ):
        """Close all remaining open positions at end of backtest."""
        for symbol, trade in list(self.positions.items()):
            bars = self._get_bars_up_to_date(symbol, final_date, historical_data)
            if not bars:
                continue

            current_price = Decimal(str(bars[-1]['close']))

            trade.exit_date = final_date
            trade.exit_price = current_price
            trade.pnl = (current_price - trade.entry_price) * trade.quantity
            trade.pnl_pct = ((current_price - trade.entry_price) / trade.entry_price) * 100
            trade.is_open = False
            trade.exit_reason = ["Backtest end"]

            self.cash += current_price * trade.quantity
            self.closed_trades.append(trade)

        self.positions = {}

    def _get_bars_up_to_date(
        self,
        symbol: str,
        current_date: date,
        historical_data: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Get bars for symbol up to current date."""
        if symbol not in historical_data:
            return []

        return [
            bar for bar in historical_data[symbol]
            if bar['date'] <= current_date
        ]

    def _calculate_position_size(self, current_price: Decimal) -> int:
        """Calculate position size based on strategy parameters."""
        position_value = self.cash * (self.strategy.position_size_pct / 100)
        quantity = int(position_value / current_price)
        return quantity

    def _record_equity_state(
        self,
        current_date: date,
        historical_data: Dict[str, List[Dict[str, Any]]]
    ):
        """Record current equity state."""
        # Calculate positions value
        positions_value = Decimal('0')

        for symbol, trade in self.positions.items():
            bars = self._get_bars_up_to_date(symbol, current_date, historical_data)
            if bars:
                current_price = Decimal(str(bars[-1]['close']))
                positions_value += current_price * trade.quantity

        total_value = self.cash + positions_value

        state = BacktestState(
            date=current_date,
            cash=self.cash,
            positions_value=positions_value,
            total_value=total_value,
            open_positions=len(self.positions),
            trades_count=len(self.closed_trades)
        )

        self.equity_curve.append(state)

    def _calculate_metrics(self) -> Dict[str, Any]:
        """Calculate backtest performance metrics."""
        if not self.closed_trades:
            return self._get_empty_metrics()

        final_value = self.cash + sum(
            trade.exit_price * trade.quantity
            for trade in self.positions.values()
        )

        # Basic metrics
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100

        winning_trades = [t for t in self.closed_trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in self.closed_trades if t.pnl and t.pnl <= 0]

        win_rate = (len(winning_trades) / len(self.closed_trades)) * 100 if self.closed_trades else 0

        avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else Decimal('0')
        avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else Decimal('0')

        # Calculate daily returns for Sharpe ratio
        daily_returns = []
        for i in range(1, len(self.equity_curve)):
            prev_value = float(self.equity_curve[i-1].total_value)
            curr_value = float(self.equity_curve[i].total_value)
            if prev_value > 0:
                daily_return = (curr_value - prev_value) / prev_value
                daily_returns.append(daily_return)

        sharpe_ratio = self._calculate_sharpe_ratio(daily_returns)
        sortino_ratio = self._calculate_sortino_ratio(daily_returns)
        max_drawdown = self._calculate_max_drawdown()

        # Annualized return
        days = (self.end_date - self.start_date).days
        years = days / 365.25
        annual_return = (((final_value / self.initial_capital) ** (1 / years)) - 1) * 100 if years > 0 else 0

        return {
            'final_capital': final_value,
            'total_return': total_return,
            'annual_return': annual_return,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': len(self.closed_trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'avg_trade_pnl': sum(t.pnl for t in self.closed_trades) / len(self.closed_trades) if self.closed_trades else Decimal('0')
        }

    def _calculate_sharpe_ratio(self, daily_returns: List[float], risk_free_rate: float = 0.04) -> Optional[Decimal]:
        """Calculate Sharpe ratio."""
        if not daily_returns or len(daily_returns) < 2:
            return None

        avg_return = statistics.mean(daily_returns)
        std_return = statistics.stdev(daily_returns)

        if std_return == 0:
            return None

        # Annualize
        annual_return = avg_return * 252
        annual_std = std_return * (252 ** 0.5)

        sharpe = (annual_return - risk_free_rate) / annual_std

        return Decimal(str(round(sharpe, 4)))

    def _calculate_sortino_ratio(self, daily_returns: List[float], risk_free_rate: float = 0.04) -> Optional[Decimal]:
        """Calculate Sortino ratio (uses downside deviation)."""
        if not daily_returns or len(daily_returns) < 2:
            return None

        avg_return = statistics.mean(daily_returns)

        # Downside deviation (only negative returns)
        downside_returns = [r for r in daily_returns if r < 0]
        if not downside_returns:
            return None

        downside_std = statistics.stdev(downside_returns) if len(downside_returns) > 1 else 0

        if downside_std == 0:
            return None

        # Annualize
        annual_return = avg_return * 252
        annual_downside_std = downside_std * (252 ** 0.5)

        sortino = (annual_return - risk_free_rate) / annual_downside_std

        return Decimal(str(round(sortino, 4)))

    def _calculate_max_drawdown(self) -> Decimal:
        """Calculate maximum drawdown."""
        if not self.equity_curve:
            return Decimal('0')

        peak = float(self.initial_capital)
        max_dd = Decimal('0')

        for state in self.equity_curve:
            value = float(state.total_value)

            if value > peak:
                peak = value

            drawdown = ((peak - value) / peak) * 100 if peak > 0 else 0
            if drawdown > float(max_dd):
                max_dd = Decimal(str(drawdown))

        return max_dd

    def _get_empty_metrics(self) -> Dict[str, Any]:
        """Return empty metrics when no trades."""
        return {
            'final_capital': self.cash,
            'total_return': Decimal('0'),
            'annual_return': Decimal('0'),
            'sharpe_ratio': None,
            'sortino_ratio': None,
            'max_drawdown': Decimal('0'),
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': Decimal('0'),
            'avg_win': Decimal('0'),
            'avg_loss': Decimal('0'),
            'avg_trade_pnl': Decimal('0')
        }

    async def _create_backtest_record(self, metrics: Dict[str, Any]) -> Backtest:
        """Create backtest database record."""
        backtest = Backtest.objects.create(
            strategy=self.strategy,
            start_date=self.start_date,
            end_date=self.end_date,
            initial_capital=self.initial_capital,
            final_capital=metrics['final_capital'],
            total_return=metrics['total_return'],
            annual_return=metrics['annual_return'],
            sharpe_ratio=metrics['sharpe_ratio'],
            sortino_ratio=metrics['sortino_ratio'],
            max_drawdown=metrics['max_drawdown'],
            total_trades=metrics['total_trades'],
            winning_trades=metrics['winning_trades'],
            losing_trades=metrics['losing_trades'],
            win_rate=metrics['win_rate'],
            avg_trade_pnl=metrics['avg_trade_pnl'],
            status='completed',
            completed_at=timezone.now(),
            results={
                'trades': [
                    {
                        'symbol': t.symbol,
                        'entry_date': t.entry_date.isoformat(),
                        'entry_price': float(t.entry_price),
                        'exit_date': t.exit_date.isoformat() if t.exit_date else None,
                        'exit_price': float(t.exit_price) if t.exit_price else None,
                        'quantity': t.quantity,
                        'pnl': float(t.pnl) if t.pnl else None,
                        'pnl_pct': float(t.pnl_pct) if t.pnl_pct else None
                    }
                    for t in self.closed_trades
                ]
            },
            equity_curve=[
                {
                    'date': state.date.isoformat(),
                    'value': float(state.total_value),
                    'cash': float(state.cash),
                    'positions_value': float(state.positions_value)
                }
                for state in self.equity_curve
            ]
        )

        return backtest


async def run_backtest(
    strategy: Strategy,
    start_date: date,
    end_date: date,
    initial_capital: Decimal
) -> Backtest:
    """
    Convenience function to run a backtest.

    Args:
        strategy: Strategy to backtest
        start_date: Start date
        end_date: End date
        initial_capital: Starting capital

    Returns:
        Backtest instance with results

    Example:
        >>> from datetime import date
        >>> backtest = await run_backtest(
        >>>     strategy=my_strategy,
        >>>     start_date=date(2023, 1, 1),
        >>>     end_date=date(2024, 1, 1),
        >>>     initial_capital=Decimal('100000')
        >>> )
        >>> print(f"Return: {backtest.total_return}%")
        >>> print(f"Win rate: {backtest.win_rate}%")
    """
    engine = BacktestEngine(strategy, start_date, end_date, initial_capital)
    return await engine.run()
