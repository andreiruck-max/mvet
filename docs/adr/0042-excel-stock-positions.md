# ADR 0042 — Posição de estoque por Excel

Somente master envia XLSX, confere prévia e aplica. Primeira aba, valores simples, limite de 5 MB/25 MB descompactado/5.000 linhas. Modelo disponível na própria tela. Cabeçalhos SKU, Quantidade e Custo médio obrigatórios; Produto obrigatório para novos SKUs. Unidade nova padrão UN, existentes preservam nome/unidade. Não alterar categoria, markup individual ou situação existente.

Depósito selecionado ou coluna por linha; divergência bloqueia. SKUs repetidos por depósito são erro, nunca soma. Coluna Valor total é opcional e conferida com tolerância de arredondamento de custo de 6 casas. Quantidades até 4 casas, não negativas. Fórmulas só são aceitas com resultado numérico salvo pelo Excel; nenhuma fórmula é executada. Tela orienta recalcular/salvar antes de enviar. Fórmulas sem cache numérico, células com erros, XML externo e entidades são rejeitados. Nenhuma linha é ignorada silenciosamente por erro.

Versão 3 mantém o serviço auditado da ADR0038, com dois modos. Posição atual (padrão) substitui saldos abrangidos no momento de aplicar. Posição histórica substitui a base e soma movimentos posteriores. Neste modo, nova importação do mesmo depósito/base ou presença de conciliação posterior é bloqueada: corrigir por contagem atual. Contagens atuais diferentes podem ocorrer no mesmo dia, assim como bases históricas de depósitos distintos; a antiga unicidade global de data é retirada. Digest único continua impedindo reaplicação idêntica. JSON versão 2 mantém digest e semântica histórica.

Ausentes são preservados por padrão. Zerar ausentes exige opção explícita, restrita aos depósitos representados por linhas válidas. Arquivo vazio nunca zera estoque. Novo produto com definições divergentes entre depósitos é erro.

Prévia não grava. Confirmação valida token, revisão de catálogo/depósitos/saldos/livro e mutex, aplicando atomicamente todos os itens. Contagem atual não atravessa mudança de dia sem nova prévia. Ajustes preservam o livro, custos históricos, vendas e financeiro; preço sugerido da loja acompanha o custo local. Importação não executada automaticamente por instalador/migration.
