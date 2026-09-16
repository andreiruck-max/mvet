# Estoque — contrato para Fase 2
Estado: especificado, ainda não implementado nesta entrega.
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

Carga e interface ainda não implementadas; esta atualização registra a decisão e os critérios de aceite.
