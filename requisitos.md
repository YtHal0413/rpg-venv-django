## EXIGÊNCIAS DO PROJETO COM ESCOPO ATUALIZADO

Os requisitos abaixo foram levantados a partir da documentação, telas, rotas, modelos e persistência presentes no repositório. Alguns requisitos possuem evidência executável correspondente na versão anterior do projeto; não significa que o requisito tenha sido validado por uma suíte de testes.

### Estado da primeira etapa Django

A primeira etapa implementa os fluxos RF-01 a RF-07: página inicial pública, login explícito por e-mail e senha, cadastro separado, rejeição de credenciais inválidas e logout, proteção das rotas provisórias, edição do próprio nome de usuário/e-mail/senha e avatar. Avatares aceitam PNG/JPG/JPEG com validação de conteúdo e limite de 16 MiB. As demais áreas ainda não foram migradas: rotas não autenticadas redirecionam para login e, após autenticação, exibem uma resposta vazia provisória.

Esta etapa também estabelece persistência no ORM Django e senhas com o mecanismo de hash do Django, configura idioma pt-BR, proteção CSRF e segredo de produção via ambiente. Os demais requisitos abaixo permanecem como escopo futuro, salvo quando forem implementados em etapas posteriores.

### Estado da segunda etapa Django: biblioteca de arquivos

Implementados para usuários autenticados: listagem exclusiva dos próprios arquivos, upload e remoção, busca por nome, filtros “Documentos” e “Handouts”, visualização de PDFs/imagens e controles de zoom. A biblioteca aceita PDF e imagens PNG/JPG/JPEG, valida assinatura/formato real, correspondência com a extensão e limite de 16 MiB. Os arquivos ficam em armazenamento de mídia por usuário; a pré-visualização verifica a propriedade e aceita requisições HTTP de intervalo para que o PDF.js busque partes do PDF sem transferir/renderizar todas as páginas de uma vez. As páginas do PDF são renderizadas sob demanda perto da área visível.

Esta entrega cobre apenas PDF e imagem, conforme o escopo solicitado para a etapa. O requisito RF-57 menciona também documentos textuais; esses formatos continuam pendentes de decisão e não são aceitos pela biblioteca atual. A associação de arquivos a campanhas foi implementada na quinta etapa.

### Estado da terceira etapa Django: chaves de acesso

Implementados: botão e modal de loja nas páginas autenticadas migradas; pacotes de 1, 5 e 10 chaves, com compra habilitada somente para 1; confirmação de compra demonstrativa sem cobrança; geração de código alfanumérico no formato `XXXX-YYYY-ZZZZ-AAA`, único e de uso único; resgate restrito à conta compradora; ativação persistente do acesso ilimitado; indicador de acesso na área de coleções; e histórico das chaves no perfil. O envio real de e-mail não está habilitado; a notificação após a compra mantém apenas um aviso nominal.

As políticas de acesso básico/ilimitado estão centralizadas: conta básica pode ter uma ficha ativa, participar de uma campanha por vez e não pode criar campanhas; conta com chave não tem esses limites. A criação e participação em campanhas aplicam esses limites. A aquisição nesta etapa é demonstrativa, sem preço ou provedor de pagamento.

### Estado da quinta etapa Django: campanhas

Implementados os fluxos de criação e gerenciamento de campanhas, convites, entrada e saída, limite de participação, edição pelo mestre, vínculo de fichas/arquivos/templates, presença periódica, espectadores, início e parada de sessões e histórico visível ao mestre. Fichas compartilhadas respeitam a visibilidade e são carregadas em modo somente leitura; arquivos só são acessíveis aos membros quando vinculados à campanha. Participantes podem copiar o template do mestre, inclusive quando já possuem outro de mesmo nome.

As relações de participantes, fichas e arquivos são mantidas por relacionamentos ORM, e as sessões registram data, duração e participantes elegíveis online no início. O chatbot Gemini, o contexto persistido da conversa e os relatórios RF-52 a RF-56 e RNF-16 a RNF-19 foram implementados nesta etapa.

### Estrutura do Banco de Dados

Lista com as principais entidades e seus respectivos atributos e relacionamentos:

|Usuario| id (PK) - email (Único) - senha (String) - nome (String) - avatarUrl (String, Opcional) - temChave (Boolean, Padrão: false) - dataCriacao (DateTime).

|FichaPersonagem| id (PK) - nome (String) - aspecto(String) - avatarUrl (String, Opcional) - dataCriacao (DateTime) - estruturaJson (String) - templateID (FK) - usuarioID (FK) 

