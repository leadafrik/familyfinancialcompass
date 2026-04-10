-- Migration 001: Extend scenarios.module check constraint to all four calculators.
-- Safe to run on an existing database (drops and recreates the constraint only).

alter table scenarios
    drop constraint if exists scenarios_module_check;

alter table scenarios
    add constraint scenarios_module_check
    check (module in ('rent_vs_buy', 'retirement_survival', 'job_offer', 'college_vs_retirement'));
