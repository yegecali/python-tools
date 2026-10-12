# java_cacerts_installer

Script de Python que descarga los certificados TLS de una lista de dominios e
los importa en el truststore `cacerts` de tu instalación de Java. Sirve para
que Java confíe en servidores con certificados internos o no reconocidos
(por ejemplo, Artifactory o Nexus de la empresa).

## Requisitos

- Python 3 (solo usa la librería estándar).
- Un JDK o JRE instalado, con `bin/keytool` (o `bin\keytool.exe` en Windows).

Funciona en **macOS, Linux y Windows**.

## Preparación

Crea un archivo `domains.json` **dentro de la carpeta de tu Java** con un array
de dominios:

```json
[
  "google.com",
  "artifactory.empresa.com",
  "https://nexus.empresa.com:8443"
]
```

Cada entrada puede ser un dominio simple o una URL. Si no indica puerto, se usa el `443`.

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
2. Lee `domains.json` desde la carpeta de Java y elimina duplicados.
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
