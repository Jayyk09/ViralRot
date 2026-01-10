-- Users table
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    password    TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Collections table (groups of related videos)
CREATE TABLE IF NOT EXISTS collections (
    id                SERIAL PRIMARY KEY,
    user_id           INT NOT NULL REFERENCES users(id),
    collection_title  TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Videos table
CREATE TABLE IF NOT EXISTS videos (
    id                SERIAL PRIMARY KEY,
    user_id           INT NOT NULL REFERENCES users(id),
    s3_key            TEXT NOT NULL,
    video_title       TEXT,
    video_description TEXT,
    collection_id     INT REFERENCES collections(id),
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_videos_user_id ON videos(user_id);
CREATE INDEX IF NOT EXISTS idx_videos_collection_id ON videos(collection_id);
CREATE INDEX IF NOT EXISTS idx_collections_user_id ON collections(user_id);

-- Seed test users
INSERT INTO users (email, password)
VALUES
    ('alice@example.com', 'password1'),
    ('bob@example.com',   'password2')
ON CONFLICT (email) DO NOTHING;
