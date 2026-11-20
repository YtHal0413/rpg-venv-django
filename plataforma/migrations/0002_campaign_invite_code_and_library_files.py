import plataforma.models
from django.db import migrations, models


def populate_invite_codes(apps, schema_editor):
    campaign_model = apps.get_model("plataforma", "Campaign")
    for campaign in campaign_model.objects.filter(invite_code__isnull=True).iterator():
        campaign.invite_code = plataforma.models.generate_invite_code()
        campaign.save(update_fields=["invite_code"])


class Migration(migrations.Migration):
    dependencies = [("plataforma", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="invite_code",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.RunPython(populate_invite_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="campaign",
            name="invite_code",
            field=models.CharField(
                default=plataforma.models.generate_invite_code,
                max_length=32,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="campaign",
            name="library_books",
            field=models.ManyToManyField(
                blank=True,
                related_name="campaigns",
                to="plataforma.librarybook",
            ),
        ),
    ]
