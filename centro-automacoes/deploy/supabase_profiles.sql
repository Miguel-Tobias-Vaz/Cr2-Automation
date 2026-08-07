-- Opto Automações — perfis Supabase (referência)
-- Auth: auth.users | Perfil: public.profiles
-- role: admin | editor (editor = usuário comum no painel)

create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text,
  nome text,
  role text not null default 'editor' check (role in ('admin', 'editor')),
  ativo boolean not null default true,
  bio text,
  cargo text,
  avatar text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, nome, role)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'nome', split_part(new.email, '@', 1)),
    coalesce(new.raw_user_meta_data->>'role', 'editor')
  );
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

alter table public.profiles enable row level security;

-- Leitura: qualquer autenticado com perfil ativo
create policy "profiles_select_authenticated"
  on public.profiles for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles me
      where me.id = auth.uid() and me.ativo = true
    )
  );

-- Edição: só o próprio (sem role, ativo, email)
create policy "profiles_update_own"
  on public.profiles for update
  to authenticated
  using (id = auth.uid())
  with check (
    id = auth.uid()
    and role = (select p.role from public.profiles p where p.id = auth.uid())
    and ativo = (select p.ativo from public.profiles p where p.id = auth.uid())
    and email = (select p.email from public.profiles p where p.id = auth.uid())
  );

-- Admin: gerir role e ativo de outros
create policy "profiles_admin_update"
  on public.profiles for update
  to authenticated
  using (
    exists (
      select 1 from public.profiles me
      where me.id = auth.uid() and me.role = 'admin' and me.ativo = true
    )
  );

-- Primeiro admin: no SQL Editor, após criar user no Auth:
-- update public.profiles set role = 'admin' where email = 'seu@email.com';
