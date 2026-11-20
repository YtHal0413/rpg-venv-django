import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.db.models.functions import Lower


def library_upload_path(instance, filename):
    return f"library/{instance.owner_id}/{filename}"


def generate_invite_code():
    return uuid.uuid4().hex.upper()


class PlayerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rpg_profile",
        primary_key=True,
    )
    display_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    activated = models.BooleanField(default=False)
    avatar = models.FileField(upload_to="avatars/users/", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="plataforma_unique_profile_email_ci",
            )
        ]

    @property
    def id(self):
        return self.user_id

    @property
    def nome(self):
        return self.display_name

    @property
    def imagem_avatar(self):
        return self.avatar.url if self.avatar else None

    @property
    def chave_ativada(self):
        return self.activated

    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        if not self.email:
            self.email = self.user.email.strip().lower()
        return super().save(*args, **kwargs)


class Campaign(models.Model):
    master = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rpg_campaigns")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    invite_code = models.CharField(max_length=32, unique=True, default=generate_invite_code)
    players = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="joined_rpg_campaigns", blank=True)
    characters = models.ManyToManyField("CharacterSheet", related_name="campaigns", blank=True)
    library_books = models.ManyToManyField("LibraryBook", related_name="campaigns", blank=True)
    files = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    @property
    def id_mestre(self):
        return self.master_id

    @property
    def nome(self):
        return self.name

    @property
    def descricao(self):
        return self.description

    @property
    def jogadores(self):
        user_ids = list(self.players.values_list("id", flat=True))
        if self.master_id not in user_ids:
            user_ids.append(self.master_id)
        return PlayerProfile.objects.filter(user_id__in=user_ids).select_related("user")

    @property
    def personagens(self):
        return self.characters.all()

    @property
    def arquivos(self):
        return [book.name for book in self.library_books.all()]

    @property
    def codigo_convite(self):
        return self.invite_code

    def __str__(self):
        return self.name


class CharacterSheet(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rpg_sheets")
    name = models.CharField(max_length=100, default="Novo Personagem")
    subtitle = models.CharField(max_length=100, blank=True)
    avatar_path = models.CharField(max_length=255, blank=True)
    visibility = models.CharField(max_length=16, default="todos")
    structure = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    @property
    def id_usuario(self):
        return self.owner_id

    @property
    def nome_personagem(self):
        return self.name

    @property
    def subtitulo(self):
        return self.subtitle

    @property
    def aspecto_personagem(self):
        return self.subtitle

    @property
    def avatar(self):
        return self.avatar_path or None

    @avatar.setter
    def avatar(self, value):
        self.avatar_path = value or ""

    @property
    def visibilidade(self):
        return self.visibility

    def __str__(self):
        return self.name


class SheetTemplate(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rpg_sheet_templates")
    source_sheet = models.ForeignKey(CharacterSheet, on_delete=models.SET_NULL, null=True, blank=True, related_name="saved_templates")
    name = models.CharField(max_length=100)
    structure = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)


class LibraryBook(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rpg_library_books")
    file = models.FileField(upload_to=library_upload_path)
    uploaded_at = models.DateTimeField(default=timezone.now)

    @property
    def name(self):
        return self.file.name.rsplit("/", 1)[-1]
