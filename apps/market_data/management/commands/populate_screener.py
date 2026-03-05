"""
Management command to populate the StockScreener table from Alpha Vantage.

Usage:
    python manage.py populate_screener
    python manage.py populate_screener --symbols AAPL MSFT NVDA TSLA
    python manage.py populate_screener --symbols AAPL MSFT --overview
"""
import asyncio
import time
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from apps.market_data.models import StockScreener
from apps.market_data.providers.alpha_vantage import AlphaVantageProvider


# Default set of symbols — covers overview strip + common stocks
DEFAULT_SYMBOLS = [
    # Overview strip proxies
    ('SPY',  'SPDR S&P 500 ETF Trust',     'etf',    'ETF',              'NYSE ARCA'),
    ('QQQ',  'Invesco QQQ Trust',           'etf',    'ETF',              'NASDAQ'),
    ('GLD',  'SPDR Gold Shares',            'etf',    'ETF',              'NYSE ARCA'),
    ('VIX',  'CBOE Volatility Index',       'index',  '',                 ''),

    # Tech
    ('AAPL', 'Apple Inc.',                  'stock',  'Technology',       'NASDAQ'),
    ('MSFT', 'Microsoft Corp.',             'stock',  'Technology',       'NASDAQ'),
    ('NVDA', 'NVIDIA Corp.',                'stock',  'Technology',       'NASDAQ'),
    ('TSLA', 'Tesla Inc.',                  'stock',  'Consumer Discretionary', 'NASDAQ'),
    ('META', 'Meta Platforms Inc.',         'stock',  'Technology',       'NASDAQ'),
    ('AMZN', 'Amazon.com Inc.',             'stock',  'Consumer Discretionary', 'NASDAQ'),
    ('GOOGL','Alphabet Inc.',               'stock',  'Technology',       'NASDAQ'),

    # Finance
    ('JPM',  'JPMorgan Chase & Co.',        'stock',  'Finance',          'NYSE'),
    ('BAC',  'Bank of America Corp.',       'stock',  'Finance',          'NYSE'),
    ('GS',   'Goldman Sachs Group Inc.',    'stock',  'Finance',          'NYSE'),

    # Energy
    ('XOM',  'ExxonMobil Corp.',            'stock',  'Energy',           'NYSE'),
    ('CVX',  'Chevron Corp.',               'stock',  'Energy',           'NYSE'),

    # Healthcare
    ('JNJ',  'Johnson & Johnson',           'stock',  'Healthcare',       'NYSE'),
    ('UNH',  'UnitedHealth Group Inc.',     'stock',  'Healthcare',       'NYSE'),

    # Consumer
    ('WMT',  'Walmart Inc.',                'stock',  'Consumer Staples', 'NYSE'),
    ('KO',   'Coca-Cola Co.',               'stock',  'Consumer Staples', 'NYSE'),
]

# Overview symbols that require special handling (no AV quote)
SKIP_LIVE_FETCH = {'VIX', 'QQQ', 'GLD'}


def _to_decimal(val, default=None):
    try:
        return Decimal(str(val)) if val is not None else default
    except (InvalidOperation, TypeError):
        return default


def _to_int(val, default=None):
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default


class Command(BaseCommand):
    help = 'Populate StockScreener table from Alpha Vantage quotes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--symbols',
            nargs='+',
            help='Specific symbols to fetch. Defaults to a curated list.',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=12.0,
            help='Seconds between requests (Alpha Vantage free: 5/min = 12s delay). Default: 12',
        )

    def handle(self, *args, **options):
        api_key = getattr(settings, 'ALPHA_VANTAGE_API_KEY', '')
        if not api_key:
            raise CommandError(
                'ALPHA_VANTAGE_API_KEY is not set in settings. '
                'Add it to your .env file and make sure base.py reads it.'
            )

        provider = AlphaVantageProvider(api_key)
        delay = options['delay']

        # Build symbol list
        if options['symbols']:
            # User supplied custom symbols — use minimal metadata
            symbol_list = [(s.upper(), '', 'stock', '', '') for s in options['symbols']]
        else:
            symbol_list = DEFAULT_SYMBOLS

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f'Fetching {len(symbol_list)} symbols from Alpha Vantage '
                f'(delay={delay}s between requests)…'
            )
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        created = updated = skipped = 0

        for i, entry in enumerate(symbol_list):
            symbol, name, _type, sector, exchange = entry

            if i > 0:
                self.stdout.write(f'  ⏳ Waiting {delay}s (rate limit)…')
                time.sleep(delay)

            self.stdout.write(f'[{i+1}/{len(symbol_list)}] Fetching {symbol}…', ending='')

            try:
                quote = loop.run_until_complete(provider.get_quote(symbol))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f' SKIP ({e})'))
                skipped += 1
                continue

            if not quote:
                self.stdout.write(self.style.WARNING(' no data'))
                skipped += 1
                continue

            price = _to_decimal(quote.get('close'))
            volume = _to_int(quote.get('volume'))
            open_ = _to_decimal(quote.get('open'))
            high = _to_decimal(quote.get('high'))
            low = _to_decimal(quote.get('low'))

            # Compute change_pct from open → close
            change_pct = None
            if price and open_ and open_ != 0:
                change_pct = ((price - open_) / open_) * 100

            defaults = {
                'name': name or symbol,
                'price': price or Decimal('0'),
                'change_pct': change_pct,
                'volume': volume,
                'sector': sector,
                'exchange': exchange,
            }

            obj, was_created = StockScreener.objects.update_or_create(
                symbol=symbol,
                defaults=defaults,
            )

            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(' ✓ created'))
            else:
                updated += 1
                self.stdout.write(self.style.SUCCESS(' ✓ updated'))

        loop.close()

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done — {created} created, {updated} updated, {skipped} skipped.'
        ))
        self.stdout.write(
            'Run again any time to refresh prices. '
            'RSI/P-E/market-cap can be filled in via broker data or a premium AV plan.'
        )
