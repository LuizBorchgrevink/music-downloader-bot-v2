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
from threading import Thread

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TOKEN')
DOWNLOAD_DIR = "descargas"

# ==================== CLASE PARA TRACKING DE PROGRESO ====================

class ProgressTracker:
    def __init__(self, message):
        self.message = message
        self.start_time = time.time()
        self.last_update = 0
        self.current_task = ""
        self.task_times = {}
        self.task_start = None

    async def start_task(self, task_name):
        """Inicia una nueva tarea y registra el tiempo"""
        if self.task_start and self.current_task:
            # Finalizar tarea anterior
            elapsed = time.time() - self.task_start
            self.task_times[self.current_task] = elapsed

        self.current_task = task_name
        self.task_start = time.time()

        await self.update_message(f"🔄 {task_name}...\n⏱️ Iniciando tarea...")

    async def update_progress(self, progress_info):
        """Actualiza el progreso de la tarea actual"""
        current_time = time.time()

        # Limitar actualizaciones cada 2 segundos para evitar spam
        if current_time - self.last_update < 2:
            return

        self.last_update = current_time
        task_elapsed = current_time - self.task_start if self.task_start else 0

        mensaje = f"🔄 {self.current_task}\n"
        mensaje += f"⏱️ Tiempo tarea: {task_elapsed:.1f}s\n"
        mensaje += f"📊 {progress_info}\n"

        # Mostrar tiempos de tareas completadas
        if self.task_times:
            mensaje += "\n✅ Tareas completadas:\n"
            for task, duration in self.task_times.items():
                mensaje += f"• {task}: {duration:.1f}s\n"

        await self.update_message(mensaje)

    async def finish_task(self, success=True):
        """Finaliza la tarea actual"""
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
        """Actualiza el mensaje de Telegram"""
        try:
            await self.message.edit_text(text)
        except Exception as e:
            # Si falla la edición, enviar nuevo mensaje
            logger.error(f"Error editando mensaje: {e}")

# ==================== FUNCIONES ORIGINALES ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎶 Bienvenido a MusicDownloader Bot Avanzado\n\n"
        "📺 YouTube: Videos, audio, playlists\n"
        "🎵 Spotify: Música y playlists\n" 
        "🎧 SoundCloud: Tracks y sets\n"
        "💽 Bandcamp: Álbumes y tracks\n\n"
        "🔄 Nuevo: Seguimiento de progreso en tiempo real\n"
        "⏱️ Nuevo: Tiempos detallados de cada tarea\n\n"
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
        "🎥 Formatos disponibles:\n"
        "• MP4: Video completo (YouTube)\n"
        "• MP3: Audio comprimido\n"
        "• FLAC: Audio sin pérdida\n"
        "• WAV: Audio sin comprimir\n\n"
        "📊 Información de progreso:\n"
        "• Tiempo por tarea individual\n"
        "• Progreso de descarga en %\n"
        "• Velocidad de descarga\n"
        "• Tiempo total del proceso\n\n"
        "ℹ️ Usa /info [URL] para ver detalles sin descargar\n"
        "🔧 Usa /config para verificar configuración del sistema\n"
        "❗Uso educativo únicamente"
    )

# ==================== FUNCIONES YOUTUBE CON PROGRESO ====================

def obtener_info_youtube(url):
    """Obtiene información de un video de YouTube usando yt-dlp"""
    ydl_opts = {'quiet': True, 'no_warnings': True}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'titulo': info.get('title', 'N/A'),
                'canal': info.get('uploader', 'N/A'),
                'duracion': info.get('duration', 0),
                'fecha': info.get('upload_date', 'N/A'),
                'vistas': info.get('view_count', 0),
                'descripcion': info.get('description', 'N/A')[:200] + '...' if info.get('description') else 'N/A',
                'es_playlist': info.get('_type') == 'playlist',
                'cantidad_videos': len(info.get('entries', [])) if info.get('_type') == 'playlist' else 1,
                'tamaño_aprox': info.get('filesize') or info.get('filesize_approx', 0)
            }
    except Exception as e:
        logger.error(f"Error obteniendo info: {e}")
        return None

