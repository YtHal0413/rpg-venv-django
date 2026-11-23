# RPG.Venv v0.4 portado para Django

## Descrição do Projeto

O projeto consiste em uma plataforma voltada para a criação e o gerenciamento universal de fichas de personagens e campanhas de RPG, visando suprir a falta de plataformas dedicadas a alta customização e sistemas de nicho ou próprios.

Tal proposta foi estruturada para integrar, em um único projeto, competências técnicas assimiladas durante o curso de Tecnologia em Sistemas para Internet: Programação Orientada a Objetos, Desenvolvimento para Web, Banco de Dados e Marketing digital.

## Principais Funcionalidades

- Criador customizável de fichas de personagens.
- Simulador integrado de rolagens de dados.
- Criador e controlador de campanhas de RPG.
- Biblioteca de uploads de PDFs e imagens.
- Chatbot de interpretação para personagens de jogadores ausentes.

### Outros recursos

- Cadastro, Login e Logout de usuários
- Edição de dados cadastrais de perfil
- Simulador de aquisição de chave de acesso à plataforma
- Criação de templates para replicação rápida de fichas
- Anexo de arquivos da biblioteca, fichas e templates na campanha

## Arquitetura e Tecnologias

- Backend: Python orientado a objetos + Frameworks/bibliotecas: Django, Pillow e dotenv
- Frontend: JavaScript, HTML e CSS + Framework: Tailwind CSS
- Banco de dados: SQLite.

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


`GEMINI_API_KEY` é obrigatória para usar o chatbot. `GEMINI_MODEL` é opcional; quando omitida, o projeto usa `gemini-3.1-flash-lite`. O arquivo `.env` é carregado pelo Django e ignorado pelo Git para evitar que a chave seja enviada ao repositório. Não compartilhe nem publique esse arquivo. Após criar ou alterar o `.env`, reinicie o servidor Django.

Se o chatbot falhar, a mensagem agora informa o status HTTP retornado pelo Google: `401`/`403` indica chave ou permissão; `429` indica limite/cota; `404` indica modelo inexistente. O log do servidor mostra o código e a descrição retornada pela API, sem registrar a chave. Confira o uso e os limites do projeto no Google AI Studio. Não compartilhe a chave nem o arquivo `.env`. Para `503`, o chatbot repete a chamada uma vez e, se necessário, tenta o modelo estável `gemini-3.5-flash-lite` antes de informar a indisponibilidade.


