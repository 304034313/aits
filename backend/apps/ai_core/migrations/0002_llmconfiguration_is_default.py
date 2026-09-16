from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_core', '0001_llmconfiguration'),
    ]

    operations = [
        migrations.AddField(
            model_name='llmconfiguration',
            name='is_default',
            field=models.BooleanField(
                default=False,
                help_text='同类型下用户仅可有一条默认；加载模型时优先使用启用的默认配置',
                verbose_name='默认配置',
            ),
        ),
        migrations.AlterModelOptions(
            name='llmconfiguration',
            options={
                'ordering': ['-is_default', '-is_active', '-created_at'],
                'verbose_name': 'AI模型配置',
                'verbose_name_plural': 'AI模型配置',
            },
        ),
    ]
