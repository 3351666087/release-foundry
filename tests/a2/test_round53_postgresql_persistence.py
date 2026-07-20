from __future__ import annotations

import os

import pytest


POSTGRES_DSN = os.environ.get("POSTGRES_DSN")


@pytest.fixture(scope="module", autouse=True)
def round53_postgresql_schema() -> None:
    if not POSTGRES_DSN:
        return
    import psycopg

    with psycopg.connect(POSTGRES_DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS a2_round53_proof")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS a2_round53_proof.candidate_records (
                    candidate_hash TEXT PRIMARY KEY,
                    collection_hash TEXT NOT NULL,
                    conservation_hash TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    CHECK (candidate_hash LIKE 'sha256:%'),
                    CHECK (collection_hash LIKE 'sha256:%'),
                    CHECK (conservation_hash LIKE 'sha256:%'),
                    CHECK (decision IN ('PASS', 'BLOCK', 'INCOMPLETE'))
                )
                """
            )


@pytest.mark.skipif(not POSTGRES_DSN, reason="same-round PostgreSQL DSN not provided")
def test_round53_hash_only_candidate_record_survives_reconnect() -> None:
    import psycopg

    candidate_hash = "sha256:" + "5" * 64
    collection_hash = "sha256:" + "6" * 64
    conservation_hash = "sha256:" + "7" * 64
    with psycopg.connect(POSTGRES_DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO a2_round53_proof.candidate_records (
                    candidate_hash,
                    collection_hash,
                    conservation_hash,
                    decision
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (candidate_hash) DO UPDATE SET
                    collection_hash = EXCLUDED.collection_hash,
                    conservation_hash = EXCLUDED.conservation_hash,
                    decision = EXCLUDED.decision
                """,
                (candidate_hash, collection_hash, conservation_hash, "BLOCK"),
            )

    with psycopg.connect(POSTGRES_DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT collection_hash, conservation_hash, decision
                FROM a2_round53_proof.candidate_records
                WHERE candidate_hash = %s
                """,
                (candidate_hash,),
            )
            assert cursor.fetchone() == (
                collection_hash,
                conservation_hash,
                "BLOCK",
            )


@pytest.mark.skipif(not POSTGRES_DSN, reason="same-round PostgreSQL DSN not provided")
def test_round53_failed_transaction_does_not_persist_partial_decision() -> None:
    import psycopg

    candidate_hash = "sha256:" + "8" * 64
    with pytest.raises(psycopg.errors.CheckViolation):
        with psycopg.connect(POSTGRES_DSN) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO a2_round53_proof.candidate_records (
                        candidate_hash,
                        collection_hash,
                        conservation_hash,
                        decision
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        candidate_hash,
                        "sha256:" + "9" * 64,
                        "sha256:" + "a" * 64,
                        "PASS_WITHOUT_POLICY",
                    ),
                )

    with psycopg.connect(POSTGRES_DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM a2_round53_proof.candidate_records
                WHERE candidate_hash = %s
                """,
                (candidate_hash,),
            )
            assert cursor.fetchone() == (0,)
