CREATE TABLE IF NOT EXISTS users (
    sid TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student',
    photo_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subjects (
    subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_name TEXT NOT NULL,
    class_name TEXT NOT NULL,
    added_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(added_by) REFERENCES users(sid)
);

CREATE TABLE IF NOT EXISTS attendance_sessions (
    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id TEXT,
    subject_id INTEGER,
    subject TEXT NOT NULL,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    active BOOLEAN DEFAULT 1,
    FOREIGN KEY(teacher_id) REFERENCES users(sid),
    FOREIGN KEY(subject_id) REFERENCES subjects(subject_id)
);

CREATE TABLE IF NOT EXISTS valid_tokens (
    token TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS attendance_records (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    sid TEXT NOT NULL,
    name TEXT NOT NULL,
    subject_id INTEGER,
    subject TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES attendance_sessions(session_id),
    FOREIGN KEY(sid) REFERENCES users(sid),
    FOREIGN KEY(subject_id) REFERENCES subjects(subject_id),
    UNIQUE(session_id, sid)
);
