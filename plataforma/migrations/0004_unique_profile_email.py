from django.db import migrations, models
from django.db.models import Q
from django.db.models.functions import Lower


def populate_profile_emails(apps, schema_editor):
    profile_model = apps.get_model("plataforma", "PlayerProfile")
    seen = set()
    for profile in profile_model.objects.select_related("user").iterator():
        email = (profile.user.email or "").strip().lower()
        if email and email in seen:
            raise RuntimeError(
                "Contas com e-mails duplicados precisam ser corrigidas antes da migração."
            )
        if email:
            seen.add(email)
        profile.email = email
        profile.save(update_fields=["email"])


class Migration(migrations.Migration):
    dependencies = [("plataforma", "0003_link_legacy_campaign_files")]

    operations = [
        migrations.AddField(
            model_name="playerprofile",
            name="email",
            field=models.EmailField(blank=True, default="", max_length=254),
            preserve_default=False,
        ),
        migrations.RunPython(populate_profile_emails, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="playerprofile",
            constraint=models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="plataforma_unique_profile_email_ci",
            ),
        ),
    ]
