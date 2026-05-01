-- Realistic pre-tenant audit-pass fixture for UPD-046 migration tests.
--
-- The fixture is intentionally schema-introspective: it runs after migration
-- 095 and inserts data into every public base table using type-aware values.
-- Foreign-key triggers are disabled for the fixture transaction so every
-- bounded context can be represented without hand-maintaining a fragile global
-- dependency order. Check constraints still run, so generated values honor
-- common status/type/period constraints.

BEGIN;
SET LOCAL session_replication_role = replica;

CREATE OR REPLACE FUNCTION pg_temp.audit_pass_checked_text_value(
    p_table text,
    p_column text
) RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    match text[];
    constraint_def text;
BEGIN
    FOR constraint_def IN
        SELECT pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        WHERE c.conrelid = format('public.%I', p_table)::regclass
          AND c.contype = 'c'
          AND pg_get_constraintdef(c.oid) ILIKE '%' || p_column || '%'
    LOOP
        match := regexp_match(constraint_def, '''([^'']+)''');
        IF match IS NOT NULL THEN
            RETURN match[1];
        END IF;
    END LOOP;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION pg_temp.audit_pass_fixture_expr(
    p_table text,
    p_column text,
    p_data_type text,
    p_udt_name text,
    p_formatted_type text,
    p_max_length integer
) RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    enum_value text;
    raw_expr text;
    checked_text text;
