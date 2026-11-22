# ADR 0070 — Propriedade empresarial do CRM

Contatos, interações, eventos, solicitações de inativação, lotes de importação e liberações recebem owning_company obrigatório com default Mercadovet e bloqueio transitório da empresa secundária. O campo company original mantém exclusivamente o texto Empresa/fazenda do cliente, sem renomeação ou conversão.

DDL aditivo preserva a carteira, textos, atividades, agenda e histórico. Não habilita o CRM de outra empresa antes de contextualizar serviços, consultas, configuração de entrada e recorrência. Unicidades atuais de telefone/e-mail permanecem até essa etapa.

Testes verificam distinção entre fazenda do cliente e empresa proprietária, rejeição de empresa secundária e preservação de contato/interação/evento após migration. Exigir PostgreSQL/navegador antes de integrar. Sem produção.
