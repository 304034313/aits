from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0006_project_linked_api_projects'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectThirdPartyConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('grafana_dashboard_url', models.URLField(blank=True, max_length=1000, null=True, verbose_name='性能大盘地址')),
                ('ai_diagnosis_url', models.URLField(blank=True, max_length=1000, null=True, verbose_name='AI诊断大盘地址')),
                ('grafana_admin_url', models.URLField(blank=True, max_length=1000, null=True, verbose_name='Grafana后台地址')),
                ('prometheus_url', models.URLField(blank=True, max_length=1000, null=True, verbose_name='Prometheus地址')),
                ('skywalking_url', models.URLField(blank=True, max_length=1000, null=True, verbose_name='SkyWalking地址')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('project', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='third_party_config', to='projects.project', verbose_name='所属项目')),
            ],
            options={
                'verbose_name': 'project third-party config',
                'verbose_name_plural': 'project third-party configs',
                'db_table': 'project_third_party_configs',
                'ordering': ['-updated_at', '-id'],
            },
        ),
    ]

