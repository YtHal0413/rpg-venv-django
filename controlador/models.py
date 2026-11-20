from pathlib import PurePath
import re
from uuid import uuid4

from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from PIL import Image, UnidentifiedImageError


MAX_AVATAR_SIZE = 16 * 1024 * 1024
ALLOWED_AVATAR_FORMATS = {"PNG", "JPEG"}
MAX_LIBRARY_FILE_SIZE = 16 * 1024 * 1024
MAX_LIBRARY_IMAGE_PIXELS = 40_000_000
LIBRARY_IMAGE_FORMATS = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
}


def validate_avatar(uploaded_image):
    if uploaded_image.size > MAX_AVATAR_SIZE:
        raise ValidationError(_("O avatar deve ter no máximo 16 MiB."))

    try:
        with Image.open(uploaded_image) as image:
            extension = PurePath(uploaded_image.name).suffix.lower()
            expected_format = {
                ".png": "PNG",
                ".jpg": "JPEG",
                ".jpeg": "JPEG",
            }.get(extension)
            if (
                image.format not in ALLOWED_AVATAR_FORMATS
                or image.format != expected_format
            ):
                raise ValidationError(
                    _("Envie um avatar em formato PNG ou JPG/JPEG.")
                )
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValidationError(_("O arquivo enviado não é uma imagem válida.")) from error
    finally:
        uploaded_image.seek(0)


def avatar_upload_path(instance, filename):
    extension = PurePath(filename).suffix.lower()
    owner_id = instance.pk if instance.pk is not None else "novo"
    return f"avatars/{owner_id}/{uuid4().hex}{extension}"


def library_upload_path(instance, filename):
    extension = PurePath(filename).suffix.lower()
    return f"biblioteca/{instance.usuario_id}/{uuid4().hex}{extension}"


def ficha_avatar_upload_path(instance, filename):
    extension = PurePath(filename).suffix.lower()
    return f"fichas/{instance.usuario_id}/{uuid4().hex}{extension}"


def validar_codigo_convite(valor):
    if not re.fullmatch(r"[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{2}", valor):
        raise ValidationError(_("O código de convite possui formato inválido."))


def estrutura_ficha_padrao():
    return {
        "visibilidade": "todos",
        "colunas": {
            "1": {
                "ativa": True,
                "abaAtivaId": 1000,
                "abas": [
                    {
                        "id": 1000,
                        "titulo": "Geral",
                        "ehPadrao": True,
                        "secoes": [],
                    }
                ],
            },
            "2": {"ativa": True, "abaAtivaId": None, "abas": []},
            "3": {"ativa": True, "abaAtivaId": None, "abas": []},
        },
    }


def validate_library_file(uploaded_file):
    if uploaded_file.size > MAX_LIBRARY_FILE_SIZE:
        raise ValidationError(_("O arquivo deve ter no máximo 16 MiB."))

    extension = PurePath(uploaded_file.name).suffix.lower()
    try:
        if extension == ".pdf":
            header = uploaded_file.read(1024)
            uploaded_file.seek(max(0, uploaded_file.size - 4096))
            trailer = uploaded_file.read()
            if b"%PDF-" not in header or b"%%EOF" not in trailer:
                raise ValidationError(_("O arquivo enviado não é um PDF válido."))
        elif extension in LIBRARY_IMAGE_FORMATS:
            with Image.open(uploaded_file) as image:
                expected_format = LIBRARY_IMAGE_FORMATS[extension]
                if image.format != expected_format:
                    raise ValidationError(
                        _("A extensão do arquivo não corresponde ao formato da imagem.")
                    )
                if image.width * image.height > MAX_LIBRARY_IMAGE_PIXELS:
                    raise ValidationError(
                        _("A imagem excede o limite permitido de resolução.")
                    )
                image.verify()
        else:
            raise ValidationError(
                _("Envie um arquivo PDF ou uma imagem PNG/JPG/JPEG.")
            )
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as error:
        raise ValidationError(
            _("O arquivo enviado está inválido ou corrompido.")
        ) from error
    finally:
        uploaded_file.seek(0)


class UsuarioManager(UserManager):
    def normalize_email(self, email):
        return super().normalize_email(email).strip().lower()

    def get_by_natural_key(self, username):
        return self.get(email__iexact=username)

    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        if not username:
            raise ValueError("O nome de usuário é obrigatório.")

        user = self.model(
            email=self.normalize_email(email),
            username=username,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields["is_staff"] is not True:
            raise ValueError("Um superusuário precisa ter is_staff=True.")
        if extra_fields["is_superuser"] is not True:
            raise ValueError("Um superusuário precisa ter is_superuser=True.")

        return self.create_user(email, username, password, **extra_fields)


class Usuario(AbstractUser):
    email = models.EmailField(_("endereço de e-mail"), unique=True)
    tem_chave = models.BooleanField(_("acesso ilimitado"), default=False)
    avatar = models.ImageField(
        _("avatar"),
        upload_to=avatar_upload_path,
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg"]),
            validate_avatar,
        ],
    )

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="controlador_usuario_email_case_insensitive_unique",
            ),
        ]

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.__class__.objects.normalize_email(self.email)


