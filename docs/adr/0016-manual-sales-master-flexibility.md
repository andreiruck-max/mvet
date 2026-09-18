# ADR 0016 — Venda manual independente e flexibilidade do master

Data: 18/09/2026. Estado: aceito.

## Contexto

O MVet é o livro gerencial próprio. Uma venda pode não existir no Bling nem ter NF informada. O master deve conseguir iniciar lançamentos incompletos, definir imposto zero e ajustar a receita, sem perder rastreabilidade.

## Decisão

NF é opcional em vendas manuais; sem NF, a venda recebe referência interna por ID. Unicidade NF/série aplica-se apenas a números preenchidos, inclusive em canceladas. Ausência de NF não liga a venda ao Bling nem cria documento fiscal.

Master pode salvar rascunho com todos os campos comerciais vazios: data usa hoje, dinheiro zero, canal/local podem permanecer nulos e itens podem estar ausentes. Produto selecionado com quantidade vazia usa a quantidade padrão 1. Valores inválidos não são silenciosamente corrigidos. Confirmar ainda exige produto/quantidade, canal, estoque ativo, saldo suficiente e data válida. Rascunhos não produzem estoque, caixa ou DRE.

Imposto manual zero é permitido. Master não precisa informar motivo textual: o sistema registra motivo padrão e ator na auditoria. Sem regra/override, seu rascunho adota imposto manual zero. Para outros usuários continuam as validações existentes. Ausência de NF não determina automaticamente tratamento tributário.

O master pode definir receita líquida operacional antes de CMV e custos variáveis. Um ajuste assinado separado conserva a equação: produtos − desconto + frete recebido + ajuste = receita operacional. Ajuste e motivo são auditados; motivo vazio recebe descrição padrão. Receita final não pode ser negativa. Recebível, margens, DRE, dashboard e exportações usam a mesma receita; a DRE explicita a linha de ajuste. Não confundir receita com repasse líquido de marketplace nem descontar taxas duas vezes.

Após confirmação, snapshots continuam protegidos. Não existe edição destrutiva de venda confirmada, bypass de estoque negativo ou alteração de movimentos por ser master. Correções seguem cancelamento/reversão rastreável e regras do financeiro.

## Consequências

Há rascunhos incompletos no sistema, mas somente confirmações válidas entram nos resultados. Usuários operacionais não podem enviar um ajuste de receita pelo backend; a permissão de lançar venda não concede esse poder. NF importada do Bling mantém sua identidade obrigatória: a flexibilidade manual não autoriza inventar ou apagar referência externa.
