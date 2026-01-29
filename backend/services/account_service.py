"""Simple account service using psycopg2 for CRUD operations."""

from typing import Optional, Dict, List

import psycopg2
from db import get_db_conn  # <-- use shared DB helper


def create_user(email: str, password: str) -> Optional[Dict]:
    """
    Create a new user account.

    Returns:
        User dict with id, email if successful, None if email exists
    """
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (email, password)
                VALUES (%s, %s)
                RETURNING id, email, created_at
                """,
                (email, password),
            )
            row = cur.fetchone()
            conn.commit()
            return {"id": row[0], "email": row[1], "created_at": row[2]}
    except psycopg2.IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Get user by ID."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, created_at FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if row:
                return {"id": row[0], "email": row[1], "created_at": row[2]}
            return None
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[Dict]:
    """Get user by email."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, created_at FROM users WHERE email = %s",
                (email,),
            )
            row = cur.fetchone()
            if row:
                return {"id": row[0], "email": row[1], "created_at": row[2]}
            return None
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> Optional[Dict]:
    """
    Authenticate user by email and password.

    Returns:
        User dict if credentials valid, None otherwise
    """
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, created_at
                FROM users
                WHERE email = %s AND password = %s
                """,
                (email, password),
            )
            row = cur.fetchone()
            if row:
                return {"id": row[0], "email": row[1], "created_at": row[2]}
            return None
    finally:
        conn.close()


def update_password(user_id: int, new_password: str) -> bool:
    """
    Update user password.

    Returns:
        True if successful, False if user not found
    """
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password = %s WHERE id = %s",
                (new_password, user_id),
            )
            conn.commit()
            return cur.rowcount > 0
    finally:
        conn.close()


def delete_user(user_id: int) -> bool:
    """
    Delete user account.

    Returns:
        True if successful, False if user not found
    """
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
            return cur.rowcount > 0
    finally:
        conn.close()


def list_all_users() -> List[Dict]:
    """Get all users."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, created_at FROM users ORDER BY id"
            )
            rows = cur.fetchall()
            return [
                {"id": row[0], "email": row[1], "created_at": row[2]}
                for row in rows
            ]
    finally:
        conn.close()
