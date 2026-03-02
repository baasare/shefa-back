"""
Agent views with SSE streaming support (Vercel AI SDK compatible).
"""
import json
import logging
import uuid
from typing import Dict, Any

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.http import StreamingHttpResponse, JsonResponse

logger = logging.getLogger(__name__)


class TradingAgentStreamView(APIView):
    """
    API view for streaming trading agent analysis in real-time using Server-Sent Events.
    Compatible with Vercel AI SDK useChat hook.
    """
    permission_classes = [IsAuthenticated]

    @staticmethod
    async def _agent_stream_generator(request_data: Dict[str, Any], user):
        """
        Async generator that yields SSE-formatted events from the trading agent.
        
        Event types (Vercel AI SDK compatible):
        - analysis-start: Agent starts analyzing a symbol
        - tool-call: Agent invokes a tool (technical analysis, etc.)
        - tool-result: Tool returns results
        - text-delta: Agent reasoning text (streams character-by-character)
        - trade-signal: Agent generates buy/sell/hold signal
        - analysis-complete: Analysis finished for a symbol
        - data-error: Error occurred
        """
        strategy_id = request_data.get('strategy_id')
        symbols = request_data.get('symbols', [])
        message_id = request_data.get('id', f"msg-{str(uuid.uuid4())[:8]}")
        
        if not strategy_id or not symbols:
            error_event = {
                "type": "data-error",
                "id": f"error-{str(uuid.uuid4())[:8]}",
                "data": "strategy_id and symbols are required."
            }
            yield f"data: {json.dumps(error_event)}\n\n"
            return

        try:
            # TODO: Import and initialize your trading agent here
            # from apps.agents.services import TradingAgentRunner
            # 
            # agent = TradingAgentRunner(
            #     strategy_id=strategy_id,
            #     user=user
            # )
            # 
            # async for event in agent.astream_analysis(symbols):
            #     yield f"data: {json.dumps(event)}\n\n"
            
            # EXAMPLE: Mock streaming events for demonstration
            for symbol in symbols:
                # Start analysis
                yield f"data: {json.dumps({'type': 'analysis-start', 'symbol': symbol})}\n\n"
                
                # Tool call
                yield f"data: {json.dumps({'type': 'tool-call', 'toolName': 'technical_analysis'})}\n\n"
                
                # Tool result
                tool_result = {'type': 'tool-result', 'result': {'rsi': 58.2, 'macd': 'bullish'}}
                yield f"data: {json.dumps(tool_result)}\n\n"
                
                # Text delta (agent reasoning)
                reasoning = f"Analyzing {symbol}..."
                for char in reasoning:
                    yield f"data: {json.dumps({'type': 'text-delta', 'textDelta': char})}\n\n"
                
                # Trade signal
                trade_signal = {'type': 'trade-signal', 'signal': {'action': 'BUY', 'confidence': 0.78, 'entry': 178.42}}
                yield f"data: {json.dumps(trade_signal)}\n\n"
                
                # Complete
                yield f"data: {json.dumps({'type': 'analysis-complete', 'symbol': symbol})}\n\n"

        except Exception as e:
            logger.error(f"Error in agent stream: {e}", exc_info=True)
            error_event = {
                "type": "data-error",
                "id": message_id,
                "data": f"An unexpected error occurred: {str(e)}",
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    async def post(self, request, *args, **kwargs):
        """
        Handles POST requests to start streaming the agent's analysis.
        
        Expected payload:
        {
            "strategy_id": "uuid",
            "symbols": ["AAPL", "TSLA", "MSFT"],
            "id": "optional-message-id"
        }
        """
        try:
            request_data = request.data
            user = request.user
            
            stream_generator = self._agent_stream_generator(request_data, user)

            response = StreamingHttpResponse(
                streaming_content=stream_generator,
                content_type='text/event-stream',
                status=status.HTTP_200_OK
            )

            # Required headers for SSE
            response['Cache-Control'] = 'no-cache'
            response['Connection'] = 'keep-alive'
            response['X-Accel-Buffering'] = 'no'  # Disable nginx buffering

            return response

        except Exception as e:
            logger.error(f"Error in POST handler: {e}", exc_info=True)
            return JsonResponse(
                {"error": f"Server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentListView(APIView):
    """
    List all agents for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get all agents for user."""
        # TODO: Implement agent listing
        return JsonResponse({'agents': []}, status=status.HTTP_200_OK)

    def post(self, request):
        """Create a new agent."""
        # TODO: Implement agent creation
        return JsonResponse({'message': 'Agent created'}, status=status.HTTP_201_CREATED)
