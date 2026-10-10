# Segurança e configuração local

## Dados que nunca devem ser versionados

- Arquivos `.env` e variantes locais.
- Senhas, tokens, chaves de API e credenciais de banco de dados.
- Chaves privadas, certificados e arquivos de credenciais.
- Bancos locais, volumes Docker, logs, caches e ambientes virtuais.
- Relatórios ou documentos gerados que possam conter metadados locais.

Esses itens estão cobertos pelo `.gitignore`. O arquivo `.env.example` contém
somente nomes de variáveis e valores de demonstração; copie-o para `.env` e
defina os valores reais apenas na máquina de execução.

## Antes de publicar

1. Verifique os arquivos staged com `git diff --cached --name-only`.
2. Procure credenciais com uma ferramenta de secret scanning ou com as regras
   de segurança da plataforma Git.
3. Se um segredo for versionado, revogue-o imediatamente; removê-lo apenas do
   commit mais recente não elimina o valor do histórico.

## Relato de vulnerabilidades

Não publique credenciais ou detalhes exploráveis em issues públicas. Use um
canal privado do responsável pelo repositório para relatar vulnerabilidades.
