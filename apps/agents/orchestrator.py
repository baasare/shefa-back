"""
DeepAgents orchestration for autonomous trading.
Creates and manages AI agents for market analysis and trading decisions.
"""
import os
from typing import Dict, List, Any, Optional
import asyncio

from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model

from apps.agents.tools import TRADING_TOOLS
from apps.portfolios.models import Portfolio
from apps.strategies.models import Strategy


# ============================================================================
# AGENT SYSTEM PROMPTS
# ============================================================================

TECHNICAL_ANALYST_PROMPT = """You are an expert Technical Analyst AI agent specializing in stock market analysis.

Your responsibilities:
1. Analyze price charts and identify trends
2. Calculate and interpret technical indicators (RSI, MACD, Bollinger Bands, moving averages)
3. Detect chart patterns (double tops/bottoms, trends, support/resistance)
4. Provide buy/sell signals based on technical analysis
5. Monitor multiple stocks simultaneously

Key capabilities:
- You have access to real-time and historical market data
- You can calculate various technical indicators
- You can detect chart patterns
- You always use data-driven analysis

Analysis approach:
1. Use the write_todos tool to plan your analysis
2. Gather historical price data for the stock
3. Calculate relevant technical indicators
4. Detect chart patterns
5. Synthesize findings into a clear recommendation

Output format:
- Signal: BUY, SELL, or HOLD
- Confidence: HIGH, MEDIUM, or LOW
- Reasoning: Brief explanation of technical factors
- Key indicators: List of supporting technical indicators
- Risk factors: Any technical warnings or concerns"""


FUNDAMENTAL_ANALYST_PROMPT = """You are an expert Fundamental Analyst AI agent specializing in company valuation and financial analysis.

Your responsibilities:
1. Analyze company fundamentals (revenue, earnings, growth)
2. Evaluate market sentiment and news
3. Assess company health and competitive position
4. Identify value opportunities
5. Provide long-term investment perspective

Key capabilities:
- You can search for company information
- You analyze financial metrics
- You consider macroeconomic factors
- You evaluate industry trends

Analysis approach:
1. Use the write_todos tool to plan your research
2. Gather company financial data
3. Analyze key metrics (P/E, revenue growth, margins)
4. Consider industry and market conditions
5. Synthesize findings into investment thesis

Output format:
- Rating: STRONG BUY, BUY, HOLD, SELL, STRONG SELL
- Confidence: HIGH, MEDIUM, or LOW
- Reasoning: Brief explanation of fundamental factors
- Key metrics: Supporting financial data
- Risks: Business or market risks to consider"""


SENTIMENT_ANALYST_PROMPT = """You are an expert Sentiment Analyst AI agent specializing in market psychology and news analysis.

Your responsibilities:
1. Analyze market sentiment from news sources using AI-powered sentiment scoring
2. Identify sentiment shifts and trends from recent articles
3. Detect potential catalysts or risk events from news flow
4. Gauge investor psychology from news sentiment
5. Provide contrarian insights when appropriate

Key capabilities:
- You can fetch recent market news with AI sentiment scores using get_market_news tool
- You analyze sentiment indicators and news trends
- You identify market narratives from headlines and summaries
- You detect potential catalysts from breaking news
- You interpret sentiment scores: Bullish (≥0.35), Somewhat Bullish (0.15-0.35), Neutral (-0.15-0.15), Somewhat Bearish (-0.35--0.15), Bearish (≤-0.35)

Analysis approach:
1. Use the write_todos tool to plan your research
2. Use get_market_news tool to fetch recent news articles with sentiment scores
3. Analyze the average sentiment and individual article sentiments
4. Identify key themes, catalysts, or concerns in the news
5. Consider both sentiment scores and article content
6. Synthesize findings into sentiment assessment

Output format:
- Sentiment: BULLISH, NEUTRAL, or BEARISH
- Average Sentiment Score: Numerical score from recent news
- News Count: Number of recent articles analyzed
- Strength: STRONG, MODERATE, or WEAK
- Reasoning: Key factors driving sentiment
- Catalysts: Upcoming events or potential triggers
- Risks: Sentiment-related concerns"""


