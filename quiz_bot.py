import os
import sqlite3
import json
import random
import logging
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, ConversationHandler
)

# Enable Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID")) if os.getenv("OWNER_ID") else None

DB_FILE = "quiz_bot.db"

def init_db():
    """Database tables initialization"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            score INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            quiz_id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER,
            title TEXT,
            description TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id INTEGER,
            question_text TEXT,
            options TEXT,
            correct_answer TEXT,
            explanation TEXT,
            FOREIGN KEY(quiz_id) REFERENCES quizzes(quiz_id)
        )
    """)
    conn.commit()
    conn.close()

# Initialize DB on Startup
init_db()

# States for Creation & Playing Flow
(
    CREATE_TITLE, CREATE_DESC, ADD_QUESTION, 
    ADD_OPTIONS, ADD_CORRECT, ADD_EXPLANATION
) = range(6)
PLAYING_QUIZ = range(6, 7)

# --- USER QUIZ CREATION ENGINE ---
async def create_quiz_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📝 **Naya Quiz Banayein!**\n\nSabse pehle Quiz ka ek badhiya sa **Title** (Naam) likhkar bhejein:",
        parse_mode="Markdown"
    )
    context.user_data["new_quiz"] = {"questions": []}
    return CREATE_TITLE

async def create_quiz_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_quiz"]["title"] = update.message.text
    await update.message.reply_text("👍 Title save ho gaya.\n\nAb is quiz ka ek chhota sa **Description** likhkar bhejein:")
    return CREATE_DESC

async def create_quiz_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_quiz"]["description"] = update.message.text
    await update.message.reply_text("✅ Description save ho gaya!\n\nChaliye ab **Saval (Question 1)** likhkar bhejein:")
    return ADD_QUESTION

async def create_add_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["current_working_q"] = {"text": update.message.text}
    await update.message.reply_text(
        "Ab is saval ke **Options** bhejein.\nFormat: Har option ko ek nayi line me likhein (Kam se kam 2, max 4).\n\n"
        "Example:\nMumbai\nDelhi\nKolkata\nChennai"
    )
    return ADD_OPTIONS

async def create_add_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    options = [opt.strip() for opt in update.message.text.split("\n") if opt.strip()]
    if len(options) < 2:
        await update.message.reply_text("❌ Kam se kam 2 options dena zaroori hai. Dubara bhejein:")
        return ADD_OPTIONS
        
    context.user_data["current_working_q"]["options"] = options
    keyboard = [[opt] for opt in options]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text("Buttons me se **Sahi Javab (Correct Answer)** par click karein:", reply_markup=reply_markup)
    return ADD_CORRECT

