# java_cacerts_installer

Script de Python que descarga los certificados TLS de una lista de dominios e
los importa en el truststore `cacerts` de tu instalación de Java. Sirve para
que Java confíe en servidores con certificados internos o no reconocidos
(por ejemplo, Artifactory o Nexus de la empresa).

## Requisitos

- Python 3.
- Un JDK o JRE instalado, con `bin/keytool` (o `bin\keytool.exe` en Windows).
- El paquete `cryptography`, listado en `requirements.txt`. Solo lo usan las herramientas de llaves y cifrado.

Funciona en **macOS, Linux y Windows**.

## Instalación

Crea un entorno virtual e instala las dependencias. Así se evita el bloqueo de `pip`
del Python del sistema (PEP 668).

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

## Preparación

Crea el archivo `config/domains.json` con un array de dominios. Puedes copiar la plantilla
[config/domains.example.json](config/domains.example.json) a `config/domains.json`. El archivo
va en `config/` del proyecto, no en la carpeta de Java:

```json
[
  "google.com",
  "artifactory.empresa.com",
  "https://nexus.empresa.com:8443"
]
```

Cada entrada puede ser un dominio simple o una URL. Si no indica puerto, se usa el `443`.

## Menú principal (`main.py`)

Reúne todas las herramientas. Sin argumentos abre el menú; con un comando ejecuta esa
herramienta directamente:

```bash
python3 main.py                                # menú interactivo
python3 main.py cacerts                        # certificados en cacerts
python3 main.py keygen --bits 4096             # llaves RSA
python3 main.py encrypt --pubkey keys/rsa_public.pem --out secret.json   # pide el valor oculto
python3 main.py decrypt --privkey keys/rsa_private.pem --in secret.json
python3 main.py qr -- "https://intranet.empresa.com"
python3 main.py textqr generate text.example.txt --out-dir qr_out
python3 main.py textqr restore parts.txt --out recuperado.txt
python3 main.py env                            # Java y Maven en Windows
```

El menú tiene estas opciones:

1. Instalar certificados en cacerts de Java.
2. Generar llaves RSA.
3. Encriptar un valor.
4. Desencriptar un valor.
5. QR de un texto corto.
6. Convertir un `.txt` en QR.
7. Restaurar texto desde las partes de QR.
8. Configurar Java y Maven para el usuario de Windows (en otros sistemas aparece marcada como no disponible).

**En Windows** usa `py` en lugar de `python3` en todos los comandos de esta guía, por ejemplo
`py main.py`. Si `py` no existe, prueba con `python`.

## Uso

```bash
python3 java_cacerts_installer.py
```

El script te pedirá:

1. **Directorio de tu Java (JAVA_HOME).** Acepta la carpeta del JDK, por ejemplo
   `/Users/tu_usuario/.sdkman/candidates/java/current`, o el bundle de macOS
   `/Library/Java/JavaVirtualMachines/jdk-21.jdk`.
2. **Contraseña del cacerts.** Se pide una sola vez. Si la dejas vacía, usa `changeit`,
   que es la contraseña por defecto de Java.

Si la instalación de Java está en una ruta protegida (por ejemplo,
`/Library/Java/...`), ejecútalo con permisos de administrador:

```bash
sudo python3 java_cacerts_installer.py
```

### En Windows

1. Abre **PowerShell o CMD como administrador**. Es necesario si Java está en
   `C:\Program Files\...`, porque `cacerts` queda protegido.
2. Ejecuta el script con el lanzador de Python (`py`, o `python` si así está instalado):

```powershell
py java_cacerts_installer.py
```

3. Cuando pida el directorio, puedes pegar la ruta con o sin comillas, por ejemplo:

```
C:\Program Files\Java\jdk-21
```

En Windows el script busca `bin\keytool.exe` y el `cacerts` en
`lib\security\cacerts` (o `jre\lib\security\cacerts` en Java 8).

## Qué hace el script

1. Valida el directorio de Java: busca `bin/keytool` y el archivo `cacerts`
   (en `lib/security/cacerts` para Java 9 o superior, o en
   `jre/lib/security/cacerts` para Java 8).
2. Lee `config/domains.json` y elimina duplicados.
3. Comprueba la contraseña con `keytool -list`. Si es incorrecta, se detiene
   antes de modificar nada.