|Template| id (PK) - apelido (String) - dataCriacao (DateTime) - usuarioID (FK) estruturaJson (String)

|Campanha| id (PK) - titulo (String) - descricao (String, Opcional) - mestreID (FK apontando para o usuário que criou a campanha) - participantes (relação com Usuario) - arquivos (relação com Arquivo) - codigoConvite (String, Único, estruturado em XXX-XXX-XX) - templateMestre (FK opcional) - dataCriacao (DateTime)

|CampanhaParticipante| id (PK) - campanhaID (FK) - usuarioID (FK) - entrouEm (DateTime) - ultimoAcesso (DateTime, Opcional)

|FichaCampanha| id (PK) - campanhaID (FK) - fichaID (FK) - vinculadaEm (DateTime)

|SessaoCampanha| id (PK) - campanhaID (FK) - iniciadaEm (DateTime) - encerradaEm (DateTime, Opcional) - duracaoSegundos (Integer, Opcional) - participantesJson (JSON) - relatorioJson (JSON, Opcional)

|Chaves| codigo (PK, alfanumérico aleatório de uso único estruturado em XXXX-YYYY-ZZZZ-AAA) - usuarioId (FK para a conta compradora, que é a única que pode resgatar) - foiUsada (Boolean) - criadaEm (DateTime) - resgatadaEm (DateTime, Opcional)

|Arquivo| id (PK) - nomeOriginal (String) - arquivo (String) - tipo (Documento/Handout) - dataCriacao (DateTime) - usuarioID (FK)

- Entidade sem especificação mensurável
|IA| (tabela/s relativas ao chatbot se necessário)

### Requisitos Funcionais

- Usuários, sessão e perfil 

[] RF-01: O sistema deve apresentar uma página inicial com acesso às áreas disponíveis e opção para entrar. 
[] RF-02: O sistema deve permitir iniciar sessão informando e-mail e senha. 
[] RF-03: O sistema deve permitir cadastro do usuário quando o mesmo não possui conta
[] RF-04: O sistema deve rejeitar credenciais incorretas para um usuário já cadastrado e permitir encerrar a sessão. 
[] RF-05: O sistema deve exigir sessão autenticada para acessar as áreas protegidas. 
[] RF-06: O usuário deve poder consultar e atualizar seus dados de perfil. 
[] RF-07: O usuário deve poder enviar uma imagem para usar como avatar de perfil. 
[] RF-08: O sistema deve permitir gerar e resgatar uma chave de ativação (uso unico) e registrar seu uso pelo usuário. Na aba Coleções há um indicador que informa se o usuário ativou ou não uma chave. (Implementado; código único de uso único e resgate pela conta compradora.)
[] RF-09: O sistema fornece ao usuario acesso limitado aos recursos de criação de fichas, participação e criação de campanhas para usuarios sem chave. (Limites aplicados aos fluxos migrados.)
[] RF-10: O sistema libera acesso ilimitado aos recursos da plataforma (criação e participação de campanhas e fichas de personagem) após ativação de uma chave. (Aplicado aos fluxos migrados.)

- Gerenciamento de fichas

[] RF-11: O usuário deve poder visualizar suas fichas e campanhas em uma área de coleções. 
[] RF-12: O usuário deve poder listar, gerenciar e excluir suas fichas de personagem. 
[] RF-13: O usuário deve poder criar uma ficha informando nome e aspecto do personagem (frase que resume o conceito do personagem). Caso não tenha ativado uma chave, pode criar apenas 1 ficha por vez (nunca duas ou mais). 
[] RF-14: O usuário deve poder editar e salvar a ficha.
[] RF-15: O editor deve organizar a ficha em até três colunas, cada qual com pelo menos uma aba para um máximo de 3 por coluna. 
[] RF-16: O editor deve permitir criar e excluir abas, exceto a primeira aba da primeira coluna. 
[] RF-17: O editor deve permitir criar e excluir seções dentro das abas. 
[] RF-18: O editor deve permitir criar, atualizar e excluir componentes de seção. 
[] RF-19: O editor deve oferecer os componentes: texto curto; anotações simples, detalhadas ou com checkbox; atributos simples, duplos ou complexos; contador; checkbox.
[] RF-20: O editor deve permitir alterar valores, rótulos, descrições, marcações e demais campos próprios de cada componente. 
[] RF-21: O editor deve permitir enviar ou remover a imagem do personagem de uma ficha. 
[] RF-22: O proprietário deve poder definir a visibilidade da ficha para campanhas entre “todos” e “mestres”. 
[] RF-23: O sistema deve salvar a ficha automaticamente após alterações do editor.
[] RF-24: O sistema deve salvar a estrutura e os dados da ficha no banco por meio de JSON e disponibilizá-los novamente ao carregá-la. 
[] RF-25: O proprietário deve poder salvar a estrutura atual da ficha como template apelidado.
[] RF-26: O usuário deve poder listar seus templates. 
[] RF-27: O usuário deve poder aplicar um template a uma ficha própria, preservando dados de identidade da ficha, como nome, aspecto e imagem de avatar. 
[] RF-28: O usuário deve poder excluir seus templates. 
[] RF-29: O editor deve disponibilizar um simulador de rolagem de dados. 
[] RF-30: O usuário deve poder configurar uma pilha de dados e executar a rolagem. 
[] RF-31: O simulador deve oferecer opções de contagem de sucessos e explosão de dados. 
[] RF-32: O editor deve apresentar resultados e manter histórico de rolagens durante a sessão de uso. 