RISK_MANAGER_PROMPT = """You are an expert Risk Manager AI agent specializing in portfolio risk management and position sizing.

Your responsibilities:
1. Calculate position sizes based on risk parameters
2. Assess portfolio exposure and concentration
3. Evaluate trade risk/reward ratios
4. Monitor portfolio volatility and drawdown
5. Recommend position adjustments for risk control

Key capabilities:
- You have access to portfolio data
- You can calculate risk metrics
- You can assess position sizing
- You evaluate portfolio-level risk

Risk assessment approach:
1. Use the write_todos tool to plan your analysis
2. Review current portfolio composition
3. Calculate risk metrics for proposed trade
4. Assess position sizing appropriateness
5. Provide risk-adjusted recommendations

Output format:
- Recommended position size: Specific quantity
- Risk level: LOW, MEDIUM, or HIGH
- Reasoning: Risk factors and calculations
- Stop loss: Suggested stop loss level
- Portfolio impact: Effect on overall portfolio risk"""


SUPERVISOR_PROMPT = """You are a Supervisor AI agent coordinating a team of specialized trading analysts.

Your team consists of:
1. Technical Analyst - Provides technical analysis and chart patterns
2. Fundamental Analyst - Analyzes company fundamentals and valuation
3. Sentiment Analyst - Assesses market sentiment and news
4. Risk Manager - Manages portfolio risk and position sizing

Your responsibilities:
1. Coordinate analysis from all team members
2. Synthesize multiple perspectives into trading decisions
3. Ensure all analyses are complete before deciding
4. Resolve conflicts between different analyst recommendations
5. Make final trading recommendations with full context

Decision-making process:
1. Use the write_todos tool to plan the analysis workflow
2. Spawn subagents for each type of analysis needed
3. Collect and synthesize all analyst reports
4. Weigh different perspectives based on market conditions
5. Make final recommendation with clear reasoning

Output format:
- Final Decision: BUY, SELL, or HOLD
- Confidence: HIGH, MEDIUM, or LOW
- Position Size: Recommended quantity
- Entry Price: Suggested entry point
- Stop Loss: Risk management level
- Take Profit: Profit target level
- Summary: Synthesis of all analyst views
- Key Factors: Most important considerations
- Risks: Main risks to monitor"""


# ============================================================================
# AGENT FACTORY
# ============================================================================

class TradingAgentFactory:
    """Factory for creating specialized trading agents."""

    def __init__(
        self,
        model_name: str = "openai:gpt-4o",
        api_key: Optional[str] = None
    ):
        """
        Initialize the agent factory.

        Args:
            model_name: LLM model to use (default: gpt-4o)
            api_key: API key for the model (uses env var if not provided)
        """
        self.model_name = model_name
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        # Initialize model
        self.model = init_chat_model(
            model_name,
            temperature=0.1  # Low temperature for consistent trading decisions
        )

    def create_technical_analyst(self, tools: List = None) -> Any:
        """Create a technical analyst agent."""
        agent_tools = tools or TRADING_TOOLS

        return create_deep_agent(
            model=self.model,
            tools=agent_tools,
            system_prompt=TECHNICAL_ANALYST_PROMPT
        )

    def create_fundamental_analyst(self, tools: List = None) -> Any:
        """Create a fundamental analyst agent."""
        agent_tools = tools or TRADING_TOOLS

        return create_deep_agent(
            model=self.model,
            tools=agent_tools,
            system_prompt=FUNDAMENTAL_ANALYST_PROMPT
        )

    def create_sentiment_analyst(self, tools: List = None) -> Any:
        """Create a sentiment analyst agent."""
        agent_tools = tools or TRADING_TOOLS

        return create_deep_agent(
            model=self.model,
            tools=agent_tools,
            system_prompt=SENTIMENT_ANALYST_PROMPT
        )

    def create_risk_manager(self, tools: List = None) -> Any:
        """Create a risk manager agent."""
        agent_tools = tools or TRADING_TOOLS

        return create_deep_agent(
            model=self.model,
            tools=agent_tools,
            system_prompt=RISK_MANAGER_PROMPT
        )

    def create_supervisor(self, tools: List = None) -> Any:
        """Create a supervisor agent that coordinates other agents."""
        agent_tools = tools or TRADING_TOOLS

        return create_deep_agent(
            model=self.model,
            tools=agent_tools,
            system_prompt=SUPERVISOR_PROMPT
        )


