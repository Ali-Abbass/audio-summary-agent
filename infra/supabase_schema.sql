-- Apply this file in Supabase SQL editor.
create extension if not exists pgcrypto;

create table if not exists audio_assets (
  id uuid primary key default gen_random_uuid(),
  user_email text null,
  storage_path text null,
  content_type text not null,
  duration_ms int null,
  created_at timestamptz not null default now()
);

create table if not exists transcripts (
  id uuid primary key default gen_random_uuid(),
  audio_id uuid references audio_assets(id) on delete cascade,
  text text not null,
  provider text not null,
  created_at timestamptz not null default now()
);

create table if not exists summary_requests (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  audio_id uuid null references audio_assets(id) on delete set null,
  transcript_id uuid null references transcripts(id) on delete set null,
  raw_transcript text null,
  send_at timestamptz not null,
  status text not null default 'pending',
  attempts int not null default 0,
  last_error text null,
  locked_at timestamptz null,
  lock_token uuid null,
  summary_json jsonb null,
  transcript_text text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint summary_requests_status_check check (status in ('pending', 'processing', 'sent', 'failed'))
);

create table if not exists email_deliveries (
  id uuid primary key default gen_random_uuid(),
  request_id uuid references summary_requests(id) on delete cascade,
  provider text not null,
  message_id text null,
  status text not null,
  sent_at timestamptz null,
  error text null
);

create index if not exists idx_summary_requests_status_send_at
  on summary_requests(status, send_at);

create index if not exists idx_summary_requests_lock_token
  on summary_requests(lock_token);

create or replace function set_summary_requests_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_summary_requests_updated_at on summary_requests;
create trigger trg_summary_requests_updated_at
before update on summary_requests
for each row
execute function set_summary_requests_updated_at();

create or replace function claim_due_requests(batch_size int)
returns table (
  id uuid,
  email text,
  audio_id uuid,
  transcript_id uuid,
  raw_transcript text,
  lock_token uuid,
  attempts int
)
language plpgsql
as $$
begin
  return query
  with due as (
    select sr.id
    from summary_requests sr
    where sr.status = 'pending'
      and sr.send_at <= now()
    order by sr.send_at asc
    for update skip locked
    limit greatest(batch_size, 1)
  ),
  updated as (
    update summary_requests sr
    set
      status = 'processing',
      locked_at = now(),
      lock_token = gen_random_uuid(),
      attempts = sr.attempts + 1,
      updated_at = now()
    from due
    where sr.id = due.id
    returning sr.id, sr.email, sr.audio_id, sr.transcript_id, sr.raw_transcript, sr.lock_token, sr.attempts
  )
  select * from updated;
end;
$$;