- Gerenciamento de campanhas

[] RF-33: O usuário não licenciado deve poder participar de 1 campanha por vez e não ser capaz de criar uma própria.
[] RF-34: O usuário licenciado deve poder criar e participar de quantas campanhas quiser
[] RF-35: O usuário cria uma campanha inserindo um título e uma descrição (opcional). 
[] RF-36: O sistema deve atribuir o usuário criador como mestre da campanha. 
[] RF-37: Um usuário deve poder entrar em uma campanha usando um código de convite. 
[] RF-38: O sistema deve listar campanhas das quais o usuário é mestre ou participante. 
[] RF-39: O mestre deve poder editar titulo e descrição da campanha. 
[] RF-40: O mestre deve poder excluir a campanha e remover participantes.
[] RF-41: Um participante que não seja o mestre deve poder sair da campanha.
[] RF-42: Um usuário deve poder vincular uma ficha própria a uma campanha e remover o vínculo. 
[] RF-43: A tela da campanha deve listar o mestre e usuários participantes (e se estão onlines ou não), além das fichas vinculadas, distinguindo participantes com ficha dos espectadores (participantes sem ficha). 
[] RF-44: A ficha vinculada deve poder ser visualizada conforme suas regras de acesso.
[] RF-45: O mestre deve poder vincular ou remover o vinculo à campanha um ou mais arquivos de sua biblioteca. 
[] RF-46: O mestre deve poder vincular ou remover o vinculo à campanha um template seu.
[] RF-47: Um participante deve poder copiar o template anexado pelo mestre para si.
[] RF-48: A campanha deve possuir uma aba "Histórico de Sessões", visível apenas para o mestre. Nela são armazenados um histórico com instâncias de sessão (de RPG).
[] RF-49: O sistema deve possuir um botão "Iniciar sessão" com um timer de duração.
[] RF-50: O sistema deve possuir um botão "Parar sessão", ao fazer isso, é salvo no histórico uma instância de sessão (de RPG) com a lista de participantes presentes, data e duração.
[] RF-51: O sistema deve checar quais participantes (exceto os espectadores) estão online quando o mestre Iniciar uma Sessão (contagem de presença) 
[ x ] RF-52: O sistema cria o botão “Chatbot com IA” com balão ao lado da inclusão de personagens e abre painel lateral.
[ x ] RF-53: O chatbot lê as fichas dos participantes faltosos no início da sessão, interpreta comandos Gemini e executa rolagens contextuais.
[ x ] RF-54: O chatbot responde por personagem faltoso e persiste o contexto das ações em chatbot_json da sessão.
[ x ] RF-55: Ao encerrar, o chatbot gera e persiste em relatorio_json o relatório atrelado à sessão do histórico.
[ x ] RF-56: O relatório contém resumo das ações, revisão de ficha e veredito final de cada personagem.

- Biblioteca de documentos

[] RF-57: O usuário autenticado deve poder consultar sua biblioteca pessoal de arquivos. (Implementado para PDFs e imagens.)
[] RF-58: O usuário deve poder enviar arquivos (PDFs e PNG/JPG/JPEG) para sua biblioteca. 
[] RF-59: O usuário deve poder remover arquivos de sua biblioteca. (Implementado com verificação de propriedade.)
[] RF-60: A interface deve permitir pesquisar a lista de arquivos e visualizar o arquivo selecionado. (Implementado; PDF e imagens.)
[] RF-61: A interface deve dividir a lista de arquivos por seu tipo, como "pastas" (Documentos e Imagens). (Implementado como filtros Documentos e Handouts.)
[] RF-62: O mestre deve poder selecionar livros da própria biblioteca para associá-los à campanha.