class ProgressHook:
    """Clase helper para manejar el progreso de manera sincronizada"""
    def __init__(self, tracker):
        self.tracker = tracker
        self.loop = asyncio.get_event_loop()

    def __call__(self, d):
        if d['status'] == 'downloading':
            # Programar actualización de progreso
            self.loop.call_soon_threadsafe(
                asyncio.create_task,
                self.actualizar_progreso_descarga(d)
            )
        elif d['status'] == 'finished':
            self.loop.call_soon_threadsafe(
                asyncio.create_task,
                self.tracker.start_task("Procesando archivo final")
            )

    async def actualizar_progreso_descarga(self, d):
        """Actualiza el progreso durante la descarga"""
        try:
            if '_percent_str' in d:
                porcentaje = d['_percent_str'].strip()
            else:
                porcentaje = "N/A"

            velocidad = d.get('_speed_str', 'N/A')
            eta = d.get('_eta_str', 'N/A')
            descargado = d.get('_downloaded_bytes_str', 'N/A')
            total = d.get('_total_bytes_str', 'N/A')

            progreso = f"📈 Progreso: {porcentaje}\n"
            progreso += f"🚀 Velocidad: {velocidad}\n"
            progreso += f"⏳ ETA: {eta}\n"
            progreso += f"📦 Descargado: {descargado}/{total}"

            await self.tracker.update_progress(progreso)

        except Exception as e:
            logger.error(f"Error actualizando progreso: {e}")

async def descargar_youtube_con_progreso(url, formato, directorio_temp, tracker):
    """Descarga video/audio de YouTube con seguimiento de progreso"""

    try:
        await tracker.start_task("Analizando video")

        # Crear hook de progreso
        progress_hook = ProgressHook(tracker)

        # Configurar opciones según formato
        if formato == "mp4":
            await tracker.update_progress("Configurando descarga de video...")
            ydl_opts = {
                'format': 'best[height<=720]/best',
                'outtmpl': f'{directorio_temp}/%(title)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [progress_hook],
            }
        else:  # MP3, FLAC, WAV
            await tracker.update_progress("Configurando extracción de audio...")
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{directorio_temp}/%(title)s.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': formato,
                    'preferredquality': '192' if formato == 'mp3' else '0',
                }],
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [progress_hook],
            }

        await tracker.start_task("Iniciando descarga")

        # Ejecutar descarga en un executor para evitar bloqueo
        loop = asyncio.get_event_loop()

        def download_sync():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        await loop.run_in_executor(None, download_sync)

        if formato != "mp4":
            await tracker.start_task("Convirtiendo audio")
            await asyncio.sleep(1)  # Simular tiempo de conversión

        return True

    except Exception as e:
        logger.error(f"Error descargando YouTube: {e}")
        return False

