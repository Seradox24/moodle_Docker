# Moodle 5.3.0 con Docker

Este repositorio reúne lo necesario para construir y ejecutar Moodle 5.3.0 con
Docker Compose en Linux. `compose.yaml` define los contenedores; `Dockerfile` construye
las imágenes de Moodle y Nginx; `releases/release.env` fija las versiones.
La instalación detallada está en **[deploy-runbook.md](deploy-runbook.md)**.
`main` contiene la base validada para pseudoproducción. Los resultados y los
pendientes de cada despliegue se conservan fuera de este repositorio, en la
documentación operativa del responsable de la instalación. El repositorio
contiene esta guía y el runbook; los logs y el estado de preparación para
producción se mantienen por separado. La URL del repositorio de documentación
se añadirá cuando esté disponible.

## Qué contiene el stack

| Componente | Función |
| --- | --- |
| `web` | Nginx dentro de Docker. Recibe las peticiones y sirve los archivos públicos de Moodle. |
| `app` | Moodle con PHP-FPM. Ejecuta la aplicación y se conecta a PostgreSQL y Redis. |
| `cron` | Ejecuta las tareas programadas de Moodle usando la misma imagen de `app`. |
| `db` | PostgreSQL 17.11. Guarda la base de datos en el volumen `postgres-data`. |
| `redis` | Guarda las sesiones de Moodle en memoria. |
| `code-init` | Copia el código verificado de Moodle al volumen compartido la primera vez y termina. |

Compose crea dos redes de tipo `bridge`: `application` conecta `web` con
`app`, mientras que `data` conecta `app` y `cron` con PostgreSQL y Redis.
La red `data` es interna; la base de datos y Redis no publican puertos en el
servidor. Solo `web` publica el puerto configurado para el proxy del host.

> [!IMPORTANT]
> **Redis no tiene contraseña en esta configuración.** Solo se conecta a la red
> interna `data` y no publica el puerto `6379` en el host. Conserva ambas
> condiciones: no agregues `ports:` al servicio `redis` ni lo conectes a una
> red accesible desde otros proyectos. Si necesitas acceso externo, configura
> autenticación y revisa el aislamiento antes de exponerlo.

## Estructura esperada en el servidor

```text
/srv/plataforma/moodle/          ← clon de este repositorio
├── compose.yaml
├── Dockerfile
├── .env                     ← configuración privada creada desde .env.example
├── .env.example
├── config/                  ← configuración de Moodle
├── docker/                  ← archivos para construir las imágenes
├── releases/release.env     ← versiones fijadas
└── scripts/                 ← instalación, comprobaciones y respaldos

```

Compose crea tres **volúmenes administrados por Docker** al iniciar el stack.
Son espacios de almacenamiento del servidor, no carpetas del clon de Git. Con
`COMPOSE_PROJECT_NAME=lms-moodle`, sus nombres y contenidos son:

| Volumen | Qué conserva |
| --- | --- |
| `lms-moodle_postgres-data` | Las tablas, usuarios y configuración guardados en PostgreSQL. |
| `lms-moodle_moodledata` | Los archivos que Moodle almacena fuera del código, incluidos los subidos por usuarios. |
| `lms-moodle_moodle-code` | La copia de los archivos públicos de Moodle que comparten los contenedores, junto con los plugins y temas instalados allí. |

Los volúmenes permanecen al detener o recrear contenedores. La opción
`down -v` de Compose **también elimina esos datos**, por lo que solo debe
usarse en un entorno de prueba que se quiera reiniciar. En producción,
respaldar la base de datos, `moodledata` y el código compartido antes de
cualquier cambio que afecte los volúmenes. El prefijo de sus nombres cambia si se modifica
`COMPOSE_PROJECT_NAME`.

Las sesiones en Redis son temporales: al reiniciar Redis, los usuarios deberán
iniciar sesión de nuevo. Los cursos, usuarios y archivos permanecen en
PostgreSQL y `moodledata`.

Nginx del host recibe HTTPS y reenvía a `web` por `127.0.0.1:18080`; su
configuración activa vive fuera de este repositorio.

