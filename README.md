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

### Configurar o chatbot Gemini

Crie um arquivo chamado `.env` na raiz do projeto, no mesmo nível de
`manage.py`, e adicione:

```dotenv
GEMINI_API_KEY=sua_chave_da_api_gemini
GEMINI_MODEL=gemini-3.1-flash-lite
```

`GEMINI_API_KEY` é obrigatória para usar o chatbot. `GEMINI_MODEL` é opcional;
quando omitida, o projeto usa `gemini-3.1-flash-lite`. O arquivo `.env` é
carregado pelo Django e ignorado pelo Git para evitar que a chave seja enviada
ao repositório. Não compartilhe nem publique esse arquivo. Após criar ou alterar
o `.env`, reinicie o servidor Django.

O projeto gera uma chave aleatória temporária quando `DJANGO_DEBUG` está ligado. Para executar em produção, configure `DJANGO_DEBUG=false`, uma `DJANGO_SECRET_KEY` longa e aleatória e `DJANGO_ALLOWED_HOSTS`; use HTTPS. Segredos não devem ser incluídos no código ou no controle de versão.


