# Estoque — contrato para Fase 2
Estado: implementado no PR #11, com backend PostgreSQL e fluxo visual aprovados no [CI](https://github.com/andreiruck-max/mvet/actions/runs/35041612447).
- Cadastro manual de SKU único, produto, marca, categoria, unidade, mínimo e status.
- Abertura em 15/09/2026 por movimento, quantidade e custo informados; sem lançamento de resultado.
- Locais de estoque separados; custo médio global por produto.
- Cada movimento registra quantidade, valor e custo, ator, data efetiva, horário de criação, tipo, origem, referência e observação.
- Entrada pondera custo: (valor anterior + valor recebido) / quantidade final.
- Quantidade 4 casas; custo/valorização 6; Decimal sempre. Última saída absorve resíduos.
- Confirmar saída sob lock de produtos por ID crescente. Saldo insuficiente bloqueia a operação inteira.
- Transferência conserva quantidade/valor globais. Fracionamento baixa origem e credita destino com custo proporcional; custos acessórios futuros serão explícitos.
- Kit virtual baixa componentes. Cancelamento reverte componentes efetivamente baixados, independentemente de composição futura.
- Livro imutável com reversões. Não recalcular CMV histórico.
- Aberturas após início de movimentações exigem validação de corte, sem aplicar vendas antigas duas vezes.

Testes de aceite: abertura/entrada/média/saída/negativo/local/transferência/fracionamento/kit/cancelamento e duas saídas concorrentes em PostgreSQL.

## Base inicial autorizada
Por orientação do usuário em 15/09/2026, utilizar SKU, descrição, quantidade e custo médio da aba ESTOQUE MVET de ERP Mvet(2).xlsx como saldo atual de referência para desenvolvimento. Não exigir nova contagem prévia. A autorização abrange somente estoque, sem migração integral das demais abas.

Registrar movimentos de abertura em 15/09/2026, sem efeito na DRE, como posição anterior às novas operações do sistema. Não reaplicar automaticamente vendas antigas. Validar inconsistências e duplicidades, produzir relatório e garantir idempotência da carga. Dados comerciais e planilha ficam fora do Git, em ambiente privado.

Disponibilizar ajustes de acréscimo e redução com motivo obrigatório, usuário, data efetiva e posição anterior/posterior. Reduções utilizam custo vigente; acréscimos exigem custo informado ou confirmação do custo vigente. Correção de custo é operação própria e auditada, preservando CMV histórico. Não editar nem apagar movimentos confirmados; corrigir por estorno ou novo ajuste.

Carga inicial por comando e interface manual implementadas na Fase 2.

## Uso da Fase 2
1. Abra Produtos e estoque. Cadastre locais, marcas e categorias, conforme necessário.
2. Cadastre produto simples ou kit virtual. SKU é único. A unidade descreve a unidade comercial (UN, KG etc.); mudar unidade/tipo após uso é bloqueado.
3. Use Movimentar estoque: abertura, entrada, saída, ajuste positivo/negativo, transferência, fracionamento, saída de kit ou correção de custo.
4. Para kits, edite a composição antes da primeira saída. São aceitos vários componentes simples; kits aninhados não são aceitos nesta fase.
5. Para fracionamento, informe produto/quantidade de origem e produto/quantidade produzida. Todo o custo consumido passa ao destino, sem custo adicional implícito. A conversão é informada, não inferida do nome.
6. A tela do produto mostra quantidades por local e histórico; custo aparece somente com core.view_costs.

Cada formulário leva um identificador único. Repetir envio retorna a mesma operação; reutilizar o identificador com outros dados é erro. O backend aplica autorização antes de ler ou movimentar dados.

## Datas e estornos
Abertura usa a data de corte e só pode ocorrer antes de qualquer movimento do produto. Quantidade zero preserva o custo de referência sem valor em estoque. Movimentos físicos futuros são bloqueados. Data passada é aceita somente se não preceder movimento já registrado dos produtos envolvidos; correções anteriores devem virar ajuste atual.

Estorno exige ser a última operação ainda não estornada de cada produto. Se houver operações posteriores, estorne-as em ordem inversa ou faça ajuste atual. Um estorno não é estornado novamente. Os componentes e custos originais são recuperados do livro, independentemente da composição atual do kit. Esta política é de estoque; o cancelamento comercial completo será tratado na Fase 3.