> [!IMPORTANT]
> **El límite de subida debe coincidir en ambos Nginx.** La plantilla permite
> archivos de hasta `MOODLE_MAX_UPLOAD_MB=256` MiB y peticiones de hasta
> `MOODLE_MAX_REQUEST_MB=300` MiB. En el bloque del Nginx central que envía
> tráfico a Moodle, configura al menos:
>
> ```nginx
> client_max_body_size 300M;
> ```
>
> Si el límite del Nginx central es menor, rechazará la petición antes de que
> llegue al contenedor. Si cambias `MOODLE_MAX_REQUEST_MB`, ajusta también este
> valor en el Nginx central.

## Crear el archivo `.env`

En Ubuntu, desde la raíz del clon:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Sustituye los valores de ejemplo antes de instalar:

- `POSTGRES_PASSWORD` y `MOODLE_ADMIN_PASSWORD`: dos contraseñas fuertes y distintas.
- `MOODLE_SITE_FULLNAME`, `MOODLE_SITE_SHORTNAME` y `MOODLE_ADMIN_EMAIL`: identidad y correo reales del sitio.
- `MOODLE_WWWROOT`: URL pública definitiva asignada por el Nginx central. Es la dirección que usará Moodle en sus enlaces, aunque Nginx se conecte al contenedor por localhost.
- El puerto local se configura con `MOODLE_HTTP_PORT`, siempre en loopback para el proxy HTTPS.

El `.env` contiene credenciales y está excluido de Git. Los valores de
`releases/release.env` pertenecen a la versión del repositorio y no se copian
al `.env`. La instalación y operación se realizan en Linux mediante los
scripts de `scripts/`. Para desarrollo o pruebas Linux, usar un proyecto
Compose distinto y la URL local según el runbook.
El procedimiento también está en el
[runbook](deploy-runbook.md).

En operación normal, Moodle solo lee el código. Para instalar plugins desde
Administración se abre temporalmente el modo de escritura descrito en el
[runbook](deploy-runbook.md); los plugins quedan en `moodle-code`.

## Perfil independiente de instalación

Todos los scripts aceptan `--env-file /ruta/privada/instancia.env`. Las rutas
relativas se resuelven desde el repositorio, sin depender de la consola.
El cargador rechaza variables administradas exportadas en la consola para evitar
sobrescrituras ocultas. Compose carga primero el perfil elegido y después
`releases/release.env`; las versiones pertenecen a la release, no a la instalación.
Los valores reales y secretos nunca se guardan en los ejemplos ni en este repositorio.

| Opción | Consumidor y momento |
| --- | --- |
| `COMPOSE_PROJECT_NAME` | Compose al crear contenedores, redes y volúmenes. No cambiar en instalaciones existentes sin migración explícita. |
| `MOODLE_HTTP_BIND`, `MOODLE_HTTP_PORT` | Publicación Docker al crear/recrear web; bind obligatorio 127.0.0.1 detrás del proxy del host. |
| `TZ` | Contenedores web/app/cron/db y opciones timezone/log_timezone de PostgreSQL al iniciar. Predeterminado UTC; validar zona IANA instalada en el host. |
| `MOODLE_WWWROOT` | Configuración Moodle en ejecución; el virtual host y TLS del host deben coincidir. |
| `MOODLE_SITE_FULLNAME`, `MOODLE_SITE_SHORTNAME`, `MOODLE_LANG`, `MOODLE_ADMIN_USER`, `MOODLE_ADMIN_EMAIL`, `MOODLE_ADMIN_PASSWORD` | CLI de instalación inicial. Cambiar el perfil después no modifica el sitio ni cuentas existentes. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Inicialización PostgreSQL y conexión Moodle. La rotación del rol requiere operación SQL explícita coordinada con el perfil. |

Ejemplo de respaldo externo: `sh scripts/backup.sh --env-file /ruta/privada/instancia.env /ruta/respaldos/FECHA`.
El respaldo no contiene el perfil privado. Conservarlo protegido por separado.
Los tres volúmenes siguen gestionados por Docker; no se requieren bind mounts.

