from datetime import timedelta
import logging

from celery import shared_task
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.bots.events import record_bot_event
from apps.bots.models import Bot, BotRun
from apps.bots.services import execute_paper_run, paper_connection_for

logger = logging.getLogger(__name__)


@shared_task(bind=True, soft_time_limit=120, time_limit=150, max_retries=0)
def run_paper_bot(self, run_id):
    return execute_paper_run(run_id).status


@shared_task
def schedule_active_paper_bots():
    """Enqueue due bots. A DB lock + partial unique constraint prevents duplicates."""
    now = timezone.now()
    due_ids = list(Bot.objects.filter(status='active').filter(
        Q(next_run_at__isnull=True) | Q(next_run_at__lte=now)
    ).values_list('id', flat=True)[:500])
    queued = 0

    for bot_id in due_ids:
        run = None
        bot = None
        try:
            with transaction.atomic():
                bot = Bot.objects.select_for_update().select_related('user', 'portfolio').get(id=bot_id)
                if bot.status != 'active' or (bot.next_run_at and bot.next_run_at > now):
                    continue
                if BotRun.objects.filter(bot=bot, status__in=['queued', 'running']).exists():
                    continue
                if bot.portfolio.portfolio_type != 'paper' or not paper_connection_for(bot):
                    bot.status = 'error'
                    bot.next_run_at = None
                    bot.save(update_fields=['status', 'next_run_at', 'updated_at'])
                    record_bot_event(bot, 'error', 'Verified Alpaca paper connection is unavailable; bot paused.')
                    continue
                run = BotRun.objects.create(bot=bot)
                bot.next_run_at = now + timedelta(minutes=bot.run_frequency_minutes)
                bot.save(update_fields=['next_run_at', 'updated_at'])
                record_bot_event(bot, 'run_queued', 'Scheduled paper bot run queued.', run=run)
            run_paper_bot.apply_async(args=[str(run.id)])
            queued += 1
        except IntegrityError:
            # Another scheduler instance has already created an open run.
            continue
        except Exception:
            logger.exception('Failed to enqueue paper bot %s', bot_id)
            if run is not None:
                run.status = 'failed'
                run.error_message = 'Background worker queue is unavailable. No order was submitted.'
                run.completed_at = timezone.now()
                run.save(update_fields=['status', 'error_message', 'completed_at'])
                Bot.objects.filter(id=bot_id, status='active').update(status='error', next_run_at=None)
                record_bot_event(bot, 'error', run.error_message, run=run)
    return {'queued': queued, 'checked': len(due_ids)}
