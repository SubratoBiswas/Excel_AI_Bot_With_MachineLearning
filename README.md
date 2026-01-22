# 📊 Excel Analysis Bot (with Learning)

An AI-powered Excel analysis assistant that:
- Accepts **multiple Excel files**
- Analyzes data across **files and sheets**
- Answers questions using **real SQL execution (DuckDB)**
- **Learns from user feedback** (👍 / 👎 + corrected SQL)

This bot does **not guess answers** — every result is computed from your Excel data.

---

## 🚀 Features

### Core
- Upload multiple `.xlsx` / `.xls` files
- Automatic table & schema detection
- Natural language → SQL generation
- Fast, local execution using DuckDB
- Streamlit-based chat UI

### Learning & Training
- User feedback (correct / incorrect)
- Optional corrected SQL input
- Bot reuses **successful patterns** for similar questions
- Learning scoped per dataset schema (safe & accurate)

### Safety
- Read-only SQL (SELECT / WITH only)
- No destructive queries
- Automatic result limits
- SQL validation & sanitization

---

## 🧠 How Learning Works

1. User asks a question
2. Bot generates SQL and executes it
3. User provides feedback:
   - 👍 Correct → pattern is saved
   - 👎 Incorrect → corrected SQL can be provided
4. Future similar questions reuse the best past examples

All learning is stored locally in:
