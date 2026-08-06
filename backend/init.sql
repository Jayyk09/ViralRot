-- Users table
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    password    TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Videos table
CREATE TABLE IF NOT EXISTS videos (
    id                SERIAL PRIMARY KEY,
    s3_key            TEXT NOT NULL,
    video_title       TEXT,
    video_description TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Seed test users
INSERT INTO users (email, password)
VALUES
    ('alice@example.com', 'password1'),
    ('bob@example.com',   'password2')
ON CONFLICT (email) DO NOTHING;
