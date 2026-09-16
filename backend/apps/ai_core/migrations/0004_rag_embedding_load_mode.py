# Generated migration: add embedding load mode (local/remote) to RAGConfiguration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai_core", "0003_mcpconfiguration_ragconfiguration_mcptool_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ragconfiguration",
            name="embedding_load_mode",
            field=models.CharField(
                choices=[
                    ("remote", "远程加载（联网下载/缓存）"),
                    ("local", "本地离线加载"),
                ],
                default="remote",
                help_text="local=从本地路径加载（断网可用）；remote=用 model_name 联网/缓存加载",
                max_length=10,
                verbose_name="嵌入模型加载模式",
            ),
        ),
        migrations.AddField(
            model_name="ragconfiguration",
            name="embedding_model_local_path",
            field=models.CharField(
                blank=True,
                default="",
                help_text="模型文件夹绝对路径，等价于环境变量 EMBEDDING_MODEL_LOCAL_PATH；仅 local 模式生效",
                max_length=500,
                verbose_name="嵌入模型本地路径",
            ),
        ),
        migrations.AlterField(
            model_name="ragconfiguration",
            name="embedding_model",
            field=models.CharField(
                default="BAAI/bge-large-zh-v1.5",
                help_text="HuggingFace 仓库名，等价于环境变量 EMBEDDING_MODEL_REMOTE_NAME；本地模式失败时也作为降级目标",
                max_length=100,
                verbose_name="嵌入模型名称（远程）",
            ),
        ),
    ]
