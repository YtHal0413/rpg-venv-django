from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    UserCreationForm,
)

from .models import Arquivo

Usuario = get_user_model()


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "E-mail ou senha inválidos.",
    }

    username = forms.EmailField(
        label="E-mail",
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "class": "w-full ui-surface border ui-border ui-focus-border focus:ring-2 ui-focus-ring rounded-xl px-4 py-3.5 text-white ui-placeholder outline-none transition text-sm",
                "placeholder": "seuemail@exemplo.com",
            }
        ),
    )
    password = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "class": "w-full ui-surface border ui-border ui-focus-border focus:ring-2 ui-focus-ring rounded-xl px-4 py-3.5 text-white ui-placeholder outline-none transition text-sm",
                "placeholder": "Sua senha",
            }
        ),
    )


class CadastroForm(UserCreationForm):
    email = forms.EmailField(
        label="Endereço de e-mail",
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "class": "account-input",
                "placeholder": "seuemail@exemplo.com",
            }
        ),
    )

    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ("username", "email")
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "autocomplete": "username",
                    "class": "account-input",
                    "placeholder": "Como quer ser chamado?",
                }
            ),
        }

    def clean_email(self):
        email = Usuario.objects.normalize_email(self.cleaned_data["email"])
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        return email

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("password1", "password2"):
            self.fields[field_name].widget.attrs.update(
                {
                    "autocomplete": "new-password",
                    "class": "account-input",
                    "placeholder": "Mínimo de 8 caracteres",
                }
            )


class PerfilForm(forms.ModelForm):
    remover_avatar = forms.BooleanField(
        label="Remover avatar atual",
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded ui-border ui-surface ui-checkbox ui-focus-ring",
            }
        ),
    )

    class Meta:
        model = Usuario
        fields = ("username", "email", "avatar")
        labels = {
            "username": "Nome de usuário",
            "email": "Endereço de e-mail",
            "avatar": "Foto de perfil",
        }
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "autocomplete": "username",
                    "class": "account-input",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "autocomplete": "email",
                    "class": "account-input",
                }
            ),
            "avatar": forms.FileInput(
                attrs={
                    "accept": ".png,.jpg,.jpeg,image/png,image/jpeg",
                    "class": "ui-file-input w-full text-sm ui-text-muted transition cursor-pointer",
                }
            ),
        }

    def clean_email(self):
        email = Usuario.objects.normalize_email(self.cleaned_data["email"])
        duplicate = Usuario.objects.filter(email__iexact=email).exclude(
            pk=self.instance.pk
        )
        if duplicate.exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("remover_avatar") and not self.files.get("avatar"):
            user.avatar = None
        if commit:
            user.save()
            self.save_m2m()
        return user


class SenhaPerfilForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            self.fields[field_name].widget.attrs.update(
                {
                    "autocomplete": "current-password"
                    if field_name == "old_password"
                    else "new-password",
                    "class": "account-input",
                }
            )


class ArquivoUploadForm(forms.ModelForm):
    class Meta:
        model = Arquivo
        fields = ("arquivo",)
        widgets = {
            "arquivo": forms.FileInput(
                attrs={
                    "accept": ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg",
                    "required": True,
                    "class": "absolute inset-0 w-full h-full opacity-0 cursor-pointer",
                }
            ),
        }


class CompraChaveForm(forms.Form):
    pacote = forms.ChoiceField(choices=(("1", "1 chave"),))


class ResgateChaveForm(forms.Form):
    codigo = forms.RegexField(
        regex=r"^[A-Za-z0-9]{4}(?:-[A-Za-z0-9]{4}){2}-[A-Za-z0-9]{3}$",
        label="Chave de acesso",
        max_length=18,
        error_messages={
            "invalid": "Informe uma chave no formato XXXX-YYYY-ZZZZ-AAA."
        },
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "autocapitalize": "characters",
                "class": "w-full ui-surface border ui-border ui-focus-border focus:ring-2 ui-focus-ring rounded-xl px-4 py-3 text-white ui-placeholder outline-none transition text-sm font-mono",
                "placeholder": "XXXX-YYYY-ZZZZ-AAA",
                "required": True,
            }
        ),
    )

    def clean_codigo(self):
        return self.cleaned_data["codigo"].strip().upper()


class CriarFichaForm(forms.Form):
    nome_personagem = forms.CharField(max_length=100, strip=True)
    subtitulo = forms.CharField(max_length=240, strip=True)

    def clean_nome_personagem(self):
        nome = self.cleaned_data["nome_personagem"]
        if not nome:
            raise forms.ValidationError("O nome do personagem é obrigatório.")
        return nome

    def clean_subtitulo(self):
        aspecto = self.cleaned_data["subtitulo"]
        if not aspecto:
            raise forms.ValidationError("O aspecto do personagem é obrigatório.")
        return aspecto


class CampanhaForm(forms.Form):
    titulo = forms.CharField(
        label="Título da campanha",
        max_length=100,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "class": "w-full ui-surface border ui-border ui-focus-border focus:ring-2 ui-focus-ring rounded-xl px-4 py-3.5 text-white ui-placeholder outline-none transition text-sm",
                "required": True,
            }
        ),
    )
    descricao = forms.CharField(
        label="Descrição",
        required=False,
        max_length=10000,
        strip=True,
        widget=forms.Textarea(
            attrs={
                "rows": 6,
                "class": "w-full ui-surface border ui-border ui-focus-border focus:ring-2 ui-focus-ring rounded-xl px-4 py-3.5 text-white ui-placeholder outline-none transition text-sm resize-y",
                "placeholder": "Detalhe a proposta da mesa e sua sinopse",
            }
        ),
    )


class CodigoConviteForm(forms.Form):
    codigo_campanha = forms.RegexField(
        regex=r"^[A-Za-z0-9]{3}-[A-Za-z0-9]{3}-[A-Za-z0-9]{2}$",
        max_length=10,
        error_messages={"invalid": "Informe um código no formato XXX-XXX-XX."},
        widget=forms.TextInput(
            attrs={
                "class": "min-w-0 flex-1 ui-surface border ui-border ui-focus-border rounded-xl px-4 py-3 text-sm text-white font-mono ui-placeholder outline-none transition",
                "placeholder": "XXX-XXX-XX",
                "autocapitalize": "characters",
                "required": True,
            }
        ),
    )

    def clean_codigo_campanha(self):
        return self.cleaned_data["codigo_campanha"].strip().upper()
