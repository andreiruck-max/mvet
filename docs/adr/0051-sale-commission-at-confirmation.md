# 0051 — Cliente e comissão na confirmação da venda

Data: 02/11/2026. Status: aceito.

Venda passa a guardar cliente, comissionado opcional e total manual opcional. O cadastro do canal pode apontar um comissionado padrão. Alterar esse vínculo exige manage_channels e manage_commissions. Operadores de venda podem selecionar pessoa ativa e valor manual no rascunho, sem ganhar acesso à gestão, apuração ou pagamento de comissões.

Na confirmação, pessoa explícita prevalece sobre a vinculada ao canal. Total manual, inclusive zero, prevalece sobre percentual da pessoa e padrão global. Vazio usa o padrão; não inventar percentual quando ambos estiverem ausentes. Rascunhos antigos com custo de comissão positivo são preservados como total manual. Sem pessoa nem vínculo, a venda mantém comportamento anterior: comissão informada é somente custo, sem plano. Pessoa inativa ou falta de percentual, sem total manual, impedem confirmar de forma atômica, sem saída de estoque parcial.

Geração automática usa o mesmo cálculo, comando idempotente, SaleCorrection e livro de comissões existentes. OneToOne e chave determinística impedem duplicar. A comissão substitui o custo da venda; não cria despesa adicional, recebível nem banco. Cria uma parcela com produtos − desconto + frete, vencimento na data da venda; o cronograma pode ser ajustado no controle de comissão. Base de comissão percentual continua produtos − desconto, sem frete. Criar o controle não registra recebimento nem libera comissão para pagamento.

Bling copia o nome normalizado do cliente da nota conferida para venda e plano; não aceita nome adulterado no POST. Venda manual aceita nome livre de até 240 caracteres. Confirmação preserva esse nome como histórico. Refresh externo não reescreve nomes de planos antigos. Não há comissões retroativas criadas automaticamente.

Migração vincula somente os pares explicitamente solicitados: [VENDEDOR] CESAR → CESAR OLIVEIRA; [VENDEDOR] LUCAS → LUCAS ABRANCHES. Exige cadastros ativos e correspondência única, ignorando caixa/acentos/espaços. Não cria pessoas nem percentuais e não sobrescreve vínculos existentes. Ausência ou duplicidade emite aviso para conferir Canais de venda. Outros canais são configurados pela interface.
