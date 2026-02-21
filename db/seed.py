from db.connection import get_connection

def seed_branches():
    conn = get_connection()
    cursor = conn.cursor()

    branches = [
        "BTech Cybersecurity",
        "BTech CSE",
        "BTech AI",
        "BTech IT"
    ]

    for branch in branches:
        cursor.execute(
            "INSERT OR IGNORE INTO branches (branch_name) VALUES (?)",
            (branch,)
        )

    conn.commit()
    conn.close()