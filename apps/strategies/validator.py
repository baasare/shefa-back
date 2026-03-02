"""
Strategy configuration validation and rule checking.

Validates strategy configurations before execution or backtesting.
"""
from typing import Dict, Any, List, Tuple, Optional
from decimal import Decimal
import logging

from .models import Strategy

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when strategy validation fails."""
    pass


class StrategyValidator:
    """
    Validates strategy configurations and rules.
    """

    VALID_INDICATORS = [
        'rsi', 'macd', 'bollinger_bands', 'sma', 'ema',
        'atr', 'stochastic', 'volume', 'obv', 'adx'
    ]

    VALID_ENTRY_RULES = [
        'rsi_oversold', 'rsi_overbought', 'macd_crossover', 'macd_divergence',
        'price_above_sma', 'price_below_sma', 'price_above_ema', 'price_below_ema',
        'volume_surge', 'bb_lower_touch', 'bb_upper_touch', 'golden_cross', 'death_cross'
    ]

    VALID_EXIT_RULES = [
        'profit_target', 'stop_loss', 'trailing_stop', 'time_exit',
        'rsi_exit', 'macd_exit', 'support_break', 'resistance_break'
    ]

    VALID_TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w']

    def __init__(self, strategy: Strategy):
        """Initialize validator with strategy."""
        self.strategy = strategy
        self.errors = []
        self.warnings = []

    def validate_all(self) -> Tuple[bool, List[str], List[str]]:
        """
        Perform complete validation.

        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        self.errors = []
        self.warnings = []

        # Validate basic configuration
        self._validate_basic_config()

        # Validate risk parameters
        self._validate_risk_parameters()

        # Validate watchlist
        self._validate_watchlist()

        # Validate indicators
        self._validate_indicators()

        # Validate entry rules
        self._validate_entry_rules()

        # Validate exit rules
        self._validate_exit_rules()

        # Validate portfolio association
        self._validate_portfolio()

        is_valid = len(self.errors) == 0

        return is_valid, self.errors, self.warnings

    def _validate_basic_config(self):
        """Validate basic strategy configuration."""
        if not self.strategy.name:
            self.errors.append("Strategy name is required")

        if not self.strategy.strategy_type:
            self.errors.append("Strategy type is required")

        # Validate timeframe if specified
        timeframe = self.strategy.config.get('timeframe')
        if timeframe and timeframe not in self.VALID_TIMEFRAMES:
            self.errors.append(f"Invalid timeframe: {timeframe}. Must be one of {self.VALID_TIMEFRAMES}")

    def _validate_risk_parameters(self):
        """Validate risk management parameters."""
        # Position size
        if self.strategy.position_size_pct <= 0:
            self.errors.append("Position size percentage must be greater than 0")

        if self.strategy.position_size_pct > 100:
            self.errors.append("Position size percentage cannot exceed 100%")

        if self.strategy.position_size_pct > 20:
            self.warnings.append("Position size > 20% is risky. Consider diversification")

        # Max positions
        if self.strategy.max_positions <= 0:
            self.errors.append("Max positions must be at least 1")

        if self.strategy.max_positions > 50:
            self.warnings.append("Max positions > 50 may be difficult to manage")

        # Daily loss limit
        if self.strategy.max_daily_loss_pct <= 0:
            self.warnings.append("No daily loss limit set. Consider adding one for risk management")

        if self.strategy.max_daily_loss_pct > 20:
            self.warnings.append("Daily loss limit > 20% is very risky")

    def _validate_watchlist(self):
        """Validate strategy watchlist."""
        if not self.strategy.watchlist:
            self.warnings.append("Watchlist is empty. Add symbols to trade")
            return

        if not isinstance(self.strategy.watchlist, list):
            self.errors.append("Watchlist must be a list of symbols")
            return

        if len(self.strategy.watchlist) > 100:
            self.warnings.append("Watchlist has > 100 symbols. This may impact performance")

        # Validate symbol format (basic check)
        for symbol in self.strategy.watchlist:
            if not isinstance(symbol, str):
                self.errors.append(f"Invalid symbol: {symbol}. Must be a string")
            elif not symbol.isupper():
                self.warnings.append(f"Symbol {symbol} should be uppercase")
            elif len(symbol) > 5:
                self.warnings.append(f"Symbol {symbol} seems unusually long")

    def _validate_indicators(self):
        """Validate indicator configuration."""
        config = self.strategy.config

        if not config:
            self.warnings.append("No indicator configuration. Strategy may not have sufficient data")
            return

        # Check if at least one indicator is enabled
        has_indicators = any(
            config.get(f'use_{ind}', False)
            for ind in ['rsi', 'macd', 'bollinger', 'sma', 'ema', 'atr', 'stochastic']
        )

        if not has_indicators:
            self.warnings.append("No indicators enabled. Strategy will have limited analysis capability")

        # Validate RSI settings
        if config.get('use_rsi'):
            period = config.get('rsi_period', 14)
            if period < 2 or period > 50:
                self.warnings.append(f"RSI period {period} is unusual. Typical range: 10-20")

        # Validate Bollinger Bands settings
        if config.get('use_bollinger'):
            period = config.get('bb_period', 20)
            if period < 10 or period > 50:
                self.warnings.append(f"Bollinger Bands period {period} is unusual. Typical: 20")

        # Validate SMA settings
        if config.get('use_sma'):
            periods = config.get('sma_periods', [20, 50])
            for period in periods:
                if period < 5 or period > 200:
                    self.warnings.append(f"SMA period {period} is unusual")

    def _validate_entry_rules(self):
        """Validate entry rules configuration."""
        if not self.strategy.entry_rules:
            self.errors.append("No entry rules defined. Strategy cannot generate buy signals")
            return

        if not isinstance(self.strategy.entry_rules, dict):
            self.errors.append("Entry rules must be a dictionary")
            return

        # Validate each rule
        for rule_name, rule_config in self.strategy.entry_rules.items():
            if rule_name.startswith('_'):  # Skip metadata fields
                continue

            if rule_name not in self.VALID_ENTRY_RULES:
                self.warnings.append(f"Unknown entry rule: {rule_name}")

            # Validate rule-specific configuration
            self._validate_entry_rule_config(rule_name, rule_config)

        # Check if rules make sense together
        if 'rsi_oversold' in self.strategy.entry_rules and 'rsi_overbought' in self.strategy.entry_rules:
            self.warnings.append("Both RSI oversold and overbought rules present. These are contradictory")

    def _validate_entry_rule_config(self, rule_name: str, rule_config: Dict[str, Any]):
        """Validate specific entry rule configuration."""
        if rule_name == 'rsi_oversold':
            threshold = rule_config.get('threshold', 30)
            if threshold < 10 or threshold > 50:
                self.warnings.append(f"RSI oversold threshold {threshold} is unusual. Typical: 20-30")

        elif rule_name == 'rsi_overbought':
            threshold = rule_config.get('threshold', 70)
            if threshold < 50 or threshold > 90:
                self.warnings.append(f"RSI overbought threshold {threshold} is unusual. Typical: 70-80")

        elif rule_name == 'volume_surge':
            multiplier = rule_config.get('multiplier', 1.5)
            if multiplier < 1.1 or multiplier > 5.0:
                self.warnings.append(f"Volume surge multiplier {multiplier} is unusual. Typical: 1.5-3.0")

        elif rule_name == 'price_above_sma' or rule_name == 'price_below_sma':
            period = rule_config.get('period', 20)
            if period < 5 or period > 200:
                self.warnings.append(f"SMA period {period} is unusual for entry rule")

    def _validate_exit_rules(self):
        """Validate exit rules configuration."""
        if not self.strategy.exit_rules:
            self.warnings.append("No exit rules defined. Positions may not be closed automatically")
            return

        if not isinstance(self.strategy.exit_rules, dict):
            self.errors.append("Exit rules must be a dictionary")
            return

        # Validate each rule
        for rule_name, rule_config in self.strategy.exit_rules.items():
            if rule_name.startswith('_'):
                continue

            if rule_name not in self.VALID_EXIT_RULES:
                self.warnings.append(f"Unknown exit rule: {rule_name}")

            # Validate rule-specific configuration
            self._validate_exit_rule_config(rule_name, rule_config)

        # Recommend having both profit and loss exits
        has_profit_exit = 'profit_target' in self.strategy.exit_rules
        has_loss_exit = 'stop_loss' in self.strategy.exit_rules or 'trailing_stop' in self.strategy.exit_rules

        if not has_profit_exit:
            self.warnings.append("No profit target defined. Consider adding one")

        if not has_loss_exit:
            self.errors.append("No stop loss defined. This is required for risk management")

    def _validate_exit_rule_config(self, rule_name: str, rule_config: Dict[str, Any]):
        """Validate specific exit rule configuration."""
        if rule_name == 'profit_target':
            percentage = rule_config.get('percentage', 5.0)
            if percentage < 0.5:
                self.warnings.append(f"Profit target {percentage}% is very small")
            elif percentage > 50:
                self.warnings.append(f"Profit target {percentage}% is very large")

        elif rule_name == 'stop_loss':
            percentage = rule_config.get('percentage', 2.0)
            if percentage < 0.5:
                self.warnings.append(f"Stop loss {percentage}% is very tight. May get stopped out frequently")
            elif percentage > 10:
                self.warnings.append(f"Stop loss {percentage}% is very wide. Risk may be too high")

        elif rule_name == 'trailing_stop':
            percentage = rule_config.get('percentage', 3.0)
            if percentage < 1.0:
                self.warnings.append(f"Trailing stop {percentage}% is very tight")
            elif percentage > 20:
                self.warnings.append(f"Trailing stop {percentage}% is very wide")

    def _validate_portfolio(self):
        """Validate portfolio association."""
        if not self.strategy.portfolio:
            self.warnings.append("Strategy not associated with a portfolio. It cannot execute trades")


