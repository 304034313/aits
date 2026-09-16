from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api_testing', '0012_alter_apiendpoint_options_alter_apitestcase_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='apitestcase',
            name='created_source',
            field=models.CharField(
                choices=[('manual', 'Manual'), ('ai', 'AI Generated'), ('import', 'Imported')],
                db_index=True,
                default='manual',
                help_text='用例创建来源：手工、AI 生成、导入（如 Postman）',
                max_length=16,
                verbose_name='created source',
            ),
        ),
    ]
