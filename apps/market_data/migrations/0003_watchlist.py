import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('market_data', '0002_stockscreener'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Watchlist',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('symbol', models.CharField(max_length=20, verbose_name='Symbol')),
                ('name', models.CharField(blank=True, default='', max_length=255, verbose_name='Asset Name')),
                ('asset_type', models.CharField(
                    choices=[
                        ('stock', 'Stock'),
                        ('crypto', 'Crypto'),
                        ('etf', 'ETF'),
                        ('index', 'Index'),
                        ('other', 'Other'),
                    ],
                    default='stock',
                    max_length=20,
                    verbose_name='Asset Type',
                )),
                ('added_at', models.DateTimeField(auto_now_add=True, verbose_name='Added At')),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='watchlist_items',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Watchlist Item',
                'verbose_name_plural': 'Watchlist Items',
                'db_table': 'market_watchlist',
                'ordering': ['-added_at'],
            },
        ),
        migrations.AddIndex(
            model_name='watchlist',
            index=models.Index(fields=['user', '-added_at'], name='market_watc_user_id_added_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='watchlist',
            unique_together={('user', 'symbol')},
        ),
    ]
