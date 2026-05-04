import psycopg2
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde la raíz del proyecto si existe
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

def check_connection():
    """Diagnóstico rápido de conexión a la base de datos."""
    
    # Parámetros de conexión (prioridad a variables de entorno)
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5433')
    db_name = os.getenv('DB_NAME', 'Verge')
    db_user = os.getenv('DB_USER', 'postgres')
    db_pass = os.getenv('DB_PASS', 'postgres')

    print(f"--- Diagnóstico de Base de Datos ---")
    print(f"Intentando conectar a {db_host}:{db_port} (DB: {db_name})...")

    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_pass,
            connect_timeout=5
        )
        cur = conn.cursor()
        cur.execute('SELECT version();')
        db_version = cur.fetchone()
        print(f"✅ Conexión EXITOSA.")
        print(f"Versión de PostgreSQL: {db_version[0]}")
        
        # Prueba de lectura simple
        cur.execute('SELECT COUNT(*) FROM "SimulatedTrades"')
        count = cur.fetchone()[0]
        print(f"Total de trades en tabla 'SimulatedTrades': {count}")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        print("\nSugerencia: Verificá que los contenedores de Docker estén corriendo y que el puerto coincida.")

if __name__ == "__main__":
    check_connection()
