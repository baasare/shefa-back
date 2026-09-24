from apps.bots.models import BotEvent


def record_bot_event(bot, event_type, message, *, run=None, data=None):
    """Persist a user-safe event before it is exposed through the API/SSE."""
    return BotEvent.objects.create(
        bot=bot,
        run=run,
        event_type=event_type,
        message=message[:500],
        data=data or {},
    )
