"""Collection service for grouping related videos."""

import os
from typing import Optional, Dict, List
from db import get_db_conn
import google.genai as genai
from dotenv import load_dotenv


def create_collection(
    user_id: int,
    collection_title: str,
) -> int:
    """
    Create a new collection.

    Args:
        user_id: The user who owns this collection
        collection_title: Title for the collection

    Returns:
        The new collection id
    """
    conn = get_db_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO collections (user_id, collection_title)
                VALUES (%s, %s)
                RETURNING id;
                """,
                (user_id, collection_title),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("INSERT INTO collections RETURNING id returned no row")
            collection_id = row[0]
            return int(collection_id)
    finally:
        conn.close()


def get_collection(collection_id: int) -> Optional[Dict]:
    """
    Get collection by ID.

    Returns:
        Collection dict with id, user_id, collection_title, created_at
    """
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, collection_title, created_at
                FROM collections
                WHERE id = %s
                """,
                (collection_id,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0],
                    "user_id": row[1],
                    "collection_title": row[2],
                    "created_at": row[3],
                }
            return None
    finally:
        conn.close()


def get_user_collections(
    user_id: int,
    offset: int = 0,
    limit: int = 10,
) -> List[Dict]:
    """
    Get all collections for a user.

    Returns:
        List of collection dicts, ordered by newest first
    """
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, collection_title, created_at
                FROM collections
                WHERE user_id = %s
                ORDER BY created_at DESC, id DESC
                OFFSET %s
                LIMIT %s
                """,
                (user_id, offset, limit),
            )
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "user_id": row[1],
                    "collection_title": row[2],
                    "created_at": row[3],
                }
                for row in rows
            ]
    finally:
        conn.close()


def generate_collection_title(subtopic_titles: List[str]) -> str:
    """
    Generate a collection title from subtopic titles using Gemini AI.

    Args:
        subtopic_titles: List of subtopic titles

    Returns:
        A generated collection title
    """
    if not subtopic_titles:
        return "Untitled Collection"
    
    # If there's only one subtopic, use it directly
    if len(subtopic_titles) == 1:
        return subtopic_titles[0]
    
    try:
        # Load API key
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        
        # Initialize Gemini client
        client = genai.Client(api_key=api_key)
        
        # Create prompt for title generation
        subtopic_list = "\n".join([f"- {title}" for title in subtopic_titles])
        prompt = f"""Generate a concise, engaging title (max 60 characters) for a video collection based on these subtopics:

{subtopic_list}

Requirements:
- Must be 60 characters or less
- Should capture the main theme or topic
- Should be engaging and clear
- Do not use quotes or special formatting
- Return ONLY the title, nothing else

Title:"""
        
        # Call Gemini API
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        
        # Extract the generated title
        if response and response.text:
            title = response.text.strip()
            # Remove quotes if present
            title = title.strip('"').strip("'")
            # Truncate if too long
            if len(title) > 60:
                title = title[:57] + "..."
            return title
        
    except Exception as e:
        print(f"⚠️  Warning: Failed to generate title with Gemini: {e}")
    
    # Fallback to simple concatenation if Gemini fails
    if len(subtopic_titles) <= 3:
        return " & ".join(subtopic_titles)
    return f"{subtopic_titles[0]} & {subtopic_titles[1]} & More"

def find_last_collection(user_id: int) -> Optional[Dict]:
    """
    Find the most recent collection for a user.

    Args:
        user_id: The user ID

    Returns:
        The most recent collection dict or None
    """
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM collections
                WHERE user_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0]
                }
            return None
    finally:
        conn.close()