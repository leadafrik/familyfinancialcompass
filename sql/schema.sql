create extension if not exists "pgcrypto";

create table if not exists property_tax_rates (
    id uuid primary key default gen_random_uuid(),
    state_code text not null unique,
    effective_rate numeric(8,6) not null,
    source_name text not null,
    source_version text not null,
    sourced_at date not null,
    created_at timestamptz not null default now()
);

create table if not exists insurance_rates (
    id uuid primary key default gen_random_uuid(),
    state_code text not null unique,
    annual_premium_cents bigint not null,
    source_name text not null,
    source_version text not null,
    sourced_at date not null,
    created_at timestamptz not null default now()
);

create table if not exists mortgage_rates (
    id uuid primary key default gen_random_uuid(),
    rate_date date not null unique,
    thirty_year_fixed numeric(8,6) not null,
    fifteen_year_fixed numeric(8,6) not null,
    source_name text not null default 'Freddie Mac PMMS',
    created_at timestamptz not null default now()
);

create table if not exists inflation_data (
    id uuid primary key default gen_random_uuid(),
    month_date date not null unique,
    cpi_value numeric(12,4) not null,
    yoy_change numeric(8,6) not null,
    source_name text not null default 'BLS CPI',
    created_at timestamptz not null default now()
);

create table if not exists market_calibrations (
    id uuid primary key default gen_random_uuid(),
    market_region text not null,
    version text not null,
    home_appreciation_mean numeric(8,6) not null,
    home_appreciation_stddev numeric(8,6) not null,
    investment_return_mean numeric(8,6) not null,
    investment_return_sigma_conservative numeric(8,6) not null,
    investment_return_sigma_moderate numeric(8,6) not null,
    investment_return_sigma_aggressive numeric(8,6) not null,
    rent_growth_mean numeric(8,6) not null,
    rent_growth_stddev numeric(8,6) not null,
    mortgage_rate_stddev numeric(8,6) not null,
    correlation_matrix_json jsonb not null,
    sourced_at date not null,
    created_at timestamptz not null default now(),
    unique (market_region, version)
);

create table if not exists behavioral_adjustments (
    id uuid primary key default gen_random_uuid(),
    version text not null unique,
    loss_aversion_lambda numeric(8,4) not null,
    panic_sale_expected_return_penalty numeric(8,6) not null,
    stable_income_liquidity_premium numeric(8,6) not null,
    variable_income_liquidity_premium numeric(8,6) not null,
    notes text,
    created_at timestamptz not null default now()
);

create table if not exists assumption_sets (
    id uuid primary key default gen_random_uuid(),
    set_key text not null unique,
    model_version text not null,
    refresh_mode text not null default 'auto',
    source_label text not null,
    cache_date date not null,
    assumptions_json jsonb not null,
    audit_trail_json jsonb not null,
    dynamic_inputs_json jsonb not null default '{}'::jsonb,
    is_active boolean not null default false,
    created_at timestamptz not null default now(),
    activated_at timestamptz not null default now(),
    check (refresh_mode in ('auto', 'manual'))
);

create table if not exists scenarios (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    created_at timestamptz not null default now(),
    module text not null default 'rent_vs_buy',
    market_region text not null default 'national',
    idempotency_key text,
    inputs_snapshot jsonb not null,
    assumptions_snapshot jsonb not null,
    model_version text not null,
    check (module in ('rent_vs_buy'))
);

create table if not exists scenario_outputs (
    scenario_id uuid primary key references scenarios(id) on delete cascade,
    computed_at timestamptz not null default now(),
    output_blob jsonb not null,
    probability_buy_beats_rent double precision,
    median_terminal_advantage_cents bigint,
    median_break_even_month integer
);

create index if not exists idx_scenarios_user_id_created_at on scenarios (user_id, created_at desc);
create unique index if not exists idx_scenarios_user_id_idempotency_key
    on scenarios (user_id, idempotency_key)
    where idempotency_key is not null;
create unique index if not exists idx_assumption_sets_active
    on assumption_sets ((1))
    where is_active;
create index if not exists idx_scenarios_module_created_at on scenarios (module, created_at desc);
create index if not exists idx_scenarios_market_region_created_at on scenarios (market_region, created_at desc);
create index if not exists idx_scenario_outputs_probability on scenario_outputs (probability_buy_beats_rent);