async def create_add_correct(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    selected = update.message.text
    q_data = context.user_data["current_working_q"]
    
    if selected not in q_data["options"]:
        await update.message.reply_text("❌ Diye gaye options me se hi chunyein. Dubara koshish karein:")
        return ADD_CORRECT
        
    q_data["correct"] = selected
    await update.message.reply_text(
        "💡 Is saval ke liye koi **Explanation** likhein.\nAgar nahi likhna chahte toh `/skip` type karein:",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADD_EXPLANATION

async def create_add_explanation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    q_data = context.user_data["current_working_q"]
    q_data["explanation"] = "" if text.lower() == "/skip" else text
    
    context.user_data["new_quiz"]["questions"].append(q_data)
    keyboard = [["➕ Naya Saval Jodein", "💾 Quiz Save Karein"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        f"✅ Saval jud gaya! Ab tak total {len(context.user_data['new_quiz']['questions'])} saval hain.\n\nAap kya karna chahte hain?",
        reply_markup=reply_markup
    )
    return ADD_QUESTION

async def handle_creation_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    choice = update.message.text
    if choice == "➕ Naya Saval Jodein":
        await update.message.reply_text("Agla **Saval (Question)** likhkar bhejein:", reply_markup=ReplyKeyboardRemove())
        return ADD_QUESTION
    elif choice == "💾 Quiz Save Karein":
        quiz = context.user_data["new_quiz"]
        if not quiz["questions"]:
            await update.message.reply_text("❌ Khali quiz save nahi ki ja sakti.")
            return ADD_QUESTION
            
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO quizzes (creator_id, title, description) VALUES (?, ?, ?)", (update.message.from_user.id, quiz["title"], quiz["description"]))
        quiz_id = cursor.lastrowid
        
        for q in quiz["questions"]:
            cursor.execute("INSERT INTO questions (quiz_id, question_text, options, correct_answer, explanation) VALUES (?, ?, ?, ?, ?)", (quiz_id, q["text"], json.dumps(q["options"]), q["correct"], q["explanation"]))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"🎉 **Quiz Save Ho Gaya!**\n\n🆔 **Quiz ID:** `{quiz_id}`\n📚 **Title:** {quiz['title']}\n\nKhelne ke liye `/play_id {quiz_id}` use karein.", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    return await create_add_question(update, context)
# --- DATABASE QUIZ PLAYING ENGINE ---
async def play_quiz_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Khelne ke liye Quiz ID chahiye. Example: `/play_id 1`")
        return
    quiz_id = context.args[0]
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT title, description FROM quizzes WHERE quiz_id = ?", (quiz_id,))
    quiz_data = cursor.fetchone()
    
    if not quiz_data:
        await update.message.reply_text("❌ Is ID ka koi quiz database me nahi mila.")
        conn.close()
        return
        
    title, desc = quiz_data
    cursor.execute("SELECT question_text, options, correct_answer, explanation FROM questions WHERE quiz_id = ?", (quiz_id,))
    questions_rows = cursor.fetchall()
    conn.close()
    
    if not questions_rows:
        await update.message.reply_text("❌ Is quiz me koi saval nahi hain.")
        return

    context.user_data["active_quiz"] = {
        "title": title,
        "questions": [{"text": r[0], "options": json.loads(r[1]), "correct": r[2], "explanation": r[3]} for r in questions_rows],
        "current_index": 0, "score": 0
    }
    random.shuffle(context.user_data["active_quiz"]["questions"])
    
    await update.message.reply_text(f"🏁 **Quiz Shuru Ho Rahi Hai!**\n\n📝 **Title:** {title}\n💡 **Description:** {desc}", parse_mode="Markdown")
    return await send_next_db_question(update, context)

async def send_next_db_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quiz = context.user_data["active_quiz"]
    idx = quiz["current_index"]
    if idx >= len(quiz["questions"]):
        await (update.message or update.callback_query.message).reply_text(
            f"🎉 **Quiz Complete!**\n\nAapka score: *{quiz['score']}/{len(quiz['questions'])}*", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    q = quiz["questions"][idx]
    opts = list(q["options"])
    random.shuffle(opts)
    keyboard = [[opt] for opt in opts]
    
    msg_text = f"❓ **Question {idx + 1}:**\n{q['text']}"
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    if update.message:
        await update.message.reply_text(msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.callback_query.message.reply_text(msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    return PLAYING_QUIZ

async def handle_db_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_ans = update.message.text
    quiz = context.user_data["active_quiz"]
    q = quiz["questions"][quiz["current_index"]]
    
    if user_ans == q["correct"]:
        quiz["score"] += 1
        await update.message.reply_text("✅ **Sahi Javab!**", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ **Galat Javab!**\n\nSahi tha: *{q['correct']}*\n💡 _Explanation:_ {q['explanation']}", parse_mode="Markdown")
        
    quiz["current_index"] += 1
    return await send_next_db_question(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Action cancel kar diya gaya hai.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- OWNER CONTROL COMMANDS ---
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_ID:
        return
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    total_quizzes = cursor.execute("SELECT COUNT(*) FROM quizzes").fetchone()[0]
    total_questions = cursor.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    conn.close()
    await update.message.reply_text(f"📊 **Bot Status Panel**\n\nTotal Created Quizzes: {total_quizzes}\nTotal Questions Stored: {total_questions}", parse_mode="Markdown")

# --- MAIN APP START ENGINE ---
def main():
    if not BOT_TOKEN:
        print("Error: Set BOT_TOKEN inside .env file")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    create_handler = ConversationHandler(
        entry_points=[CommandHandler("create", create_quiz_start)],
        states={
            CREATE_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_quiz_title)],
            CREATE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_quiz_desc)],
            ADD_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_creation_choice)],
            ADD_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_add_options)],
            ADD_CORRECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_add_correct)],
            ADD_EXPLANATION: [MessageHandler(filters.TEXT, create_add_explanation)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    play_handler = ConversationHandler(
        entry_points=[CommandHandler("play_id", play_quiz_by_id)],
        states={PLAYING_QUIZ: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_db_quiz_answer)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    application.add_handler(create_handler)
    application.add_handler(play_handler)
    application.add_handler(CommandHandler("stats", stats))

    print("🚀 Advanced SQLite Quiz Bot is active...")
    application.run_polling()

if __name__ == "__main__":
    main()
  
