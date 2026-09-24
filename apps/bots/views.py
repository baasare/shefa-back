import json
import logging
import time

from django.db import IntegrityError, transaction
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.bots.events import record_bot_event
from apps.bots.llm import BotAIError, draft_bot
from apps.bots.models import Bot, BotEvent, BotRun
from apps.bots.serializers import (
    BotDraftRequestSerializer,
    BotEventSerializer,
    BotRunSerializer,
    BotSerializer,
)
from apps.bots.tasks import run_paper_bot
from apps.brokers.models import BrokerConnection
from apps.portfolios.models import Portfolio

logger = logging.getLogger(__name__)


def get_or_create_paper_portfolio(user):
    portfolio, _ = Portfolio.objects.get_or_create(
        user=user,
        name='Paper Trading',
        defaults={
            'portfolio_type': 'paper',
            'initial_capital': 100000,
            'cash_balance': 100000,
            'total_equity': 100000,
        },
    )
    if portfolio.portfolio_type != 'paper':
        raise ValueError('The default portfolio is not a paper portfolio.')
    return portfolio


def paper_connection_for(bot):
    connection = BrokerConnection.objects.filter(
        user=bot.user,
        portfolio=bot.portfolio,
        broker='alpaca_paper',
        status='active',
        is_paper_trading=True,
    ).first()
    return connection


class BotViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = BotSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return Bot.objects.filter(user=self.request.user).select_related('portfolio').prefetch_related('runs')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            portfolio = get_or_create_paper_portfolio(request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        bot = Bot.objects.create(user=request.user, portfolio=portfolio, **serializer.validated_data)
        record_bot_event(bot, 'bot_created', 'Paper bot draft created.')
        return Response(self.get_serializer(bot).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        bot = serializer.save()
        record_bot_event(bot, 'bot_updated', 'Bot rules updated.', data={'config_version': bot.config_version})

    def perform_destroy(self, instance):
        if instance.status == 'active':
            from rest_framework.exceptions import ValidationError
            raise ValidationError('Pause or stop the bot before deleting it.')
        instance.delete()

    @action(detail=False, methods=['post'], url_path='draft')
    def draft(self, request):
        serializer = BotDraftRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            draft = draft_bot(serializer.validated_data['idea'])
        except BotAIError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(draft.model_dump())

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        bot = self.get_object()
        if bot.portfolio.portfolio_type != 'paper':
            return Response({'detail': 'Live trading is disabled.'}, status=status.HTTP_409_CONFLICT)
        if not paper_connection_for(bot):
            return Response(
                {'detail': 'Connect and verify an Alpaca paper account for this paper portfolio before starting the bot.'},
                status=status.HTTP_409_CONFLICT,
            )
        if bot.status == 'active':
            return Response(self.get_serializer(bot).data)
        bot.status = 'active'
        bot.next_run_at = timezone.now()
        bot.save(update_fields=['status', 'next_run_at', 'updated_at'])
        record_bot_event(bot, 'bot_status', 'Paper bot started.')
        return Response(self.get_serializer(bot).data)

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        bot = self.get_object()
        if bot.status != 'active':
            return Response({'detail': 'Only a running bot can be paused.'}, status=status.HTTP_409_CONFLICT)
        bot.status = 'paused'
        bot.next_run_at = None
        bot.save(update_fields=['status', 'next_run_at', 'updated_at'])
        record_bot_event(bot, 'bot_status', 'Paper bot paused. Queued runs will not submit new orders.')
        return Response(self.get_serializer(bot).data)

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        bot = self.get_object()
        bot.status = 'stopped'
        bot.next_run_at = None
        bot.save(update_fields=['status', 'next_run_at', 'updated_at'])
        record_bot_event(bot, 'bot_status', 'Paper bot stopped. Queued runs will not submit new orders.')
        return Response(self.get_serializer(bot).data)

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        bot = self.get_object()
        if bot.status != 'active':
            return Response({'detail': 'Start the bot before requesting a run.'}, status=status.HTTP_409_CONFLICT)
        if not paper_connection_for(bot):
            return Response({'detail': 'An active Alpaca paper connection is required.'}, status=status.HTTP_409_CONFLICT)
        try:
            with transaction.atomic():
                locked_bot = Bot.objects.select_for_update().get(id=bot.id, user=request.user)
                if locked_bot.status != 'active':
                    return Response({'detail': 'Start the bot before requesting a run.'}, status=status.HTTP_409_CONFLICT)
                if not paper_connection_for(locked_bot):
                    return Response({'detail': 'An active Alpaca paper connection is required.'}, status=status.HTTP_409_CONFLICT)
                run = BotRun.objects.create(bot=locked_bot)
                record_bot_event(locked_bot, 'run_queued', 'Paper bot run queued.', run=run)
        except IntegrityError:
            return Response({'detail': 'A run is already queued or running for this bot.'}, status=status.HTTP_409_CONFLICT)

        try:
            run_paper_bot.apply_async(args=[str(run.id)])
        except Exception:
            logger.exception('Could not queue paper bot run %s', run.id)
            run.status = 'failed'
            run.error_message = 'Background worker is unavailable. No order was submitted.'
            run.completed_at = timezone.now()
            run.save(update_fields=['status', 'error_message', 'completed_at'])
            record_bot_event(bot, 'error', run.error_message, run=run)
            return Response({'detail': run.error_message}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(BotRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['get'])
    def runs(self, request, pk=None):
        bot = self.get_object()
        runs = bot.runs.all()[:100]
        return Response(BotRunSerializer(runs, many=True).data)

    @action(detail=True, methods=['get'])
    def events(self, request, pk=None):
        bot = self.get_object()
        events = bot.events.all()[:200]
        return Response(BotEventSerializer(events, many=True).data)

    @action(detail=True, methods=['get'])
    def stream(self, request, pk=None):
        bot = self.get_object()
        try:
            last_id = max(0, int(request.headers.get('Last-Event-ID', '0')))
        except ValueError:
            last_id = 0
        user_id = request.user.id
        bot_id = bot.id
        try:
            initial_event_ids = list(BotEvent.objects.filter(
                bot_id=bot_id, bot__user_id=user_id
            ).order_by('-id').values_list('id', flat=True)[:200])
            initial_last_id = max(initial_event_ids, default=0) if last_id <= 0 else last_id
        except Exception:
            initial_last_id = last_id

        def event_stream():
            from django.db import close_old_connections

            started = time.monotonic()
            last_heartbeat = started
            cursor = initial_last_id
            yield 'retry: 3000\n\n'
            while time.monotonic() - started < 600:
                close_old_connections()
                events = BotEvent.objects.filter(bot_id=bot_id, bot__user_id=user_id, id__gt=cursor).order_by('id')[:100]
                for event in events:
                    payload = BotEventSerializer(event).data
                    yield f"id: {event.id}\nevent: {event.event_type}\ndata: {json.dumps(payload, default=str)}\n\n"
                    cursor = event.id
                now = time.monotonic()
                if now - last_heartbeat >= 15:
                    yield ': heartbeat\n\n'
                    last_heartbeat = now
                time.sleep(2)
            close_old_connections()

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache, no-transform'
        response['X-Accel-Buffering'] = 'no'
        return response
