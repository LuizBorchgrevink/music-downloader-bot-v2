
import os

# Obtener variables de entorno de Replit
repl_slug = os.environ.get('REPL_SLUG', 'python-template')
repl_owner = os.environ.get('REPL_OWNER', 'tu-username')

# Construir la URL
url = f"https://{repl_slug}.{repl_owner}.replit.dev"

print(f"🔗 URL exacta de tu bot: {url}")
print(f"📱 Puerto interno: 8080")
print(f"🌐 Puerto externo: 80")
