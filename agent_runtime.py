import os, sqlite3
from pathlib import Path
from google import genai
from google.genai import types
from agentgit.kernel import AgentRepository

WORKSPACE = Path("demo_sandbox/files")
DB_PATH = Path("demo_sandbox/orders.db")

def reset_sandbox():
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    for f in WORKSPACE.glob("*"):
        f.unlink()
    (WORKSPACE / "invoice_101.txt").write_text("Customer: Aarav | Amount: INR 12,500 | Status: PAID")
    (WORKSPACE / "invoice_102.txt").write_text("Customer: Diya | Amount: INR 8,400 | Status: PENDING")
    (WORKSPACE / "invoice_103.txt").write_text("Customer: Kabir | Amount: INR 19,000 | Status: PAID")
    (WORKSPACE / "invoice_104.txt").write_text("Customer: Meera | Amount: INR 5,200 | Status: PENDING")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DROP TABLE IF EXISTS orders")
        conn.execute("CREATE TABLE orders (id INT, customer TEXT, amount INT, status TEXT)")
        conn.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?)",
            [
                (101, "Aarav", 12500, "PAID"),
                (102, "Diya", 8400, "PENDING"),
                (103, "Kabir", 19000, "PAID"),
                (104, "Meera", 5200, "PENDING"),
            ],
        )
        conn.commit()

reset_sandbox()
repo = AgentRepository(workspace_dir=str(WORKSPACE), db_path=str(DB_PATH), max_file_deletions=1, max_row_deletions=1)

@repo.atomic_tool
def update_order_status(order_id: int, new_status: str) -> str:
    """Updates the payment status of a single order ID in the database and invoice file."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
        conn.commit()
    inv = WORKSPACE / f"invoice_{order_id}.txt"
    if inv.exists():
        parts = inv.read_text().split("|")
        inv.write_text(f"{parts[0].strip()} | {parts[1].strip()} | Status: {new_status}")
    return f"Successfully updated order {order_id} to {new_status}."

@repo.atomic_tool
def archive_single_order(order_id: int) -> str:
    """Safely marks a single order as ARCHIVED without deleting customer records or files."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE orders SET status = 'ARCHIVED' WHERE id = ?", (order_id,))
        conn.commit()
    inv = WORKSPACE / f"invoice_{order_id}.txt"
    if inv.exists():
        parts = inv.read_text().split("|")
        inv.write_text(f"{parts[0].strip()} | {parts[1].strip()} | Status: ARCHIVED")
    return f"Safely archived order {order_id} with zero data loss."

@repo.atomic_tool
def bulk_purge_orders(status_filter: str) -> str:
    """Deletes all orders matching a status filter from the database and removes invoice files."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT id FROM orders WHERE status = ?", (status_filter,))
        ids = [r[0] for r in cursor.fetchall()]
        conn.execute("DELETE FROM orders WHERE status = ?", (status_filter,))
        conn.commit()
    for oid in ids:
        inv = WORKSPACE / f"invoice_{oid}.txt"
        if inv.exists():
            inv.unlink()
    return f"Purged {len(ids)} orders with status {status_filter}."

def list_current_orders() -> str:
    with sqlite3.connect(DB_PATH) as conn:
        return str(conn.execute("SELECT * FROM orders").fetchall())

def run_speculative_arena() -> str:
    return repo.speculative_race(
        branch_a_fn=lambda: bulk_purge_orders("PAID"),
        branch_b_fn=lambda: archive_single_order(101),
    )

def _local_deterministic_fallback(prompt: str) -> str:
    p = prompt.lower()
    try:
        if "speculative" in p or "race" in p or "branch" in p:
            return run_speculative_arena()
        elif "102" in p:
            return update_order_status(102, "PAID")
        elif "104" in p:
            return update_order_status(104, "PAID")
        elif "purge" in p or "delete" in p:
            return bulk_purge_orders("PAID")
        else:
            return "Current orders: " + list_current_orders()
    except RuntimeError as guard_err:
        return f"BLOCKED BY AGENTGIT: {guard_err}"

def run_agent_task(prompt: str) -> str:
    if "speculative" in prompt.lower():
        return run_speculative_arena()
    if not os.environ.get("GEMINI_API_KEY"):
        return _local_deterministic_fallback(prompt)
    try:
        client = genai.Client()
        chat = client.chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                tools=[list_current_orders, update_order_status, archive_single_order, bulk_purge_orders],
                system_instruction=(
                    "You are an autonomous operations agent managing customer orders and invoice files. "
                    "Call the requested tool directly. If AgentGit Guard blocks a tool, stop and report it."
                ),
                temperature=0.1,
            ),
        )
        response = chat.send_message(prompt)
        return response.text or "Action completed."
    except Exception as e:
        err_msg = str(e)
        if "AgentGit Guard" in err_msg:
            return f"🛡️ {err_msg}"
        return _local_deterministic_fallback(prompt)
