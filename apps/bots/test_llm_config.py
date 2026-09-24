from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.bots.llm import BotAIError, BotDraft, TradeSuggestion, _structured_model, suggest_trade


class BotLLMConfigurationTests(SimpleTestCase):
    @override_settings(GEMINI_API_KEY='')
    def test_missing_gemini_key_fails_with_clear_setup_message(self):
        with self.assertRaisesRegex(BotAIError, 'Gemini API key'):
            _structured_model(BotDraft)

    @override_settings(GEMINI_API_KEY='test-key', BOT_LLM_MODEL='gemini-3.8-flash')
    @patch('langchain.chat_models.init_chat_model')
    def test_initializes_configured_gemini_model_and_structured_schema(self, init_model):
        structured_model = MagicMock()
        init_model.return_value.with_structured_output.return_value = structured_model

        result = _structured_model(BotDraft)

        init_model.assert_called_once_with(
            'gemini-3.8-flash',
            model_provider='google_genai',
            api_key='test-key',
            timeout=30,
        )
        init_model.return_value.with_structured_output.assert_called_once_with(BotDraft)
        self.assertIs(result, structured_model)

    @patch('apps.bots.llm._structured_model')
    def test_trade_prompt_contains_market_data_and_bot_idea_without_account_context(self, get_model):
        model = MagicMock()
        model.invoke.return_value = TradeSuggestion(action='hold', explanation='Wait for clearer data.')
        get_model.return_value = model

        suggest_trade(
            bot=SimpleNamespace(
                idea='Prefer low volatility.',
                max_order_value='250',
                max_open_positions=3,
                daily_loss_limit_pct='2.0',
                symbols=['AAPL', 'MSFT'],
            ),
            symbol='AAPL',
            quote={'bid': '100', 'ask': '101', 'timestamp': '2026-09-24T14:00:00Z'},
            bars=[{'close': '100'}],
            portfolio={
                'portfolio_value_usd': '10000',
                'daily_pnl_pct': '1.25',
                'open_positions': 2,
                'position_symbols': ['MSFT'],
            },
        )

        messages = model.invoke.call_args.args[0]
        prompt = messages[1][1]
        self.assertIn('Prefer low volatility.', prompt)
        self.assertIn('AAPL', prompt)
        self.assertIn('portfolio_value_usd', prompt)
        self.assertIn('10000', prompt)
        self.assertIn('position_symbols', prompt)
        self.assertIn('maximum_order_value_usd', prompt)
