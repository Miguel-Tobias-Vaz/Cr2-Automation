# Segurança Supabase — Opto Automações (VPS multi-usuário)

Checklist para o administrador do projeto Supabase antes de abrir o painel na internet.

## 1. Cadastro fechado

No painel Supabase: **Authentication → Providers → Email** (ou provedor usado):

- Desabilite **Enable sign ups** (cadastro público).
- Crie usuários manualmente em **Authentication → Users → Add user**.
- Envie convite ou senha temporária por canal seguro.

## 2. Tabela `profiles` e RLS

Execute o script de referência: [`supabase_profiles.sql`](supabase_profiles.sql)

Confirme:

- RLS **habilitado** em `public.profiles`.
- Políticas `profiles_select_authenticated`, `profiles_update_own`, `profiles_admin_update` ativas.
- Usuário comum **não** consegue alterar `role` ou `ativo` do próprio perfil.

## 3. Primeiro administrador

Após criar o usuário no Auth:

```sql
update public.profiles
set role = 'admin', ativo = true
where email = 'seu@email.com';
```

No servidor (`opto.env`):

```
OPTO_PRINCIPAL_ADMIN=seu@email.com
```

`OPTO_PRINCIPAL_ADMIN` controla quem abre o **painel Admin** (fila global, cleanup). Pode ser o mesmo e-mail do admin Supabase ou lista separada por vírgula.

## 4. Desativar contas

Para bloquear acesso sem apagar o usuário:

```sql
update public.profiles set ativo = false where email = 'usuario@exemplo.com';
```

O backend rejeita sessões com `ativo = false` ([`supabase_auth.py`](../backend/supabase_auth.py)).

## 5. Chaves e segredos

| Chave | Uso |
|-------|-----|
| **Anon (public)** | Front + validação JWT no backend — pode ir no front |
| **Service role** | **Nunca** no painel nem no repositório — só scripts admin no Supabase |

Rotacione a anon key se vazou; atualize `OPTO_SUPABASE_ANON_KEY` e `front/supabase-config.js` na VPS.

## 6. HTTPS

Tokens JWT **sempre** em HTTPS. Use Let's Encrypt (`certbot --nginx`) — ver [`nginx-opto.conf`](nginx-opto.conf).

## 7. Senhas do portal CR2 / WordPress

Login Supabase **não** substitui credenciais que o usuário informa nas automações. Oriente:

- Senhas de portal só nos formulários do painel (gravadas em `runtime.json` no servidor).
- Troca periódica no portal de origem.
- Não reutilizar a senha do e-mail Supabase.

## 8. Variáveis VPS recomendadas

Ver [`opto.env.example`](opto.env.example):

```
OPTO_REQUIRE_AUTH=1
OPTO_SUPABASE_URL=...
OPTO_SUPABASE_ANON_KEY=...
OPTO_PRINCIPAL_ADMIN=admin@seu-dominio.com
OPTO_CORS_ORIGINS=https://seu-dominio.com
OPTO_BIND_HOST=127.0.0.1
```