class Arquivo(models.Model):
    class Tipo(models.TextChoices):
        DOCUMENTO = "documento", _("Documento")
        HANDOUT = "handout", _("Handout")

    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="arquivos",
    )
    nome_original = models.CharField(max_length=255)
    arquivo = models.FileField(
        upload_to=library_upload_path,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf", "png", "jpg", "jpeg"]
            ),
            validate_library_file,
        ],
    )
    tipo = models.CharField(
        max_length=12,
        choices=Tipo.choices,
        editable=False,
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome_original", "id"]

    def clean(self):
        super().clean()
        if self.arquivo and self.arquivo.name:
            extension = PurePath(self.arquivo.name).suffix.lower()
            if extension == ".pdf":
                self.tipo = self.Tipo.DOCUMENTO
            elif extension in LIBRARY_IMAGE_FORMATS:
                self.tipo = self.Tipo.HANDOUT
            else:
                raise ValidationError(
                    {"arquivo": _("Envie um arquivo PDF ou uma imagem PNG/JPG/JPEG.")}
                )

        if self.arquivo and not self.nome_original:
            self.nome_original = PurePath(self.arquivo.name).name[:255]

    def __str__(self):
        return self.nome_original


class Chave(models.Model):
    codigo = models.CharField(
        primary_key=True,
        max_length=18,
        validators=[
            RegexValidator(
                regex=r"^[A-Z0-9]{4}(?:-[A-Z0-9]{4}){2}-[A-Z0-9]{3}$",
                message=_("O código deve seguir o formato XXXX-YYYY-ZZZZ-AAA."),
            )
        ],
    )
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="chaves",
    )
    foi_usada = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)
    resgatada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criada_em", "codigo"]

    def __str__(self):
        return self.codigo


class FichaPersonagem(models.Model):
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="fichas",
    )
    nome = models.CharField(max_length=100)
    aspecto = models.CharField(max_length=240, blank=True)
    avatar = models.ImageField(
        upload_to=ficha_avatar_upload_path,
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg"]),
            validate_avatar,
        ],
    )
    estrutura_json = models.JSONField(default=estrutura_ficha_padrao)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-atualizada_em", "id"]

    def __str__(self):
        return self.nome


class TemplateFicha(models.Model):
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="templates_ficha",
    )
    ficha_origem = models.ForeignKey(
        FichaPersonagem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="templates_criados",
    )
    nome = models.CharField(max_length=100)
    estrutura_json = models.JSONField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em", "id"]

    def __str__(self):
        return self.nome


class Campanha(models.Model):
    mestre = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="campanhas_mestras",
    )
    titulo = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    codigo_convite = models.CharField(
        max_length=10,
        unique=True,
        validators=[validar_codigo_convite],
    )
    participantes = models.ManyToManyField(
        Usuario,
        through="CampanhaParticipante",
        related_name="campanhas_participadas",
    )
    arquivos = models.ManyToManyField(
        Arquivo,
        blank=True,
        related_name="campanhas",
    )
    template_mestre = models.ForeignKey(
        TemplateFicha,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="campanhas",
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-atualizada_em", "id"]

    def __str__(self):
        return self.titulo


class CampanhaParticipante(models.Model):
    campanha = models.ForeignKey(
        Campanha,
        on_delete=models.CASCADE,
        related_name="vinculos_participantes",
    )
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="vinculos_campanhas",
    )
    entrou_em = models.DateTimeField(auto_now_add=True)
    ultimo_acesso = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campanha", "usuario"],
                name="controlador_campanha_participante_unique",
            ),
        ]
        ordering = ["entrou_em", "id"]

    def __str__(self):
        return f"{self.usuario} — {self.campanha}"


class FichaCampanha(models.Model):
    campanha = models.ForeignKey(
        Campanha,
        on_delete=models.CASCADE,
        related_name="vinculos_fichas",
    )
    ficha = models.ForeignKey(
        FichaPersonagem,
        on_delete=models.CASCADE,
        related_name="vinculos_campanhas",
    )
    vinculada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campanha", "ficha"],
                name="controlador_campanha_ficha_unique",
            ),
        ]
        ordering = ["vinculada_em", "id"]

    def __str__(self):
        return f"{self.ficha} — {self.campanha}"


class SessaoCampanha(models.Model):
    campanha = models.ForeignKey(
        Campanha,
        on_delete=models.CASCADE,
        related_name="sessoes",
    )
    iniciada_em = models.DateTimeField()
    encerrada_em = models.DateTimeField(null=True, blank=True)
    duracao_segundos = models.PositiveIntegerField(null=True, blank=True)
    participantes_json = models.JSONField(default=list)
    relatorio_json = models.JSONField(null=True, blank=True)
    chatbot_json = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campanha"],
                condition=models.Q(encerrada_em__isnull=True),
                name="controlador_campanha_sessao_ativa_unique",
            ),
        ]
        ordering = ["-iniciada_em", "-id"]

    @property
    def ativa(self):
        return self.encerrada_em is None

    def __str__(self):
        return f"Sessão de {self.campanha} em {self.iniciada_em:%d/%m/%Y}"
