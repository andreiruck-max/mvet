# Bling — instalação e operação da importação assistida

## Escopo entregue

Conexão OAuth pelo master; consulta de NF-e emitidas; fila separada, vínculo de códigos, conferência de deduções e confirmação pelos serviços do MVet. Nenhuma escrita fiscal/comercial no Bling. Caixa/bancos, pedidos, webhooks, sincronização de estoque e importação financeira não fazem parte desta entrega.

Sem credenciais a interface mostra conexão pendente. Testes usam exclusivamente respostas sintéticas; homologar com notas reais antes do uso operacional.

## Preparar o servidor

1. Atualizar o código, instalar requirements e aplicar migrations (`python manage.py migrate`).
2. Cadastrar aplicativo na conta Bling com apenas consulta de notas fiscais. Não habilitar escrita, produtos/estoque ou financeiro para este fluxo. Confirmar a disponibilidade dos escopos no plano contratado.
3. Configurar, somente no `.env` privado do servidor: `BLING_CLIENT_ID`, `BLING_CLIENT_SECRET`, `BLING_ISSUER_CNPJ` (14 dígitos) e `BLING_REDIRECT_URI` (endereço exato do MVet seguido de `/integracoes/bling/retorno/`). O mesmo retorno deve constar no aplicativo Bling. O Bling usa o retorno cadastrado no aplicativo, não um parâmetro arbitrário enviado pelo cliente.
4. Gerar `BLING_TOKEN_KEY` com `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Guardar a chave em cofre/backup protegido separado do dump; não enviar segredos no chat nem commitá-los. Tokens rotativos ficam criptografados no PostgreSQL.
5. Reiniciar a aplicação. Master abre **Conexão Bling → Autorizar no Bling**, autentica e concede acesso. Apenas o navegador do usuário precisa alcançar o retorno interno; não expor PostgreSQL nem abrir um receptor público de webhook.
6. Para produção, usar HTTPS interno e cookies seguros conforme DEPLOYMENT.md. Não ativar DEBUG nem registrar query strings da rota de retorno em proxy/access logs: ela recebe um código OAuth de uso único.
7. Conceder individualmente as permissões abaixo. Não há concessão automática a vendedores.

A base aceita um emitente; trocar credenciais não permite misturar CNPJs. Cada chave fiscal recebida é confrontada com o CNPJ configurado. A conexão local pode ser removida sem apagar notas/vendas; revogação do aplicativo deve ser feita no Bling.

## Operar a fila

1. **Notas do Bling → Buscar notas**: selecionar período, situação e página. Cada página contém até cinco notas, com detalhes consultados no servidor. Consulte páginas seguintes quando houver indicação. A data/hora mostrada é a última página bem-sucedida, não uma declaração de sincronização completa do período.
2. Buscar **Autorizadas** e também **Canceladas** para detectar divergências. A API omite canceladas na consulta padrão; o filtro é sempre explícito. Para notas antigas já importadas, usar **Consultar esta nota novamente** no detalhe.
3. Abrir a NF. Ver número/série, data, valor fiscal, loja/pedido externos, itens, códigos, unidades e CFOP. Dados de clientes, XML, tokens e custos do Bling não são armazenados na fila.
4. SKU exato e unidade compatível resolvem automaticamente. Se o código externo for diferente, usar **Vincular código externo a um produto**, buscar o produto MVet e confirmar. O vínculo vale para futuras notas. Não existe associação aproximada por nome nem conversão automática de unidade. Vínculo já utilizado com outro produto não pode ser sobrescrito pela tela.
5. Selecionar canal, estoque e regra de imposto. Valor dos produtos é sugerido pela soma quantidade × preço unitário; não é tratado como total fiscal reconciliado. Conferir desconto, frete recebido, frete pago, taxas, DIFAL, comissão e outros custos. Deduções exigem preenchimento explícito para usuários operacionais; master pode deixar vazio para assumir zero. Adicionar MDR/antecipação em taxas extras sem duplicar valores.
6. Para o operacional, marcar a conferência; para o master, o próprio botão registra a aprovação. Clicar **Conferir e confirmar venda**. A transação cria e confirma a venda, calcula o CMV local, baixa o estoque escolhido e cria o título a receber; não recebe dinheiro automaticamente. Falha em qualquer etapa desfaz todos esses efeitos.
7. Para não incluir uma nota, **Ignorar nota** com motivo. Reconsulta mantém a decisão. **Reabrir conferência** exige ação autorizada e motivo. Uma venda local cancelada jamais é reativada pela importação.

A confirmação é individual. Nesta versão, deduções parcialmente digitadas não são salvas como rascunho de conferência: conclua vínculos antes de preencher os valores. A consulta não gera rascunhos de venda automaticamente. Não há importação em massa sem revisão.

## Limites de aceitação

Somente saída autorizada, finalidade normal, itens de produto com CFOP iniciado em 51, 61 ou 71 e unidades compatíveis. É uma triagem conservadora de venda de mercadoria, não um validador fiscal completo. O operador deve confirmar a natureza comercial. Outros CFOPs, remessas, transferências, devoluções, serviços e documentos incompletos ficam bloqueados; não ampliar a regra sem homologação e testes.

Venda retroativa mantém data comercial, mas a baixa ocorre hoje e usa o custo médio do MVet no momento da confirmação. Não existe reconstrução histórica de custo. Corte e regras locais continuam valendo.

NF/série já existente manualmente bloqueia a importação; comparar a venda existente e ignorar a entrada duplicada com motivo. Não foi implementada associação automática a uma venda manual nem edição de chave/número para contornar duplicidade.

A referência externa e o snapshot aprovado são preservados. Reconsulta atualiza somente a projeção externa; divergência fica visível na fila e não modifica deduções, canal, estoque, CMV ou estado da venda. A divergência permanece sinalizada para revisão; não há encerramento automático de divergências nesta etapa.

## Permissões

- `review_bling`: consultar fila e detalhes comerciais, sem custos/margens/saldos.
- `fetch_bling` + `review_bling`: consultar páginas e atualizar uma nota.
- `map_bling_products` + `review_bling`: vincular código externo; a busca de produtos também exige `view_stock`.
- `approve_bling` + `review_bling`: ignorar/reabrir conferência.
- Para confirmar: também `operate_sales` e `confirm_sales`.
- Conectar/desconectar: master ativo, sem delegação implícita por perfil financeiro.

## Consulta por comando

```sh
python manage.py sync_bling --user LOGIN_AUTORIZADO --start 2026-09-15 --end 2026-09-18 --page 1 --pages 20 --status 5
```

Repetir com `--status 2` para canceladas. Máximo de 100 páginas por execução, período até 366 dias. Interrompe com erro ao encontrar falha; informa a página para repetição. Notas anteriores permanecem na fila e não se duplicam. Não agendar até homologar períodos, permissões e impacto no limite compartilhado do Bling.

Consultas locais são serializadas, com intervalo mínimo de 0,4 segundo; concorrência retorna ocupação. HTTP 429 interrompe a página sem retentativa automática. Reexecutar depois de aguardar; respeitar uso de outras integrações e o limite diário da conta. Rede tem timeout, limite de resposta e redirecionamentos bloqueados. Não utilizar consulta automática agressiva.

## Recuperação e homologação

- Falha de página: consultar histórico na fila e repetir a mesma página. IDs que não puderam ser vinculados aparecem no lote; documentos inválidos têm erro individual.
- Autorização recusada/revogada ou chave perdida: master reautoriza. Nunca editar tokens no SQL.
- Restauração de backup: tokens antigos podem ter sido rotacionados pelo Bling; reautorizar antes de executar novas consultas. A restauração isolada não deve ter acesso às credenciais de produção.
- Homologar nota normal, Full, kit, desconto, MDR, SKU divergente, duplicada, cancelada e falta de estoque. Comparar números/produtos/valores com a fonte; verificar que nenhum custo do Bling aparece no CMV.
- Confirmar que cancelar localmente deixa o Bling intacto e que reconsulta não recria a venda.

Fontes do contrato: [Referência](https://developer.bling.com.br/referencia), [Aplicativos/OAuth](https://developer.bling.com.br/aplicativos), [JWT](https://developer.bling.com.br/migracao-jwt). Contrato examinado em 18/09/2026; mudanças externas exigem revisão do adaptador e nova homologação.

Vendas sem NF ou inexistentes no Bling são lançadas em **Vendas → Nova venda**, sem passar pela fila. Regras do master e ajuste líquido: ADR 0016 e SALES.md.