## Concorrência e integridade
PostgreSQL: mutex transacional do domínio de estoque (pg_advisory_xact_lock) serializa as escritas curtas, inclusive cadastros e composições. Produtos são travados em ordem de ID antes dos locais/saldos. A opção deliberadamente prioriza integridade para o volume inicial; está documentada no ADR 0007.

Movimentos e operações são imutáveis por modelo e por triggers PostgreSQL contra UPDATE/DELETE. Os saldos são projeções do livro e só são atualizados por serviços. Não há edição transacional livre no admin. Conferir com `python manage.py check_inventory`.

## Carga restrita ao estoque
O comando lê somente A:D da aba ESTOQUE MVET. Não importa a tabela auxiliar repetida nem outras abas. Usa números em cache das fórmulas; ausência de cache bloqueia a linha. Ruído decimal do Excel abaixo de 0,000000001 é normalizado. Custos são arredondados a seis casas, com aviso quando há alteração material de precisão.

```bash
python manage.py import_initial_inventory arquivo.xlsx --actor ID_USUARIO
python manage.py import_initial_inventory arquivo.xlsx --actor ID_USUARIO --merge-duplicates
python manage.py import_initial_inventory arquivo.xlsx --actor ID_USUARIO --merge-duplicates --commit
python manage.py check_inventory
```

Sem --commit, nada é gravado. O usuário deve possuir operate_stock e view_costs. A consolidação de SKU repetido é explícita e só aceita nomes iguais: soma quantidades e pondera os custos pelo valor; quantidade zero não pondera. Custos divergentes com ambas quantidades zeradas são ambíguos e bloqueados. Qualquer erro bloqueia a carga inteira. Repetir o mesmo arquivo não duplica; arquivos diferentes contendo SKUs já cadastrados não sobrescrevem os produtos.

O local padrão é Estoque inicial, pois a planilha não identifica o depósito de cada unidade. Depois, distribua por transferência. Dados reais nunca integram fixtures, commits ou artefatos públicos de CI.

## Integração com vendas (Fase 3)
SALE_OUT baixa os produtos/componentes na confirmação e SALE_RETURN devolve pelo valor original. O retorno recalcula a média corrente; não reescreve snapshots de vendas. Use cancelar na tela de vendas; estorno genérico rejeita essas operações. Produto referenciado em item, inclusive rascunho, é inativado e não excluído; tipo/unidade ficam preservados. Ver docs/SALES.md e ADR 0008.

## Compras e transferências (Fase 4)
PUR_RECEIPT valoriza cada entrada pelo rateio exato de aquisição, no estoque selecionado. PUR_RETURN cancela o recebimento somente se não houver movimentos posteriores nos produtos. Não estornar essas operações pelo estorno genérico: usar a tela de compra. Produto utilizado em item de compra também é inativado, sem exclusão física ou troca de tipo/unidade.
Transferência entre quaisquer estoques ativos continua disponível, inclusive após receber compras; conserva quantidade/valor global e média. Testes cobrem receber no Mercadovet, transferir parte ao Full, bloquear cancelamento indevido e reverter a transferência antes de cancelar a compra.

## Posição inicial por depósito (JSON privado)

`import_inventory_locations arquivo.json --username LOGIN` valida os dados e o banco
sem gravar. Acrescentar `--commit` aplica todos os depósitos numa transação.
Formato: `{"version":1,"date":"2026-09-21","products":[{"sku":"EXEMPLO","name":"Produto exemplo","unit":"UN","balances":[{"location":"Estoque Mercadovet","quantity":"2","cost":"3.50"}]}]}`.
Decimais usam ponto, sem separador de milhar. `note` opcional em cada saldo documenta
correções autorizadas. O arquivo real fica fora do Git.

Um SKU compartilhado é cadastrado uma vez. Cada depósito mantém sua quantidade;
o produto recebe custo médio global ponderado. Não sobrescreve SKUs existentes.
A data da posição não retroage ao corte: ver ADR 0018. Não reconfirmar operações
passadas já refletidas nessa posição. Após a carga, executar `check_inventory`.
A repetição é ignorada inclusive após estorno; nova aplicação exige conciliação.

## MVet 1.5 — regra vigente
A partir da 1.5, custo médio e valor são independentes por depósito (ADR 0019), substituindo as referências históricas acima ao custo global. Product exibe apenas o consolidado. Lista: depósito padrão, botões de alternância, 50 itens/página, SKU numérico, busca numérica exata e totais sem filtros. Exportações seguem o depósito. Estoques inativos continuam compondo os totais. Correção de custo afeta somente o depósito informado.