BEGIN
    IF p_data_type = 'USER-DEFINED' THEN
        SELECT e.enumlabel
          INTO enum_value
        FROM pg_type t
        JOIN pg_enum e ON e.enumtypid = t.oid
        WHERE t.typname = p_udt_name
        ORDER BY e.enumsortorder
        LIMIT 1;

        IF enum_value IS NOT NULL THEN
            RETURN format('%L::%s', enum_value, p_formatted_type);
        END IF;
    END IF;

    IF p_data_type = 'ARRAY' THEN
        RETURN format('ARRAY[]::%s', p_formatted_type);
    END IF;

    IF p_data_type = 'uuid' THEN
        RETURN 'gen_random_uuid()';
    END IF;

    IF p_data_type IN ('smallint', 'integer', 'bigint') THEN
        IF p_column ILIKE '%score%'
            OR p_column ILIKE '%percentage%'
            OR p_column ILIKE '%threshold%'
            OR p_column ILIKE '%priority%'
            OR p_column ILIKE '%rank%' THEN
            RETURN format('50::%s', p_formatted_type);
        END IF;
        IF p_column ILIKE '%count%' OR p_column ILIKE '%version%' THEN
            RETURN format('1::%s', p_formatted_type);
        END IF;
        RETURN format('(1000000 + n)::%s', p_formatted_type);
    END IF;

    IF p_data_type IN ('numeric', 'real', 'double precision') THEN
        IF p_column ILIKE '%band%'
            OR p_column ILIKE '%ratio%'
            OR p_column ILIKE '%alpha%'
            OR p_column ILIKE '%score%'
            OR p_column ILIKE '%confidence%'
            OR p_column ILIKE '%probability%' THEN
            RETURN format('0.5::%s', p_formatted_type);
        END IF;
        IF p_column ILIKE '%threshold%' OR p_column ILIKE '%percentage%' THEN
            RETURN format('50::%s', p_formatted_type);
        END IF;
        RETURN format('(1000000 + n)::%s', p_formatted_type);
    END IF;

    IF p_data_type = 'boolean' THEN
        RETURN '(n % 2 = 0)';
    END IF;

    IF p_data_type = 'jsonb' THEN
        RETURN 'jsonb_build_object(''fixture'', n)';
    END IF;

    IF p_data_type = 'json' THEN
        RETURN 'json_build_object(''fixture'', n)::json';
    END IF;

    IF p_data_type LIKE 'timestamp%' THEN
        IF p_column ILIKE '%end%' OR p_column ILIKE '%expires%' THEN
            RETURN format('(now() + interval ''1 day'' + make_interval(secs => n))::%s', p_formatted_type);
        END IF;
        RETURN format('(now() + make_interval(secs => n))::%s', p_formatted_type);
    END IF;

    IF p_data_type = 'date' THEN
        RETURN format('(current_date + n)::%s', p_formatted_type);
    END IF;

    IF p_data_type = 'interval' THEN
        RETURN format('(''1 hour''::interval)::%s', p_formatted_type);
    END IF;

    IF p_data_type = 'bytea' THEN
        RETURN 'decode(md5(n::text), ''hex'')';
    END IF;

    IF p_data_type = 'inet' THEN
        RETURN '''127.0.0.1''::inet';
    END IF;

    IF p_data_type = 'tsvector' THEN
        RETURN 'to_tsvector(''simple'', ''fixture'')';
    END IF;

    checked_text := pg_temp.audit_pass_checked_text_value(p_table, p_column);
    IF checked_text IS NOT NULL THEN
        raw_expr := quote_literal(checked_text);
    ELSIF p_column ILIKE '%email%' THEN
        raw_expr := quote_literal('fixture-') || ' || n || ' || quote_literal('@example.com');
    ELSIF p_column ILIKE '%url%' OR p_column ILIKE '%uri%' THEN
        raw_expr := quote_literal('https://example.com/fixture/') || ' || n';
    ELSIF p_column ILIKE '%hash%' OR p_column ILIKE '%sha%' THEN
        raw_expr := 'repeat(''a'', 64)';
    ELSIF p_column ILIKE '%slug%' THEN
        raw_expr := quote_literal('fixture-') || ' || n';
    ELSIF p_column ILIKE '%fqn%' THEN
        raw_expr := quote_literal('fixture.agent.') || ' || n';
    ELSIF p_column = 'region_role' THEN
        raw_expr := quote_literal('primary');
    ELSIF p_column = 'component' THEN
        raw_expr := quote_literal('postgres');
    ELSIF p_column = 'health' THEN
        raw_expr := quote_literal('healthy');
    ELSIF p_column = 'run_kind' THEN
        raw_expr := quote_literal('rehearsal');
    ELSIF p_column = 'outcome' THEN
        raw_expr := quote_literal('succeeded');
    ELSIF p_column = 'period_type' THEN
        raw_expr := quote_literal('daily');
    ELSIF p_column = 'anomaly_type' THEN
        raw_expr := quote_literal('sudden_spike');
    ELSIF p_column = 'severity' THEN
        raw_expr := quote_literal('low');
    ELSIF p_column = 'state' THEN
        raw_expr := quote_literal('open');
    ELSIF p_column = 'metric_name' THEN
        raw_expr := quote_literal('demographic_parity');
    ELSIF p_column ILIKE '%role%' THEN
        raw_expr := quote_literal('member');
    ELSIF p_column ILIKE '%provider%' THEN
        raw_expr := quote_literal('google');
    ELSIF p_column ILIKE '%locale%' OR p_column ILIKE '%language%' THEN
        raw_expr := quote_literal('en');
    ELSIF p_column ILIKE '%theme%' THEN
        raw_expr := quote_literal('light');
    ELSIF p_column ILIKE '%format%' THEN
        raw_expr := quote_literal('json');
    ELSIF p_column ILIKE '%currency%' THEN
        raw_expr := quote_literal('USD');
    ELSIF p_column ILIKE '%country%' THEN
        raw_expr := quote_literal('DE');
    ELSIF p_column ILIKE '%region%' THEN
        raw_expr := quote_literal('eu-central');
    ELSIF p_column = 'status' THEN
        raw_expr := CASE WHEN p_table = 'maintenance_windows' THEN quote_literal('scheduled') ELSE quote_literal('active') END;
    ELSE
        raw_expr := quote_literal('fixture-' || p_table || '-' || p_column || '-') || ' || n';
    END IF;

    IF p_max_length IS NOT NULL THEN
        RETURN format('left((%s), %s)::%s', raw_expr, p_max_length, p_formatted_type);
    END IF;
    RETURN format('(%s)::%s', raw_expr, p_formatted_type);
END;
$$;

CREATE OR REPLACE PROCEDURE pg_temp.audit_pass_seed_table(
    p_table text,
    p_rows integer DEFAULT 1
)
LANGUAGE plpgsql
AS $$
DECLARE
    column_list text;
    value_list text;
BEGIN
    SELECT
        string_agg(format('%I', c.column_name), ', ' ORDER BY c.ordinal_position),
        string_agg(
            pg_temp.audit_pass_fixture_expr(
                p_table,
                c.column_name,
                c.data_type,
                c.udt_name,
                format_type(a.atttypid, a.atttypmod),
                c.character_maximum_length
            ),
            ', ' ORDER BY c.ordinal_position
        )
    INTO column_list, value_list
    FROM information_schema.columns c
    JOIN pg_class cls ON cls.relname = c.table_name
    JOIN pg_namespace ns ON ns.oid = cls.relnamespace AND ns.nspname = c.table_schema
    JOIN pg_attribute a ON a.attrelid = cls.oid AND a.attname = c.column_name
    WHERE c.table_schema = 'public'
      AND c.table_name = p_table
      AND c.is_generated = 'NEVER'
      AND c.is_identity = 'NO'
      AND c.column_name <> 'tenant_id'
      AND a.attisdropped IS FALSE;

    IF column_list IS NULL THEN
        FOR n IN 1..p_rows LOOP
            EXECUTE format('INSERT INTO %I DEFAULT VALUES', p_table);
        END LOOP;
        RETURN;
    END IF;

    EXECUTE format(
        'INSERT INTO %I (%s) SELECT %s FROM generate_series(1, %s) AS fixture(n)',
        p_table,
        column_list,
        value_list,
        p_rows
    );
END;
$$;

DO $$
DECLARE
    table_record record;
    row_target integer;
BEGIN
    FOR table_record IN
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND table_name <> 'alembic_version'
        ORDER BY table_name
    LOOP
        row_target := CASE
            WHEN table_record.table_name IN ('executions', 'audit_chain_entries', 'cost_attributions') THEN 100000
            ELSE 1
        END;
        CALL pg_temp.audit_pass_seed_table(table_record.table_name, row_target);
    END LOOP;
END;
$$;

COMMIT;
