# RPGpédia em Django

Port da plataforma de RPG originalmente feita com Flask. O projeto mantém o editor visual de fichas, a rolagem de dados, modelos de ficha, campanhas, biblioteca PDF, perfil/avatar e o fluxo de ativação.

## Requisitos

- Python 3.12+
- Dependências de `requirements.txt`

## Executar localmente

```powershell
cd rpg-venv-django
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Abra `http://127.0.0.1:8000` e use **Criar conta** para cadastrar-se. O login só aceita contas já cadastradas e as senhas são armazenadas pelo sistema de autenticação do Django. Em desenvolvimento, a chave de ativação é `HA4H4nF1tR1A0HA4`; ela só é exibida nas páginas quando `DEBUG` está habilitado.

Após entrar na conta, acesse `http://127.0.0.1:8000/personagens` para encontrar o assistente de criação de personagens, visível na própria página. Ele usa `django-ai-sdk` com Google Gemini. Configure a chave da API no ambiente antes de iniciar o servidor; sem ela, o assistente aparece como indisponível. Não salve a chave no código ou no repositório:

```powershell
$env:GOOGLE_API_KEY = "sua-chave-do-Gemini"
# Opcional: $env:GEMINI_MODEL = "gemini-2.5-flash"
python manage.py runserver
```

O assistente sugere nome, aspecto e conceito a partir da ideia informada. A sugestão só preenche os campos depois que você escolher **Usar sugestão**; a ficha continua sendo criada pelo formulário normal. O texto da ideia é enviado ao Google Gemini. O `django-ai-sdk` está em versão de prévia e pode ter alterações incompatíveis; o projeto exige Python 3.12 ou superior por causa desse pacote.

O SQLite é criado em `rpg_django.sqlite3`; uploads privados ficam em `media/` e são entregues por endpoints que verificam sessão, propriedade e acesso à campanha. O painel administrativo está em `/admin/`; crie um administrador com `python manage.py createsuperuser`.

Para produção, configure `DJANGO_SECRET_KEY` e `RPG_ACTIVATION_KEY` com valores secretos, `DJANGO_DEBUG=0` e `DJANGO_ALLOWED_HOSTS` com os hosts permitidos. O servidor não inicia em produção se as duas chaves não estiverem configuradas. O redirecionamento HTTPS e as cookies de sessão e CSRF seguras ficam habilitados; habilite HSTS somente depois de confirmar que todo o domínio funciona exclusivamente em HTTPS.

A aplicação usa autenticação, sessões, CSRF, ORM e migrations do Django. As fichas permanecem em JSON para manter o contrato usado pelo editor JavaScript. Usuários sem licença podem criar uma ficha e participar de uma campanha por vez; usuários licenciados não têm esses limites. Cada coluna aceita no máximo três abas, e a primeira aba da primeira coluna não pode ser removida. Convites usam códigos aleatórios únicos, em vez de IDs sequenciais.

## Funcionalidades portadas

- Cadastro explícito e login por e-mail, sessão, perfil, avatar e ativação da plataforma.
- Criação, edição, listagem e exclusão de campanhas; convite por código único, gerenciamento de participantes, vínculo de fichas e anexos da biblioteca.
- Criação e gerenciamento de fichas com três colunas, abas, seções e nove tipos de componente.
- Salvamento automático via API, templates de ficha e avatar do personagem.
- Rolagem e histórico de dados no editor visual.
- Biblioteca com upload, leitura e remoção de PDF, PNG e JPG/JPEG, com validação de conteúdo e controle de acesso.

## Testes

```powershell
python manage.py test
```
