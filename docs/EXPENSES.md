# Despesas por competência

Em `/despesas/`, registre o valor, descrição, competência do consumo/serviço, data do documento/contrato e vencimento. Fornecedor, favorecido livre, centro de custo, observação e conta prevista são opcionais. Cada despesa cria um único título a pagar, sem movimentar banco. Pagamento parcial/integral e estorno usam o financeiro existente; nunca registrar um débito independente para pagar novamente a mesma despesa.

Competência e documento respeitam o corte da empresa. Pendências anteriores são abertura no financeiro, sem nova despesa. Vencimento não pode anteceder o documento. Pagamento antecipado de competência futura é permitido: a saída ocorre no pagamento e o relatório reconhece a competência futura.

## Plano de contas
Novo cadastro sugere o próximo código livre entre irmãos, inclusive reservando códigos inativos. Selecionar um grupo ajusta a sugestão e a natureza; código digitado manualmente é preservado. **Usar código sugerido** reaplica a sugestão. A sugestão não é reserva: se outra pessoa usar o código antes de salvar, a validação de unicidade pede a revisão. Edição de categorias existentes não renumera registros.

Em **Plano de contas e regras**, cadastre um grupo, por exemplo `04 Despesas operacionais`, natureza operacional e **Aceita lançamentos** desmarcado. Depois crie categorias analíticas como `04.01 Honorários contábeis`. Códigos têm dois dígitos por nível, até oito níveis; filhos têm a mesma natureza do pai. Não há categorias empresariais obrigatórias embutidas.

Despesas aceitam apenas categorias analíticas operacionais ou financeiras. Contas de ativo, passivo, patrimônio e receita não recebem despesas. Compra de estoque e amortização de principal continuam nos módulos próprios. Categoria utilizada permite mudar nome ou inativar; código, pai, natureza e caráter analítico ficam protegidos. Não há exclusão destrutiva pela interface.

## Classificação e correção
A nova despesa prioriza favorecido livre e opcional. O vínculo com fornecedor cadastrado fica em uma seção adicional; sem favorecido, o título usa o nome do fornecedor, como antes. Nenhum dos dois é exigido e nomes livres não criam fornecedores automaticamente. Categoria tem pesquisa por código/nome e mostra o caminho completo no plano; só oferece categorias válidas com ancestrais ativos. Filtrar as opções conserva a categoria já selecionada.

Categoria manual prevalece. Em branco, são aplicadas regras ativas por prioridade crescente, com desempate pela ordem de cadastro. Campos: descrição, favorecido ou CPF/CNPJ do fornecedor; operadores: contém, igual e começa com. Comparação ignora maiúsculas/minúsculas e espaços nas extremidades. CPF/CNPJ deve usar o mesmo formato do cadastro. Ancestral inativo também desabilita a categoria. Sem correspondência, a despesa fica **A classificar**, separada no relatório.

Despesa guarda cópia do caminho/natureza da categoria e da regra aplicada. Renomear categoria ou editar regra não altera histórico. **Corrigir classificação** exige motivo e versão atual; permite categoria manual ou reaplicação explícita das regras atuais. A revisão conserva valores anteriores/novos, usuário e horário. Pode corrigir despesa paga: relatório muda, dinheiro e competência permanecem iguais.

Master pode usar **Editar despesa** para corrigir valor, competência, documento e demais campos, informando motivo. O título acompanha a edição e o histórico guarda antes/depois. Valor não pode ficar abaixo do principal liquidado; documento não pode ultrapassar pagamento existente. Para corrigir pagamentos, estorne e baixe novamente. Cancelamento cancela também a obrigação; não apaga histórico. Não se pode cancelar apenas o título vinculado deixando despesa ativa.

## Recorrência mensal
Marque **Despesa recorrente mensal** na criação. Em **Preparar próximos meses**, escolha de 1 a 24 meses e confira a prévia antes de confirmar. Competência e vencimento avançam com base nas datas originais; dia 31 usa o último dia de meses curtos e volta a 31 quando disponível. Data do documento/contrato original é conservada.

Cada ocorrência cria sua despesa e obrigação, sem pagamento. Categoria manual é conservada; classificação automática é conferida pelas regras atuais na prévia. Alteração relevante entre prévia e confirmação exige nova conferência. A geração usa índice de mês único e transação: repetir não duplica; meses cancelados não são recriados. **Parar novas ocorrências** preserva as já geradas. Para alterar valor/padrão futuro, pare a série e registre nova base.