async def verificar_spotdl():
    """Verifica si spotdl está instalado y configurado"""
    try:
        proceso = await asyncio.create_subprocess_exec(
            "spotdl", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proceso.communicate()
        return proceso.returncode == 0
    except FileNotFoundError:
        return False

async def descargar_spotify_con_progreso(url, directorio_temp, tracker):
    """Descarga de Spotify con seguimiento de progreso"""
    try:
        await tracker.start_task("Verificando Spotify")

        # Verificar si spotdl está disponible
        if not await verificar_spotdl():
            logger.error("spotdl no está instalado o configurado")
            await tracker.update_progress("❌ spotdl no disponible")
            return False

        await tracker.start_task("Descargando desde Spotify")
        await tracker.update_progress("Conectando a Spotify...")

        # Configurar comando con opciones mejoradas
        comando = [
            "spotdl",
            url,
            "--output", directorio_temp,
            "--format", "mp3",
            "--bitrate", "192k",
            "--threads", "1"  # Reducir threads para evitar errores
        ]

        logger.info(f"Comando Spotify: {' '.join(comando)}")

        # Ejecutar comando con timeout
        proceso = await asyncio.create_subprocess_exec(
            *comando,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        await tracker.update_progress("Descargando metadatos...")
        await asyncio.sleep(2)

        await tracker.update_progress("Descargando audio...")

        try:
            # Timeout de 5 minutos para Spotify
            stdout, stderr = await asyncio.wait_for(
                proceso.communicate(), 
                timeout=300
            )
        except asyncio.TimeoutError:
            proceso.kill()
            logger.error("Timeout en descarga de Spotify")
            await tracker.update_progress("❌ Timeout en descarga")
            return False

        stdout_text = stdout.decode('utf-8', errors='ignore')
        stderr_text = stderr.decode('utf-8', errors='ignore')

        logger.info(f"Spotify stdout: {stdout_text}")
        if stderr_text:
            logger.warning(f"Spotify stderr: {stderr_text}")

        if proceso.returncode == 0:
            await tracker.update_progress("✅ Descarga completada")
            # Verificar si realmente se descargó algo
            archivos = [f for f in os.listdir(directorio_temp) if f.endswith(('.mp3', '.m4a', '.flac'))]
            if archivos:
                return True
            else:
                logger.error("No se encontraron archivos descargados de Spotify")
                return False
        else:
            logger.error(f"Error Spotify (código {proceso.returncode}): {stderr_text}")
            await tracker.update_progress(f"❌ Error: {stderr_text[:100]}")
            return False

    except Exception as e:
        logger.error(f"Error descargando Spotify: {e}")
        await tracker.update_progress(f"❌ Error: {str(e)[:100]}")
        return False

async def descargar_otros_con_progreso(url, formato, directorio_temp, tracker):
    """Descarga de SoundCloud/Bandcamp con seguimiento de progreso"""
    try:
        await tracker.start_task("Descargando desde plataforma musical")

        if formato == "mp4":
            comando = [
                "yt-dlp", "-f", "bestvideo+bestaudio/best",
                "-o", f"{directorio_temp}/%(title)s.%(ext)s", url
            ]
        else:
            comando = [
                "yt-dlp", "-o", f"{directorio_temp}/%(title)s.%(ext)s",
                "--extract-audio", "--audio-format", formato, url
            ]

        await tracker.update_progress("Iniciando descarga...")

        proceso = await asyncio.create_subprocess_exec(
            *comando,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proceso.communicate()

        if proceso.returncode == 0:
            await tracker.update_progress("Descarga completada")
            return True
        else:
            logger.error(f"Error otros: {stderr.decode()}")
            return False

    except Exception as e:
        logger.error(f"Error descargando otros: {e}")
        return False

# ==================== COMANDO INFO CON TIEMPOS ====================

async def info_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para obtener información de un video con medición de tiempo"""
    if len(context.args) == 0:
        await update.message.reply_text(
            "📋 Uso del comando info:\n\n"
            "/info [URL]\n\n"
            "Ejemplos:\n"
            "• /info https://youtube.com/watch?v=ejemplo\n"
            "• /info https://youtu.be/ejemplo\n\n"
            "⏱️ Incluye tiempos de análisis"
        )
        return

    url = context.args[0]

    if not any(x in url for x in ["spotify.com", "youtu.be", "m.youtube.com", "youtube.com", 
        "bandcamp.com", "soundcloud.com", "vt.tiktok.com", "vm.tiktok.com", "tiktok.com", "instagram.com", "facebook.com", "twitter.com", "reddit.com", "twitch.tv", "vimeo.com", "dailymotion.com", "vk.com", "ok.ru", "coub.com", "mixcloud.com", "deezer.com", "apple.com/music", "tidal.com", "qobuz.com", "amazon.com/music", "pandora.com", "pinterest.com", "pin.it", "co.pinterest.com"]):
        await update.message.reply_text("❌ El comando /info solo funciona con enlaces de YouTube.")
        return

    # Mensaje inicial con timestamp
    inicio = time.time()
    mensaje_inicial = await update.message.reply_text("🔍 Analizando video...\n⏱️ Iniciando análisis...")

    try:
        # Obtener información
        info = obtener_info_youtube(url)
        tiempo_analisis = time.time() - inicio

        if info:
            duracion_texto = f"{info['duracion']//60}:{info['duracion']%60:02d}" if info['duracion'] > 0 else "N/A"
            vistas_texto = f"{info['vistas']:,}" if info['vistas'] > 0 else "N/A"
            tamaño_mb = info['tamaño_aprox'] / (1024 * 1024) if info['tamaño_aprox'] else 0

            mensaje_info = f"""
✅ ANÁLISIS COMPLETADO
⏱️ Tiempo de análisis: {tiempo_analisis:.2f}s

📺 INFORMACIÓN DEL VIDEO

🎬 Título: {info['titulo']}
👤 Canal: {info['canal']}
⏱️ Duración: {duracion_texto} min
📅 Fecha: {info['fecha']}
👀 Vistas: {vistas_texto}
📏 Tamaño aprox: {tamaño_mb:.1f} MB

📝 Descripción:
{info['descripcion']}

{'🎵 Tipo: Playlist (' + str(info['cantidad_videos']) + ' videos)' if info['es_playlist'] else '🎥 Tipo: Video individual'}

💡 Tip: Envía este enlace al bot para descargarlo
            """

            await mensaje_inicial.edit_text(mensaje_info)
        else:
            await mensaje_inicial.edit_text(
                f"❌ Error en el análisis\n"
                f"⏱️ Tiempo transcurrido: {tiempo_analisis:.2f}s\n"
                f"No se pudo obtener la información del video."
            )

    except Exception as e:
        tiempo_error = time.time() - inicio
        await mensaje_inicial.edit_text(
            f"❌ Error durante el análisis\n"
            f"⏱️ Tiempo antes del error: {tiempo_error:.2f}s\n"
            f"🔍 Error: {str(e)}"
        )

async def comando_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para verificar configuración y diagnosticar problemas"""
    mensaje_inicial = await update.message.reply_text("🔧 Verificando configuración del sistema...")

    diagnostico = "🔧 DIAGNÓSTICO DEL SISTEMA\n\n"

    # Verificar yt-dlp
    try:
        import yt_dlp
        diagnostico += "✅ yt-dlp: Instalado correctamente\n"
    except ImportError:
        diagnostico += "❌ yt-dlp: NO instalado\n"

    # Verificar spotdl
    try:
        proceso = await asyncio.create_subprocess_exec(
            "spotdl", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proceso.communicate()
        if proceso.returncode == 0:
            version = stdout.decode().strip()
            diagnostico += f"✅ spotdl: {version}\n"
        else:
            diagnostico += f"⚠️ spotdl: Instalado pero con errores\n"
    except FileNotFoundError:
        diagnostico += "❌ spotdl: NO instalado\n"

    # Verificar FFmpeg
    try:
        proceso = await asyncio.create_subprocess_exec(
            "ffmpeg", "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proceso.communicate()
        if proceso.returncode == 0:
            # Extraer versión de FFmpeg
            lineas = stdout.decode().split('\n')
            version_linea = [l for l in lineas if l.startswith('ffmpeg version')]
            if version_linea:
                version = version_linea[0].split()[2]
                diagnostico += f"✅ FFmpeg: {version}\n"
            else:
                diagnostico += "✅ FFmpeg: Instalado\n"
        else:
            diagnostico += "⚠️ FFmpeg: Instalado pero con errores\n"
    except FileNotFoundError:
        diagnostico += "❌ FFmpeg: NO instalado\n"

    # Verificar conectividad
    diagnostico += "\n🌐 CONECTIVIDAD:\n"
    try:
        import urllib.request
        urllib.request.urlopen('https://www.youtube.com', timeout=5)
        diagnostico += "✅ YouTube: Accesible\n"
    except:
        diagnostico += "❌ YouTube: No accesible\n"

    try:
        import urllib.request
        urllib.request.urlopen('https://open.spotify.com', timeout=5)
        diagnostico += "✅ Spotify: Accesible\n"
    except:
        diagnostico += "❌ Spotify: No accesible\n"

    # Instrucciones de solución
    diagnostico += "\n🔧 SOLUCIONES:\n\n"
    diagnostico += "📦 Para instalar dependencias:\n"
    diagnostico += "• pip install yt-dlp spotdl\n\n"

    diagnostico += "🎵 Para configurar Spotify:\n"
    diagnostico += "• spotdl --generate-config\n"
    diagnostico += "• Opcionalmente configura Client ID/Secret\n\n"

    diagnostico += "🎬 Para instalar FFmpeg:\n"
    diagnostico += "• Windows: Descargar de ffmpeg.org\n"
    diagnostico += "• macOS: brew install ffmpeg\n"
    diagnostico += "• Linux: apt install ffmpeg\n\n"

    diagnostico += "💡 ALTERNATIVAS PARA SPOTIFY:\n"
    diagnostico += "• Busca la canción en YouTube\n"
    diagnostico += "• Usa SoundCloud si está disponible\n"
    diagnostico += "• Prueba con enlaces de álbum completo"

    await mensaje_inicial.edit_text(diagnostico)

# ==================== FUNCIONES ACTUALIZADAS CON PROGRESO ====================

async def recibir_enlace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    # Verificar plataformas soportadas
    plataformas_soportadas = [
        "spotify.com", "youtu.be", "m.youtube.com", "youtube.com", 
        "bandcamp.com", "soundcloud.com", "vt.tiktok.com", "vm.tiktok.com", "tiktok.com", "instagram.com", "facebook.com", "twitter.com", "reddit.com", "twitch.tv", "vimeo.com", "dailymotion.com", "vk.com", "ok.ru", "coub.com", "mixcloud.com", "deezer.com", "apple.com/music", "tidal.com", "qobuz.com", "amazon.com/music", "pandora.com", 
    ]

    if not any(x in url for x in plataformas_soportadas):
        await update.message.reply_text(
            "❌ Enlace no soportado\n\n"
            "✅ Plataformas compatibles:\n"
            "• YouTube (videos/playlists)\n"
            "• Spotify (música)\n"
            "• SoundCloud (tracks)\n"
            "• Bandcamp (música)\n\n"
            "📝 Envía un enlace válido de estas plataformas."
        )
        return

    context.user_data["url"] = url

    # Análisis previo para YouTube con tiempo
    if any(x in url for x in ["youtu.be", "youtube.com", "m.youtube.com"]):
        inicio_analisis = time.time()
        mensaje_analisis = await update.message.reply_text("🔍 Pre-analizando video...")

        info = obtener_info_youtube(url)
        tiempo_analisis = time.time() - inicio_analisis

        if info:
            duracion = f"{info['duracion']//60}:{info['duracion']%60:02d}" if info['duracion'] > 0 else "N/A"

            await mensaje_analisis.edit_text(
                f"✅ Análisis completado ({tiempo_analisis:.1f}s)\n\n"
                f"📺 Video detectado:\n"
                f"🎬 {info['titulo']}\n"
                f"👤 {info['canal']}\n"
                f"⏱️ {duracion} min\n"
                f"{'🎵 Playlist (' + str(info['cantidad_videos']) + ' videos)' if info['es_playlist'] else '🎥 Video individual'}\n\n"
                f"⬇️ Selecciona el formato:"
            )

    # Crear teclado de opciones
    keyboard = [
        [
            InlineKeyboardButton("🎵 MP3", callback_data="format:mp3"),
            InlineKeyboardButton("🎶 FLAC", callback_data="format:flac"),
            InlineKeyboardButton("💽 WAV", callback_data="format:wav"),
            InlineKeyboardButton("📱 MP4", callback_data="format:mp4")
        ]
    ]

    if not any(x in url for x in ["youtu.be", "youtube.com", "m.youtube.com"]):
        await update.message.reply_text(
            "🎯 Selecciona el formato de descarga:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        # Para YouTube, enviar teclado en mensaje separado
        await update.message.reply_text(
            "⚡ ¡Listo para descargar!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def descargar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    formato = query.data.split(":")[1]
    url = context.user_data.get("url")

    if not url:
        await query.edit_message_text("⚠️ Error: No se encontró enlace válido.")
        return

    # Crear tracker de progreso
    mensaje_inicial = await query.message.reply_text(
        f"🚀 INICIANDO DESCARGA\n"
        f"🎯 Formato: {formato.upper()}\n"
        f"🔗 Preparando proceso..."
    )

    tracker = ProgressTracker(mensaje_inicial)

    # Crear directorio temporal
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            exito = False
            es_youtube = any(x in url for x in ["youtu.be", "youtube.com", "m.youtube.com"])
            es_spotify = "spotify.com" in url

            # Determinar método de descarga
            if es_spotify:
                # Verificar spotdl antes de intentar
                if not await verificar_spotdl():
                    await tracker.start_task("Spotify no disponible, intentando con yt-dlp")
                    await tracker.update_progress("Buscando alternativa en YouTube...")

                    # Intentar con yt-dlp como respaldo
                    exito = await descargar_youtube_con_progreso(url, formato, temp_dir, tracker)

                    if not exito:
                        await tracker.finish_task(success=False)
                        await query.message.reply_text(
                            "❌ Spotify no disponible\n\n"
                            "🔧 Soluciones:\n"
                            "1. Instala spotdl: pip install spotdl\n"
                            "2. Verifica que FFmpeg esté instalado\n"
                            "3. Configura spotdl: spotdl --generate-config\n"
                            "4. Usa /config para diagnóstico completo\n\n"
                            "💡 Alternativas:\n"
                            "• Busca la canción en YouTube\n"
                            "• Copia el nombre y búscalo manualmente"
                        )
                        return
                else:
                    exito = await descargar_spotify_con_progreso(url, temp_dir, tracker)

                    # Si falla Spotify, intentar con YouTube
                    if not exito:
                        await tracker.start_task("Spotify falló, intentando alternativa")
                        await tracker.update_progress("Probando método alternativo...")

                        # Extraer nombre de la canción para buscar en YouTube
                        try:
                            import re
                            # Extraer información básica del enlace de Spotify
                            if "/track/" in url:
                                track_id = url.split("/track/")[1].split("?")[0]
                                search_query = f"ytsearch1:{track_id}"  # Búsqueda básica
                                exito = await descargar_youtube_con_progreso(search_query, formato, temp_dir, tracker)
                        except:
                            pass
            elif es_youtube:
                exito = await descargar_youtube_con_progreso(url, formato, temp_dir, tracker)
            else:  # SoundCloud, Bandcamp
                exito = await descargar_otros_con_progreso(url, formato, temp_dir, tracker)

            if exito:
                await tracker.start_task("Enviando archivos")

                archivos = [f for f in os.listdir(temp_dir) if os.path.isfile(os.path.join(temp_dir, f))]
                archivos_enviados = 0
                archivos_info = []

                if not archivos:
                    await tracker.finish_task(success=False)
                    await query.message.reply_text("❌ No se encontraron archivos descargados.")
                    return

                for archivo in archivos:
                    ruta = os.path.join(temp_dir, archivo)
                    tamaño_mb = os.path.getsize(ruta) / (1024 * 1024)

                    if tamaño_mb > 50:
                        archivos_info.append(f"⚠️ {archivo}: {tamaño_mb:.1f}MB (muy grande)")
                        continue

                    try:
                        inicio_envio = time.time()

                        if formato == "mp4" and archivo.endswith(('.mp4', '.mkv', '.webm')):
                            with open(ruta, "rb") as video_file:
                                await query.message.reply_video(
                                    video=video_file,
                                    caption=f"📱 {archivo}\n🎯 {formato.upper()} • {tamaño_mb:.1f}MB"
                                )
                        else:
                            with open(ruta, "rb") as audio_file:
                                await query.message.reply_audio(
                                    audio=audio_file,
                                    title=archivo.rsplit('.', 1)[0],
                                    caption=f"🎵 {archivo}\n🎯 {archivo.split('.')[-1].upper()} • {tamaño_mb:.1f}MB"
                                )

                        tiempo_envio = time.time() - inicio_envio
                        archivos_enviados += 1
                        archivos_info.append(f"✅ {archivo}: {tamaño_mb:.1f}MB ({tiempo_envio:.1f}s)")

                    except Exception as e:
                        logger.error(f"Error enviando {archivo}: {e}")
                        archivos_info.append(f"❌ {archivo}: Error - {str(e)[:50]}")

                # Finalizar con resumen completo
                await tracker.finish_task(success=True)

                # Enviar resumen detallado
                resumen = f"📊 RESUMEN DETALLADO\n\n"
                resumen += f"📁 Archivos procesados: {len(archivos)}\n"
                resumen += f"✅ Enviados exitosamente: {archivos_enviados}\n"
                resumen += f"🎯 Formato: {formato.upper()}\n\n"

                if archivos_info:
                    resumen += "📋 Detalle de archivos:\n"
                    for info in archivos_info[:10]:  # Limitar a 10 para no saturar
                        resumen += f"• {info}\n"

                resumen += f"\n🔄 Envía otro enlace para continuar"

                await query.message.reply_text(resumen)

            else:
                await tracker.finish_task(success=False)
                await query.message.reply_text("❌ Error durante la descarga. Revisa la consola para más detalles.")

        except Exception as e:
            await tracker.finish_task(success=False)
            logger.error(f"Error general en descarga: {e}")
            await query.message.reply_text(f"❌ Error inesperado:\n{str(e)[:200]}")

# ==================== CONFIGURACIÓN DEL BOT ====================

def main():
    """Función principal para ejecutar el bot"""

    print("🚀 Iniciando MusicDownloader Bot con seguimiento de progreso...")

    # Verificar dependencias críticas
    dependencias = {
        'yt-dlp': 'yt-dlp',
        'spotdl': 'spotdl', 
        'ffmpeg': 'ffmpeg'
    }

    for nombre, comando in dependencias.items():
        try:
            if nombre == 'yt-dlp':
                import yt_dlp
                print(f"✅ {nombre} disponible")
            else:
                resultado = subprocess.run([comando, '--version'], 
                                         capture_output=True, 
                                         timeout=5)
                if resultado.returncode == 0:
                    print(f"✅ {nombre} disponible")
                else:
                    print(f"⚠️ {nombre} instalado pero con problemas")
        except (ImportError, FileNotFoundError, subprocess.TimeoutExpired):
            print(f"❌ {nombre} no disponible")
            if nombre == 'yt-dlp':
                print("   Instala con: pip install yt-dlp")
            elif nombre == 'spotdl':
                print("   Instala con: pip install spotdl")
                print("   Configura con: spotdl --generate-config")
            elif nombre == 'ffmpeg':
                print("   Instala FFmpeg desde: https://ffmpeg.org/download.html")

    # Crear directorio de descargas
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
        print(f"📁 Directorio creado: {DOWNLOAD_DIR}")

    # Configurar el bot
    app = Application.builder().token(TOKEN).build()

    # Añadir manejadores
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("info", info_comando))
    app.add_handler(CommandHandler("config", comando_config))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_enlace))
    app.add_handler(CallbackQueryHandler(descargar, pattern="^format:"))

    print("🤖 Bot iniciado correctamente")
    print("📊 Características:")
    print("  • Seguimiento de progreso en tiempo real")
    print("  • Medición de tiempo por tarea")
    print("  • Resúmenes detallados de descarga")
    print("  • Soporte YouTube, Spotify, SoundCloud, Bandcamp")
    print("  • Manejo robusto de errores")
    print("  • Diagnóstico de dependencias")
    print("\n✅ Listo para recibir enlaces...")
    print("\n💡 Si Spotify no funciona, usa: /config")

    # Ejecutar bot
    app.run_polling()

if __name__ == "__main__":
    main()