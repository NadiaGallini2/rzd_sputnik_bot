# Импортируйте необходимые модули
import logging
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ParseMode, ChatAction
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    MessageHandler,
    Filters,
    JobQueue,
)
import fitz  # PyMuPDF
from transformers import pipeline
from dotenv import load_dotenv


# Загрузка переменных окружения из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получение API токена из переменных окружения
API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')

if not API_TOKEN:
    logger.error("Не найден API токен. Пожалуйста, установите TELEGRAM_API_TOKEN в переменные окружения.")
    exit(1)

# Функция для извлечения текста из PDF
def extract_text_from_pdf(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text += page.get_text("text")
        logger.info("Текст успешно извлечен из PDF.")
        return text
    except Exception as e:
        logger.error(f"Ошибка при извлечении текста из PDF: {e}")
        return ""

# Загрузка текста из PDF при запуске
PDF_PATH = r'Documents/Коллективный договор.pdf'  # Используйте сырую строку или прямые слэши
if not os.path.exists(PDF_PATH):
    logger.error(f"Файл PDF не найден по пути: {PDF_PATH}")
    pdf_text = ""
else:
    pdf_text = extract_text_from_pdf(PDF_PATH)

# Инициализация модели QnA
try:
    question_answerer = pipeline("question-answering", model="distilbert-base-uncased-distilled-squad")
    logger.info("Модель QnA успешно загружена.")
except Exception as e:
    logger.error(f"Ошибка при загрузке модели QnA: {e}")
    question_answerer = None

# Обработчик команды /start
def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Функции", callback_data='functions')],
        [InlineKeyboardButton("Контакты", callback_data='contacts')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_message = (
        "**Добро пожаловать!** 👋\n\n"
        "Я ваш чат-бот соцподдержки сотрудников РЖД. Выберите одну из опций ниже:\n\n"
        "Нажмите на кнопку 'Функции', чтобы узнать, как я могу помочь вам."
    )
    try:
        with open('static/logo.png', 'rb') as photo:
            context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo,
                caption=welcome_message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
    except FileNotFoundError:
        logger.error("Файл logo.png не найден в папке static.")
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=welcome_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

# Обработчик команды /help
def help_command(update: Update, context: CallbackContext):
    help_text = (
        "Доступные команды:\n"
        "/start - Начать общение с ботом\n"
        "/help - Показать этот список команд\n"
        "Отправьте любое сообщение, чтобы задать вопрос по содержимому PDF."
    )
    context.bot.send_message(chat_id=update.effective_chat.id, text=help_text, parse_mode=ParseMode.MARKDOWN)

# Обработчик нажатий на кнопки
def button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    logger.info(f"Нажата кнопка: {query.data}")

    if query.data == 'functions':
        functions_text = (
            "**Функции бота:**\n"
            "1. Информация о льготах\n"
            "2. Помощь в трудных ситуациях\n"
            "3. Связь с HR\n\n"
            "Выберите опцию, чтобы получить подробную информацию."
        )
        context.bot.send_message(chat_id=query.message.chat_id, text=functions_text, parse_mode=ParseMode.MARKDOWN)

    elif query.data == 'contacts':
        contacts_text = (
            "**Контакты для связи:**\n"
            "📧 Email: support@rzd.ru\n"
            "📞 Телефон: +7 (495) 123-45-67\n"
            "🕒 Время работы: Пн-Пт, 9:00-18:00"
        )
        context.bot.send_message(chat_id=query.message.chat_id, text=contacts_text, parse_mode=ParseMode.MARKDOWN)

# Функция для отправки ответа пользователю после задержки
def send_answer(context: CallbackContext):
    user_question, chat_id = context.job.context
    try:
        result = question_answerer(question=user_question, context=pdf_text)
        answer = result.get('answer', 'Извините, я не смог найти ответ на ваш вопрос.')
        score = result.get('score', 0)
        logger.info(f"Ответ: {answer} (score: {score})")
        context.bot.send_message(chat_id=chat_id, text=f"**Ответ:** {answer}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Ошибка при обработке вопроса: {e}")
        context.bot.send_message(chat_id=chat_id, text="Извините, произошла ошибка при обработке вашего вопроса.")

# Обработчик вопросов пользователей
def handle_question(update: Update, context: CallbackContext):
    user_question = update.message.text.strip()
    logger.info(f"Получен вопрос: {user_question}")
    
    if not user_question.startswith('/'):
        chat_id = update.effective_chat.id

        # Отправляем действие "typing"
        context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        
        # Добавляем задачу для отправки ответа через 1 секунду
        context.job_queue.run_once(send_answer, 1, context=(user_question, chat_id))

# Основная функция для запуска бота
def main():
    logger.info("Запуск бота...")
    updater = Updater(API_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Обработчики команд
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))

    # Обработчик нажатий на кнопки
    dp.add_handler(CallbackQueryHandler(button))

    # Обработчик текстовых сообщений для вопросов
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_question))

    # Запуск бота
    updater.start_polling()
    logger.info("Бот запущен и готов к работе!")
    updater.idle()

if __name__ == '__main__':
    main()
