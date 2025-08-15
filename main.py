from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import subprocess
import os
import yt_dlp
from pathlib import Path
import tempfile
import logging
import time
import asyncio
from datetime import datetime
from flask import Flask
 

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de Flask para mantener activo el bot
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot activo!"

TOKEN = os.environ.get('TOKEN')
DOWNLOAD_DIR = "descargas"

class ProgressTracker:
    def __init__(self, message):
        self.message = message
        self.start_time = time.time()
        self.last_update = 0
        self.current_task = ""
        self.task_times = {}
        self.task_start = None

    async def start_task(self, task_name):
        if self.task_start and self.current_task:
            elapsed = time.time() - self.task_start
            self.task_times[self.current_task] = elapsed

        self.current_task = task_name
        self.task_start = time.time()
        await self.update_message(f"🔄 {task_name}...\n⏱️ Iniciando tarea...")

    async def update_progress(self, progress_info):
        current_time = time.time()
        if current_time - self.last_update < 2:
            return

        self.last_update = current_time
        task_elapsed = current_time - self.task_start if self.task_start else 0

        mensaje = f"🔄 {self.current_task}\n"
        mensaje += f"⏱️ Tiempo tarea: {task_elapsed:.1f}s\n"
        mensaje += f"📊 {progress_info}\n"

        if self.task_times:
            mensaje += "\n✅ Tareas completadas:\n"
            for task, duration in self.task_times.items():
                mensaje += f"• {task}: {duration:.1f}s\n"

        await self.update_message(mensaje)

    async def finish_task(self, success=True):
        if self.task_start and self.current_task:
            elapsed = time.time() - self.task_start
            self.task_times[self.current_task] = elapsed

        total_time = time.time() - self.start_time

        status = "✅ PROCESO COMPLETADO" if success else "❌ PROCESO FALLIDO"

        mensaje = f"{status}\n"
        mensaje += f"🕐 Tiempo total: {total_time:.1f}s\n\n"

        if self.task_times:
            mensaje += "📋 Resumen de tiempos:\n"
            for task, duration in self.task_times.items():
                mensaje += f"• {task}: {duration:.1f}s\n"

        await self.update_message(mensaje)

    async def update_message(self, text):
        try:
            await self.message.edit_text(text)
        except Exception as e:
            logger.error(f"Error editando mensaje: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎶 Bienvenido a MusicDownloader Bot Avanzado\n\n"
        "📺 YouTube: Videos, audio, playlists\n"
        "🎵 Spotify: Música y playlists\n" 
        "🎧 SoundCloud: Tracks y sets\n"
        "💽 Bandcamp: Álbumes y tracks\n\n"
        "Envía cualquier enlace compatible y elige tu formato preferido.\n"
        "✅ Solo para fines educativos.\n\n"
        "Comandos:\n"
        "• /info - Ver información de video/audio\n"
        "• /ayuda - Guía de uso completa\n"
        "• /config - Verificar configuración del sistema"
    )

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 Guía de uso completa:\n\n"
        "🔗 Plataformas soportadas:\n"
        "• YouTube (videos/audio/playlists)\n"
        "• Spotify (tracks/álbumes/playlists)\n"
        "• SoundCloud (tracks/sets)\n"
        "• Bandcamp (música)\n\n"
        "📋 Proceso de descarga:\n"
        "1️⃣ Envía un enlace válido\n"
        "2️⃣ Selecciona el formato deseado\n"
        "3️⃣ Observa el progreso en tiempo real\n"
        "4️⃣ Recibe tu archivo con resumen de tiempos\n\n"
        "ℹ️ Usa /info [URL] para ver detalles sin descargar\n"
        "🔧 Usa /config para verificar configuración del sistema\n"
        "❗Uso educativo únicamente"
    )

async def info_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("📋 Uso: /info [URL]")
        return

    url = context.args[0]

    if not any(x in url for x in ["youtu.be", "youtube.com"]):
        await update.message.reply_text("❌ Solo enlaces de YouTube")
        return

    mensaje_inicial = await update.message.reply_text("🔍 Analizando video...")

    try:
        info = obtener_info_youtube(url)

        if info:
            duracion_texto = f"{info['duracion']//60}:{info['duracion']%60:02d}" if info['duracion'] > 0 else "N/A"

            mensaje_info = f"""
✅ INFORMACIÓN DEL VIDEO

🎬 Título: {info['titulo']}
👤 Canal: {info['canal']}
⏱️ Duración: {duracion_texto}
📅 Fecha: {info['fecha']}
            """
            await mensaje_inicial.edit_text(mensaje_info)
        else:
            await mensaje_inicial.edit_text("❌ Error al obtener información")

    except Exception as e:
        await mensaje_inicial.edit_text(f"❌ Error: {str(e)}")

async def comando_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = "🔧 DIAGNÓSTICO DEL SISTEMA\n\n"

    # Verificaciones básicas
    try:
        import yt_dlp
        mensaje += "✅ yt-dlp instalado\n"
    except ImportError:
        mensaje += "❌ yt-dlp NO instalado\n"

    await update.message.reply_text(mensaje)

def obtener_info_youtube(url):
    ydl_opts = {'quiet': True, 'no_warnings': True}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'titulo': info.get('title', 'N/A'),
                'canal': info.get('uploader', 'N/A'),
                'duracion': info.get('duration', 0),
                'fecha': info.get('upload_date', 'N/A'),
            }
    except Exception as e:
        logger.error(f"Error obteniendo info: {e}")
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Aquí iría tu lógica para manejar los mensajes de descarga
    await update.message.reply_text("🔍 Procesando tu enlace...")

def run_flask():
    app.run(host='0.0.0.0', port=8080)
     

def main():
    application = Application.builder().token(TOKEN).build()

    # Manejadores
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ayuda", ayuda))
    application.add_handler(CommandHandler("info", info_comando))
    application.add_handler(CommandHandler("config", comando_config))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Iniciar Flask en segundo plano
    import threading
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Iniciar bot
    application.run_polling()

if __name__ == "__main__":
    main()