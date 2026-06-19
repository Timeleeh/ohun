-- 오행운 Supabase(PostgreSQL) 스키마
-- 확정 반영: 그룹 최대 6명, 토스 연동 양력 생년월일만(calendar solar 고정),
--            그룹별 지정 시각 하루 1회 배치(gen_time), (group_id,date) 캐시 dedup.
-- 주의: 운세는 '그룹 컨텍스트'로 생성되므로 개인 운세도 group_id별로 저장한다
--       (02 문서의 user_id+date 단일 캐시 대신 group 단위로 설계).

create extension if not exists "pgcrypto";

-- 사용자 (토스 연동 양력 생년월일)
create table if not exists users (
  id          uuid primary key default gen_random_uuid(),
  toss_user_id text unique not null,
  name        text not null,
  birth_date  date not null,                 -- 양력
  birth_time  time,                          -- 선택(미입력 시 일주 기반만)
  created_at  timestamptz not null default now()
);

-- 그룹 (단톡방 단위)
create table if not exists groups (
  id           uuid primary key default gen_random_uuid(),
  name         text not null,
  owner_id     uuid not null references users(id) on delete cascade,
  invite_code  text unique not null,
  gen_time     time not null default '08:00', -- 매일 운세 생성 시각(사용자 지정)
  last_active  date,                          -- 비활성 그룹 배치 제외 판단
  created_at   timestamptz not null default now()
);

-- 그룹 멤버 (최대 6명: 애플리케이션/트리거에서 강제)
create table if not exists group_members (
  id         uuid primary key default gen_random_uuid(),
  group_id   uuid not null references groups(id) on delete cascade,
  user_id    uuid not null references users(id) on delete cascade,
  joined_at  timestamptz not null default now(),
  unique (group_id, user_id)
);

-- 그룹·날짜 단위 운세 헤더 (캐시 키)
create table if not exists daily_group_fortunes (
  group_id      uuid not null references groups(id) on delete cascade,
  date          date not null,
  day_element   text not null,               -- 그날 오행 한자 (예: 木)
  group_comment text not null,
  created_at    timestamptz not null default now(),
  primary key (group_id, date)
);

-- 멤버별 개인 운세 (그룹 컨텍스트)
create table if not exists daily_personal_fortunes (
  group_id      uuid not null references groups(id) on delete cascade,
  date          date not null,
  member_id     uuid not null references users(id) on delete cascade,
  line          text not null,
  score         int  not null check (score between 1 and 5),
  base_element  text not null,               -- 룰 기반 베이스 라벨
  primary key (group_id, date, member_id)
);

-- 멤버 간 케미 (good/caution)
create table if not exists daily_bonds (
  group_id   uuid not null references groups(id) on delete cascade,
  date       date not null,
  pair_id    text not null,                  -- "{a_id}__{b_id}"
  user_a_id  uuid not null references users(id) on delete cascade,
  user_b_id  uuid not null references users(id) on delete cascade,
  type       text not null check (type in ('good','caution')),
  line       text not null,
  primary key (group_id, date, pair_id)
);

-- 배치 조회 가속
create index if not exists idx_groups_gen_time on groups (gen_time);
create index if not exists idx_group_members_group on group_members (group_id);

-- 그룹 최대 6명 강제 트리거
create or replace function enforce_group_size() returns trigger as $$
begin
  if (select count(*) from group_members where group_id = new.group_id) >= 6 then
    raise exception '그룹 최대 인원(6명)을 초과할 수 없습니다';
  end if;
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_enforce_group_size on group_members;
create trigger trg_enforce_group_size
  before insert on group_members
  for each row execute function enforce_group_size();
