#!/usr/bin/env python3
"""
HPE Morpheus POC Bible — Air-gapped POC Seeder
================================================
Creates a POC record directly in the database so the SE can hand the customer
a working /poc/<token> URL without needing the admin dashboard.

Run inside the app container:
  docker compose -f docker-compose.airgapped.yml run --rm app python scripts/seed_poc.py
"""

import os
import sys
import secrets
from datetime import date, timedelta

# ── Dependencies (all available in the app container) ────────────────────────
import bcrypt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:airgapped_local@db:5432/pocbible",
)

# ─────────────────────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"  {label}{suffix}: ").strip()
    return value if value else default


def main() -> None:
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║  HPE Morpheus POC Bible — Air-gapped POC Seeder      ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    # ── Collect POC details ──────────────────────────────────────────────────
    today = date.today()
    customer_name = prompt("Customer name", "Acme Corp")
    poc_id = prompt("POC ID", f"POC-{today.strftime('%Y%m')}-001")
    start_str = prompt("Start date (YYYY-MM-DD)", today.isoformat())
    try:
        start_date = date.fromisoformat(start_str)
    except ValueError:
        print(f"\n  ✗ Invalid date: {start_str!r}. Use YYYY-MM-DD format.")
        sys.exit(1)

    duration_str = prompt("Duration (days)", "45")
    duration = int(duration_str) if duration_str.isdigit() else 45
    end_date = start_date + timedelta(days=duration)

    watermark = prompt("Watermark text (printed on checklist)", customer_name)
    license_type = prompt("License type", "Standard License")

    print()

    # ── Connect to DB ────────────────────────────────────────────────────────
    try:
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        db = Session()
        # Quick connectivity check
        db.execute(text("SELECT 1"))
    except Exception as exc:
        print(f"  ✗ Cannot connect to database: {exc}")
        print()
        print("  Make sure the app container is running:")
        print("    docker compose -f docker-compose.airgapped.yml up -d")
        print("  Then retry this script.")
        sys.exit(1)

    try:
        # ── Ensure SE user exists ────────────────────────────────────────────
        SE_EMAIL = os.getenv("ADMIN_EMAIL", "se@local.airgapped")
        SE_PASSWORD = os.getenv("ADMIN_PASSWORD", "localadmin123")

        row = db.execute(
            text("SELECT id FROM users WHERE email = :e"), {"e": SE_EMAIL}
        ).fetchone()

        if row:
            se_id = row[0]
            print(f"  ✓ SE user already exists  ({SE_EMAIL})")
        else:
            db.execute(
                text(
                    """
                    INSERT INTO users (email, name, password_hash, role, is_active, is_master)
                    VALUES (:email, :name, :pw, 'se', true, false)
                    """
                ),
                {
                    "email": SE_EMAIL,
                    "name": os.getenv("ADMIN_NAME", "Local SE"),
                    "pw": hash_password(SE_PASSWORD),
                },
            )
            db.commit()
            se_id = db.execute(
                text("SELECT id FROM users WHERE email = :e"), {"e": SE_EMAIL}
            ).fetchone()[0]
            print(f"  ✓ Created SE user         ({SE_EMAIL})")

        # ── Check if POC already exists ──────────────────────────────────────
        existing = db.execute(
            text("SELECT access_token FROM pocs WHERE poc_id = :pid"),
            {"pid": poc_id},
        ).fetchone()

        if existing:
            token = existing[0]
            print(f"  ⚠  POC {poc_id!r} already in database — reusing existing token.")
        else:
            token = secrets.token_hex(8)  # 16-char hex, same as the app generates
            db.execute(
                text(
                    """
                    INSERT INTO pocs (
                        poc_id, access_token, customer_name, se_id,
                        start_date, end_date,
                        modules, license_type, watermark_text,
                        status, force_blocked, admin_override
                    ) VALUES (
                        :poc_id, :token, :customer_name, :se_id,
                        :start_date, :end_date,
                        '{}', :license_type, :watermark,
                        'active', false, false
                    )
                    """
                ),
                {
                    "poc_id": poc_id,
                    "token": token,
                    "customer_name": customer_name,
                    "se_id": se_id,
                    "start_date": start_date,
                    "end_date": end_date,
                    "license_type": license_type,
                    "watermark": watermark,
                },
            )
            db.commit()
            print(f"  ✓ POC record created      ({poc_id})")

        # ── Print result ─────────────────────────────────────────────────────
        print()
        print("  ┌─────────────────────────────────────────────────────┐")
        print(f"  │  Customer URL  →  http://localhost:8000/poc/{token}  │")
        print("  └─────────────────────────────────────────────────────┘")
        print()
        print(f"  Customer:   {customer_name}")
        print(f"  POC ID:     {poc_id}")
        print(f"  Period:     {start_date} → {end_date}  ({duration} days)")
        print(f"  License:    {license_type}")
        print()
        print("  Share the URL above with the customer.")
        print("  They only need a browser — no login, no dashboard.")
        print()

        # ── If on a LAN, suggest the machine IP as well ──────────────────────
        try:
            import socket
            ip = socket.gethostbyname(socket.gethostname())
            if not ip.startswith("127."):
                print(f"  LAN access (same network):  http://{ip}:8000/poc/{token}")
                print()
        except Exception:
            pass

    except Exception as exc:
        db.rollback()
        print(f"  ✗ Error: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
