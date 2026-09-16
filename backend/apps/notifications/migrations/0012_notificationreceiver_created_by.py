from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0011_alter_notificationreceiver_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationreceiver",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="created_notification_receivers",
                to=settings.AUTH_USER_MODEL,
                verbose_name="创建人",
            ),
        ),
    ]
