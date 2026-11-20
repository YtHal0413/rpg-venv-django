import os

from django.db import migrations


def link_legacy_campaign_files(apps, schema_editor):
    Campaign = apps.get_model("plataforma", "Campaign")
    LibraryBook = apps.get_model("plataforma", "LibraryBook")
    Through = Campaign.library_books.through

    for campaign in Campaign.objects.exclude(files=[]).iterator():
        for legacy_name in campaign.files:
            name = os.path.basename(str(legacy_name))
            book = (
                LibraryBook.objects.filter(owner_id=campaign.master_id, file__endswith=f"/{name}")
                .order_by("pk")
                .first()
            )
            if book:
                Through.objects.get_or_create(campaign_id=campaign.pk, librarybook_id=book.pk)


class Migration(migrations.Migration):
    dependencies = [("plataforma", "0002_campaign_invite_code_and_library_files")]

    operations = [migrations.RunPython(link_legacy_campaign_files, migrations.RunPython.noop)]
