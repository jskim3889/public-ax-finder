-- 공공 AX 사례 찾기: 신청자(리드) 저장소
-- Supabase 대시보드 → SQL Editor → New query에 전체를 붙여 넣고 Run. 여러 번 실행해도 된다.
--
-- 서버(Vercel)만 Secret key(sb_secret_…)로 접근한다. 브라우저용 키(anon·publishable)로는
-- 테이블도 함수도 쓸 수 없게 RLS를 켜고 정책을 두지 않으며, 실행 권한도 거둔다 (7강 RLS).
-- 마지막 신청일로부터 1년이 지난 신청자는 register_lead가 호출될 때 지운다(신청 기록도 함께).

create table if not exists public.leads (
  id           bigint generated always as identity primary key,
  email        text not null unique,          -- 소문자로 저장
  name         text not null,
  org          text not null,
  consented_at timestamptz not null default now(),  -- 마지막 동의 시각
  first_seen   timestamptz not null default now(),
  last_seen    timestamptz not null default now(),
  visits       integer not null default 1
);

create table if not exists public.lead_requests (
  id         bigint generated always as identity primary key,
  lead_id    bigint not null references public.leads(id) on delete cascade,
  kind       text not null check (kind in ('map', 'report')),
  ids        text[] not null default '{}',     -- 담은 사업 id
  query      text not null default '',
  needs      text not null default '',
  created_at timestamptz not null default now()
);

create index if not exists leads_last_seen_idx on public.leads (last_seen);
create index if not exists lead_requests_lead_idx on public.lead_requests (lead_id);

alter table public.leads enable row level security;
alter table public.lead_requests enable row level security;
revoke all on public.leads, public.lead_requests from anon, authenticated;
grant select, insert, update, delete on public.leads, public.lead_requests to service_role;

-- 조회·등록·방문 수 갱신을 한 문장으로 묶는다. 동시에 두 번 신청해도 첫 신청은 한 번만 잡힌다
create or replace function public.register_lead(p_email text, p_name text, p_org text)
returns table (lead_id bigint, is_new boolean, visits integer)
language plpgsql
set search_path = public
as $$
begin
  delete from public.leads l where l.last_seen < now() - interval '1 year';
  return query
  insert into public.leads as l (email, name, org)
  values (lower(trim(p_email)), p_name, p_org)
  on conflict (email) do update
    set name = excluded.name, org = excluded.org,
        consented_at = now(), last_seen = now(), visits = l.visits + 1
  returning l.id, (xmax = 0), l.visits;
end;
$$;

create or replace function public.log_lead_request(
  p_lead bigint, p_kind text, p_ids text[], p_query text, p_needs text)
returns void
language sql
set search_path = public
as $$
  insert into public.lead_requests (lead_id, kind, ids, query, needs)
  values (p_lead, p_kind, coalesce(p_ids, '{}'), coalesce(p_query, ''), coalesce(p_needs, ''));
$$;

revoke execute on function public.register_lead(text, text, text) from public, anon, authenticated;
revoke execute on function public.log_lead_request(bigint, text, text[], text, text) from public, anon, authenticated;
grant execute on function public.register_lead(text, text, text) to service_role;
grant execute on function public.log_lead_request(bigint, text, text[], text, text) to service_role;

-- 확인용 (선택): 최근 신청 20건
-- select l.email, l.org, l.visits, r.kind, r.created_at
-- from public.lead_requests r join public.leads l on l.id = r.lead_id
-- order by r.created_at desc limit 20;
