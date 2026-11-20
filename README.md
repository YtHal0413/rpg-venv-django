# RPG.Venv 0.2 portado para Django

## Executar localmente no Windows

No Terminal, a partir desta pasta:

```Terminal
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

O projeto gera uma chave aleatória temporária quando `DJANGO_DEBUG` está ligado. Para executar em produção, configure `DJANGO_DEBUG=false`, uma `DJANGO_SECRET_KEY` longa e aleatória e `DJANGO_ALLOWED_HOSTS`; use HTTPS. Segredos não devem ser incluídos no código ou no controle de versão.


