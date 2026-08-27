{#
    dbt's default behavior concatenates the profile's target schema with a
    model's +schema config — a model configured for "cdm_dbt" would actually
    land in "dbt_staging_cdm_dbt" on the dev target. That defeats the whole
    point of giving marts their own clearly-named schema (see the comment in
    dbt_project.yml on why marts targets cdm_dbt specifically, not cdm). This
    is dbt Labs' own documented override for custom schema names: use the
    schema exactly as configured, falling back to the target's default
    schema only when a model doesn't set one.
#}

{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