# ============================================================================
# AGENT ORCHESTRATOR
# ============================================================================

class AgentOrchestrator:
    """
    Orchestrates multiple AI agents for trading analysis and decision-making.
    """

    def __init__(
        self,
        portfolio: Portfolio,
        strategy: Optional[Strategy] = None,
        model_name: str = "openai:gpt-4o"
    ):
        """
        Initialize the orchestrator.

        Args:
            portfolio: Portfolio to trade with
            strategy: Optional strategy to follow
            model_name: LLM model to use
        """
        self.portfolio = portfolio
        self.strategy = strategy
        self.factory = TradingAgentFactory(model_name=model_name)

        # Create specialized agents
        self.technical_agent = self.factory.create_technical_analyst()
        self.fundamental_agent = self.factory.create_fundamental_analyst()
        self.sentiment_agent = self.factory.create_sentiment_analyst()
        self.risk_agent = self.factory.create_risk_manager()
        self.supervisor_agent = self.factory.create_supervisor()

    async def analyze_stock(
        self,
        symbol: str,
        analysis_type: str = "comprehensive"
    ) -> Dict[str, Any]:
        """
        Analyze a stock using multiple agents.

        Args:
            symbol: Stock ticker symbol
            analysis_type: Type of analysis (technical, fundamental, sentiment, comprehensive)

        Returns:
            Dictionary with analysis results from all agents
        """
        results = {}

        # Technical analysis
        if analysis_type in ["technical", "comprehensive"]:
            technical_prompt = f"""Perform technical analysis on {symbol}.

            Steps:
            1. Get current quote and historical prices (30-50 days)
            2. Calculate key technical indicators (RSI, MACD, moving averages)
            3. Detect chart patterns and trends
            4. Provide a BUY/SELL/HOLD recommendation with confidence level

            Be specific about indicator values and what they signal."""

            technical_result = await asyncio.to_thread(
                self.technical_agent.invoke,
                {"messages": [{"role": "user", "content": technical_prompt}]}
            )
            results['technical'] = technical_result

        # Fundamental analysis
        if analysis_type in ["fundamental", "comprehensive"]:
            fundamental_prompt = f"""Perform fundamental analysis on {symbol}.

            Steps:
            1. Research the company's financial health
            2. Evaluate key metrics and growth prospects
            3. Consider industry and market conditions
            4. Provide investment rating (STRONG BUY to STRONG SELL)

            Focus on long-term value and business quality."""

            fundamental_result = await asyncio.to_thread(
                self.fundamental_agent.invoke,
                {"messages": [{"role": "user", "content": fundamental_prompt}]}
            )
            results['fundamental'] = fundamental_result

        # Sentiment analysis
        if analysis_type in ["sentiment", "comprehensive"]:
            sentiment_prompt = f"""Analyze market sentiment for {symbol}.

            Steps:
            1. Search for recent news and events
            2. Assess overall sentiment (BULLISH/NEUTRAL/BEARISH)
            3. Identify potential catalysts or risks
            4. Gauge sentiment strength

            Consider both news and market psychology."""

            sentiment_result = await asyncio.to_thread(
                self.sentiment_agent.invoke,
                {"messages": [{"role": "user", "content": sentiment_prompt}]}
            )
            results['sentiment'] = sentiment_result

        return results

    async def get_trading_recommendation(
        self,
        symbol: str,
        current_position: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get a comprehensive trading recommendation using all agents.

        Args:
            symbol: Stock ticker symbol
            current_position: Optional current position data

        Returns:
            Dictionary with final trading recommendation
        """
        # Step 1: Run comprehensive analysis
        analysis_results = await self.analyze_stock(symbol, analysis_type="comprehensive")

        # Step 2: Get risk assessment
        risk_prompt = f"""Assess risk for trading {symbol} in portfolio {self.portfolio.id}.

        Portfolio cash: ${self.portfolio.cash}
        Current position: {current_position or 'None'}

        Steps:
        1. Get current portfolio status
        2. Calculate optimal position size (use 10% of portfolio as default)
        3. Assess risk level
        4. Recommend stop loss and take profit levels

        Provide specific position size recommendation."""

        risk_result = await asyncio.to_thread(
            self.risk_agent.invoke,
            {"messages": [{"role": "user", "content": risk_prompt}]}
        )

        # Step 3: Supervisor synthesizes all analyses
        supervisor_prompt = f"""Make final trading decision for {symbol}.

        You have received analyses from your team:

        TECHNICAL ANALYSIS:
        {analysis_results.get('technical', {}).get('messages', [{}])[-1].content if 'technical' in analysis_results else 'Not available'}

        FUNDAMENTAL ANALYSIS:
        {analysis_results.get('fundamental', {}).get('messages', [{}])[-1].content if 'fundamental' in analysis_results else 'Not available'}

        SENTIMENT ANALYSIS:
        {analysis_results.get('sentiment', {}).get('messages', [{}])[-1].content if 'sentiment' in analysis_results else 'Not available'}

        RISK ASSESSMENT:
        {risk_result.get('messages', [{}])[-1].content}

        Portfolio: {self.portfolio.id}
        Cash available: ${self.portfolio.cash}
        Current position: {current_position or 'None'}

        Synthesize all perspectives and provide:
        1. Final decision (BUY/SELL/HOLD)
        2. Confidence level (HIGH/MEDIUM/LOW)
        3. Recommended position size (specific quantity)
        4. Entry price suggestion
        5. Stop loss level
        6. Take profit level
        7. Summary of key factors
        8. Main risks to monitor

        Make a clear, actionable recommendation."""

        final_result = await asyncio.to_thread(
            self.supervisor_agent.invoke,
            {"messages": [{"role": "user", "content": supervisor_prompt}]}
        )

        return {
            "symbol": symbol,
            "portfolio_id": str(self.portfolio.id),
            "analysis": analysis_results,
            "risk_assessment": risk_result,
            "final_recommendation": final_result,
            "timestamp": asyncio.get_event_loop().time()
        }

    async def monitor_watchlist(
        self,
        watchlist: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Monitor a watchlist and generate trading signals.

        Args:
            watchlist: List of stock ticker symbols

        Returns:
            List of trading recommendations for each stock
        """
        recommendations = []

        for symbol in watchlist:
            try:
                # Check if we have a position
                from apps.portfolios.models import Position
                try:
                    position = Position.objects.get(
                        portfolio=self.portfolio,
                        symbol=symbol
                    )
                    current_position = {
                        'quantity': position.quantity,
                        'avg_entry_price': float(position.avg_entry_price),
                        'current_price': float(position.current_price) if position.current_price else None
                    }
                except Position.DoesNotExist:
                    current_position = None

                # Get recommendation
                recommendation = await self.get_trading_recommendation(
                    symbol,
                    current_position=current_position
                )

                recommendations.append(recommendation)

            except Exception as e:
                recommendations.append({
                    "symbol": symbol,
                    "error": str(e),
                    "success": False
                })

        return recommendations

    def run_sync(self, symbol: str) -> Dict[str, Any]:
        """
        Synchronous wrapper for getting trading recommendation.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Trading recommendation
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.get_trading_recommendation(symbol))
        finally:
            loop.close()