def validate_strategy(strategy: Strategy) -> Tuple[bool, List[str], List[str]]:
    """
    Convenience function to validate a strategy.

    Args:
        strategy: Strategy instance to validate

    Returns:
        Tuple of (is_valid, errors, warnings)

    Example:
        >>> is_valid, errors, warnings = validate_strategy(my_strategy)
        >>> if not is_valid:
        >>>     print("Validation errors:", errors)
        >>> if warnings:
        >>>     print("Warnings:", warnings)
    """
    validator = StrategyValidator(strategy)
    return validator.validate_all()


def validate_strategy_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate strategy configuration dictionary before creating strategy.

    Args:
        config: Strategy configuration dictionary

    Returns:
        Tuple of (is_valid, errors)

    Example:
        >>> config = {
        >>>     'use_rsi': True,
        >>>     'rsi_period': 14,
        >>>     'timeframe': '1d'
        >>> }
        >>> is_valid, errors = validate_strategy_config(config)
    """
    errors = []

    # Validate timeframe
    timeframe = config.get('timeframe')
    if timeframe and timeframe not in StrategyValidator.VALID_TIMEFRAMES:
        errors.append(f"Invalid timeframe: {timeframe}")

    # Validate indicator settings
    if config.get('use_rsi'):
        period = config.get('rsi_period', 14)
        if period < 2 or period > 50:
            errors.append(f"Invalid RSI period: {period}")

    if config.get('use_bollinger'):
        period = config.get('bb_period', 20)
        std_dev = config.get('bb_std_dev', 2)
        if period < 10 or period > 50:
            errors.append(f"Invalid Bollinger Bands period: {period}")
        if std_dev < 1 or std_dev > 4:
            errors.append(f"Invalid Bollinger Bands std dev: {std_dev}")

    return len(errors) == 0, errors


def validate_entry_rules(entry_rules: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate entry rules dictionary.

    Args:
        entry_rules: Entry rules configuration

    Returns:
        Tuple of (is_valid, errors)
    """
    errors = []

    if not entry_rules:
        errors.append("Entry rules cannot be empty")
        return False, errors

    for rule_name, rule_config in entry_rules.items():
        if rule_name.startswith('_'):
            continue

        if rule_name not in StrategyValidator.VALID_ENTRY_RULES:
            errors.append(f"Unknown entry rule: {rule_name}")

        if not isinstance(rule_config, dict):
            errors.append(f"Rule {rule_name} config must be a dictionary")

    return len(errors) == 0, errors


def validate_exit_rules(exit_rules: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate exit rules dictionary.

    Args:
        exit_rules: Exit rules configuration

    Returns:
        Tuple of (is_valid, errors)
    """
    errors = []

    if not exit_rules:
        errors.append("Exit rules should be defined for risk management")

    # Check for stop loss
    has_stop_loss = any(
        rule in exit_rules
        for rule in ['stop_loss', 'trailing_stop']
    )

    if not has_stop_loss:
        errors.append("At least one stop loss rule (stop_loss or trailing_stop) is required")

    for rule_name, rule_config in exit_rules.items():
        if rule_name.startswith('_'):
            continue

        if rule_name not in StrategyValidator.VALID_EXIT_RULES:
            errors.append(f"Unknown exit rule: {rule_name}")

        if not isinstance(rule_config, dict):
            errors.append(f"Rule {rule_name} config must be a dictionary")

    return len(errors) == 0, errors
