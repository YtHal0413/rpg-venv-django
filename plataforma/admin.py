from django.contrib import admin

from .models import Campaign, CharacterSheet, LibraryBook, PlayerProfile, SheetTemplate


@admin.register(PlayerProfile)
class PlayerProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "activated")
    search_fields = ("display_name", "user__email")
    list_filter = ("activated",)


@admin.register(CharacterSheet)
class CharacterSheetAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "visibility", "created_at")
    search_fields = ("name", "owner__email")
    list_filter = ("visibility",)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "master", "invite_code", "created_at")
    search_fields = ("name", "master__email", "invite_code")


@admin.register(SheetTemplate)
class SheetTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "created_at")
    search_fields = ("name", "owner__email")


@admin.register(LibraryBook)
class LibraryBookAdmin(admin.ModelAdmin):
    list_display = ("file", "owner", "uploaded_at")
    search_fields = ("file", "owner__email")