4. Crea un respaldo `cacerts.bak` la primera vez que se ejecuta. Si ya existe, no lo sobrescribe.
5. Para cada dominio:
   - Se conecta por TLS y obtiene el certificado del servidor. No valida la
     cadena, porque el objetivo es precisamente confiar en ese certificado.
   - Guarda el certificado en `<carpeta-java>/certs/<dominio>.crt`.
   - Elimina la entrada anterior con el mismo alias, si existe, e importa el
     certificado nuevo en `cacerts`.
6. Muestra un resumen con los dominios instalados y los que fallaron.

El alias de cada certificado es el nombre del dominio. Si el puerto no es `443`,
el alias incluye el puerto, por ejemplo `nexus.empresa.com_8443`.

## Salida de ejemplo

```
Directorio de tu Java (JAVA_HOME): /Users/yegecali/.sdkman/candidates/java/current
Contrasena del cacerts [changeit]:
[+] Backup creado: .../lib/security/cacerts.bak
[+] google.com: certificado guardado en .../certs/google.com.crt
[+] google.com: importado en cacerts
[+] github.com: certificado guardado en .../certs/github.com.crt
[+] github.com: importado en cacerts

Resumen: 2 instalados, 0 con error
```

Si algún dominio falla, el script termina con código de salida `1` y lista los
dominios con error.

## Limitaciones

- **Solo se importa el certificado hoja** (el del servidor). No se descargan
  los certificados intermedios de la cadena. Para la mayoría de casos de uso
  directo funciona, pero si un servidor depende de un intermedio que no está en
  `cacerts`, podría seguir fallando.
- **La contraseña se pasa como argumento a `keytool`**, así que es visible
  brevemente en la lista de procesos del sistema.
- Solo se contemplan certificados accesibles por HTTPS en el puerto indicado.

## Restaurar el original

Si algo sale mal, restaura el respaldo:

```bash
cp <carpeta-java>/lib/security/cacerts.bak <carpeta-java>/lib/security/cacerts
```

En Windows (como administrador):

```powershell
copy "<carpeta-java>\lib\security\cacerts.bak" "<carpeta-java>\lib\security\cacerts"
```

Los archivos `.crt` en `certs/` se pueden borrar sin efectos, porque ya están
importados en `cacerts`.

## Generar llaves RSA (`rsa_keygen.py`)

