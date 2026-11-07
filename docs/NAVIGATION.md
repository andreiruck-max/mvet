# Navegação e ações rápidas

Revisão de 07/11/2026. Alteração preparada na branch de trabalho; integração depende de autorização.

## Critério
A navegação entre áreas e consultas continua na própria aba. Ações curtas abrem uma janela sobre a tela atual. O cadastro completo de uma venda ou compra, a conferência de notas, importações, conciliações com prévia e relatórios continuam em página própria. WhatsApp conserva a abertura externa explícita.

| Área revisada | Janela de ação | Página própria |
| --- | --- | --- |
| Financeiro | Transferência, crédito/débito em conta, cadastro/edição de conta, título manual, edição de título, baixar pagamento | Fluxo, extratos, ficha e histórico do título/operação |
| Despesas | Nova despesa, edição, categorias e regras | Lista, relatório, baixa em lote e geração de recorrências com prévia |
| Comissões | Recebimento, estorno/ajuste, revisão de parcelas e pagamento | Definição inicial do plano, ficha completa, apuração e relatórios |
| CRM | Cadastro/edição do contato, registrar interação, próxima ação/status, analisar solicitação | Carteira, ficha e histórico, importação, distribuição e indicadores |
| Estoque | Cadastro/edição do produto, contagem, preço individual e movimento avulso | Listagem, kits, transferência em lote, posição Excel com prévia, comparação Bling e planejamento |
| Compras | Cadastro/edição do fornecedor | Compra com itens/parcelas, recebimento, conferência Bling e consultas |
| Vendas | Ações de comissão acessadas pela venda | Lançamento, correção de valores/CMV, recuperação e tributação com impacto amplo |
| Administração | — | Usuários/permissões, senha, conexão Bling, configurações globais e notificações |

## Comportamento
- Cancelar ou fechar mantém a tela, filtros, seleção e rolagem de origem. Alterações não salvas exigem confirmação antes de descartar.
- Salvar retorna à mesma URL, com filtros e página, atualizando os dados e restaurando rolagem e foco quando o link ainda existe. Mensagens de resultado continuam usando o mecanismo do Django.
- Se a tela de origem contém um formulário POST em edição, preserva esses campos e avisa que é preciso atualizar após salvá-los; não recarrega silenciosamente e não descarta o rascunho.
- Erros de validação ficam na janela com os valores informados. O envio não é repetido automaticamente; a proteção de idempotência dos serviços continua ativa.
- Fechar, Escape e Abrir nesta página ficam disponíveis. No celular a janela ocupa a tela, com cabeçalho e fechamento acessíveis. Cliques modificados e downloads mantêm o comportamento do navegador.
- Sem JavaScript ou suporte a dialog, os links normais continuam operando. Sessão expirada/falha de carregamento oferece abertura normal, sem repetir operações.

## Implementação e manutenção
`apps/core/modals.py` é a lista explícita de ações elegíveis. `static/action-modal.js` usa dialog nativo com formulário isolado em iframe de mesma origem, preservando scripts de moeda, busca, datas, CSRF e as validações existentes sem reinicializar scripts globais. Apenas as rotas autorizadas para modal permitem SAMEORIGIN; demais páginas continuam DENY. A nova rota GET de pagamento só exibe o formulário; a liquidação continua no serviço POST original e com suas permissões. Não há migração nem alteração nos cálculos financeiros.

Novas ações devem ser classificadas nessa lista e ter teste de retorno à origem, validação e permissão. Não abrir modais dentro de modais. A revisão cobriu rotas, templates, scripts de navegação e fluxos de testes dos módulos acima; as páginas longas foram mantidas por decisão de uso, e não por conversão incompleta.
