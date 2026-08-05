create table public.recipe_reports (
  id uuid primary key default gen_random_uuid(),
  origin text not null,
  recipe_url text not null,
  categories text[] not null,
  note text,
  recipe_snapshot jsonb,
  client_version text,
  api_version text not null,
  user_agent text,
  created_at timestamptz not null default now(),

  constraint recipe_reports_origin_check
    check (origin in ('user', 'automatic')),

  constraint recipe_reports_recipe_url_present_check
    check (btrim(recipe_url) <> ''),

  constraint recipe_reports_recipe_url_size_check
    check (octet_length(recipe_url) <= 2048),

  constraint recipe_reports_categories_nonempty_check
    check (
      cardinality(categories) > 0
      and array_position(categories, null) is null
    ),

  constraint recipe_reports_categories_values_check
    check (
      categories <@ array[
        'ingredient_parsing',
        'directions',
        'media',
        'metadata',
        'rendering',
        'other',
        'unable_to_parse'
      ]::text[]
    ),

  constraint recipe_reports_note_size_check
    check (note is null or char_length(note) <= 4000),

  constraint recipe_reports_other_note_check
    check (
      not categories && array['other']::text[]
      or (note is not null and btrim(note) <> '')
    ),

  constraint recipe_reports_snapshot_object_check
    check (
      recipe_snapshot is null
      or jsonb_typeof(recipe_snapshot) = 'object'
    ),

  constraint recipe_reports_snapshot_size_check
    check (
      recipe_snapshot is null
      or octet_length(recipe_snapshot::text) <= 131072
    ),

  constraint recipe_reports_client_version_size_check
    check (
      client_version is null
      or char_length(client_version) <= 128
    ),

  constraint recipe_reports_api_version_present_check
    check (btrim(api_version) <> ''),

  constraint recipe_reports_api_version_size_check
    check (char_length(api_version) <= 128),

  constraint recipe_reports_user_agent_size_check
    check (
      user_agent is null
      or char_length(user_agent) <= 1024
    ),

  constraint recipe_reports_origin_payload_check
    check (
      (
        origin = 'user'
        and recipe_snapshot is not null
        and client_version is not null
        and btrim(client_version) <> ''
        and not categories && array['unable_to_parse']::text[]
      )
      or
      (
        origin = 'automatic'
        and recipe_snapshot is null
        and categories = array['unable_to_parse']::text[]
      )
    )
);

comment on table public.recipe_reports is
  'Append-only reports of malformed recipe results and automatic parsing failures.';

comment on column public.recipe_reports.recipe_snapshot is
  'Untrusted diagnostic snapshot of the recipe JSON shown to the client.';

comment on column public.recipe_reports.client_version is
  'Opaque client build identifier supplied with user reports.';

comment on column public.recipe_reports.api_version is
  'Opaque server deployment identifier';

create index recipe_reports_created_at_idx
  on public.recipe_reports (created_at desc);

create index recipe_reports_recipe_url_idx
  on public.recipe_reports (recipe_url);

create index recipe_reports_categories_idx
  on public.recipe_reports using gin (categories);

alter table public.recipe_reports enable row level security;

revoke all on table public.recipe_reports from anon;
revoke all on table public.recipe_reports from authenticated;
revoke all on table public.recipe_reports from service_role;

grant select, insert on table public.recipe_reports to service_role;