La release del instalador 1.1.1 utiliza Moodle 5.3.0 LTS, PHP 8.3.36 y
PostgreSQL 17.11, con referencias fijadas por SHA/digest. Moodle 5.3 requiere
PHP 8.3 y PostgreSQL 17 como mínimo. Véanse los
[requisitos oficiales](https://moodledev.io/general/releases/5.3).
La imagen ejecuta `composer install --no-dev --classmap-authoritative` con el
`composer.lock` oficial y la imagen `COMPOSER_IMAGE` fijada en la release: Moodle
5.3 carga dependencias como `league/oauth2-server` solo desde `vendor/`, y sin
ellas la API REST (`/api/rest/v2/openapi.json`) responde HTTP 500. `vendor/`
queda fuera de `public/` y Composer no permanece en la imagen final.

Esta línea admite **instalaciones nuevas con volúmenes vacíos**. No cambiar
la imagen PostgreSQL 16 por 17 sobre un volumen existente ni reutilizar los
volúmenes de Moodle 5.2.4. Migrar base de datos, código y plugins requiere un
procedimiento independiente con respaldo y retorno; no está incluido aquí.
El inicializador rechaza código de otra release y la restauración requiere
el manifiesto original coincidente.

La rama `moodle-5.2.4` y el tag `moodle-5.2.4-launcher-1.0.7` conservan la
base anterior sin modificaciones. Las releases distinguen la versión de
Moodle de la del instalador. El nombre genérico del repositorio es
`Seradox24/moodle_Docker`; las carpetas históricas locales no se renombran.

El workflow `Validate release` comprueba perfiles e instalación, operación,
reinicio, respaldo y restauración en proyectos desechables de Linux. No publica
imágenes ni despliega servicios. Los plugins externos requieren validación propia.

## Paquete reproducible de plugins

Las instalaciones nuevas incorporan al finalizar Completion Progress y Certificate
Studio, fijados para Moodle 5.3. Para omitirlos, usar `--plugins none` en
`install.sh`. El [catálogo y procedimiento de actualización](plugins/README.md)
incluye los ZIP oficiales, checksums y un instalador offline para sitios nuevos
o existentes.

## Respaldo periódico y ensayo de recuperación

`python3 scripts/backup-retained.py --env-file /ruta/privada/instancia.env --destination /ruta/respaldos --keep 7`
serializa ejecuciones mediante un bloqueo, comprueba los checksums y conserva
los siete respaldos completos más recientes. Un fallo conserva el directorio
`.partial`, devuelve error y no elimina respaldos previos. Ejecutarlo con umask
0077 desde un timer del host, con zona IANA y hora explícitas; revisar journal
ante fallos. Detiene brevemente app/web/cron. El almacenamiento local no
sustituye una copia externa.

`sh scripts/restore.sh --env-file /ruta/privada/recuperacion.env --backup /ruta/respaldo`
requiere un proyecto sin contenedores ni volúmenes existentes, metadata de
release coincidente e imágenes disponibles. Restaura los tres componentes sin
modificar el proyecto original. Para un ensayo, usar otro nombre Compose, otro
puerto loopback y URL local con `MOODLE_SSLPROXY=false` y
`MOODLE_REVERSEPROXY=true`; no apuntar el proxy público al ensayo.
Comprobar login y contenido antes de retirar únicamente los recursos del ensayo.
Validación estática de perfiles: `python3 tests/profiles.py` (Linux con Compose).

El Nginx del host se genera desde el perfil efectivo mediante
`python3 scripts/render-proxy.py --env-file /ruta/privada/instancia.env --acme-root /var/www/letsencrypt --certificate-dir /etc/letsencrypt/live/DOMINIO`.
Sin `--certificate-dir` genera solo HTTP/ACME. Guardar primero la salida en un
archivo temporal y comprobarla antes de instalar; validar con `nginx -t` y
recargar. El generador no instala certificados ni modifica Nginx por sí mismo.
`TZ` también genera `date.timezone` en PHP al iniciar y configura la zona del sitio Moodle en ejecución; web incluye tzdata.
