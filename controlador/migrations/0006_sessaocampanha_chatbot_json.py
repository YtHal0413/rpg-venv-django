from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("controlador", "0005_campanha_campanhaparticipante_campanha_participantes_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="sessaocampanha",
            name="chatbot_json",
            field=models.JSONField(default=dict),
        ),
    ]
