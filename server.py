# Importaciones necesarias para el servidor HTTP y manejo de base de datos
import http.server
import socketserver
import urllib.parse
import psycopg2
import pandas as pd
import os

# Configuración del servidor
PORT = 8000
TEMPLATE_FILE = 'templates/index.html'

# Configuración de conexión a PostgreSQL
# Estos parámetros deben coincidir con tu instalación de PostgreSQL
DB_CONFIG = {
    'dbname': 'tarea_crud',      # Nombre de la base de datos
    'user': 'postgres',          # Usuario de PostgreSQL
    'password': '13579',         # Contraseña del usuario
    'host': '127.0.0.1',         # Dirección IP del servidor PostgreSQL
    'port': '5432'               # Puerto por defecto de PostgreSQL
}

def init_db():
    """
    Inicializa la base de datos creando la tabla 'productos' si no existe.
    Esta función se ejecuta al iniciar el servidor.
    """
    conn = psycopg2.connect(**DB_CONFIG)
    c = conn.cursor()
    # Crear tabla productos con los campos necesarios para el CRUD
    c.execute('''CREATE TABLE IF NOT EXISTS productos (
        id SERIAL PRIMARY KEY,           # ID autoincremental
        nombre VARCHAR(255) NOT NULL,    # Nombre del producto
        precio DECIMAL(10,2) NOT NULL,   # Precio con 2 decimales
        stock INTEGER NOT NULL           # Cantidad en stock
    )''')
    conn.commit()
    conn.close()

class Handler(http.server.SimpleHTTPRequestHandler):
    """
    Manejador personalizado para las peticiones HTTP.
    Gestiona tanto las peticiones GET (mostrar página) como POST (operaciones CRUD).
    """
    
    def do_GET(self):
        """
        Maneja las peticiones GET:
        - Sirve archivos estáticos (CSS) desde /static/
        - Muestra la página principal con la tabla de productos y formulario
        """
        # Si la petición es para archivos estáticos (CSS), usar el handler por defecto
        if self.path.startswith('/static/'):
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
        
        # Extraer el ID del producto a editar desde los parámetros de la URL
        edit_id = None
        if '?' in self.path:
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            edit_id = params.get('edit', [None])[0]
        
        # Conectar a PostgreSQL y obtener todos los productos usando Pandas
        conn = psycopg2.connect(**DB_CONFIG)
        df = pd.read_sql_query('SELECT * FROM productos', conn)
        conn.close()
        
        # Leer la plantilla HTML
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            html = f.read()
        
        # Generar las filas de la tabla de productos
        rows = ''
        for _, row in df.iterrows():
            # Marcar la fila que se está editando con una clase CSS especial
            clase = ' class="edit-row"' if edit_id and str(row["id"]) == edit_id else ''
            rows += f'<tr{clase}>'
            rows += f'<td>{row["id"]}</td>'
            rows += f'<td>{row["nombre"]}</td>'
            rows += f'<td>${row["precio"]:.2f}</td>'
            rows += f'<td>{row["stock"]}</td>'
            rows += '<td>'
            # Botones de Editar y Eliminar para cada producto
            rows += f'''
                <form method="get" action="/" style="display:inline">
                    <input type="hidden" name="edit" value="{row['id']}">
                    <button type="submit">Editar</button>
                </form>
                <form method="post" action="/" style="display:inline" onsubmit="return confirm('¿Eliminar producto?')">
                    <input type="hidden" name="action" value="delete">
                    <input type="hidden" name="id" value="{row['id']}">
                    <button type="submit">Eliminar</button>
                </form>
            '''
            rows += '</td></tr>'
        
        # Generar el formulario: agregar nuevo producto o editar existente
        if edit_id and not df.empty and int(edit_id) in df['id'].values:
            # Si estamos editando, mostrar formulario con datos del producto
            prod = df[df['id'] == int(edit_id)].iloc[0]
            form = f'''
            <h2>Editar producto</h2>
            <form method="post" action="/">
                <input type="hidden" name="action" value="edit">
                <input type="hidden" name="id" value="{prod['id']}">
                <label>Nombre: <input name="nombre" value="{prod['nombre']}" required></label><br>
                <label>Precio: <input name="precio" type="number" step="0.01" value="{prod['precio']}" required></label><br>
                <label>Stock: <input name="stock" type="number" value="{prod['stock']}" required></label><br>
                <button type="submit">Guardar</button>
                <a href="/" class="cancelar">Cancelar</a>
            </form>
            '''
        else:
            # Si no estamos editando, mostrar formulario para agregar nuevo producto
            form = '''
            <h2>Agregar producto</h2>
            <form method="post" action="/">
                <input type="hidden" name="action" value="add">
                <label>Nombre: <input name="nombre" required></label><br>
                <label>Precio: <input name="precio" type="number" step="0.01" required></label><br>
                <label>Stock: <input name="stock" type="number" required></label><br>
                <button type="submit">Agregar</button>
            </form>
            '''
        
        # Reemplazar los placeholders en la plantilla HTML con el contenido generado
        html = html.replace('{{tabla_productos}}', rows)
        html = html.replace('{{formulario}}', form)
        
        # Enviar la respuesta HTTP con el HTML generado
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def do_POST(self):
        """
        Maneja las peticiones POST para las operaciones CRUD:
        - add: Agregar nuevo producto
        - edit: Editar producto existente
        - delete: Eliminar producto
        """
        # Leer los datos enviados por el formulario
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = urllib.parse.parse_qs(post_data.decode('utf-8'))
        action = data.get('action', [''])[0]
        
        # Conectar a PostgreSQL para realizar la operación
        conn = psycopg2.connect(**DB_CONFIG)
        c = conn.cursor()
        
        # Ejecutar la operación correspondiente según el action
        if action == 'add':
            # Insertar nuevo producto en la base de datos
            c.execute('INSERT INTO productos (nombre, precio, stock) VALUES (%s, %s, %s)', (
                data['nombre'][0], float(data['precio'][0]), int(data['stock'][0])
            ))
        elif action == 'edit':
            # Actualizar producto existente
            c.execute('UPDATE productos SET nombre=%s, precio=%s, stock=%s WHERE id=%s', (
                data['nombre'][0], float(data['precio'][0]), int(data['stock'][0]), int(data['id'][0])
            ))
        elif action == 'delete':
            # Eliminar producto por ID
            c.execute('DELETE FROM productos WHERE id=%s', (int(data['id'][0]),))
        
        # Confirmar los cambios en la base de datos
        conn.commit()
        conn.close()
        
        # Redirigir de vuelta a la página principal para mostrar los cambios
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()

# Punto de entrada principal del programa
if __name__ == '__main__':
    # Crear las carpetas necesarias si no existen
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    # Inicializar la base de datos
    init_db()
    
    # Iniciar el servidor HTTP en el puerto especificado
    with socketserver.TCPServer(('', PORT), Handler) as httpd:
        print(f'Servidor corriendo en http://localhost:{PORT}')
        print('Presiona Ctrl+C para detener el servidor')
        httpd.serve_forever() 