Esta fase oferece geração mensal por confirmação humana. Agendamento automático, outras periodicidades e edição em lote não estão implementados.

## Consulta e permissões
Filtros por competência (períodos rápidos ou datas), categoria/subcategorias, fornecedor, descrição/favorecido, centro de custo e situação. Lista paginada. Relatório agrupa cópias históricas e separa despesas operacionais, financeiras e não classificadas, incluindo valores pagos ou pendentes conforme filtros. Canceladas são excluídas do resultado.

`operate_expenses`: lançar, consultar registros, corrigir/cancelar e gerar recorrência. `manage_expense_rules`: plano e regras. `view_expense_reports`: consolidados por competência, inclusive API. Operar despesas não concede acesso a bancos nem relatório consolidado. ADMINISTRADOR/FINANCEIRO recebem os três; GERENCIAL recebe consulta consolidada. Backend verifica cada rota e serviço.

## Integração com a futura DRE
Usar Expense ativo por competência e natureza histórica. FinancialTitle associado representa obrigação, não nova despesa; seu rótulo financeiro básico não substitui o plano de contas. Despesas financeiras ficam separadas do EBITDA. Juros adicionais na liquidação precisam ser reconhecidos uma única vez pela política da Fase 7, sem repetir despesa financeira já cadastrada. Não classificados devem ficar visíveis, sem atribuição silenciosa ao operacional. O relatório desta fase não é uma DRE completa.

## Integridade
Decimal/NUMERIC 18,2, chave idempotente/fingerprint, mutex transacional comum, título/despesa/auditoria atômicos e revisão otimista. PostgreSQL impede edição de valores/datas de despesa, exclusão, reclassificação sem revisão correspondente e edição de revisões. Sem CRUD transacional no admin. Testes incluem concorrência, rollback, histórico, permissões, CSRF, recorrência e interface Chromium.

## Plano Mercadovet — 10/10/2026
O atualizador instala o plano por `install_mercadovet_chart`; repetir não duplica. Códigos conflitantes recebem alternativa livre e categorias já utilizadas são preservadas. A instalação não reclassifica despesas históricas. Grupo patrimonial permite filhos de naturezas diversas; nunca lançar principal de financiamento como despesa. Juros são financeiros. Tributos, taxas, fretes e comissões já computados nas vendas não devem ser repetidos em Despesas.

Depreciação/amortização: selecione a categoria específica em Nova despesa e informe a competência. Não gera título nem banco. A DRE deduz após o EBITDA. Registro é manual por competência, sem recorrência financeira. Categoria Pendente de classificação mantém resultado parcial, sem dedução automática do operacional. ADR 0037 prevalece sobre as limitações de naturezas descritas acima.

## Despesas — cartões e filtros automáticos (16/10/2026)

Lista de despesas mostra total registrado, principal liquidado (incluindo baixas futuras), saldo pendente e saldo vencido sobre todos os registros filtrados, antes da paginação. Canceladas e despesas sem movimento financeiro são destacadas separadamente quando presentes; canceladas não compõem o total registrado. Juros e descontos não são confundidos com o principal. Cartões exigem view_expense_reports, preservando a permissão de consolidados. Seleções/datas aplicam filtros automaticamente; textos após pausa de 700 ms, na lista e no relatório. Botão continua disponível sem JavaScript.

Cartões de totais usam faixa compacta no computador e duas colunas no celular, mantendo as explicações das baixas futuras e do saldo vencido.

## Edição e baixa conjunta
Na ficha, **Editar despesa** (master) permite alterar os campos comerciais, vencimento e conta prevista, com motivo obrigatório. Conta prevista não transfere pagamentos anteriores. Alterar categoria conserva revisão; manter a categoria preserva sua classificação histórica. Converter entre obrigação financeira e depreciação sem título exige cancelar/registrar. Edição da base não altera ocorrências já geradas. Canceladas não são editáveis.

Na lista, marque as despesas pendentes ou **Selecionar pendentes desta página** → **Baixar selecionadas** → escolha conta/data → **Conferir baixa** → **Confirmar baixa**. A conferência mostra soma e categoria de cada despesa. Baixa integral dos saldos pendentes, com lançamentos individuais na mesma conta/data; categorias permanecem independentes. Para parcial/juros/descontos, abra o pagamento individual. Não inclui outras páginas automaticamente. Se houver alteração durante a conferência, todo o lote é recusado. Repetir a confirmação não duplica. Baixas futuras só impactam caixa na data escolhida. Exige permissões de operar despesas, financeiro e pagar títulos. ADR 0046.
