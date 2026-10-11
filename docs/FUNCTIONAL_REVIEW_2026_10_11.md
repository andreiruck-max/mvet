# Revisão funcional — 11/10/2026

Revisão transversal do código e testes do MVet, sem acesso ao banco operacional.
Dados de validação são sintéticos. Não equivale a uma auditoria contábil dos lançamentos
nem a garantia de ausência de falhas.

## Problemas corrigidos

1. **Vencimento reagendado inconsistente:** consultas de compras, ficha do fornecedor,
   detalhe da compra e exportações usavam o vencimento contratual da parcela, embora o
   financeiro já utilizasse o vencimento renegociado. Agora usam a previsão atual do
   título; o vencimento original permanece armazenado e é identificado nas fichas.
   Rascunhos sem título continuam usando a data da parcela. Filtros, ordenação e XLSX/PDF
   compartilham a mesma data corrente. Não há alteração no valor nem no histórico.
2. **Excel do caixa ignorava a visão:** o quadro horizontal exportava sempre realizado,
   mesmo ao escolher Realizado + previsto. Agora respeita a seleção, incluindo baixas
   futuras e compromissos; a aba detalhada identifica explicitamente realizado e projetado. Os botões de exportação
   voltam a estar acessíveis na página do caixa, restritos à permissão de exportar financeiro.
3. **Cálculo duplicado do caixa:** a página materializava duas vezes o mesmo livro para
   montar cartões e grade. Passa a reutilizar a projeção, reduzindo consultas e tempo
   sob o lock compartilhado, mantendo uma única base de cálculo.
4. **Validação numérica:** decimais com magnitude extrema podiam gerar InvalidOperation
   antes da validação do limite. O limite passa a ser verificado antes da quantização.
5. **Justificativa de cancelamento sem caixa:** depreciações não passavam pela validação
   do motivo usada pelos títulos. Agora o cancelamento também exige motivo de até 500 caracteres.
6. **Escopo bancário mais claro:** a Dashboard informa contas ativas e inativas;
   o fluxo operacional permanece só com ativas. Essa diferença é deliberada (ADR 0027),
   não foi alterada nem tratada como erro de saldo.

## Áreas examinadas

- Acessos: políticas individuais, permissões por capacidade e navegação de retorno.
- Estoque/produtos: movimentos, estornos, custos por depósito, preços, contagem e planejamento.
- Vendas: confirmação, correção, cancelamento, tributação e vínculo com comissões.
- Compras: confirmação/recebimento separados, rateios, parcelas, fornecedores e exportações.
- Financeiro/despesas/DRE: baixas futuras, projeções, estornos, classificação e recorrência.
- CRM: carteira, normalização, importação, histórico e distribuição diária.
- Bling: transporte, atualização de credenciais, normalização, elegibilidade e ações em massa.
- Relatórios/notificações: filtros, agregações, exportações, alertas e restrição de dados.
- Interface/configuração: entradas monetárias, busca de produtos, configuração Django e checagem da instalação.

Não foi alterada política tributária, de comissão, confirmação de nota, custo histórico,
permissão ou regra de reconhecimento da DRE. Nenhuma migration necessária.

## Melhorias futuras identificadas, sem mudança automática

- O lock global garante consistência, mas relatórios longos e importações extensas ainda
  podem atrasar operações. Medir com volume real antes de trocar a estratégia de isolamento.
- Importação do CRM e seleção de responsáveis fazem consultas por linha/usuário.
  Para volumes maiores, avaliar carregamento em lote mantendo duplicidades e permissões.
- Disponibilidade de kits deve evoluir de forma consistente por depósito também no catálogo
  e exportações; hoje a apresentação do kit não tem a mesma cobertura dos produtos simples.
- O estoque de reposição usa movimentação efetiva como histórico; mudanças de depósito de
  vendas antigas podem concentrar saídas na data da correção. Uma evolução deve distinguir
  demanda comercial e data física, sem reescrever o livro.

## Validação

Testes de regressão cobrem vencimento atual/original, filtros de atrasados, ordenação por
fornecedor, exportação, projeção futura sem duplicação, escopo de contas inativas,
quantidade de cálculos do caixa, valores extremos e motivo obrigatório. Aceitação em
Chromium confere a ficha renegociada e o arquivo baixado na visão projetada.
A suíte completa e os gates PostgreSQL/Windows/navegador são exigidos antes da integração.
