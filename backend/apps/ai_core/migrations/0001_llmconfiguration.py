# 已有表 ai_llm_configurations 且无迁移记录时：python manage.py migrate ai_core 0001 --fake
# 然后执行 python manage.py migrate ai_core 应用 0002 以添加 is_default。

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LLMConfiguration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'model_type',
                    models.CharField(
                        choices=[('llm', 'LLM'), ('vision', 'Vision Model')],
                        default='llm',
                        max_length=10,
                        verbose_name='模型类型',
                    ),
                ),
                ('provider', models.CharField(max_length=20, verbose_name='模型提供商')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否启用')),
                ('api_key', models.CharField(blank=True, max_length=500, verbose_name='API密钥')),
                ('base_url', models.URLField(blank=True, max_length=500, verbose_name='基础URL')),
                ('model_name', models.CharField(max_length=100, verbose_name='模型名称')),
                ('extra_config', models.JSONField(blank=True, default=dict, verbose_name='扩展配置')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                (
                    'created_by',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='llm_configurations',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='创建者',
                    ),
                ),
            ],
            options={
                'verbose_name': 'AI模型配置',
                'verbose_name_plural': 'AI模型配置',
                'db_table': 'ai_llm_configurations',
                'ordering': ['-is_active', '-created_at'],
            },
        ),
    ]