Genera un par de llaves RSA en formato PEM. Requiere el paquete `cryptography`
(ver [Instalación](#instalación)):

```bash
python3 rsa_keygen.py                       # 2048 bits, carpeta keys/, prefijo rsa
python3 rsa_keygen.py --bits 4096 --name app
python3 rsa_keygen.py --force               # sobrescribe si ya existen
```

Opciones:

- `--name`: prefijo de los archivos (default `rsa`).
- `--bits`: 2048, 3072 o 4096 (default 2048).
- `--out`: carpeta de salida (default `keys`).
- `--force`: sobrescribe archivos existentes.

Genera:

- `<name>_private.pem`: llave privada en PKCS#8. Se te pide una passphrase opcional
  para cifrarla. En macOS/Linux queda con permisos `600`.
- `<name>_public.pem`: llave pública en formato SubjectPublicKeyInfo.

Las llaves no se suben al repositorio: `keys/` y `*.pem` están en `.gitignore`.

## Encriptar y desencriptar valores (`rsa_crypt.py`)

Cifra un valor con la llave pública RSA y lo descifra con la llave privada. Usa un
esquema híbrido: una clave AES-256-GCM aleatoria cifra el valor y RSA-OAEP (SHA-256)
cifra esa clave. RSA solo no puede cifrar valores grandes (unos 190 bytes con 2048 bits).

```bash
# Encriptar: si no pasas --value, lo pide de forma oculta (no queda en el historial)
python3 rsa_crypt.py encrypt --pubkey keys/rsa_public.pem --out secret.json

# Desencriptar: imprime el valor, o usa --out para guardarlo en un archivo
python3 rsa_crypt.py decrypt --privkey keys/rsa_private.pem --in secret.json
cat secret.json | python3 rsa_crypt.py decrypt --privkey keys/rsa_private.pem
```

El resultado es un JSON con `v`, `key`, `nonce` y `data`, todos en base64. Si la llave
privada tiene passphrase, el script la pide al desencriptar. Si la llave es incorrecta
o el JSON fue alterado, el script se detiene sin mostrar datos.

Requiere `cryptography` (ver [Instalación](#instalación)).

## Configurar Java y Maven en Windows (`windows_env_setup.py`)

Configura las variables del **usuario actual** (no las del sistema, no requiere
administrador): `JAVA_HOME`, `MAVEN_HOME`, `M2_HOME` y `PATH`. Las versiones disponibles
se leen de dos archivos JSON:

- `config/java.json`: versiones de Java, con la ruta a la carpeta del JDK.
- `config/maven.json`: versiones de Maven y perfiles de `settings.xml` (uno por Artifactory).

Copia las plantillas [config/java.example.json](config/java.example.json) y
[config/maven.example.json](config/maven.example.json) a `config/java.json` y
`config/maven.json`. Los archivos reales están en `.gitignore` porque contienen tus rutas.

```json
{
  "versions": {
    "21": "C:\\Program Files\\Java\\jdk-21"
  }
}
```

```json
{
  "versions": { "3.9.9": "C:\\tools\\apache-maven-3.9.9" },
  "settings_profiles": {
    "artifactory-empresa": "C:\\tools\\maven\\settings-empresa.xml",
    "artifactory-cliente": "C:\\tools\\maven\\settings-cliente.xml"
  }
}
```

Edita los dos archivos copiados con tus rutas y ejecuta desde una terminal normal:

```powershell
py windows_env_setup.py
```

El script pregunta qué configurar (Java, Maven o ambos) y qué versión usar, muestra los
cambios y pide confirmación antes de aplicarlos. Antes de escribir:

- Quita de `PATH` las entradas de otros JDK o Maven (carpetas `jdk*\bin`, `jre*\bin`,
  `maven*\bin`) y antepone `%JAVA_HOME%\bin` y `%MAVEN_HOME%\bin`.
- Si configuras Maven, te muestra el perfil de `settings.xml` activo y te pregunta cuál
  usar (o `(no cambiar)`). El elegido se copia a `%USERPROFILE%\.m2\settings.xml`.
- Si `~/.m2/settings.xml` tiene cambios que no coinciden con ningún perfil, los guarda en
  `settings.xml.<fecha>.bak` antes de reemplazarlo.

Edita tus configuraciones en los archivos de cada perfil, no en `~/.m2/settings.xml`:
ese archivo se reemplaza cada vez que cambias de perfil.

Abre una terminal nueva después de ejecutarlo y verifica con `java -version` y `mvn -v`.
Las aplicaciones abiertas (IDE, etc.) necesitan reiniciarse para ver los cambios.

## Generar códigos QR (`qr_generator.py`)

Genera un código QR a partir de un texto. Sin `--out` lo muestra en la terminal;
con `--out` lo guarda como `.png` o `.svg`.

```bash
python3 qr_generator.py "https://intranet.empresa.com"       # en pantalla
python3 qr_generator.py "Contraseña Wi-Fi" --out wifi.png     # imagen PNG
python3 qr_generator.py "texto" --out link.svg --ec H         # SVG, máxima corrección de errores
python3 qr_generator.py --out link.png                        # pide el texto por consola
```

Opciones:

- `--out`: archivo de salida (`.png` o `.svg`).
- `--ec`: nivel de corrección de errores, `L`, `M` (default), `Q` o `H`.
- `--box`: tamaño de cada módulo en píxeles (default 10).

La capacidad depende del nivel `--ec` (medida en bytes, no en caracteres):

| `--ec` | Máximo en bytes |
|--------|-----------------|
| L      | 2953            |
| M (default) | 2331       |
| Q      | 1663            |
| H      | 1273            |

Los caracteres con acento o emoji ocupan 2 a 4 bytes en UTF-8, así que el límite en
caracteres es menor. Un texto que supere el límite se rechaza con un mensaje claro.

## Convertir un `.txt` grande en QR (`text_qr.py`)

Toma un archivo de texto, limpia los espacios y saltos de línea sobrantes, lo comprime y lo
divide en uno o varios QR. Opcionalmente lo encripta con RSA antes de generar los códigos.

```bash
# Generar los QR como PNG (uno por parte)
python3 text_qr.py generate text.example.txt --out-dir qr_out

# Mostrarlos en la terminal, uno por uno (Enter para la siguiente parte)
python3 text_qr.py generate text.example.txt

# Encriptar con tu llave publica
python3 text_qr.py generate text.example.txt --encrypt --pubkey keys/rsa_public.pem --out-dir qr_out

# Reconstruir el texto: escribe el contenido de cada QR en una linea de parts.txt
python3 text_qr.py restore parts.txt --out recuperado.txt
python3 text_qr.py restore parts.txt --privkey keys/rsa_private.pem --out recuperado.txt  # encriptado
```

Opciones de `generate`:

- `--chunk`: caracteres por parte (default 1200). Con menos partes hay menos códigos que escanear.
- `--keep-newlines`: conserva los saltos de párrafo. Por defecto todo queda en una línea.
- `--ec` y `--box`: igual que en `qr_generator.py`.

Cómo se limpia el texto: se colapsan espacios, tabulaciones y saltos de línea repetidos.
Sin `--keep-newlines`, todo el texto queda en una sola línea separada por espacios.

Cada QR contiene una línea con este formato: `TQR1|modo|identificador|parte/total|datos`.
El identificador es un hash del mensaje completo, así que `restore` detecta partes faltantes,
partes de otro mensaje o partes copiadas con un error.

**Flujo con el celular:** escanea cada QR, copia el texto que muestra el lector y pégalo en
una línea de `parts.txt`. Después ejecuta `restore`.

**Llaves:** `keys/public-key.example` y `keys/private-key.example` son solo plantillas. Para
usarlas, genera tu par con `rsa_keygen.py --name llave` y renombra los archivos a
`keys/rsa_public.pem` y `keys/rsa_private.pem`, o pasa las rutas con `--pubkey` y `--privkey`.

Capacidad: cada parte debe caber en un QR (ver la tabla de la sección de QR). Con el
valor por defecto `--chunk 1200` cabe con el nivel `M`.

## Configuración (`.env`)

Los valores por defecto del proyecto están en `.env`. Para empezar:

```bash
cp .env.example .env
```

Variables principales:

| Variable | Default | Uso |
|---|---|---|
| `CACERTS_PASSWORD` | `changeit` | contraseña por defecto del cacerts de Java |
| `DOMAINS_FILE` | `config/domains.json` | lista de dominios a instalar |
| `JAVA_CONFIG_FILE` / `MAVEN_CONFIG_FILE` | `config/java.json` / `config/maven.json` | versiones de Java y Maven (Windows) |
| `KEYS_DIR` | `keys` | carpeta de las llaves |
| `RSA_KEY_BITS` | `2048` | tamaño por defecto de las llaves RSA |
| `PUBLIC_KEY_FILE` / `PRIVATE_KEY_FILE` | `keys/rsa_public.pem` / `keys/rsa_private.pem` | llaves usadas por defecto |
| `QR_ERROR_CORRECTION` | `M` | corrección de errores de los QR (L, M, Q o H) |
| `QR_BOX_SIZE` | `10` | tamaño de cada módulo en PNG |
| `QR_CHUNK_SIZE` | `1200` | caracteres por parte al dividir un texto en QR |

Reglas:

- Las rutas relativas se cuentan desde la carpeta del proyecto, no desde donde ejecutes el comando.
- Una variable real del sistema tiene prioridad sobre el `.env`. Por ejemplo, `QR_CHUNK_SIZE=300 python3 text_qr.py generate ...` lo usa solo en esa ejecución.
- Un argumento de línea de comandos, como `--ec H`, tiene prioridad sobre todo lo anterior.
- `.env` está en `.gitignore`, porque puede contener contraseñas. Lo que se versiona es `.env.example`.

## Pruebas unitarias

Las pruebas están en `tests/` y usan `pytest`. Cubren la configuración `.env`, la instalación
de certificados (lectura de dominios y búsqueda de `keytool`), las llaves RSA y el cifrado,
los QR y `text_qr` (incluido el reensamblado y los errores), y la lógica de Windows (PATH,
perfiles de `settings.xml` y el registro, simulado). No necesitan red ni `keytool`, y no usan tu `.env`.

```bash
python3 -m pip install -r requirements.txt -r requirements-dev.txt
python3 -m pytest
```

En **GitHub Actions** (`.github/workflows/tests.yml`) las pruebas se ejecutan en cada push a
`main` sobre Ubuntu, macOS y Windows, con Python 3.12 y 3.14. Si alguna falla, el push queda
marcado en rojo. También puedes lanzarlas a mano desde la pestaña *Actions*.
