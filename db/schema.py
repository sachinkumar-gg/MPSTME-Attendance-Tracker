from db.connection import get_connection

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS user_subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        subject_name TEXT NOT NULL,
        class_type TEXT CHECK(class_type IN ('theory','tutorial','lab')) NOT NULL,
        classes_per_week INTEGER NOT NULL,
        total_weeks INTEGER NOT NULL,
        total_classes INTEGER NOT NULL,
        required_classes INTEGER NOT NULL,
        attended INTEGER DEFAULT 0,
        conducted INTEGER DEFAULT 0,
        lab_hours INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS attendance_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        subject_name TEXT NOT NULL,
        status TEXT CHECK(status IN ('present','absent')),
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()