- Persistência e interfaces do sistema 

[] RF-63: O sistema deve inicializar as tabelas SQL a partir do esquema e manter as entidades de usuários, fichas, campanhas, templates e arquivos. 
[] RF-64: O sistema deve disponibilizar endpoints JSON para carregar/salvar fichas e gerenciar templates. 
[] RF-65: O sistema deve informar operações e erros ao usuário por mensagens na interface ou respostas de erro da API. 
[] RF-66: O sistema deve mostrar um botão "Receba acesso Ilimitado" ao lado do icone de perfil. Ele abre uma modal "Adiquirir chaves". (Implementado nas páginas autenticadas migradas.)
[] RF-67: A modal "Adiquirir chaves" lista tres opções de pacotes de chave com 1, 5 e 10 chaves (apenas o primeiro está disponível). (Implementado; pacotes de 5 e 10 estão desabilitados.)
[] RF-68: A modal "Adiquirir chaves" gera um código XXXX-YYYY-ZZZZ-AAA de uso único ao comprar um pacote de chaves e o envia por email ao email cadastrado pelo usuário. (Implementado para compra demonstrativa do pacote de 1 chave; sem cobrança.)
[] RF-69: A modal "Adiquirir chaves" possui um campo de resgate de chaves, quando feito isso, é registrado no perfil do usuário um item de lista com a chave resgatada. (Implementado; resgate vinculado à conta compradora.)

### Requisitos Não-Funcionais

[] RNF-01: A aplicação deve ser acessível por navegador por meio de uma aplicação web. 
[] RNF-02: A interface deve oferecer conteúdo em português brasileiro. 
[] RNF-03: A interface deve adaptar sua apresentação a diferentes larguras de tela 
[] RNF-04: A aplicação deve persistir os dados principais entre acessos. 
[] RNF-05: A imagem de perfil deve restringir-se às extensões PNG, JPG/JPEG. 
[] RNF-06: A biblioteca deve aceitar apenas arquivos de extensão PDF, PNG e JPG/JPEG. (Implementado com validação do conteúdo correspondente.)
[] RNF-07: A interface deve fornecer retorno visual para ações e erros comuns. 
[] RNF-08: O editor deve refletir alterações da ficha dinamicamente sem exigir recarga completa para cada ação. 
[] RNF-09: Segredos de sessão devem ser fornecidos por configuração segura, sem valor padrão conhecido no código. 
[] RNF-10: Senhas devem ser armazenadas usando algoritmo apropriado de criptografia.
[] RNF-11: Autenticação deve comprovar a identidade e impedir cadastro implícito por qualquer combinação nova de e-mail/senha. 
[] RNF-12: Operações de leitura e escrita devem aplicar autorização consistente por usuário, campanha e ficha. 
[] RNF-13: O sistema deve manter consistência nas relações de campanha e ficha 
[] RNF-14: As alterações devem ser preservadas com tratamento explícito de falhas de gravação e retorno confiável ao usuário. 
[] RNF-15: Dados de entrada e arquivos enviados devem ser validados pelo conteúdo, formato, tamanho e contexto de uso. (Parcialmente implementado nesta etapa para PDFs, imagens, tamanho e propriedade dos uploads.)
[ x ] RNF-16: respostas coerentes com ficha, aspecto, estrutura e contexto da personagem interpretada.
[ x ] RNF-17: rolagens simuladas pelo servidor com quantidade de dados, dificuldade e regra de explosão.
[ x ] RNF-18: relatórios padronizados por personagem com resumo, revisão da ficha e veredito.
[ x ] RNF-19: a IA consulta os três últimos relatórios da campanha antes de interpretar a sessão atual.


### Requisitos ainda sem especificação mensurável

O repositório não define valores-alvo ou mecanismos verificáveis para os itens abaixo. Portanto, não devem ser apresentados como garantias atuais:

- tempo máximo de resposta, capacidade de usuários simultâneos ou volume máximo de fichas/campanhas;
- disponibilidade, recuperação após falha, backup e restauração do banco e dos arquivos;
- política de retenção, privacidade, exportação e exclusão de dados pessoais;
- monitoramento, auditoria, logs estruturados e alertas operacionais;
- Métodos de segurança;

Esses pontos são lacunas de especificação/validação identificadas no material do projeto; a lista não afirma que cada controle esteja completamente ausente de toda execução possível, mas que não foi estabelecido como requisito mensurável nem demonstrado pelos arquivos examinados.