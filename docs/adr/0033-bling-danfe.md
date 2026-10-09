# ADR 0033 — NF autorizada com DANFE emitida

A API Bling distingue Autorizada (5) de Emitida DANFE (6). Ambos são aceitos na conferência de vendas, mantendo chave/emitente, saída, finalidade, itens, permissões e confirmação explícita. Canceladas e demais situações permanecem bloqueadas.

A seleção padrão da tela consulta 5 e 6 separadamente, com paginação para ambos. O valor 56 identifica apenas essa seleção local; nunca é enviado como situação à API. Consulta específica continua independente de data/situação.

Trocar 5 por 6 ou vice-versa não caracteriza alteração comercial nem duplica venda/estoque. O status externo verdadeiro e o snapshot aprovado são preservados. Alterações comerciais e cancelamentos continuam sinalizando divergência. Recuperação explícita pelo master aceita ambos os status.

Referências verificadas em 09/10/2026: https://developer.bling.com.br/referencia e https://ajuda.bling.com.br/hc/pt-br/articles/4410476179095-Gerar-e-enviar-a-remessa-para-a-Logística-Olist (artigo 4410476179095).

A API retornou vazio também em consultas por número com situação 6 explícita na máquina do usuário. A presente correção de status não demonstra resolução dessa segunda ocorrência; requer diagnóstico por ID/chave fiscal.
